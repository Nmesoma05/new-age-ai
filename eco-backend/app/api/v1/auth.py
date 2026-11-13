import json
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.clientip import client_ip
from app.core.config import get_settings
from app.core.deps import Principal, get_principal, get_session
from app.core.errors import AppError
from app.schemas.common import (
    ChangePasswordIn,
    ForgotIn,
    LoginIn,
    RefreshIn,
    ResetIn,
    SignupIn,
    SignupOut,
    TokensOut,
    UserOut,
    UserPatch,
)
from app.services import accounts, audit, privacy, recovery
from app.services.storage import content_disposition

router = APIRouter(prefix="/v1", tags=["auth"])


def _local_only() -> None:
    if get_settings().auth_mode != "local":
        raise AppError(404, "not_found", "Not found", "Sign-in is handled by the identity provider.")


@router.post("/auth/signup", response_model=SignupOut, status_code=201, dependencies=[Depends(_local_only)])
async def signup(body: SignupIn, request: Request, session: AsyncSession = Depends(get_session)):
    ip, s = client_ip(request), get_settings()
    await ratelimit.check("signup", ip, s.signup_ip_per_hour, 3600)
    await ratelimit.hit("signup", ip)
    user, org = await accounts.signup(session, email=str(body.email).lower(), password=body.password,
                                      display_name=body.display_name, country=body.country, currency=body.currency,
                                      product=body.product, request=request, accept_terms=body.accept_terms)
    tokens = await accounts.issue_tokens(session, user.id, user_agent=request.headers.get("user-agent"))
    tokens.pop("_refresh_id")
    return {"user": UserOut.model_validate(user), "personal_org_id": org.id, "tokens": tokens}


@router.post("/auth/login", response_model=TokensOut, dependencies=[Depends(_local_only)])
async def login(body: LoginIn, request: Request, session: AsyncSession = Depends(get_session)):
    ip, s = client_ip(request), get_settings()
    await ratelimit.check("login_fail", ip, s.login_ip_max_failures, 900)
    try:
        return await accounts.login(session, email=str(body.email).lower(), password=body.password, request=request)
    except AppError as e:
        if e.code == "invalid_credentials":
            await ratelimit.hit("login_fail", ip)  # only failures count, so a busy office network isn't punished
        raise


@router.post("/auth/refresh", response_model=TokensOut, dependencies=[Depends(_local_only)])
async def refresh(body: RefreshIn, request: Request, session: AsyncSession = Depends(get_session)):
    return await accounts.refresh(session, body.refresh_token, request)


@router.post("/auth/logout", status_code=204, dependencies=[Depends(_local_only)])
async def logout(body: RefreshIn, session: AsyncSession = Depends(get_session)):
    await accounts.logout(session, body.refresh_token)
    return Response(status_code=204)


@router.post("/auth/password/forgot", status_code=202, dependencies=[Depends(_local_only)])
async def forgot_password(body: ForgotIn, request: Request):
    ip = client_ip(request)
    await ratelimit.check("forgot", ip, get_settings().forgot_ip_per_hour, 3600)
    await ratelimit.hit("forgot", ip)
    return await recovery.forgot(str(body.email), request)


@router.post("/auth/password/reset", dependencies=[Depends(_local_only)])
async def reset_password(body: ResetIn, request: Request):
    return await recovery.reset(body.token, body.new_password, request)


@router.post("/me/password", dependencies=[Depends(_local_only)])
async def change_password(body: ChangePasswordIn, request: Request, p: Principal = Depends(get_principal)):
    out = await recovery.change(p.id, body.current_password, body.new_password, request)
    # every session was revoked; this device gets fresh tokens so the person stays signed in here
    tokens = await accounts.issue_tokens(p.session, p.id, user_agent=request.headers.get("user-agent"))
    tokens.pop("_refresh_id")
    return {**out, "tokens": tokens}


@router.get("/me", response_model=UserOut)
async def me(p: Principal = Depends(get_principal)):
    return p.user


@router.patch("/me", response_model=UserOut)
async def update_me(body: UserPatch, request: Request, p: Principal = Depends(get_principal)):
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(p.user, k, v)
    await p.session.flush()
    await p.session.refresh(p.user)
    await audit.record(p.session, "account.updated", actor_id=p.id, target_type="user", target_id=p.id,
                       metadata={"fields": sorted(changes)}, request=request)
    return p.user


class DeleteAccountIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    confirm: Literal["DELETE"]


@router.get("/me/export")
async def export_my_data(request: Request, p: Principal = Depends(get_principal)):
    """Everything we hold about or by you, as one JSON file (right of access and portability)."""
    data = await privacy.export(p.session, p.id)
    await audit.record(p.session, "account.exported", actor_id=p.id, target_type="user", target_id=p.id,
                       request=request)
    body = json.dumps(data, default=str, ensure_ascii=False, indent=1).encode()
    return Response(body, media_type="application/json", headers={
        "Content-Disposition": content_disposition(f"my-data-{datetime.now(UTC).date().isoformat()}.json")})


@router.post("/me/delete")
async def delete_my_account(body: DeleteAccountIn, request: Request, p: Principal = Depends(get_principal)):
    """Right to erasure. Needs the current password and the word DELETE."""
    return await privacy.delete_account(p.session, p.id, body.password, request)
