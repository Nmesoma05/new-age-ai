import io
import zipfile

from tests.helpers import PDF_BYTES, pdf_file


async def test_upload_list_download_delete(client, signup, make_workspace):
    a = await signup("Ada")
    ws = await make_workspace(a)
    r = await client.post(f"/v1/workspaces/{ws}/documents", headers=a.h, files=pdf_file("../../etc/passwd.pdf"))
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["content_type"] == "application/pdf" and doc["filename"] == "passwd.pdf"
    assert doc["scan_status"] == "clean" and len(doc["sha256"]) == 64
    page = (await client.get(f"/v1/workspaces/{ws}/documents", headers=a.h)).json()
    assert [d["id"] for d in page["data"]] == [doc["id"]]
    link = (await client.post(f"/v1/workspaces/{ws}/documents/{doc['id']}/download-url", headers=a.h)).json()
    got = await client.get(link["url"].replace("http://test", ""))
    assert got.status_code == 200 and got.content == PDF_BYTES
    assert got.headers["content-disposition"].startswith("attachment;")
    assert (await client.delete(f"/v1/workspaces/{ws}/documents/{doc['id']}", headers=a.h)).status_code == 204
    assert (await client.get(f"/v1/workspaces/{ws}/documents/{doc['id']}", headers=a.h)).status_code == 404
    assert (await client.get(link["url"].replace("http://test", ""))).status_code == 404


async def test_type_is_sniffed_not_trusted(client, signup, make_workspace):
    a = await signup("Ada")
    ws = await make_workspace(a)
    exe = b"MZ\x90\x00\x03\x00\x00\x00" + bytes(range(256)) * 4
    r = await client.post(f"/v1/workspaces/{ws}/documents", headers=a.h, files=pdf_file("cv.pdf", exe))
    assert r.status_code == 415 and r.json()["code"] == "unsupported_file"


async def test_macro_docx_rejected_and_clean_docx_accepted(client, signup, make_workspace):
    a = await signup("Ada")
    ws = await make_workspace(a)

    def docx(with_macro: bool) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("[Content_Types].xml", "<Types/>")
            z.writestr("word/document.xml", "<w:document/>")
            if with_macro:
                z.writestr("word/vbaProject.bin", b"\x00\x01")
        return buf.getvalue()

    ok = await client.post(f"/v1/workspaces/{ws}/documents", headers=a.h, files=pdf_file("cv.docx", docx(False)))
    assert ok.status_code == 201 and ok.json()["content_type"].endswith("wordprocessingml.document")
    bad = await client.post(f"/v1/workspaces/{ws}/documents", headers=a.h, files=pdf_file("cv.docm", docx(True)))
    assert bad.status_code == 415


async def test_size_limit(client, signup, make_workspace, monkeypatch):
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 1024)
    a = await signup("Ada")
    ws = await make_workspace(a)
    r = await client.post(f"/v1/workspaces/{ws}/documents", headers=a.h, files=pdf_file("big.pdf", PDF_BYTES + b"x" * 2000))
    assert r.status_code == 413 and r.json()["code"] == "file_too_large"


async def test_unscanned_files_cannot_be_downloaded(client, signup, make_workspace, owner_db):
    a = await signup("Ada")
    ws = await make_workspace(a)
    doc = (await client.post(f"/v1/workspaces/{ws}/documents", headers=a.h, files=pdf_file())).json()
    owner_db.execute("UPDATE documents SET scan_status = 'pending' WHERE id = %s", (doc["id"],))
    r = await client.post(f"/v1/workspaces/{ws}/documents/{doc['id']}/download-url", headers=a.h)
    assert r.status_code == 409 and r.json()["code"] == "file_not_ready"


async def test_tampered_download_token(client, signup, make_workspace):
    a = await signup("Ada")
    ws = await make_workspace(a)
    doc = (await client.post(f"/v1/workspaces/{ws}/documents", headers=a.h, files=pdf_file())).json()
    link = (await client.post(f"/v1/workspaces/{ws}/documents/{doc['id']}/download-url", headers=a.h)).json()
    path = link["url"].replace("http://test", "")
    assert (await client.get(path[:-3] + "abc")).status_code == 404


async def test_viewer_cannot_upload(client, signup, activate_plan):
    owner, viewer = await signup("Owner"), await signup("Viewer")
    org = (await client.post("/v1/orgs", headers=owner.h, json={"name": "Agency"})).json()["id"]
    await activate_plan(org, "team")
    await client.post(f"/v1/orgs/{org}/products", headers=owner.h, json={"product": "creator"})
    await client.post(f"/v1/orgs/{org}/members", headers=owner.h, json={"email": viewer.email, "role": "member"})
    ws = (await client.post(f"/v1/orgs/{org}/workspaces", headers=owner.h, json={"name": "C", "product": "creator"})).json()["id"]
    await client.post(f"/v1/workspaces/{ws}/members", headers=owner.h, json={"user_id": str(viewer.user_id), "role": "viewer"})
    r = await client.post(f"/v1/workspaces/{ws}/documents", headers=viewer.h, files=pdf_file())
    assert r.status_code == 403


async def test_storage_keys_are_tenant_prefixed(client, signup, make_workspace, owner_db):
    a = await signup("Ada")
    ws = await make_workspace(a)
    await client.post(f"/v1/workspaces/{ws}/documents", headers=a.h, files=pdf_file("../evil.pdf"))
    key = owner_db.execute("SELECT storage_key FROM documents").fetchone()[0]
    assert key.startswith(f"org/{a.org_id}/ws/{ws}/") and ".." not in key and "evil" not in key
