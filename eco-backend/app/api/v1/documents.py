import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from sqlalchemy import select

from app.ai.ingest import ingest_document
from app.ai.providers import get_embedder
from app.core.config import get_settings
from app.core.deps import WsCtx, ws_ctx
from app.core.errors import AppError, not_found
from app.core.pagination import page_of, paginate
from app.models import Document, Project
from app.schemas.common import DocumentOut, DownloadUrlOut
from app.services import audit
from app.services.storage import (
    content_disposition,
    get_storage,
    safe_filename,
    scan,
    sha256_hex,
    sign_download,
    sniff_content_type,
    storage_key,
    verify_download,
)

router = APIRouter(prefix="/v1", tags=["documents"])


async def _read_limited(upload: UploadFile, limit: int) -> bytes:
    chunks, total = [], 0
    while chunk := await upload.read(1024 * 1024):
        total += len(chunk)
        if total > limit:
            raise AppError(413, "file_too_large", "File too large", f"Files can be up to {limit // (1024 * 1024)} MB.")
        chunks.append(chunk)
    if total == 0:
        raise AppError(422, "empty_file", "Empty file", "The file has no content.")
    return b"".join(chunks)


@router.post("/workspaces/{workspace_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(file: UploadFile = File(...), project_id: uuid.UUID | None = Form(default=None),
                          ctx: WsCtx = Depends(ws_ctx), embedder=Depends(get_embedder)):
    await ctx.require("ws.write")
    if project_id:
        pr = await ctx.session.get(Project, project_id)
        if pr is None or pr.workspace_id != ctx.workspace.id:
            raise not_found("project")
    data = await _read_limited(file, get_settings().max_upload_bytes)
    content_type = sniff_content_type(data)
    doc_id = uuid.uuid4()
    key = storage_key(ctx.workspace.org_id, ctx.workspace.id, doc_id)
    status = await scan(data)
    if status == "rejected":
        await audit.record(ctx.session, "document.rejected", actor_id=ctx.principal.id, org_id=ctx.workspace.org_id,
                           workspace_id=ctx.workspace.id, target_type="document", metadata={"reason": "malware_scan"},
                           request=ctx.request)
        raise AppError(422, "file_rejected", "File rejected", "The file failed the security scan and was not stored.")
    doc = Document(id=doc_id, workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, project_id=project_id,
                   uploaded_by=ctx.principal.id, filename=safe_filename(file.filename or ""), content_type=content_type,
                   size_bytes=len(data), sha256=sha256_hex(data), storage_key=key, scan_status=status)
    ctx.session.add(doc)
    await ctx.session.flush()
    await get_storage().put(key, data)  # written after the row so a failed insert leaves no orphan object
    if status == "clean":
        # Index text for retrieval. Extraction failures keep the upload and set text_status.
        await ingest_document(ctx.session, doc, data, embedder)
        await ctx.session.flush()
    await ctx.session.refresh(doc)
    await audit.record(ctx.session, "document.uploaded", actor_id=ctx.principal.id, org_id=ctx.workspace.org_id,
                       workspace_id=ctx.workspace.id, target_type="document", target_id=doc.id,
                       metadata={"content_type": content_type, "size_bytes": len(data)}, request=ctx.request)
    return doc


@router.get("/workspaces/{workspace_id}/documents")
async def list_documents(cursor: str | None = None, limit: int = 25, ctx: WsCtx = Depends(ws_ctx)):
    stmt = paginate(select(Document).where(Document.workspace_id == ctx.workspace.id, Document.deleted_at.is_(None)),
                    Document, cursor, limit)
    rows = (await ctx.session.execute(stmt)).scalars().all()
    return page_of(list(rows), limit, lambda r: DocumentOut.model_validate(r))


async def _doc(ctx: WsCtx, document_id: uuid.UUID) -> Document:
    doc = await ctx.session.get(Document, document_id)
    if doc is None or doc.workspace_id != ctx.workspace.id or doc.deleted_at is not None:
        raise not_found("document")
    return doc


@router.get("/workspaces/{workspace_id}/documents/{document_id}", response_model=DocumentOut)
async def get_document(document_id: uuid.UUID, ctx: WsCtx = Depends(ws_ctx)):
    return await _doc(ctx, document_id)


@router.post("/workspaces/{workspace_id}/documents/{document_id}/download-url", response_model=DownloadUrlOut)
async def download_url(document_id: uuid.UUID, request: Request, ctx: WsCtx = Depends(ws_ctx)):
    doc = await _doc(ctx, document_id)
    if doc.scan_status != "clean":
        raise AppError(409, "file_not_ready", "File not ready", "The file is still being checked for safety.")
    token, exp = sign_download(doc.storage_key, doc.id, doc.filename, doc.content_type)
    await audit.record(ctx.session, "document.download_link_created", actor_id=ctx.principal.id,
                       org_id=ctx.workspace.org_id, workspace_id=ctx.workspace.id, target_type="document",
                       target_id=doc.id, request=ctx.request)
    return DownloadUrlOut(url=str(request.url_for("download_file", token=token)), expires_at=exp)


@router.get("/files/{token}", name="download_file", include_in_schema=False)
async def download_file(token: str):
    claims = verify_download(token)
    try:
        data = await get_storage().get(claims["k"])
    except (FileNotFoundError, KeyError):
        raise AppError(404, "file_not_found", "Not found", "This file no longer exists.") from None
    return Response(content=data, media_type=claims["t"], headers={
        "Content-Disposition": content_disposition(claims["f"]),
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox"})


@router.delete("/workspaces/{workspace_id}/documents/{document_id}", status_code=204)
async def delete_document(document_id: uuid.UUID, ctx: WsCtx = Depends(ws_ctx)):
    await ctx.require("ws.write")
    doc = await _doc(ctx, document_id)
    doc.deleted_at = datetime.now(UTC)
    await ctx.session.flush()
    await get_storage().delete(doc.storage_key)
    await audit.record(ctx.session, "document.deleted", actor_id=ctx.principal.id, org_id=ctx.workspace.org_id,
                       workspace_id=ctx.workspace.id, target_type="document", target_id=doc.id, request=ctx.request)
    return Response(status_code=204)
