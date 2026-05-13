"""Quota management API endpoints."""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from mlflow_oidc_auth.db.models.quota import SqlUserQuota

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mlflow_oidc_auth.logger import get_logger
from mlflow_oidc_auth.store import store
from mlflow_oidc_auth.utils import get_is_admin, get_username

from ._prefix import QUOTA_ROUTER_PREFIX, EXPERIMENT_OWNERSHIP_ROUTER_PREFIX

logger = get_logger()

quota_router = APIRouter(
    prefix=QUOTA_ROUTER_PREFIX,
    tags=["quota"],
    responses={
        403: {"description": "Forbidden - Insufficient permissions"},
        404: {"description": "Resource not found"},
    },
)

ownership_router = APIRouter(
    prefix=EXPERIMENT_OWNERSHIP_ROUTER_PREFIX,
    tags=["quota"],
    responses={
        403: {"description": "Forbidden - Insufficient permissions"},
        404: {"description": "Resource not found"},
    },
)


class SetQuotaRequest(BaseModel):
    quota_bytes: Optional[int] = None
    soft_cap_fraction: Optional[float] = None


class TransferOwnershipRequest(BaseModel):
    new_owner: str


class QuotaResponse(BaseModel):
    username: str
    user_id: int
    quota_bytes: Optional[int]
    soft_cap_fraction: float
    used_bytes: int
    hard_blocked: bool
    email: Optional[str]
    last_reconciled_at: Optional[str]
    last_notified_at: Optional[str]

    @classmethod
    def from_db_model(cls, quota: "SqlUserQuota", username: str) -> "QuotaResponse":
        from mlflow_oidc_auth.utils.quota import effective_quota_bytes, effective_soft_cap_fraction

        return cls(
            username=username,
            user_id=quota.user_id,
            quota_bytes=effective_quota_bytes(quota),
            soft_cap_fraction=effective_soft_cap_fraction(quota),
            used_bytes=quota.used_bytes,
            hard_blocked=quota.hard_blocked,
            email=quota.email,
            last_reconciled_at=quota.last_reconciled_at.isoformat() if quota.last_reconciled_at else None,
            last_notified_at=quota.soft_notified_at.isoformat() if quota.soft_notified_at else None,
        )


@quota_router.get("/users", summary="List all user quotas")
async def list_user_quotas(is_admin: bool = Depends(get_is_admin)) -> JSONResponse:
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        quotas = store.list_all_user_quotas()
        result = []
        for q in quotas:
            user = store.get_user_by_id(q.user_id)
            if user is None:
                continue
            result.append(QuotaResponse.from_db_model(q, user.username).model_dump())
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"Error listing quotas: {e}")
        raise HTTPException(status_code=500, detail="Failed to list quotas")


@quota_router.get("/users/{username}", summary="Get quota for a user")
async def get_user_quota(
    username: str,
    current_username: str = Depends(get_username),
    is_admin: bool = Depends(get_is_admin),
) -> JSONResponse:
    if not is_admin and current_username != username:
        raise HTTPException(status_code=403, detail="Access denied")

    if store.get_user_profile(username) is None:
        raise HTTPException(status_code=404, detail=f"User {username} not found")

    try:
        from mlflow_oidc_auth.utils.quota import effective_quota_bytes, effective_soft_cap_fraction

        user = store.get_user_profile(username)
        quota = store.get_user_quota(username)
        if quota is None:
            response = QuotaResponse(
                username=username,
                user_id=user.id,
                quota_bytes=effective_quota_bytes(None),
                soft_cap_fraction=effective_soft_cap_fraction(None),
                used_bytes=0,
                hard_blocked=False,
                email=None,
                last_reconciled_at=None,
                last_notified_at=None,
            )
        else:
            response = QuotaResponse.from_db_model(quota, username)
        return JSONResponse(content=response.model_dump())
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting quota for {username}: {e}")
        raise HTTPException(status_code=500, detail="Failed to get quota")


@quota_router.put("/users/{username}", summary="Set quota for a user")
async def set_user_quota(
    username: str,
    quota_request: SetQuotaRequest = Body(...),
    is_admin: bool = Depends(get_is_admin),
) -> JSONResponse:
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        user = store.get_user_profile(username)
        if user is None:
            raise HTTPException(status_code=404, detail=f"User {username} not found")
        store.set_user_quota(username, quota_request.quota_bytes, quota_request.soft_cap_fraction)
        return JSONResponse(content={"message": f"Quota set for {username}"})
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting quota for {username}: {e}")
        raise HTTPException(status_code=500, detail="Failed to set quota")


@quota_router.delete("/users/{username}", summary="Remove quota for a user (unlimited)")
async def delete_user_quota(
    username: str,
    is_admin: bool = Depends(get_is_admin),
) -> JSONResponse:
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    try:
        store.delete_user_quota(username)
        return JSONResponse(content={"message": f"Quota removed for {username}"})
    except Exception as e:
        logger.error(f"Error deleting quota for {username}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete quota")


@quota_router.post("/reconcile", summary="Trigger manual quota reconciliation")
async def trigger_reconcile(is_admin: bool = Depends(get_is_admin)) -> JSONResponse:
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    from mlflow_oidc_auth.utils.quota import reconcile_all_quotas

    errors = reconcile_all_quotas()
    if errors:
      return JSONResponse(status_code=500, content={
        "errors": errors
      })

    return JSONResponse(content={"message": "Quota reconciliation triggered"})

@ownership_router.post("/{experiment_id}/transfer-ownership", summary="Transfer experiment ownership")
async def transfer_experiment_ownership(
    experiment_id: str,
    body: TransferOwnershipRequest = Body(...),
    current_username: str = Depends(get_username),
    is_admin: bool = Depends(get_is_admin),
) -> JSONResponse:
    from mlflow_oidc_auth.permissions import EDIT, MANAGE
    from mlflow_oidc_auth.utils.quota import get_experiment_owner

    try:
        # Check that the requester is the current manager or an admin
        current_owner = get_experiment_owner(experiment_id)
        if not is_admin and current_username != current_owner:
            raise HTTPException(status_code=403, detail="Only the experiment owner or an admin can transfer ownership")

        new_owner = body.new_owner
        if current_owner == new_owner:
            return JSONResponse(content={"message": "No change — new owner is already the owner"})

        # Ensure new_owner exists
        new_owner_user = store.get_user_profile(new_owner)
        if new_owner_user is None:
            raise HTTPException(status_code=404, detail=f"User {new_owner} not found")

        # Downgrade current owner's permission to EDIT
        if current_owner:
            try:
                store.update_experiment_permission(experiment_id, current_owner, EDIT.name)
            except Exception:
                pass  # May not have an existing permission row if they were deleted

        # Upgrade (or create) new owner's permission to MANAGE
        try:
            store.update_experiment_permission(experiment_id, new_owner, MANAGE.name)
        except Exception:
            store.create_experiment_permission(experiment_id, new_owner, MANAGE.name)

        return JSONResponse(content={"message": f"Ownership of experiment {experiment_id} transferred to {new_owner}"})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error transferring ownership of experiment {experiment_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to transfer ownership")
