"""File storage, type validation and malware scanning.

Objects are stored under keys `org/<org_id>/ws/<workspace_id>/<document_id>`; the original filename is
metadata only, never part of the key. Downloads use short-lived signed tokens, and only for files whose
scan_status is 'clean'.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import os
import shutil
import socket
import struct
import uuid
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import jwt

from app.core.config import get_settings
from app.core.errors import AppError

ALLOWED = {
    "application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain", "image/png", "image/jpeg",
}


def sniff_content_type(data: bytes) -> str:
    """Decide the type from the bytes, never from the client's filename or Content-Type header."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = set(z.namelist())
                if "[Content_Types].xml" in names and any(n.startswith("word/") for n in names):
                    if any(n.lower().endswith("vbaproject.bin") for n in names):
                        raise AppError(415, "unsupported_file", "Unsupported file", "Macro-enabled documents are not accepted.")
                    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except zipfile.BadZipFile:
            pass
    if b"\x00" not in data[:8192]:
        try:
            data.decode("utf-8")
            return "text/plain"
        except UnicodeDecodeError:
            pass
    raise AppError(415, "unsupported_file", "Unsupported file", "Upload a PDF, DOCX, TXT, PNG or JPG file.")


def safe_filename(name: str) -> str:
    base = os.path.basename(name or "").replace("\x00", "").strip() or "upload"
    return "".join(c for c in base if c.isprintable())[:255]


def storage_key(org_id: uuid.UUID, workspace_id: uuid.UUID, document_id: uuid.UUID) -> str:
    return f"org/{org_id}/ws/{workspace_id}/{document_id}"


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if not str(p).startswith(str(self.root) + os.sep):
            raise AppError(400, "invalid_key", "Invalid storage key")
        return p

    async def put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(p.write_bytes, data)
        os.chmod(p, 0o600)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread(self._path(key).read_bytes)

    async def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            await asyncio.to_thread(p.unlink)

    async def delete_prefix(self, prefix: str) -> int:
        """Delete every object under prefix (e.g. "org/<id>/"); returns how many."""
        base = self._path(prefix.rstrip("/") + "/x").parent
        if not base.exists():
            return 0
        files = [f for f in base.rglob("*") if f.is_file()]
        for f in files:
            await asyncio.to_thread(f.unlink)
        await asyncio.to_thread(shutil.rmtree, base, True)
        return len(files)


class S3Storage:
    """S3-compatible storage (e.g. Supabase Storage's S3 endpoint). Requires `boto3`; not exercised by tests."""

    def __init__(self, bucket: str, endpoint_url: str | None):
        import boto3  # optional dependency
        self.bucket = bucket
        self.client = boto3.client("s3", endpoint_url=endpoint_url)

    async def put(self, key: str, data: bytes) -> None:
        await asyncio.to_thread(self.client.put_object, Bucket=self.bucket, Key=key, Body=data,
                                ServerSideEncryption="AES256")

    async def get(self, key: str) -> bytes:
        obj = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self.client.delete_object, Bucket=self.bucket, Key=key)

    async def delete_prefix(self, prefix: str) -> int:
        def run() -> int:
            n = 0
            for page in self.client.get_paginator("list_objects_v2").paginate(Bucket=self.bucket, Prefix=prefix):
                keys = [{"Key": o["Key"]} for o in page.get("Contents", [])]
                if keys:
                    self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": keys, "Quiet": True})
                    n += len(keys)
            return n
        return await asyncio.to_thread(run)


_storage = None


def get_storage():
    global _storage
    if _storage is None:
        s = get_settings()
        _storage = S3Storage(s.s3_bucket, s.s3_endpoint_url) if s.storage_backend == "s3" else LocalStorage(s.storage_local_dir)
    return _storage


def reset_storage() -> None:
    global _storage
    _storage = None


def parse_clamd_reply(reply: bytes) -> str:
    """clamd answers "stream: OK", "stream: <Signature> FOUND" or "... ERROR", NUL-terminated in z-mode (QA/launch
    BUG-15: the NUL used to make every clean file look rejected). Errors (e.g. size limit) stay 'pending', never
    'clean'."""
    text = reply.decode(errors="replace").strip("\0 \r\n")
    if text.endswith(" OK"):
        return "clean"
    if text.endswith(" FOUND"):
        return "rejected"
    return "pending"


async def scan(data: bytes) -> str:
    """Return 'clean' or 'rejected'. ClamAV INSTREAM over TCP; 'pending' if the scanner is unreachable."""
    s = get_settings()
    if s.file_scanner == "disabled_dev_only":
        return "clean"

    def _clamd() -> str:
        with socket.create_connection((s.clamav_host, s.clamav_port), timeout=30) as sock:
            sock.sendall(b"zINSTREAM\0")
            for i in range(0, len(data), 65536):
                chunk = data[i:i + 65536]
                sock.sendall(struct.pack("!L", len(chunk)) + chunk)
            sock.sendall(struct.pack("!L", 0))
            reply = b""
            while not reply.endswith(b"\0") and len(reply) < 4096:  # z-mode replies end with a NUL
                part = sock.recv(4096)
                if not part:
                    break
                reply += part
        return parse_clamd_reply(reply)

    try:
        return await asyncio.to_thread(_clamd)
    except OSError:
        return "pending"  # stays undownloadable until a rescan job marks it clean


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sign_download(key: str, document_id: uuid.UUID, filename: str, content_type: str) -> tuple[str, datetime]:
    s = get_settings()
    exp = datetime.now(UTC) + timedelta(seconds=s.download_url_ttl_seconds)
    token = jwt.encode({"k": key, "d": str(document_id), "f": filename, "t": content_type, "exp": exp,
                        "typ": "download"}, s.jwt_secret.get_secret_value(), algorithm="HS256")
    return token, exp


def verify_download(token: str) -> dict:
    try:
        claims = jwt.decode(token, get_settings().jwt_secret.get_secret_value(), algorithms=["HS256"],
                            options={"require": ["exp"]})
    except jwt.PyJWTError:
        raise AppError(404, "file_not_found", "Not found", "This download link is invalid or has expired.") from None
    if claims.get("typ") != "download":
        raise AppError(404, "file_not_found", "Not found")
    return claims


def content_disposition(filename: str) -> str:
    """RFC 6266 attachment header that survives any filename (QA BUG-02).

    HTTP headers are latin-1, so a name like "Chịamaka Ọkafọ CV.pdf" crashed the response. We send an ASCII
    fallback plus the exact name as UTF-8 in filename*; quotes, backslashes and control characters can't break out.
    """
    import unicodedata
    from urllib.parse import quote

    name = "".join(c for c in (filename or "download") if c.isprintable()).strip() or "download"
    ascii_ = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    ascii_ = "".join(c if (c.isalnum() or c in " ._-()") else "_" for c in ascii_).strip() or "download"
    return f"attachment; filename=\"{ascii_[:150]}\"; filename*=UTF-8''{quote(name[:150], safe='')}"
