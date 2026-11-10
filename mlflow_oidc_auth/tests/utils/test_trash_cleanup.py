"""Tests for the trash-cleanup helpers used by the quota retention sweep.

They pin the rules shared with the admin trash cleanup endpoint: a run whose artifacts could
not be deleted is kept, an experiment that still holds a run is kept, every page is read, and
an artifact URI that resolves to a storage root is refused.
"""

from unittest.mock import MagicMock, patch

import pytest
from mlflow.entities import ViewType
from mlflow.exceptions import InvalidUrlException, MlflowException
from mlflow.store.entities.paged_list import PagedList

from mlflow_oidc_auth.utils import trash_cleanup


def _make_run(run_id: str, artifact_uri: str = "s3://bucket/run/artifacts"):
    run = MagicMock()
    run.info.run_id = run_id
    run.info.artifact_uri = artifact_uri
    return run


def _store(deleted_pages, remaining=()):
    """A tracking store whose DELETED_ONLY search returns ``deleted_pages`` and ALL returns ``remaining``."""
    store = MagicMock()
    pages = iter(deleted_pages)

    def search_runs(**kwargs):
        if kwargs["run_view_type"] == ViewType.DELETED_ONLY:
            return next(pages)
        return list(remaining)

    store.search_runs.side_effect = search_runs
    return store


class TestFetchAllPages:
    def test_follows_page_tokens_to_the_end(self):
        pages = {None: PagedList([1, 2], "t1"), "t1": PagedList([3], "t2"), "t2": PagedList([4], None)}

        assert trash_cleanup.fetch_all_pages(lambda token: pages[token]) == [1, 2, 3, 4]

    def test_a_plain_list_is_one_page(self):
        assert trash_cleanup.fetch_all_pages(lambda token: [1, 2]) == [1, 2]

    def test_a_repeated_token_raises_instead_of_looping_or_truncating(self):
        pages = {None: PagedList([1], "t1"), "t1": PagedList([2], "t1")}

        with pytest.raises(MlflowException, match="repeated a page token"):
            trash_cleanup.fetch_all_pages(lambda token: pages[token])


class TestDeleteRunArtifacts:
    def test_direct_artifact_uri_uses_artifact_repository_registry(self):
        repo = MagicMock()
        with (
            patch("mlflow.server.handlers._is_servable_proxied_run_artifact_root", return_value=False),
            patch("mlflow_oidc_auth.utils.trash_cleanup.get_artifact_repository", return_value=repo) as mock_get_repo,
        ):
            trash_cleanup.delete_run_artifacts("s3://bucket/run/artifacts")

        mock_get_repo.assert_called_once_with("s3://bucket/run/artifacts")
        repo.delete_artifacts.assert_called_once_with()

    def test_proxied_artifact_uri_uses_mlflow_artifacts_repo_with_workspace_scoped_path(self, monkeypatch):
        from mlflow.server import ARTIFACTS_DESTINATION_ENV_VAR

        monkeypatch.setenv(ARTIFACTS_DESTINATION_ENV_VAR, "s3://bucket/dest")
        repo = MagicMock()
        with (
            patch("mlflow.server.handlers._is_servable_proxied_run_artifact_root", return_value=True),
            patch("mlflow.server.handlers._get_artifact_repo_mlflow_artifacts", return_value=repo),
            patch("mlflow.server.handlers._get_proxied_run_artifact_destination_path", return_value="raw/path"),
            patch("mlflow.server.handlers._get_workspace_scoped_repo_path_if_enabled", return_value="scoped/path") as mock_scope,
        ):
            trash_cleanup.delete_run_artifacts("mlflow-artifacts:/exp/run/artifacts")

        mock_scope.assert_called_once_with("raw/path")
        repo.delete_artifacts.assert_called_once_with("scoped/path")

    @pytest.mark.parametrize(
        "artifact_uri",
        [
            "mlflow-artifacts:/",
            "mlflow-artifacts://host",
            "mlflow-artifacts://host/",
            "mlflow-artifacts:/./",
            "mlflow-artifacts:/a/..",
            "s3://bucket",
            "s3://bucket/",
            "file:///",
        ],
    )
    def test_a_uri_naming_a_storage_root_is_refused(self, artifact_uri):
        proxied_repo, direct_repo = MagicMock(), MagicMock()
        with (
            patch("mlflow.server.handlers._is_servable_proxied_run_artifact_root", return_value=artifact_uri.startswith("mlflow-artifacts")),
            patch("mlflow.server.handlers._get_artifact_repo_mlflow_artifacts", return_value=proxied_repo),
            patch("mlflow_oidc_auth.utils.trash_cleanup.get_artifact_repository", return_value=direct_repo),
        ):
            with pytest.raises(MlflowException, match="storage root"):
                trash_cleanup.delete_run_artifacts(artifact_uri)

        proxied_repo.delete_artifacts.assert_not_called()
        direct_repo.delete_artifacts.assert_not_called()

    def test_an_http_proxy_uri_with_only_the_route_is_refused(self):
        repo = MagicMock()
        with (
            patch("mlflow.server.handlers._is_servable_proxied_run_artifact_root", return_value=True),
            patch("mlflow.server.handlers._get_artifact_repo_mlflow_artifacts", return_value=repo),
        ):
            with pytest.raises(MlflowException, match="storage root"):
                trash_cleanup.delete_run_artifacts("https://mlflow.example/api/2.0/mlflow-artifacts/artifacts/")

        repo.delete_artifacts.assert_not_called()


