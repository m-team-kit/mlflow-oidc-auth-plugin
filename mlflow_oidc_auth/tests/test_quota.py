"""Unit tests for the storage quota system."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from mlflow.exceptions import MlflowException


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_quota(quota_bytes=None, used_bytes=0, soft_cap_fraction=0.9, hard_blocked=False, soft_notified_at=None):
    q = MagicMock()
    q.quota_bytes = quota_bytes
    q.used_bytes = used_bytes
    q.soft_cap_fraction = soft_cap_fraction
    q.hard_blocked = hard_blocked
    q.soft_notified_at = soft_notified_at
    return q


# ---------------------------------------------------------------------------
# enforce_quota
# ---------------------------------------------------------------------------


class TestEnforceQuota:
    def test_no_quota_row_no_global_default_allows(self):
        """When there is no quota row and no global default, request should pass."""
        with patch("mlflow_oidc_auth.utils.quota.store") as mock_store, patch("mlflow_oidc_auth.utils.quota.config") as mock_config:
            mock_store.get_user_quota.return_value = None
            mock_config.QUOTA_DEFAULT_BYTES = None

            from mlflow_oidc_auth.utils.quota import enforce_quota

            enforce_quota("alice")  # Should not raise

    def test_no_quota_row_with_global_default_unlimited(self):
        """Global default of None means unlimited."""
        with patch("mlflow_oidc_auth.utils.quota.store") as mock_store, patch("mlflow_oidc_auth.utils.quota.config") as mock_config:
            mock_store.get_user_quota.return_value = None
            mock_config.QUOTA_DEFAULT_BYTES = None

            from mlflow_oidc_auth.utils.quota import enforce_quota

            enforce_quota("bob")  # Should not raise

    def test_within_quota_allows(self):
        """Request within quota should pass."""
        with patch("mlflow_oidc_auth.utils.quota.store") as mock_store, patch("mlflow_oidc_auth.utils.quota.config") as mock_config:
            mock_store.get_user_quota.return_value = _make_quota(quota_bytes=1_000_000, used_bytes=500_000)
            mock_config.QUOTA_DEFAULT_BYTES = None

            from mlflow_oidc_auth.utils.quota import enforce_quota

            enforce_quota("alice")  # Should not raise

    def test_exactly_at_quota_raises(self):
        """Request at exactly quota_bytes should be blocked."""
        from mlflow.exceptions import MlflowException

        with patch("mlflow_oidc_auth.utils.quota.store") as mock_store, patch("mlflow_oidc_auth.utils.quota.config") as mock_config:
            mock_store.get_user_quota.return_value = _make_quota(quota_bytes=1_000_000, used_bytes=1_000_000)
            mock_config.QUOTA_DEFAULT_BYTES = None

            from mlflow_oidc_auth.utils.quota import enforce_quota

            with pytest.raises(MlflowException, match="quota exceeded|Storage quota"):
                enforce_quota("alice")

    def test_over_quota_raises(self):
        """Request over quota should be blocked."""
        from mlflow.exceptions import MlflowException

        with patch("mlflow_oidc_auth.utils.quota.store") as mock_store, patch("mlflow_oidc_auth.utils.quota.config") as mock_config:
            mock_store.get_user_quota.return_value = _make_quota(quota_bytes=1_000_000, used_bytes=2_000_000)
            mock_config.QUOTA_DEFAULT_BYTES = None

            from mlflow_oidc_auth.utils.quota import enforce_quota

            with pytest.raises(MlflowException):
                enforce_quota("alice")

    def test_null_quota_bytes_allows(self):
        """quota_bytes = None on the row means unlimited."""
        with patch("mlflow_oidc_auth.utils.quota.store") as mock_store, patch("mlflow_oidc_auth.utils.quota.config") as mock_config:
            mock_store.get_user_quota.return_value = _make_quota(quota_bytes=None, used_bytes=999_999_999)
            mock_config.QUOTA_DEFAULT_BYTES = None

            from mlflow_oidc_auth.utils.quota import enforce_quota

            enforce_quota("alice")  # Should not raise


# ---------------------------------------------------------------------------
# Reconciliation
# ---------------------------------------------------------------------------


class TestReconcileUserQuota:
    def _make_store(self, username, quota, owner_experiment_ids=None):
        mock_store = MagicMock()
        mock_store.get_user_quota.return_value = quota
        if owner_experiment_ids is not None:
            perm_mocks = []
            for exp_id in owner_experiment_ids:
                p = MagicMock()
                p.experiment_id = exp_id
                p.permission = "MANAGE"
                perm_mocks.append(p)
            mock_store.list_experiment_permissions.return_value = perm_mocks
        return mock_store

    def test_no_quota_row_creates_row_with_used_bytes(self):
        """reconcile_user_quota should create a quota row and populate used_bytes when none exists."""
        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota._calculate_used_bytes", return_value=(1_000_000, {})),
        ):
            mock_store.get_user_quota.return_value = None

            from mlflow_oidc_auth.utils.quota import reconcile_user_quota

            reconcile_user_quota("alice")
            mock_store.set_user_quota.assert_called_once_with("alice", None, None)
            mock_store.update_user_quota_used_bytes.assert_called_once_with("alice", 1_000_000)

    def test_reconcile_aggregates_artifact_sizes(self):
        """Reconciliation should sum artifact sizes and update used_bytes."""
        quota = _make_quota(quota_bytes=100_000_000, used_bytes=0)

        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow_oidc_auth.utils.quota._calculate_used_bytes", return_value=(5_000_000, {})) as mock_calc,
            patch("mlflow_oidc_auth.utils.email.send_soft_cap_warning") as mock_email,
        ):
            mock_store.get_user_quota.return_value = quota
            mock_config.QUOTA_DEFAULT_BYTES = None

            from mlflow_oidc_auth.utils.quota import reconcile_user_quota

            reconcile_user_quota("alice")

            mock_calc.assert_called_once_with("alice")
            mock_store.update_user_quota_used_bytes.assert_called_once_with("alice", 5_000_000)
            mock_email.assert_not_called()

    def test_reconcile_sends_soft_cap_email(self):
        """Reconciliation should send a warning when soft cap is crossed."""
        quota = _make_quota(quota_bytes=10_000_000, used_bytes=0, soft_cap_fraction=0.9, soft_notified_at=None)

        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow_oidc_auth.utils.quota._calculate_used_bytes", return_value=(9_500_000, {})),
            patch("mlflow_oidc_auth.utils.email.send_soft_cap_warning") as mock_email,
        ):
            mock_store.get_user_quota.return_value = quota
            mock_config.QUOTA_DEFAULT_BYTES = None

            from mlflow_oidc_auth.utils.quota import reconcile_user_quota

            reconcile_user_quota("alice")
            mock_email.assert_called_once()


# ---------------------------------------------------------------------------
# Ownership transfer
# ---------------------------------------------------------------------------


class TestOwnershipTransfer:
    def test_get_experiment_owner_returns_manage_holder(self):
        """get_experiment_owner should return the username of the MANAGE holder."""
        perm = MagicMock()
        perm.permission = "MANAGE"
        perm.user_id = 42

        user = MagicMock()
        user.username = "alice"

        with patch("mlflow_oidc_auth.utils.quota.store") as mock_store:
            mock_store.list_experiment_permissions_for_experiment.return_value = [perm]
            mock_store.get_user_by_id.return_value = user

            from mlflow_oidc_auth.utils.quota import get_experiment_owner

            assert get_experiment_owner("exp-123") == "alice"

    def test_get_experiment_owner_returns_none_when_no_manage(self):
        """get_experiment_owner should return None when no MANAGE row exists."""
        perm = MagicMock()
        perm.permission = "EDIT"
        perm.user_id = 42

        with patch("mlflow_oidc_auth.utils.quota.store") as mock_store:
            mock_store.list_experiment_permissions_for_experiment.return_value = [perm]

            from mlflow_oidc_auth.utils.quota import get_experiment_owner

            assert get_experiment_owner("exp-123") is None


# ---------------------------------------------------------------------------
# reconcile_user_quota — missing branches
# ---------------------------------------------------------------------------


class TestReconcileUserQuotaThresholds:
    """Cover the hard-cap, soft-reset, and unlimited-cleanup branches."""

    def test_hard_cap_blocks_and_notifies_when_not_previously_blocked(self):
        """At or above the hard cap, the user is blocked and notified."""
        quota = _make_quota(quota_bytes=1000, hard_blocked=False, soft_notified_at=None)

        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow_oidc_auth.utils.quota._calculate_used_bytes", return_value=(1500, {})),
            patch("mlflow_oidc_auth.utils.email.send_hard_cap_notification", return_value=True) as mock_hard_email,
            patch("mlflow_oidc_auth.utils.email.send_soft_cap_warning") as mock_soft_email,
        ):
            mock_store.get_user_quota.return_value = quota
            mock_config.QUOTA_DEFAULT_BYTES = None

            from mlflow_oidc_auth.utils.quota import reconcile_user_quota

            reconcile_user_quota("alice")

        mock_store.set_quota_hard_blocked.assert_called_once_with("alice", True)
        mock_hard_email.assert_called_once()
        mock_soft_email.assert_not_called()
        mock_store.set_quota_soft_notified_at.assert_called_once()
        # The timestamp argument should be a tz-aware UTC datetime
        _, kwargs_ts = mock_store.set_quota_soft_notified_at.call_args[0]
        assert kwargs_ts.tzinfo is timezone.utc

    def test_hard_cap_suppresses_reminder_within_24h(self):
        """If already notified within 24h, no new email is sent."""
        recent = datetime.now(timezone.utc) - timedelta(hours=1)
        quota = _make_quota(quota_bytes=1000, hard_blocked=True, soft_notified_at=recent)

        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow_oidc_auth.utils.quota._calculate_used_bytes", return_value=(1500, {})),
            patch("mlflow_oidc_auth.utils.email.send_hard_cap_notification") as mock_hard_email,
        ):
            mock_store.get_user_quota.return_value = quota
            mock_config.QUOTA_DEFAULT_BYTES = None

            from mlflow_oidc_auth.utils.quota import reconcile_user_quota

            reconcile_user_quota("alice")

        mock_hard_email.assert_not_called()
        # Already blocked — should NOT toggle hard_blocked again
        mock_store.set_quota_hard_blocked.assert_not_called()

    def test_hard_cap_reminds_again_after_24h(self):
        """Daily reminder fires once 24h has elapsed since the last notification."""
        stale = datetime.now(timezone.utc) - timedelta(hours=25)
        quota = _make_quota(quota_bytes=1000, hard_blocked=True, soft_notified_at=stale)

        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow_oidc_auth.utils.quota._calculate_used_bytes", return_value=(1500, {})),
            patch("mlflow_oidc_auth.utils.email.send_hard_cap_notification", return_value=True) as mock_hard_email,
        ):
            mock_store.get_user_quota.return_value = quota
            mock_config.QUOTA_DEFAULT_BYTES = None

            from mlflow_oidc_auth.utils.quota import reconcile_user_quota

            reconcile_user_quota("alice")

        mock_hard_email.assert_called_once()
        mock_store.set_quota_soft_notified_at.assert_called_once()

    def test_drop_below_soft_cap_resets_notification_timestamp(self):
        """When usage drops back below the soft cap, the warning timestamp clears."""
        old_notification = datetime.now(timezone.utc) - timedelta(days=2)
        quota = _make_quota(
            quota_bytes=1000,
            soft_cap_fraction=0.9,
            hard_blocked=False,
            soft_notified_at=old_notification,
        )

        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow_oidc_auth.utils.quota._calculate_used_bytes", return_value=(500, {})),  # 50%, well below
            patch("mlflow_oidc_auth.utils.email.send_soft_cap_warning") as mock_soft_email,
        ):
            mock_store.get_user_quota.return_value = quota
            mock_config.QUOTA_DEFAULT_BYTES = None

            from mlflow_oidc_auth.utils.quota import reconcile_user_quota

            reconcile_user_quota("alice")

        mock_soft_email.assert_not_called()
        mock_store.set_quota_soft_notified_at.assert_called_once_with("alice", None)

    def test_drop_below_hard_cap_clears_hard_blocked(self):
        """A user previously hard-blocked is unblocked once usage drops."""
        quota = _make_quota(quota_bytes=1000, hard_blocked=True, soft_notified_at=None)

        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow_oidc_auth.utils.quota._calculate_used_bytes", return_value=(400, {})),  # below soft cap too
        ):
            mock_store.get_user_quota.return_value = quota
            mock_config.QUOTA_DEFAULT_BYTES = None

            from mlflow_oidc_auth.utils.quota import reconcile_user_quota

            reconcile_user_quota("alice")

        mock_store.set_quota_hard_blocked.assert_called_once_with("alice", False)

    def test_unlimited_quota_clears_stale_enforcement_state(self):
        """When effective quota is None, stale hard_blocked / soft_notified_at are cleared."""
        previously = datetime.now(timezone.utc) - timedelta(hours=2)
        quota = _make_quota(quota_bytes=None, hard_blocked=True, soft_notified_at=previously)

        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow_oidc_auth.utils.quota._calculate_used_bytes") as mock_calc,
        ):
            mock_store.get_user_quota.return_value = quota
            mock_config.QUOTA_DEFAULT_BYTES = None  # No global default → unlimited

            from mlflow_oidc_auth.utils.quota import reconcile_user_quota

            reconcile_user_quota("alice")

        # No artifact recalculation when there's no quota to enforce
        mock_calc.assert_not_called()
        mock_store.set_quota_hard_blocked.assert_called_once_with("alice", False)
        mock_store.set_quota_soft_notified_at.assert_called_once_with("alice", None)
        mock_store.update_user_quota_used_bytes.assert_not_called()


# ---------------------------------------------------------------------------
# _calculate_used_bytes — workspace iteration
# ---------------------------------------------------------------------------


def _make_perm(experiment_id: str, permission: str = "MANAGE"):
    p = MagicMock()
    p.experiment_id = experiment_id
    p.permission = permission
    return p


def _make_run(artifact_uri: str = "s3://bucket/run"):
    run = MagicMock()
    run.info.artifact_uri = artifact_uri
    return run


class TestCalculateUsedBytesWorkspaceIteration:
    """The post-workspace-merge rewrite needs to traverse workspaces correctly."""

    def test_no_owned_experiments_returns_zero(self):
        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow.tracking.MlflowClient") as mock_client_cls,
        ):
            mock_store.list_experiment_permissions.return_value = []
            mock_config.MLFLOW_ENABLE_WORKSPACES = False

            from mlflow_oidc_auth.utils.quota import _calculate_used_bytes

            total, _ = _calculate_used_bytes("alice")
            assert total == 0
            mock_client_cls.return_value.search_runs.assert_not_called()

    def test_workspaces_disabled_single_pass(self):
        """With workspaces off, a single (None) iteration sums all experiments."""
        exp = MagicMock()
        exp.lifecycle_stage = "active"
        exp.artifact_location = "s3://bucket/exp"

        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow.tracking.MlflowClient") as mock_client_cls,
            patch("mlflow_oidc_auth.utils.quota._sum_artifacts", return_value=42),
            patch("mlflow_oidc_auth.utils.quota._get_experiment_size_cache") as mock_cache_fn,
        ):
            mock_store.list_experiment_permissions.return_value = [_make_perm("e1"), _make_perm("e2")]
            mock_store.list_registered_model_permissions.return_value = []
            mock_config.MLFLOW_ENABLE_WORKSPACES = False
            mock_client_cls.return_value.get_experiment.return_value = exp
            mock_cache_fn.return_value.get.return_value = None  # cache miss → compute

            from mlflow_oidc_auth.utils.quota import _calculate_used_bytes

            # 2 experiments × _sum_artifacts returning 42 each
            total, sizes = _calculate_used_bytes("alice")
            assert total == 2 * 42
            assert sizes == {"e1": 42, "e2": 42}

    def test_skips_experiment_in_wrong_workspace_and_finds_it_in_correct_one(self):
        """An experiment that lives in workspace B is skipped in A and counted in B."""
        ws_a = MagicMock(name="ws_a")
        ws_a.name = "ws-a"
        ws_b = MagicMock(name="ws_b")
        ws_b.name = "ws-b"

        exp_b = MagicMock()
        exp_b.lifecycle_stage = "active"
        exp_b.artifact_location = "s3://b"

        client = MagicMock()
        # In ws-a: raise (experiment doesn't exist there). In ws-b: return experiment.
        client.get_experiment.side_effect = [
            MlflowException("not found"),
            exp_b,
        ]

        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow.tracking.MlflowClient", return_value=client),
            patch("mlflow.server.handlers._get_workspace_store") as mock_get_ws_store,
            patch("mlflow.utils.workspace_context.set_server_request_workspace") as mock_set_ws,
            patch("mlflow.utils.workspace_context.clear_server_request_workspace") as mock_clear_ws,
            patch("mlflow_oidc_auth.utils.quota._sum_artifacts", return_value=100),
            patch("mlflow_oidc_auth.utils.quota._get_experiment_size_cache") as mock_cache_fn,
        ):
            mock_store.list_experiment_permissions.return_value = [_make_perm("e1")]
            mock_store.list_registered_model_permissions.return_value = []
            mock_config.MLFLOW_ENABLE_WORKSPACES = True
            mock_get_ws_store.return_value.list_workspaces.return_value = [ws_a, ws_b]
            mock_cache_fn.return_value.get.return_value = None  # cache miss → compute

            from mlflow_oidc_auth.utils.quota import _calculate_used_bytes

            total, sizes = _calculate_used_bytes("alice")
            assert total == 100
            assert sizes == {"e1": 100}

        # Both workspaces were entered; experiment was tried twice
        assert mock_set_ws.call_args_list == [(("ws-a",),), (("ws-b",),)]
        assert mock_clear_ws.call_count == 2
        assert client.get_experiment.call_count == 2

    def test_short_circuits_once_all_experiments_located(self):
        """Once every owned experiment is found, remaining workspaces are skipped."""
        ws_a = MagicMock()
        ws_a.name = "ws-a"
        ws_b = MagicMock()
        ws_b.name = "ws-b"

        exp_a = MagicMock()
        exp_a.lifecycle_stage = "active"
        exp_a.artifact_location = "s3://a"

        client = MagicMock()
        client.get_experiment.return_value = exp_a

        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow.tracking.MlflowClient", return_value=client),
            patch("mlflow.server.handlers._get_workspace_store") as mock_get_ws_store,
            patch("mlflow.utils.workspace_context.set_server_request_workspace") as mock_set_ws,
            patch("mlflow.utils.workspace_context.clear_server_request_workspace"),
            patch("mlflow_oidc_auth.utils.quota._sum_artifacts", return_value=10),
            patch("mlflow_oidc_auth.utils.quota._get_experiment_size_cache") as mock_cache_fn,
        ):
            mock_store.list_experiment_permissions.return_value = [_make_perm("e1")]
            mock_store.list_registered_model_permissions.return_value = []
            mock_config.MLFLOW_ENABLE_WORKSPACES = True
            mock_get_ws_store.return_value.list_workspaces.return_value = [ws_a, ws_b]
            mock_cache_fn.return_value.get.return_value = None  # cache miss → compute

            from mlflow_oidc_auth.utils.quota import _calculate_used_bytes

            total, sizes = _calculate_used_bytes("alice")
            assert total == 10
            assert sizes == {"e1": 10}

        # Found in ws-a → never enters ws-b
        assert mock_set_ws.call_args_list == [(("ws-a",),)]

    def test_experiment_not_in_any_workspace_logs_warning(self, caplog):
        """Experiments missing in every workspace are logged but don't break the sweep."""
        ws_a = MagicMock()
        ws_a.name = "ws-a"
        client = MagicMock()
        client.get_experiment.side_effect = MlflowException("nope")

        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow.tracking.MlflowClient", return_value=client),
            patch("mlflow.server.handlers._get_workspace_store") as mock_get_ws_store,
            patch("mlflow.utils.workspace_context.set_server_request_workspace"),
            patch("mlflow.utils.workspace_context.clear_server_request_workspace"),
            patch("mlflow_oidc_auth.utils.quota._get_experiment_size_cache") as mock_cache_fn,
        ):
            mock_store.list_experiment_permissions.return_value = [_make_perm("e-orphan")]
            mock_store.list_registered_model_permissions.return_value = []
            mock_config.MLFLOW_ENABLE_WORKSPACES = True
            mock_get_ws_store.return_value.list_workspaces.return_value = [ws_a]
            mock_cache_fn.return_value.get.return_value = None  # cache miss → compute

            from mlflow_oidc_auth.utils.quota import _calculate_used_bytes

            total, _ = _calculate_used_bytes("alice")
            assert total == 0

        assert "e-orphan" in caplog.text
        assert "any workspace" in caplog.text

    def test_workspace_enumeration_failure_falls_back_to_single_pass(self, caplog):
        """If listing workspaces fails, fall back to one None-context sweep instead of giving up."""
        exp = MagicMock()
        exp.lifecycle_stage = "active"
        exp.artifact_location = "s3://fallback"

        client = MagicMock()
        client.get_experiment.return_value = exp

        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow.tracking.MlflowClient", return_value=client),
            patch("mlflow.server.handlers._get_workspace_store", side_effect=RuntimeError("ws store down")),
            patch("mlflow.utils.workspace_context.set_server_request_workspace") as mock_set_ws,
            patch("mlflow.utils.workspace_context.clear_server_request_workspace"),
            patch("mlflow_oidc_auth.utils.quota._sum_artifacts", return_value=7),
            patch("mlflow_oidc_auth.utils.quota._get_experiment_size_cache") as mock_cache_fn,
        ):
            mock_store.list_experiment_permissions.return_value = [_make_perm("e1")]
            mock_store.list_registered_model_permissions.return_value = []
            mock_config.MLFLOW_ENABLE_WORKSPACES = True
            mock_cache_fn.return_value.get.return_value = None  # cache miss → compute

            from mlflow_oidc_auth.utils.quota import _calculate_used_bytes

            total, sizes = _calculate_used_bytes("alice")
            assert total == 7
            assert sizes == {"e1": 7}

        # Fallback enters context with None
        mock_set_ws.assert_called_once_with(None)
        assert "Could not enumerate workspaces" in caplog.text

    def test_uses_cached_size_skips_workspace_lookup(self):
        """Experiments with a valid cache entry skip workspace iteration entirely."""
        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow.tracking.MlflowClient") as mock_client_cls,
            patch("mlflow_oidc_auth.utils.quota._sum_artifacts") as mock_sum,
            patch("mlflow_oidc_auth.utils.quota._get_experiment_size_cache") as mock_cache_fn,
        ):
            mock_store.list_experiment_permissions.return_value = [_make_perm("e1"), _make_perm("e2")]
            mock_store.list_registered_model_permissions.return_value = []
            mock_config.MLFLOW_ENABLE_WORKSPACES = False
            cached = {"e1": 100, "e2": 200}
            mock_cache_fn.return_value.get.side_effect = lambda exp_id: cached.get(exp_id)

            from mlflow_oidc_auth.utils.quota import _calculate_used_bytes

            total, sizes = _calculate_used_bytes("alice")

        assert total == 300
        assert sizes == {"e1": 100, "e2": 200}
        mock_sum.assert_not_called()
        mock_client_cls.return_value.get_experiment.assert_not_called()


