"""Helpers for permanently deleting soft-deleted MLflow runs and experiments.

Used by the quota retention sweep (``utils.quota.cleanup_trash``) and, for artifact deletion,
by the admin trash cleanup endpoint (``routers.trash``), so both follow the same rules:

* a run whose artifacts could not be deleted is kept, so its files are never orphaned and the
  next sweep retries (a malformed artifact URI names no storage to act on, so that run is
  still deleted, as ``mlflow gc`` does);
* an experiment is hard-deleted only once no run of any lifecycle stage remains in it, because
  MLflow cascades an experiment's hard delete onto its runs;
* every page of a store search is read;
* an artifact URI that resolves to a storage root rather than a run's own directory is refused,
  so one bad run can never delete every other run's artifacts;
* a proxied ``mlflow-artifacts:`` URI this server cannot resolve (it is not serving artifacts,
  or has no ``--artifacts-destination``) is refused rather than handed to a repository that
  would resolve it somewhere else.

Artifact paths are workspace-scoped through MLflow's own helper, so the caller must run inside
the experiment's workspace context.
"""

import os
import posixpath
import urllib.parse
from typing import Any, Callable, List, Optional

from mlflow.entities import ViewType
from mlflow.exceptions import InvalidUrlException, MlflowException
from mlflow.protos.databricks_pb2 import INVALID_PARAMETER_VALUE
from mlflow.store.artifact.artifact_repository_registry import get_artifact_repository

from mlflow_oidc_auth.logger import get_logger

logger = get_logger()


def fetch_all_pages(fetch_page: Callable[[Optional[str]], Any]) -> List[Any]:
    """Collect every page of a paged MLflow search.

    Parameters:
        fetch_page: Returns the page for a page token (None for the first page).

    Returns:
        The items of every page, in order.

    Raises:
        MlflowException: When the store repeats a page token, since a partial list must never be
            taken for the whole. Errors from ``fetch_page`` propagate unchanged.
    """
    items: List[Any] = []
    seen_tokens = set()
    token = None
    while True:
        page = fetch_page(token)
        items.extend(page)
        token = getattr(page, "token", None)
        if not isinstance(token, str) or not token:
            return items
        if token in seen_tokens:
            raise MlflowException("The store repeated a page token", error_code=INVALID_PARAMETER_VALUE)
        seen_tokens.add(token)


def _refuse_root(path: Optional[str], artifact_uri: str) -> None:
    """Raise if ``path`` names no directory below a storage root."""
    if not posixpath.normpath("/" + (path or "")).strip("/"):
        raise MlflowException(
            f"Refusing to delete artifacts at '{artifact_uri}': it resolves to a storage root, not a run's own directory.",
            error_code=INVALID_PARAMETER_VALUE,
        )


def delete_run_artifacts(artifact_uri: str) -> None:
    """Delete a run's artifacts, handling the mlflow-artifacts proxy case.

    Parameters:
        artifact_uri: The run's artifact root URI, as the tracking store returns it.

    Raises:
        MlflowException: If the URI resolves to a storage root rather than a run's directory, or
            is a proxied ``mlflow-artifacts:`` URI this server cannot resolve.
        Anything the artifact repository raises. Callers decide what a failure means.
    """
    from mlflow.server import ARTIFACTS_DESTINATION_ENV_VAR
    from mlflow.server.handlers import (
        _get_artifact_repo_mlflow_artifacts,
        _get_proxied_run_artifact_destination_path,
        _get_workspace_scoped_repo_path_if_enabled,
        _is_servable_proxied_run_artifact_root,
    )

    _refuse_root(urllib.parse.urlparse(artifact_uri).path, artifact_uri)

    proxied = _is_servable_proxied_run_artifact_root(artifact_uri)
    if urllib.parse.urlparse(artifact_uri).scheme == "mlflow-artifacts" and not (proxied and os.environ.get(ARTIFACTS_DESTINATION_ENV_VAR)):
        raise MlflowException(
            f"Cannot resolve proxied artifact URI '{artifact_uri}': this server is not serving artifacts from an --artifacts-destination.",
            error_code=INVALID_PARAMETER_VALUE,
        )

    if proxied:
        artifact_path = _get_proxied_run_artifact_destination_path(artifact_uri)
        # An http(s) proxy URI can carry a path that is only the artifacts route itself.
        _refuse_root(artifact_path, artifact_uri)
        artifact_repo = _get_artifact_repo_mlflow_artifacts()
        artifact_repo.delete_artifacts(_get_workspace_scoped_repo_path_if_enabled(artifact_path))
    else:
        get_artifact_repository(artifact_uri).delete_artifacts()


def hard_delete_run(run_id: str, artifact_uri: str, store: Any) -> bool:
    """Delete a run's artifacts, then hard-delete the run row.

    Parameters:
        run_id: The soft-deleted run.
        artifact_uri: The run's artifact root URI.
        store: The tracking store.

    Returns:
        True if the run was hard-deleted. False if its artifacts could not be deleted, in which
        case the run is kept so that its files are not orphaned.

    Raises:
        Anything ``store._hard_delete_run`` raises.
    """
    try:
        delete_run_artifacts(artifact_uri)
    except InvalidUrlException as e:
        # The URI names no storage location to act on; nothing can be orphaned.
        logger.warning(f"Could not delete artifacts for run {run_id}: {e}")
    except Exception as e:
        logger.error(f"Keeping run {run_id}: its artifacts could not be deleted: {e}")
        return False

    store._hard_delete_run(run_id)
    return True


def hard_delete_experiment_with_runs(experiment_id: str, store: Any) -> bool:
    """Hard-delete every soft-deleted run in an experiment, then the experiment if it is empty.

    Parameters:
        experiment_id: The soft-deleted experiment.
        store: The tracking store.

    Returns:
        True if the experiment was hard-deleted. False if a run remains in it (kept because its
        artifacts could not be deleted, or not deleted at all), since hard-deleting the
        experiment would cascade onto that run.

    Raises:
        Anything the store raises while searching or deleting. The experiment is then kept.
    """
    deleted_runs = fetch_all_pages(
        lambda token: store.search_runs(
            experiment_ids=[experiment_id],
            filter_string="",
            run_view_type=ViewType.DELETED_ONLY,
            page_token=token,
        )
    )
    for run in deleted_runs:
        hard_delete_run(run.info.run_id, run.info.artifact_uri, store)

    remaining = store.search_runs(
        experiment_ids=[experiment_id],
        filter_string="",
        run_view_type=ViewType.ALL,
        max_results=1,
    )
    if remaining:
        logger.warning(f"Keeping experiment {experiment_id}: run(s) remain in it")
        return False

    store._hard_delete_experiment(experiment_id)
    return True
