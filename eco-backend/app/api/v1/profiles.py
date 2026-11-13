"""Division profiles: one per workspace. Each endpoint only works on workspaces of its own product."""
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.core.deps import WsCtx, ws_ctx
from app.core.errors import AppError, not_found
from app.models import BusinessProfile, ClientAccount, ProfessionalProfile
from app.schemas.common import (
    BusinessProfileIn,
    BusinessProfileOut,
    ClientAccountIn,
    ClientAccountOut,
    ProfessionalProfileIn,
    ProfessionalProfileOut,
)
from app.services import audit

router = APIRouter(prefix="/v1/workspaces/{workspace_id}", tags=["profiles"])


def _product(ctx: WsCtx, product: str) -> None:
    if ctx.workspace.product != product:
        raise AppError(409, "wrong_product", "Wrong product", f"This endpoint is for {product} workspaces.")


async def _get(ctx: WsCtx, model):
    return (await ctx.session.execute(select(model).where(model.workspace_id == ctx.workspace.id))).scalar_one_or_none()


async def _upsert(ctx: WsCtx, model, data: dict, action: str, extra: dict | None = None):
    await ctx.require("ws.write")
    row = await _get(ctx, model)
    if row is None:
        row = model(workspace_id=ctx.workspace.id, org_id=ctx.workspace.org_id, **(extra or {}), **data)
        ctx.session.add(row)
    else:
        for k, v in data.items():
            setattr(row, k, v)
        row.version += 1
    await ctx.session.flush()
    await ctx.session.refresh(row)
    await audit.record(ctx.session, action, actor_id=ctx.principal.id, org_id=ctx.workspace.org_id,
                       workspace_id=ctx.workspace.id, target_type=model.__tablename__, target_id=row.id,
                       metadata={"version": row.version}, request=ctx.request)
    return row


@router.get("/client-account", response_model=ClientAccountOut)
async def get_client_account(ctx: WsCtx = Depends(ws_ctx)):
    _product(ctx, "creator")
    row = await _get(ctx, ClientAccount)
    if row is None:
        raise not_found("client_account")
    return row


@router.put("/client-account", response_model=ClientAccountOut)
async def put_client_account(body: ClientAccountIn, ctx: WsCtx = Depends(ws_ctx)):
    _product(ctx, "creator")
    data = body.model_dump(mode="json")
    return await _upsert(ctx, ClientAccount, data, "profile.client_account_saved")


@router.get("/business-profile", response_model=BusinessProfileOut)
async def get_business_profile(ctx: WsCtx = Depends(ws_ctx)):
    _product(ctx, "business")
    row = await _get(ctx, BusinessProfile)
    if row is None:
        raise not_found("business_profile")
    return row


@router.put("/business-profile", response_model=BusinessProfileOut)
async def put_business_profile(body: BusinessProfileIn, ctx: WsCtx = Depends(ws_ctx)):
    _product(ctx, "business")
    return await _upsert(ctx, BusinessProfile, body.model_dump(mode="json"), "profile.business_saved")


@router.get("/professional-profile", response_model=ProfessionalProfileOut)
async def get_professional_profile(ctx: WsCtx = Depends(ws_ctx)):
    _product(ctx, "freelancer")
    row = await _get(ctx, ProfessionalProfile)
    if row is None:
        raise not_found("professional_profile")
    return row


@router.put("/professional-profile", response_model=ProfessionalProfileOut)
async def put_professional_profile(body: ProfessionalProfileIn, ctx: WsCtx = Depends(ws_ctx)):
    _product(ctx, "freelancer")
    return await _upsert(ctx, ProfessionalProfile, body.to_row(), "profile.professional_saved",
                         extra={"user_id": ctx.principal.id})
