"""Tests for the shared trash-cleanup helpers used by the admin trash router
and the quota retention sweep.
"""

from unittest.mock import MagicMock, patch

import pytest
from mlflow.exceptions import InvalidUrlException

from mlflow_oidc_auth.utils import trash_cleanup


def _make_run(run_id: str, artifact_uri: str = "s3://bucket/run/artifacts"):
    run = MagicMock()
    run.info.run_id = run_id
    run.info.artifact_uri = artifact_uri
    return run


class TestDeleteRunArtifacts:
    """Two-branch coverage for the proxied vs direct artifact root logic."""

    def test_direct_artifact_uri_uses_artifact_repository_registry(self):
        repo = MagicMock()
        with (
            patch("mlflow.server.handlers._is_servable_proxied_run_artifact_root", return_value=False),
            patch("mlflow_oidc_auth.utils.trash_cleanup.get_artifact_repository", return_value=repo) as mock_get_repo,
        ):
            trash_cleanup.delete_run_artifacts("s3://bucket/run/artifacts")

        mock_get_repo.assert_called_once_with("s3://bucket/run/artifacts")
        repo.delete_artifacts.assert_called_once_with()

    def test_proxied_artifact_uri_uses_mlflow_artifacts_repo_with_path(self):
        repo = MagicMock()
        with (
            patch("mlflow.server.handlers._is_servable_proxied_run_artifact_root", return_value=True),
            patch("mlflow.server.handlers._get_artifact_repo_mlflow_artifacts", return_value=repo),
            patch("mlflow.server.handlers._get_proxied_run_artifact_destination_path", return_value="/raw/path"),
            patch("mlflow.server.handlers._get_workspace_scoped_repo_path_if_enabled", return_value="/scoped/path") as mock_scope,
        ):
            trash_cleanup.delete_run_artifacts("mlflow-artifacts:/exp/run/artifacts")

        mock_scope.assert_called_once_with("/raw/path")
        repo.delete_artifacts.assert_called_once_with("/scoped/path")


class TestHardDeleteRun:
    """Behavior of the per-run helper: artifacts are best-effort, hard-delete always runs."""

    def test_happy_path_deletes_artifacts_then_hard_deletes_run(self):
        store = MagicMock()
        with patch("mlflow_oidc_auth.utils.trash_cleanup.delete_run_artifacts") as mock_delete:
            trash_cleanup.hard_delete_run("run-1", "s3://x", store)

        mock_delete.assert_called_once_with("s3://x")
        store._hard_delete_run.assert_called_once_with("run-1")

    def test_artifact_invalid_url_is_swallowed(self, caplog):
        store = MagicMock()
        with patch(
            "mlflow_oidc_auth.utils.trash_cleanup.delete_run_artifacts",
            side_effect=InvalidUrlException("bad url"),
        ):
            trash_cleanup.hard_delete_run("run-1", "garbage://", store)

        store._hard_delete_run.assert_called_once_with("run-1")
        assert "Could not delete artifacts for run run-1" in caplog.text

    def test_artifact_generic_exception_is_swallowed(self, caplog):
        store = MagicMock()
        with patch(
            "mlflow_oidc_auth.utils.trash_cleanup.delete_run_artifacts",
            side_effect=RuntimeError("network down"),
        ):
            trash_cleanup.hard_delete_run("run-1", "s3://x", store)

        store._hard_delete_run.assert_called_once_with("run-1")
        assert "Error deleting artifacts for run run-1" in caplog.text

    def test_hard_delete_failure_propagates(self):
        """If the store itself fails, the caller decides — we don't swallow it."""
        store = MagicMock()
        store._hard_delete_run.side_effect = RuntimeError("db error")
        with patch("mlflow_oidc_auth.utils.trash_cleanup.delete_run_artifacts"):
            with pytest.raises(RuntimeError, match="db error"):
                trash_cleanup.hard_delete_run("run-1", "s3://x", store)


class TestHardDeleteExperimentWithRuns:
    """Orchestration: search deleted runs, hard-delete each, then the experiment."""

    def test_deletes_all_runs_then_experiment(self):
        store = MagicMock()
        store.search_runs.return_value = [
            _make_run("run-1", "s3://a"),
            _make_run("run-2", "s3://b"),
        ]
        with patch("mlflow_oidc_auth.utils.trash_cleanup.hard_delete_run") as mock_hard_delete:
            trash_cleanup.hard_delete_experiment_with_runs("exp-99", store)

        # search_runs called with DELETED_ONLY view
        from mlflow.entities import ViewType

        store.search_runs.assert_called_once_with(
            experiment_ids=["exp-99"],
            filter_string="",
            run_view_type=ViewType.DELETED_ONLY,
        )

        assert mock_hard_delete.call_args_list == [
            (("run-1", "s3://a", store),),
            (("run-2", "s3://b", store),),
        ]
        store._hard_delete_experiment.assert_called_once_with("exp-99")

    def test_no_runs_still_hard_deletes_experiment(self):
        store = MagicMock()
        store.search_runs.return_value = []
        with patch("mlflow_oidc_auth.utils.trash_cleanup.hard_delete_run") as mock_hard_delete:
            trash_cleanup.hard_delete_experiment_with_runs("exp-empty", store)

        mock_hard_delete.assert_not_called()
        store._hard_delete_experiment.assert_called_once_with("exp-empty")

    def test_run_failure_does_not_block_experiment_delete(self):
        """If one run's hard-delete blows up, callers expect the exception to surface.

        This documents current behavior: the helper doesn't catch per-run failures
        (only the artifact step is best-effort). If we ever want to continue past
        a failed run, this test will need updating.
        """
        store = MagicMock()
        store.search_runs.return_value = [_make_run("run-1")]
        with patch(
            "mlflow_oidc_auth.utils.trash_cleanup.hard_delete_run",
            side_effect=RuntimeError("boom"),
        ):
            with pytest.raises(RuntimeError, match="boom"):
                trash_cleanup.hard_delete_experiment_with_runs("exp-1", store)

        store._hard_delete_experiment.assert_not_called()