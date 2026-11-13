"""Hybrid retrieval over the current workspace only: full-text (OR of query words) + vector similarity,
merged with reciprocal-rank fusion. Every query filters on the run's workspace_id *and* runs under RLS, and
every returned snippet is checked against the run scope before it can reach a prompt."""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import text

from app.ai.context import AgentContext

_WORDS = re.compile(r"[^\W_]{2,}", re.UNICODE)
RRF_K = 60


@dataclass
class Snippet:
    ref: str            # mem:<id> | doc:<document_id>#<chunk_index> | asset:<id>
    kind: str           # memory | doc | asset
    workspace_id: uuid.UUID
    text: str
    untrusted: bool
    score: float = 0.0
    meta: dict = field(default_factory=dict)


def _tsquery(q: str) -> str | None:
    words = list(dict.fromkeys(w.lower() for w in _WORDS.findall(q)))[:24]
    return " | ".join(words) or None


def _vec_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


async def _ranked(ctx: AgentContext, fts_sql: str, vec_sql: str, params: dict, tsq: str | None,
                  qvec: list[float] | None, k: int) -> dict[str, tuple[float, dict]]:
    scores: dict[str, tuple[float, dict]] = {}
    lists = []
    if tsq:
        lists.append((await ctx.session.execute(text(fts_sql), {**params, "tsq": tsq, "k": k})).mappings().all())
    if qvec is not None:
        lists.append((await ctx.session.execute(text(vec_sql), {**params, "qv": _vec_literal(qvec), "k": k}))
                     .mappings().all())
    for rows in lists:
        for rank, row in enumerate(rows):
            key = str(row["key"])
            prev = scores.get(key, (0.0, dict(row)))[0]
            scores[key] = (prev + 1.0 / (RRF_K + rank + 1), dict(row))
    return scores


async def search(ctx: AgentContext, query: str, *, k: int = 6, kinds: tuple[str, ...] = ("memory", "doc", "asset"),
                 document_ids: list[uuid.UUID] | None = None) -> list[Snippet]:
    tsq = _tsquery(query)
    qvec = None
    if ctx.embedder is not None and query.strip():
        try:
            qvec = (await ctx.embedder.embed([query]))[0]
        except Exception:  # retrieval degrades to full-text rather than failing the run
            qvec = None
    base = {"ws": ctx.workspace_id, "uid": ctx.user_id}
    out: list[Snippet] = []

    if "memory" in kinds:
        where = ("m.workspace_id = :ws AND m.status = 'active' "
                 "AND (m.visibility = 'workspace' OR m.owner_user_id = :uid)")
        sel = "SELECT m.id AS key, m.workspace_id, m.content AS body, m.kind, m.source FROM memory_items m"
        scores = await _ranked(
            ctx, f"{sel} WHERE {where} AND m.tsv @@ to_tsquery('simple', :tsq) "
                 f"ORDER BY ts_rank(m.tsv, to_tsquery('simple', :tsq)) DESC LIMIT :k",
            f"{sel} WHERE {where} AND m.embedding IS NOT NULL ORDER BY m.embedding <=> CAST(:qv AS vector) LIMIT :k",
            base, tsq, qvec, k)
        for key, (score, row) in scores.items():
            out.append(Snippet(f"mem:{key}", "memory", row["workspace_id"], row["body"],
                               untrusted=row["source"] == "agent_proposed", score=score, meta={"kind": row["kind"]}))

    if "doc" in kinds:
        where = ("c.workspace_id = :ws AND d.deleted_at IS NULL AND d.scan_status = 'clean'")
        params = dict(base)
        if document_ids:
            where += " AND c.document_id = ANY(:docs)"
            params["docs"] = list(document_ids)
        sel = ("SELECT c.id AS key, c.workspace_id, c.document_id, c.chunk_index, c.text AS body, d.filename "
               "FROM document_chunks c JOIN documents d ON d.id = c.document_id")
        scores = await _ranked(
            ctx, f"{sel} WHERE {where} AND c.tsv @@ to_tsquery('simple', :tsq) "
                 f"ORDER BY ts_rank(c.tsv, to_tsquery('simple', :tsq)) DESC LIMIT :k",
            f"{sel} WHERE {where} AND c.embedding IS NOT NULL ORDER BY c.embedding <=> CAST(:qv AS vector) LIMIT :k",
            params, tsq, qvec, k)
        for _key, (score, row) in scores.items():
            out.append(Snippet(f"doc:{row['document_id']}#{row['chunk_index']}", "doc", row["workspace_id"],
                               row["body"], untrusted=True, score=score, meta={"filename": row["filename"]}))

    if "asset" in kinds and tsq:
        rows = (await ctx.session.execute(text(
            "SELECT a.id, a.workspace_id, a.title, a.type, v.body_text FROM assets a "
            "JOIN asset_versions v ON v.asset_id = a.id AND v.version = a.current_version "
            "WHERE a.workspace_id = :ws AND a.deleted_at IS NULL "
            "AND to_tsvector('simple', a.title || ' ' || v.body_text) @@ to_tsquery('simple', :tsq) "
            "ORDER BY a.updated_at DESC LIMIT :k"), {**base, "tsq": tsq, "k": k})).mappings().all()
        for rank, r in enumerate(rows):
            out.append(Snippet(f"asset:{r['id']}", "asset", r["workspace_id"],
                               f"{r['title']} ({r['type']}): {r['body_text'][:1500]}", untrusted=True,
                               score=1.0 / (RRF_K + rank + 1)))

    for s in out:
        ctx.assert_in_scope(s.workspace_id)
    out.sort(key=lambda s: s.score, reverse=True)
    return out[: k * 2]
