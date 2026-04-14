from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional, List

if TYPE_CHECKING:
    from mlflow_oidc_auth.db.models.quota import SqlUserQuota

from mlflow.exceptions import MlflowException
from mlflow.protos.databricks_pb2 import RESOURCE_LIMIT_EXCEEDED

from mlflow_oidc_auth.config import config
from mlflow_oidc_auth.logger import get_logger
from mlflow_oidc_auth.store import store

logger = get_logger()


def effective_quota_bytes(quota: Optional["SqlUserQuota"]) -> Optional[int]:
    """Return the active quota limit, falling back to the env default if unset."""
    if quota is not None and quota.quota_bytes is not None:
        return quota.quota_bytes
    return config.QUOTA_DEFAULT_BYTES


def effective_soft_cap_fraction(quota: Optional["SqlUserQuota"]) -> float:
    """Return the active soft-cap fraction, falling back to the env default if unset."""
    if quota is not None and quota.soft_cap_fraction is not None:
        return quota.soft_cap_fraction
    return config.QUOTA_SOFT_CAP_FRACTION


def get_experiment_owner(experiment_id: str) -> Optional[str]:
    """Return the username of the MANAGE-permission holder of an experiment, or None."""
    from mlflow_oidc_auth.permissions import MANAGE

    try:
        perms = store.list_experiment_permissions_for_experiment(experiment_id)
        for perm in perms:
            if perm.permission == MANAGE.name:
                user = store.get_user_by_id(perm.user_id)
                if user:
                    return user.username
    except Exception:
        pass
    return None


def enforce_quota(username: str) -> None:
    """Raise MlflowException if the user's storage quota is exceeded.

    Effective quota resolution:
    - If the user has an explicit quota_bytes set, use that.
    - Otherwise (no row, or quota_bytes is None), fall back to QUOTA_DEFAULT_BYTES.
    - If the effective quota is None, the user is unlimited.
    """
    quota = store.get_user_quota(username)
    limit = effective_quota_bytes(quota)

    if limit is None:
        return  # Unlimited

    used = quota.used_bytes if quota is not None else 0

    if used >= limit:
        raise MlflowException(
            f"Storage quota exceeded for user '{username}'. "
            f"Used {used} bytes of {limit} bytes.",
            RESOURCE_LIMIT_EXCEEDED,
        )


def reconcile_user_quota(username: str) -> None:
    """Recalculate used_bytes for a single user and apply threshold logic.

    If the user has no quota row yet, one is created so that used_bytes is
    always tracked regardless of whether an explicit limit has been set.
    """
    quota = store.get_user_quota(username)
    if quota is None:
        used = _calculate_used_bytes(username)
        store.set_user_quota(username, None, None)
        store.update_user_quota_used_bytes(username, used)
        return

    effective_quota = effective_quota_bytes(quota)
    if effective_quota is None:
        # No quota applies — ensure any stale enforcement state is cleared
        if quota.hard_blocked:
            store.set_quota_hard_blocked(username, False)
        if quota.soft_notified_at is not None:
            store.set_quota_soft_notified_at(username, None)
        return

    used = _calculate_used_bytes(username)
    store.update_user_quota_used_bytes(username, used)

    # Threshold checks
    pct = used / effective_quota
    soft_fraction = effective_soft_cap_fraction(quota)

    now = datetime.now(timezone.utc)

    from mlflow_oidc_auth.utils.email import send_hard_cap_notification, send_soft_cap_warning

    # Soft cap notification
    email_address = getattr(quota, "email", None)

    if used >= effective_quota:
        # Hard cap: block and send daily reminders
        if not quota.hard_blocked:
            store.set_quota_hard_blocked(username, True)
        should_notify = quota.soft_notified_at is None or (now - quota.soft_notified_at) > timedelta(hours=24)
        if should_notify:
            sent = send_hard_cap_notification(username, used, effective_quota, email_address)
            if sent:
                store.set_quota_soft_notified_at(username, now)
    else:
        if quota.hard_blocked:
            store.set_quota_hard_blocked(username, False)
        if pct >= soft_fraction:
            # Soft cap: warn once per threshold crossing
            if quota.soft_notified_at is None:
                sent = send_soft_cap_warning(username, used, effective_quota, pct, email_address)
                if sent:
                    store.set_quota_soft_notified_at(username, now)
        else:
            # Below soft cap: reset so the warning fires again if usage climbs back up
            if quota.soft_notified_at is not None:
                store.set_quota_soft_notified_at(username, None)