class TestUnresolvableProxiedUri:
    """A proxied URI this server cannot map to its own storage is refused, never guessed."""

    @pytest.mark.parametrize("serving,destination", [(False, "s3://bucket/dest"), (True, None), (False, None)])
    def test_is_refused(self, serving, destination, monkeypatch):
        from mlflow.server import ARTIFACTS_DESTINATION_ENV_VAR, SERVE_ARTIFACTS_ENV_VAR

        monkeypatch.setenv(SERVE_ARTIFACTS_ENV_VAR, "true" if serving else "false")
        if destination:
            monkeypatch.setenv(ARTIFACTS_DESTINATION_ENV_VAR, destination)
        else:
            monkeypatch.delenv(ARTIFACTS_DESTINATION_ENV_VAR, raising=False)
        proxied_repo, direct_repo = MagicMock(), MagicMock()
        with (
            patch("mlflow.server.handlers._get_artifact_repo_mlflow_artifacts", return_value=proxied_repo),
            patch("mlflow_oidc_auth.utils.trash_cleanup.get_artifact_repository", return_value=direct_repo),
        ):
            with pytest.raises(MlflowException, match="Cannot resolve proxied artifact URI"):
                trash_cleanup.delete_run_artifacts("mlflow-artifacts:/exp-1/run-1/artifacts")

        proxied_repo.delete_artifacts.assert_not_called()
        direct_repo.delete_artifacts.assert_not_called()


class TestHardDeleteRun:
    def test_deletes_artifacts_then_the_run(self):
        store = MagicMock()
        with patch("mlflow_oidc_auth.utils.trash_cleanup.delete_run_artifacts") as mock_delete:
            assert trash_cleanup.hard_delete_run("run-1", "s3://x/run-1", store) is True

        mock_delete.assert_called_once_with("s3://x/run-1")
        store._hard_delete_run.assert_called_once_with("run-1")

    def test_a_malformed_uri_still_deletes_the_run(self, caplog):
        # There is no storage location behind it, so nothing can be orphaned.
        store = MagicMock()
        with patch("mlflow_oidc_auth.utils.trash_cleanup.delete_run_artifacts", side_effect=InvalidUrlException("bad url")):
            assert trash_cleanup.hard_delete_run("run-1", "garbage://", store) is True

        store._hard_delete_run.assert_called_once_with("run-1")
        assert "Could not delete artifacts for run run-1" in caplog.text

    @pytest.mark.parametrize("error", [RuntimeError("network down"), MlflowException("storage root")])
    def test_a_failed_artifact_delete_keeps_the_run(self, error, caplog):
        store = MagicMock()
        with patch("mlflow_oidc_auth.utils.trash_cleanup.delete_run_artifacts", side_effect=error):
            assert trash_cleanup.hard_delete_run("run-1", "s3://x/run-1", store) is False

        store._hard_delete_run.assert_not_called()
        assert "Keeping run run-1" in caplog.text

    def test_a_store_failure_propagates(self):
        store = MagicMock()
        store._hard_delete_run.side_effect = RuntimeError("db error")
        with patch("mlflow_oidc_auth.utils.trash_cleanup.delete_run_artifacts"):
            with pytest.raises(RuntimeError, match="db error"):
                trash_cleanup.hard_delete_run("run-1", "s3://x/run-1", store)


