"""MLflow 3.18's ``POST /ajax-api/3.0/mlflow/issues/schedule/state`` writes schedule-state tags on
the experiment named in the body, so it needs UPDATE on that experiment."""

from unittest.mock import patch

import pytest
from flask import Flask

from mlflow_oidc_auth.permissions import get_permission
from mlflow_oidc_auth.validators import issue as issue_mod
from mlflow_oidc_auth.validators import validate_can_sync_issue_detection_schedule

app = Flask(__name__)
PATH = "/ajax-api/3.0/mlflow/issues/schedule/state"


def _check(body, permission_name):
    seen = []

    def fake(experiment_ids, username):
        seen.append(list(experiment_ids))
        return get_permission(permission_name)

    with app.test_request_context(PATH, method="POST", json=body), patch.object(issue_mod, "permission_on_all_experiments", fake):
        return validate_can_sync_issue_detection_schedule("alice"), seen


@pytest.mark.parametrize("permission_name,allowed", [("MANAGE", True), ("EDIT", True), ("READ", False), ("NO_PERMISSIONS", False)])
def test_needs_update_on_the_named_experiment(permission_name, allowed):
    result, seen = _check({"experiment_id": "42"}, permission_name)

    assert result is allowed
    assert seen == [["42"]]


def test_no_experiment_is_refused():
    # The real helper denies an empty list; this pins that the validator does not short-circuit.
    with app.test_request_context(PATH, method="POST", json={}):
        assert validate_can_sync_issue_detection_schedule("alice") is False
