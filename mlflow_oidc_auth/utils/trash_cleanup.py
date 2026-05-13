"""Helpers for permanently deleting soft-deleted MLflow runs and experiments.

Both the admin-triggered trash cleanup and the quota-driven retention sweep
need to remove run artifacts (including via the mlflow-artifacts proxy) and
hard-delete runs/experiments from the tracking store. This module centralizes
that logic.
"""

from typing import Any

from mlflow.entities import ViewType
from mlflow.exceptions import InvalidUrlException
from mlflow.store.artifact.artifact_repository_registry import get_artifact_repository

from mlflow_oidc_auth.logger import get_logger

logger = get_logger()


def delete_run_artifacts(artifact_uri: str) -> None:
    """Delete a run's artifacts, handling the mlflow-artifacts proxy case.

    Raises whatever the artifact repository raises. Callers decide whether to
    swallow failures.
    """
    from mlflow.server.handlers import (
        _get_artifact_repo_mlflow_artifacts,
        _get_proxied_run_artifact_destination_path,
        _get_workspace_scoped_repo_path_if_enabled,
        _is_servable_proxied_run_artifact_root,
    )

    if _is_servable_proxied_run_artifact_root(artifact_uri):
        artifact_repo = _get_artifact_repo_mlflow_artifacts()
        artifact_path = _get_proxied_run_artifact_destination_path(artifact_uri)
        artifact_path = _get_workspace_scoped_repo_path_if_enabled(artifact_path)
        artifact_repo.delete_artifacts(artifact_path)
    else:
        artifact_repo = get_artifact_repository(artifact_uri)
        artifact_repo.delete_artifacts()


def hard_delete_run(run_id: str, artifact_uri: str, store: Any) -> None:
    """Delete a run's artifacts (best-effort) then hard-delete the run row.

    Artifact deletion failures are logged but do not prevent the row removal,
    matching the behavior of the admin trash cleanup endpoint.
    """
    try:
        delete_run_artifacts(artifact_uri)
    except InvalidUrlException as e:
        logger.warning(f"Could not delete artifacts for run {run_id}: {e}")
    except Exception as e:
        logger.warning(f"Error deleting artifacts for run {run_id}: {e}")

    store._hard_delete_run(run_id)


def hard_delete_experiment_with_runs(experiment_id: str, store: Any) -> None:
    """Hard-delete every soft-deleted run in an experiment, then the experiment itself."""
    deleted_runs = store.search_runs(
        experiment_ids=[experiment_id],
        filter_string="",
        run_view_type=ViewType.DELETED_ONLY,
    )
    for run in deleted_runs:
        hard_delete_run(run.info.run_id, run.info.artifact_uri, store)

    store._hard_delete_experiment(experiment_id)