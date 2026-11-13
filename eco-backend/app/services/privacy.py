"""Data-subject rights (Nigeria Data Protection Act 2023 s.34 access/erasure/portability; GDPR equivalents).

export(): everything we hold that is about or by this person, as JSON: account, memberships, professional profiles,
  memories, conversations they started (with both sides of the conversation), content and versions they wrote,
  documents they uploaded (metadata; the files themselves are downloadable in the app), opportunities,
  applications, interview sessions, and the audit events they performed. Secrets, password hashes and embeddings are
  never included.

delete(): immediate effect, then a purge.
  - Refused while the person owns a team organisation that has other members (ownership must move first) or has a
    paid plan that renews automatically (cancel first, so nobody is charged for a deleted account).
  - Their personal organisation and any team organisation where they are the only member are closed (soft-deleted
    with their workspaces), so nothing in them is reachable. scripts/purge_deleted.py removes them, files
    included, after PURGE_AFTER_DAYS (default 30): the grace period for an accidental deletion.
  - The account is anonymised at once: email, name, country, password and sessions are removed; memories and
    professional profiles are deleted. Membership in other organisations ends. Work they produced inside someone
    else's workspace (an agency's client content) belongs to that organisation and stays, credited to "Deleted user".
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import system_context
from app.core.errors import AppError
from app.core.security import verify_password
from app.models import (
    Application,
    Asset,
    AssetVersion,
    AuditEvent,
    Conversation,
    Document,
    InterviewSession,
    MemoryItem,
    Message,
    Opportunity,
    Organisation,
    OrgMember,
    PasswordResetToken,
    ProfessionalProfile,
    RefreshToken,
    Subscription,
    User,
    Workspace,
)
from app.services import audit

EXCLUDE = {"password_hash", "embedding", "embedding_model", "token_hash", "encrypted_credentials", "storage_key",
           "search_vector", "tsv", "ip", "user_agent"}


def _row(obj) -> dict:
    return {a.key: getattr(obj, a.key) for a in obj.__mapper__.column_attrs if a.key not in EXCLUDE}


async def export(session: AsyncSession, user_id: uuid.UUID) -> dict:
    async with system_context(session, user_id):
        async def rows(model, col):
            return [_row(r) for r in (await session.execute(select(model).where(col == user_id))).scalars().all()]

        user = await session.get(User, user_id)
        memberships = (await session.execute(
            select(Organisation.name, Organisation.kind, OrgMember.role, OrgMember.created_at)
            .join(OrgMember, OrgMember.org_id == Organisation.id).where(OrgMember.user_id == user_id))).all()
        convs = (await session.execute(select(Conversation).where(Conversation.created_by == user_id))).scalars().all()
        conv_ids = [c.id for c in convs]
        msgs = (await session.execute(select(Message).where(Message.conversation_id.in_(conv_ids))
                                      .order_by(Message.created_at))).scalars().all() if conv_ids else []
        return {
            "exported_at": datetime.now(UTC),
            "account": _row(user),
            "memberships": [{"organisation": n, "kind": k, "role": r, "since": c} for n, k, r, c in memberships],
            "professional_profiles": await rows(ProfessionalProfile, ProfessionalProfile.user_id),
            "memories": await rows(MemoryItem, MemoryItem.owner_user_id),
            "conversations": [{**_row(c), "messages": [_row(m) for m in msgs if m.conversation_id == c.id]}
                              for c in convs],
            "content": await rows(Asset, Asset.created_by),
            "content_versions": await rows(AssetVersion, AssetVersion.author_id),
            "documents": await rows(Document, Document.uploaded_by),
            "opportunities": await rows(Opportunity, Opportunity.created_by),
            "applications": await rows(Application, Application.created_by),
            "interview_sessions": await rows(InterviewSession, InterviewSession.created_by),
            "activity": [_row(e) for e in (await session.execute(
                select(AuditEvent).where(AuditEvent.actor_user_id == user_id).order_by(AuditEvent.id))).scalars().all()],
            "notes": ("Files you uploaded can be downloaded from each workspace. Content you wrote in another "
                      "organisation's workspace is included above; that organisation keeps its own copy."),
        }


async def delete_account(session: AsyncSession, user_id: uuid.UUID, password: str, request: Request) -> dict:
    now = datetime.now(UTC)
    async with system_context(session, user_id):
        user = await session.get(User, user_id, with_for_update=True)
        if not verify_password(password, user.password_hash):
            raise AppError(400, "wrong_password", "Password is incorrect", "Enter your current password to confirm.")
        owned = (await session.execute(select(Organisation).where(
            Organisation.owner_user_id == user_id, Organisation.deleted_at.is_(None)))).scalars().all()
        blocked = []
        for org in owned:
            others = (await session.execute(select(func.count()).select_from(OrgMember).where(
                OrgMember.org_id == org.id, OrgMember.user_id != user_id))).scalar_one()
            if others:
                blocked.append(org.name)
        if blocked:
            raise AppError(409, "transfer_ownership_first", "Transfer ownership first",
                           "You own organisations other people use. Make someone else the owner, or remove the "
                           "other members, then delete your account.", extra={"organisations": blocked})
        renewing = (await session.execute(select(Subscription).where(
            Subscription.org_id.in_([o.id for o in owned]), Subscription.status.in_(("active", "past_due")),
            Subscription.auto_renew.is_(True), Subscription.period_end > now))).scalars().first() if owned else None
        if renewing:
            raise AppError(409, "cancel_subscription_first", "Cancel your plan first",
                           "Your paid plan renews automatically. Cancel it so you aren't charged, then delete your "
                           "account.")
        closed = [o.id for o in owned]
        if closed:
            await session.execute(update(Workspace).where(Workspace.org_id.in_(closed), Workspace.deleted_at.is_(None))
                                  .values(deleted_at=now))
            await session.execute(update(Organisation).where(Organisation.id.in_(closed)).values(deleted_at=now))
        await session.execute(delete(OrgMember).where(OrgMember.user_id == user_id, OrgMember.org_id.notin_(closed)))
        await session.execute(delete(MemoryItem).where(MemoryItem.owner_user_id == user_id))
        await session.execute(delete(ProfessionalProfile).where(ProfessionalProfile.user_id == user_id))
        await session.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user_id))
        await session.execute(update(RefreshToken).where(RefreshToken.user_id == user_id,
                                                         RefreshToken.revoked_at.is_(None)).values(revoked_at=now))
        user.email = f"deleted-{user_id}@deleted.invalid"
        user.display_name, user.country, user.currency = "Deleted user", None, None
        user.password_hash, user.is_active, user.deleted_at, user.password_changed_at = None, False, now, now
        await session.flush()
        await audit.record(session, "account.deleted", actor_id=None, target_type="user", target_id=user_id,
                           metadata={"organisations_closed": len(closed)}, request=request)
    return {"status": "deleted", "organisations_closed": len(closed),
            "message": "Your account is deleted and you're signed out everywhere. Workspaces you owned are closed "
                       "now and permanently erased, files included, within 30 days."}