# ---------------------------------------------------------------------------
# reconcile_all_quotas
# ---------------------------------------------------------------------------


class TestReconcileAllQuotas:
    def test_list_users_failure_returns_single_error(self):
        with patch("mlflow_oidc_auth.utils.quota.store") as mock_store:
            mock_store.list_users.side_effect = RuntimeError("db down")

            from mlflow_oidc_auth.utils.quota import reconcile_all_quotas

            errors = reconcile_all_quotas()

        assert errors is not None
        assert len(errors) == 1
        assert "db down" in errors[0]

    def test_per_user_exception_collected_and_sweep_continues(self):
        """One user's failure must not abort reconciliation for the others."""
        u1, u2, u3 = MagicMock(username="alice"), MagicMock(username="bob"), MagicMock(username="carol")

        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.reconcile_user_quota") as mock_reconcile,
        ):
            mock_store.list_users.return_value = [u1, u2, u3]
            # bob blows up; alice + carol succeed
            mock_reconcile.side_effect = [{"e1": 100}, RuntimeError("bob exploded"), {"e3": 200}]

            from mlflow_oidc_auth.utils.quota import reconcile_all_quotas

            errors = reconcile_all_quotas()

        # all three users were attempted
        assert mock_reconcile.call_args_list == [(("alice",),), (("bob",),), (("carol",),)]
        assert errors is not None
        assert len(errors) == 1
        assert "bob exploded" in errors[0]

    def test_empty_user_list_returns_empty_errors(self):
        with (
            patch("mlflow_oidc_auth.utils.quota.store") as mock_store,
            patch("mlflow_oidc_auth.utils.quota.reconcile_user_quota") as mock_reconcile,
        ):
            mock_store.list_users.return_value = []

            from mlflow_oidc_auth.utils.quota import reconcile_all_quotas

            errors = reconcile_all_quotas()

        assert errors == []
        mock_reconcile.assert_not_called()