def _calculate_used_bytes(username: str) -> int:
    """Sum artifact sizes across all experiments owned by the given user."""
    import mlflow
    from mlflow_oidc_auth.permissions import MANAGE

    client = mlflow.tracking.MlflowClient()
    total = 0

    # Get all experiment_ids managed by this user
    user_perms = store.list_experiment_permissions(username)
    owned_experiment_ids = [p.experiment_id for p in user_perms if p.permission == MANAGE.name]

    for exp_id in owned_experiment_ids:
        runs = client.search_runs(experiment_ids=[exp_id])
        for run in runs:
            total += _sum_artifacts(run.info.artifact_uri, "")

    return total


def _sum_artifacts(artifact_uri: str, path: str) -> int:
    """Recursively sum artifact file sizes using the server's internal artifact store.

    Uses mlflow.server.handlers._list_artifacts_for_proxied_run_artifact_root so that
    mlflow-artifacts:/ URIs are resolved directly against the --artifacts-destination
    filesystem instead of going through the HTTP proxy (which fails when
    MLFLOW_TRACKING_URI is a database URI rather than an HTTP server URL).
    """
    from mlflow.server.handlers import _list_artifacts_for_proxied_run_artifact_root

    total = 0
    artifacts = _list_artifacts_for_proxied_run_artifact_root(artifact_uri, path or None)
    for artifact in artifacts:
        if artifact.is_dir:
            total += _sum_artifacts(artifact_uri, artifact.path)
        elif artifact.file_size is not None:
            total += artifact.file_size

    return total


def reconcile_all_quotas() -> Optional[List[str]]:
    """Reconcile quotas for all users, creating quota rows where missing."""
    try:
      users = store.list_users(all=True)
    except Exception as e:
      error = f"Failed getting users for quota reconciliation: {e}"
      logger.error(error)
      return [error]

    errors = []
    for user in users:
        try:
          reconcile_user_quota(user.username)
        except Exception as e:
          error = f"Error reconciling quota for {user.username}: {e}"
          logger.error(error)
          errors.append(error)

    return errors


def cleanup_trash(retention_days: int) -> None:
    """Permanently delete soft-deleted experiments older than retention_days."""
    import time
    import mlflow

    client = mlflow.tracking.MlflowClient()
    # MLflow uses milliseconds
    cutoff_ms = (time.time() - retention_days * 86400) * 1000

    try:
        deleted_experiments = client.search_experiments(
            view_type=mlflow.entities.ViewType.DELETED_ONLY,
        )
        affected_owners = set()
        for exp in deleted_experiments:
            deletion_time = getattr(exp, "last_update_time", None) or getattr(exp, "creation_time", 0)
            if deletion_time and deletion_time < cutoff_ms:
                owner = get_experiment_owner(exp.experiment_id)
                try:
                    # Hard-delete via underlying store
                    from mlflow.server.handlers import _get_tracking_store
                    _get_tracking_store().delete_experiment(exp.experiment_id)
                    logger.info(f"Permanently deleted experiment {exp.experiment_id} (owner: {owner})")
                    if owner:
                        affected_owners.add(owner)
                except Exception as e:
                    logger.error(f"Could not hard-delete experiment {exp.experiment_id}: {e}")

        for owner in affected_owners:
            try:
                reconcile_user_quota(owner)
            except Exception as e:
                logger.error(f"Error reconciling quota for {owner} after trash cleanup: {e}")

    except Exception as e:
        logger.error(f"Error during trash cleanup: {e}")
