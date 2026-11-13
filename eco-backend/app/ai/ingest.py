"""Turn uploaded documents into searchable chunks.

Extraction has hard limits so hostile files can't exhaust memory: decompressed DOCX XML is capped, PDFs are
read up to MAX_PDF_PAGES, and total extracted text is capped at MAX_TEXT_CHARS. Images aren't OCR'd yet.
"""
from __future__ import annotations

import html
import io
import re
import zipfile

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.base import EmbeddingProvider, ProviderError
from app.models import Document, DocumentChunk

MAX_TEXT_CHARS = 400_000
MAX_PDF_PAGES = 300
MAX_DOCX_XML_BYTES = 15 * 1024 * 1024
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class ExtractionUnsupported(Exception):
    pass


def extract_text(content_type: str, data: bytes) -> str:
    if content_type == "text/plain":
        text = data.decode("utf-8", errors="replace")
    elif content_type == DOCX:
        text = _docx_text(data)
    elif content_type == "application/pdf":
        text = _pdf_text(data)
    else:
        raise ExtractionUnsupported(content_type)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:MAX_TEXT_CHARS]


def _docx_text(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        info = z.getinfo("word/document.xml")
        if info.file_size > MAX_DOCX_XML_BYTES:
            raise ValueError("docx too large when decompressed")
        xml = z.read(info).decode("utf-8", errors="replace")
    # Regex, not an XML parser: no entity expansion, so no "billion laughs".
    paras = re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S)
    out = []
    for p in paras:
        runs = re.findall(r"<w:t(?: [^>]*)?>(.*?)</w:t>", p, flags=re.S)
        out.append(html.unescape("".join(runs)))
    return "\n".join(out)


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    parts, total = [], 0
    for i, page in enumerate(reader.pages):
        if i >= MAX_PDF_PAGES or total > MAX_TEXT_CHARS:
            break
        t = page.extract_text() or ""
        parts.append(t)
        total += len(t)
    return "\n\n".join(parts)


def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[tuple[int, str]]:
    """Split on paragraph, then sentence boundaries; returns (char_start, chunk)."""
    chunks: list[tuple[int, str]] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            window = text[start:end]
            cut = max(window.rfind("\n\n"), window.rfind(". "), window.rfind("\n"))
            if cut > size // 2:
                end = start + cut + 1
        piece = text[start:end].strip()
        if piece:
            chunks.append((start, piece))
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return chunks


async def ingest_document(session: AsyncSession, doc: Document, data: bytes,
                          embedder: EmbeddingProvider | None) -> str:
    """Replace the document's chunks. Returns the new text_status."""
    await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    try:
        text = extract_text(doc.content_type, data)
    except ExtractionUnsupported:
        doc.text_status = "unsupported"
        return doc.text_status
    except Exception:  # malformed file: keep the upload, just don't index it
        doc.text_status = "failed"
        return doc.text_status
    pieces = chunk_text(text)
    if not pieces:
        doc.text_status = "failed"
        return doc.text_status
    vectors: list[list[float] | None] = [None] * len(pieces)
    model = None
    if embedder is not None:
        try:
            vectors = await embedder.embed([p for _, p in pieces])
            model = embedder.model
        except ProviderError:
            vectors = [None] * len(pieces)  # full-text search still works without vectors
    for i, ((start, piece), vec) in enumerate(zip(pieces, vectors)):
        session.add(DocumentChunk(document_id=doc.id, workspace_id=doc.workspace_id, org_id=doc.org_id,
                                  chunk_index=i, text=piece, char_start=start, embedding=vec,
                                  embedding_model=model if vec is not None else None))
    doc.text_status = "ready"
    await session.flush()
    return doc.text_status