# ---------------------------------------------------------------------------
# cleanup_trash
# ---------------------------------------------------------------------------


def _make_deleted_experiment(experiment_id: str, last_update_time_ms: int):
    exp = MagicMock()
    exp.experiment_id = experiment_id
    exp.last_update_time = last_update_time_ms
    exp.creation_time = last_update_time_ms
    return exp


class TestCleanupTrash:
    def test_skips_experiments_newer_than_cutoff(self):
        """Experiments deleted recently must not be hard-deleted."""
        import time

        now_ms = int(time.time() * 1000)
        recent = _make_deleted_experiment("recent", now_ms - 1000)  # ~1 second old
        old = _make_deleted_experiment("old", now_ms - 30 * 86400 * 1000)  # 30 days old

        client = MagicMock()
        client.search_experiments.return_value = [recent, old]

        with (
            patch("mlflow_oidc_auth.utils.quota.store"),
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow.tracking.MlflowClient", return_value=client),
            patch("mlflow_oidc_auth.utils.quota.get_experiment_owner", return_value="alice"),
            patch("mlflow.server.handlers._get_tracking_store") as mock_get_store,
            patch("mlflow_oidc_auth.utils.trash_cleanup.hard_delete_experiment_with_runs") as mock_hard_delete,
            patch("mlflow_oidc_auth.utils.quota.reconcile_user_quota"),
        ):
            mock_config.MLFLOW_ENABLE_WORKSPACES = False

            from mlflow_oidc_auth.utils.quota import cleanup_trash

            cleanup_trash(retention_days=7)

        # Only the 30-day-old experiment is hard-deleted
        mock_hard_delete.assert_called_once_with("old", mock_get_store.return_value)

    def test_iterates_workspaces_and_deletes_old_experiments_in_each(self):
        """With workspaces on, each workspace is entered and its deleted experiments are processed."""
        import time

        now_ms = int(time.time() * 1000)
        old_ms = now_ms - 30 * 86400 * 1000

        ws_a = MagicMock()
        ws_a.name = "ws-a"
        ws_b = MagicMock()
        ws_b.name = "ws-b"

        exp_a = _make_deleted_experiment("exp-a", old_ms)
        exp_b = _make_deleted_experiment("exp-b", old_ms)

        client = MagicMock()
        client.search_experiments.side_effect = [[exp_a], [exp_b]]

        with (
            patch("mlflow_oidc_auth.utils.quota.store"),
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow.tracking.MlflowClient", return_value=client),
            patch("mlflow.server.handlers._get_workspace_store") as mock_get_ws_store,
            patch("mlflow.utils.workspace_context.set_server_request_workspace") as mock_set_ws,
            patch("mlflow.utils.workspace_context.clear_server_request_workspace") as mock_clear_ws,
            patch("mlflow_oidc_auth.utils.quota.get_experiment_owner", return_value="alice"),
            patch("mlflow.server.handlers._get_tracking_store"),
            patch("mlflow_oidc_auth.utils.trash_cleanup.hard_delete_experiment_with_runs") as mock_hard_delete,
            patch("mlflow_oidc_auth.utils.quota.reconcile_user_quota"),
        ):
            mock_config.MLFLOW_ENABLE_WORKSPACES = True
            mock_get_ws_store.return_value.list_workspaces.return_value = [ws_a, ws_b]

            from mlflow_oidc_auth.utils.quota import cleanup_trash

            cleanup_trash(retention_days=7)

        assert mock_set_ws.call_args_list == [(("ws-a",),), (("ws-b",),)]
        assert mock_clear_ws.call_count == 2
        deleted_ids = [c.args[0] for c in mock_hard_delete.call_args_list]
        assert deleted_ids == ["exp-a", "exp-b"]

    def test_error_in_one_workspace_does_not_abort_others(self, caplog):
        """search_experiments failure in workspace A still lets B be processed."""
        import time

        now_ms = int(time.time() * 1000)
        old_ms = now_ms - 30 * 86400 * 1000

        ws_a = MagicMock()
        ws_a.name = "ws-a"
        ws_b = MagicMock()
        ws_b.name = "ws-b"

        client = MagicMock()
        client.search_experiments.side_effect = [
            RuntimeError("workspace a broken"),
            [_make_deleted_experiment("exp-b", old_ms)],
        ]

        with (
            patch("mlflow_oidc_auth.utils.quota.store"),
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow.tracking.MlflowClient", return_value=client),
            patch("mlflow.server.handlers._get_workspace_store") as mock_get_ws_store,
            patch("mlflow.utils.workspace_context.set_server_request_workspace"),
            patch("mlflow.utils.workspace_context.clear_server_request_workspace"),
            patch("mlflow_oidc_auth.utils.quota.get_experiment_owner", return_value="alice"),
            patch("mlflow.server.handlers._get_tracking_store"),
            patch("mlflow_oidc_auth.utils.trash_cleanup.hard_delete_experiment_with_runs") as mock_hard_delete,
            patch("mlflow_oidc_auth.utils.quota.reconcile_user_quota"),
        ):
            mock_config.MLFLOW_ENABLE_WORKSPACES = True
            mock_get_ws_store.return_value.list_workspaces.return_value = [ws_a, ws_b]

            from mlflow_oidc_auth.utils.quota import cleanup_trash

            cleanup_trash(retention_days=7)

        # workspace-a failure logged; workspace-b processed
        assert "workspace a broken" in caplog.text
        mock_hard_delete.assert_called_once()
        assert mock_hard_delete.call_args.args[0] == "exp-b"

    def test_reconciles_each_affected_owner_once(self):
        """Two experiments by the same owner → one reconcile call. Different owners → one each."""
        import time

        now_ms = int(time.time() * 1000)
        old_ms = now_ms - 30 * 86400 * 1000

        exp_alice_1 = _make_deleted_experiment("exp1", old_ms)
        exp_alice_2 = _make_deleted_experiment("exp2", old_ms)
        exp_bob = _make_deleted_experiment("exp3", old_ms)

        client = MagicMock()
        client.search_experiments.return_value = [exp_alice_1, exp_alice_2, exp_bob]

        owners_by_exp = {"exp1": "alice", "exp2": "alice", "exp3": "bob"}

        with (
            patch("mlflow_oidc_auth.utils.quota.store"),
            patch("mlflow_oidc_auth.utils.quota.config") as mock_config,
            patch("mlflow.tracking.MlflowClient", return_value=client),
            patch(
                "mlflow_oidc_auth.utils.quota.get_experiment_owner",
                side_effect=lambda eid: owners_by_exp[eid],
            ),
            patch("mlflow.server.handlers._get_tracking_store"),
            patch("mlflow_oidc_auth.utils.trash_cleanup.hard_delete_experiment_with_runs"),
            patch("mlflow_oidc_auth.utils.quota.reconcile_user_quota") as mock_reconcile,
        ):
            mock_config.MLFLOW_ENABLE_WORKSPACES = False

            from mlflow_oidc_auth.utils.quota import cleanup_trash

            cleanup_trash(retention_days=7)

        reconciled = sorted(c.args[0] for c in mock_reconcile.call_args_list)
        assert reconciled == ["alice", "bob"]