class TestHardDeleteExperimentWithRuns:
    def test_deletes_runs_on_every_page_then_the_empty_experiment(self):
        store = _store([PagedList([_make_run("run-1", "s3://a/1")], "t1"), PagedList([_make_run("run-2", "s3://b/2")], None)])
        with patch("mlflow_oidc_auth.utils.trash_cleanup.hard_delete_run") as mock_hard_delete:
            assert trash_cleanup.hard_delete_experiment_with_runs("exp-99", store) is True

        assert mock_hard_delete.call_args_list == [(("run-1", "s3://a/1", store),), (("run-2", "s3://b/2", store),)]
        searches = [c.kwargs for c in store.search_runs.call_args_list]
        assert [s.get("page_token") for s in searches[:2]] == [None, "t1"]
        assert searches[2] == {"experiment_ids": ["exp-99"], "filter_string": "", "run_view_type": ViewType.ALL, "max_results": 1}
        store._hard_delete_experiment.assert_called_once_with("exp-99")

    def test_no_runs_still_deletes_the_experiment(self):
        store = _store([[]])
        with patch("mlflow_oidc_auth.utils.trash_cleanup.hard_delete_run") as mock_hard_delete:
            assert trash_cleanup.hard_delete_experiment_with_runs("exp-empty", store) is True

        mock_hard_delete.assert_not_called()
        store._hard_delete_experiment.assert_called_once_with("exp-empty")

    def test_a_remaining_run_keeps_the_experiment(self, caplog):
        # Hard-deleting the experiment would cascade onto the run that is still there.
        store = _store([[_make_run("run-1")]], remaining=[_make_run("run-1")])
        with patch("mlflow_oidc_auth.utils.trash_cleanup.hard_delete_run", return_value=False):
            assert trash_cleanup.hard_delete_experiment_with_runs("exp-1", store) is False

        store._hard_delete_experiment.assert_not_called()
        assert "Keeping experiment exp-1" in caplog.text

    def test_a_run_failure_propagates_and_keeps_the_experiment(self):
        store = _store([[_make_run("run-1")]])
        with patch("mlflow_oidc_auth.utils.trash_cleanup.hard_delete_run", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                trash_cleanup.hard_delete_experiment_with_runs("exp-1", store)

        store._hard_delete_experiment.assert_not_called()

    def test_a_failed_remaining_run_check_propagates_and_keeps_the_experiment(self):
        store = MagicMock()
        store.search_runs.side_effect = [[], RuntimeError("db down")]
        with pytest.raises(RuntimeError, match="db down"):
            trash_cleanup.hard_delete_experiment_with_runs("exp-1", store)

        store._hard_delete_experiment.assert_not_called()


class TestAgainstARealStore:
    """The same rules against MLflow's SQL store and local artifact storage."""

    @pytest.fixture
    def tracking(self, tmp_path):
        from mlflow.store.tracking.sqlalchemy_store import SqlAlchemyStore

        store = SqlAlchemyStore(f"sqlite:///{tmp_path / 'mlflow.db'}", (tmp_path / "artifacts").as_uri())
        experiment_id = store.create_experiment("exp")
        runs = [store.create_run(experiment_id, "alice", 0, [], "r") for _ in range(2)]
        for run in runs:
            path = tmp_path / "artifacts" / experiment_id / run.info.run_id / "artifacts"
            path.mkdir(parents=True, exist_ok=True)
            (path / "model.bin").write_text("x")
        store.delete_experiment(experiment_id)
        for run in runs:
            store.delete_run(run.info.run_id)
        yield store, experiment_id, runs, tmp_path
        store.engine.dispose()

    def test_deletes_runs_artifacts_and_experiment(self, tracking):
        store, experiment_id, runs, tmp_path = tracking

        assert trash_cleanup.hard_delete_experiment_with_runs(experiment_id, store) is True

        assert store.search_runs([experiment_id], "", ViewType.ALL) == []
        assert not any((tmp_path / "artifacts" / experiment_id / r.info.run_id).joinpath("artifacts", "model.bin").exists() for r in runs)
        with pytest.raises(MlflowException):
            store.get_experiment(experiment_id)

    def test_a_run_whose_artifacts_fail_survives_with_its_experiment(self, tracking):
        store, experiment_id, runs, tmp_path = tracking
        kept = runs[0].info.run_id
        real_delete = trash_cleanup.delete_run_artifacts

        def flaky(artifact_uri):
            if kept in artifact_uri:
                raise OSError("storage unavailable")
            real_delete(artifact_uri)

        with patch("mlflow_oidc_auth.utils.trash_cleanup.delete_run_artifacts", side_effect=flaky):
            assert trash_cleanup.hard_delete_experiment_with_runs(experiment_id, store) is False

        assert [r.info.run_id for r in store.search_runs([experiment_id], "", ViewType.ALL)] == [kept]
        assert (tmp_path / "artifacts" / experiment_id / kept / "artifacts" / "model.bin").exists()
        assert store.get_experiment(experiment_id).experiment_id == experiment_id
