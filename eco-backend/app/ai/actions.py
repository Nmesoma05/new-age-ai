"""Executors for approved external actions (publish, send, spend).

None are registered in production, because no write integration has been built and verified yet (see
docs/INTEGRATIONS.md, "planned"). Approving an action with no executor is refused and the action stays pending.

Contract for a future executor (enforced in api/v1/assistant.py approve_action):
- It declares the `kind` it performs and the catalog `provider` it needs. Approval is refused unless that workspace
  has a *connected* integration for the provider (not revoked, not needs_reauth).
- It runs only after a human approved this exact action. It receives the approved action, the integration row
  and an idempotency key (the action id), never the conversation or the model.
- It must send the idempotency key to the provider where the provider supports one, and must call the provider
  through app.integrations.http with idempotent=False unless the provider deduplicates by that key.
- It returns proof: a dict with `provider_ref` (the provider's id for what was created/sent/charged), plus
  optional public `url`. No `provider_ref` = not confirmed = recorded as failed, never as executed.
- If the outcome is unclear (OutcomeUnknown), the action is recorded as failed/outcome_unknown and NOT retried:
  the person is told to check the account before trying again.
"""
from __future__ import annotations

import uuid
from typing import Protocol

from app.models import Integration, PendingAction


class Executor(Protocol):
    kind: str
    provider: str

    async def execute(self, action: PendingAction, integration: Integration, idempotency_key: uuid.UUID) -> dict:
        """Carry out the action; return {"provider_ref": ..., "url"?: ...}. No secrets in the result."""
        ...


EXECUTORS: dict[str, Executor] = {}


def register(executor: Executor) -> None:
    EXECUTORS[executor.kind] = executor


def unregister(kind: str) -> None:
    EXECUTORS.pop(kind, None)
