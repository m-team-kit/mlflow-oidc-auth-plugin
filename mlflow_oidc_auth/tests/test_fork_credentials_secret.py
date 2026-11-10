"""Fork: the external user-credentials secrets store, on top of upstream's token rotation.

What these pin:

* the new ``default`` token is published to the secrets store inside the rotation's transaction,
  so a failed publish leaves the previous token working;
* only a user rotating their own token publishes it;
* ``get_idp_access_token`` exchanges the session row's refresh token under the refresh guard and
  stores the rotated refresh token back on the row.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from mlflow.exceptions import MlflowException

from mlflow_oidc_auth.routers import auth as auth_router_mod
from mlflow_oidc_auth.routers import users as users_router_mod
from mlflow_oidc_auth.session.token_vault import SessionTokens

ALICE = "alice@example.com"


def _in(days: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


@pytest.fixture
def store(tmp_path):
    from mlflow_oidc_auth.sqlalchemy_store import SqlAlchemyStore

    s = SqlAlchemyStore()
    s.init_db(f"sqlite:///{tmp_path / 'auth.db'}")
    s.create_user(ALICE, "Alice")
    yield s
    s.engine.dispose()


class TestReplaceUserTokenBeforeCommit:
    def test_the_hook_receives_the_plaintext_that_authenticates(self, store):
        seen = []

        record, plaintext, _ = store.replace_user_token(ALICE, "default", _in(30), created_by=ALICE, before_commit=seen.append)

        assert seen == [plaintext]
        assert store.authenticate_user(ALICE, plaintext)

    def test_a_failing_hook_rolls_the_rotation_back(self, store):
        _, old, _ = store.replace_user_token(ALICE, "default", _in(30), created_by=ALICE)
        attempted = []

        def fail(plaintext):
            attempted.append(plaintext)
            raise RuntimeError("secrets API down")

        with pytest.raises(MlflowException):
            store.replace_user_token(ALICE, "default", _in(30), created_by=ALICE, before_commit=fail)

        assert store.authenticate_user(ALICE, old)
        assert not store.authenticate_user(ALICE, attempted[0])
        assert [t.name for t in store.list_user_tokens(ALICE)] == ["default"]


class TestRotationPublishesTheSecret:
    @pytest.fixture
    def secrets_on(self, monkeypatch):
        monkeypatch.setattr(users_router_mod.config, "USER_CREDENTIALS_SECRETS_VO", "vo", raising=False)
        monkeypatch.setattr(users_router_mod.config, "USER_CREDENTIALS_SECRETS_API", "https://secrets.example", raising=False)
        monkeypatch.setattr(users_router_mod, "_get_user_authorization", AsyncMock(return_value="Bearer idp"))

    @pytest.mark.asyncio
    async def test_own_rotation_publishes_the_new_token(self, store, secrets_on):
        published = MagicMock(return_value=SimpleNamespace(is_success=True, status_code=200, text=""))
        with patch.object(users_router_mod, "store", store), patch.object(users_router_mod, "_update_credentials_secret", published):
            response = await users_router_mod.create_access_token(None, current_username=ALICE, is_admin=False, request=None)

        import json

        token = json.loads(response.body)["token"]
        published.assert_called_once_with("Bearer idp", ALICE, token)
        assert store.authenticate_user(ALICE, token)

    @pytest.mark.asyncio
    async def test_a_refused_publish_is_a_500_and_keeps_the_old_token(self, store, secrets_on):
        _, old, _ = store.replace_user_token(ALICE, "default", _in(30), created_by=ALICE)
        refused = MagicMock(return_value=SimpleNamespace(is_success=False, status_code=403, text="no"))
        with patch.object(users_router_mod, "store", store), patch.object(users_router_mod, "_update_credentials_secret", refused):
            with pytest.raises(HTTPException) as exc_info:
                await users_router_mod.create_access_token(None, current_username=ALICE, is_admin=False, request=None)

        assert exc_info.value.status_code == 500
        assert store.authenticate_user(ALICE, old)

    @pytest.mark.asyncio
    async def test_an_unreachable_secrets_api_is_a_502(self, store, secrets_on):
        import httpx2

        unreachable = MagicMock(side_effect=httpx2.ConnectError("down"))
        with patch.object(users_router_mod, "store", store), patch.object(users_router_mod, "_update_credentials_secret", unreachable):
            with pytest.raises(HTTPException) as exc_info:
                await users_router_mod.create_access_token(None, current_username=ALICE, is_admin=False, request=None)

        assert exc_info.value.status_code == 502

    @pytest.mark.asyncio
    async def test_an_admin_rotating_another_users_token_does_not_publish(self, store, secrets_on):
        from mlflow_oidc_auth.models import CreateAccessTokenRequest

        published = MagicMock()
        with patch.object(users_router_mod, "store", store), patch.object(users_router_mod, "_update_credentials_secret", published):
            await users_router_mod.create_access_token(
                CreateAccessTokenRequest(username=ALICE), current_username="admin@example.com", is_admin=True, request=None
            )

        published.assert_not_called()


class _Guard:
    """A held refresh guard over one session row."""

    def __init__(self, encrypted):
        self.live = True
        self.encrypted_tokens = encrypted
        self.written = []

    def write(self, encrypted):
        self.written.append(encrypted)
        return True

    def reread(self):
        return self.encrypted_tokens


class _GuardCM:
    def __init__(self, guard):
        self.guard = guard
        self.exited = False

    def __enter__(self):
        return self.guard

    def __exit__(self, *exc):
        self.exited = True


class _Vault:
    """Identity 'encryption', so the test can read what was written."""

    def encrypt(self, tokens):
        return tokens

    def decrypt(self, blob):
        return blob


class TestGetIdpAccessToken:
    @pytest.fixture
    def setup(self, monkeypatch):
        monkeypatch.setattr(auth_router_mod.config, "OIDC_USE_REFRESH_TOKEN", True, raising=False)
        guard = _Guard(SessionTokens(provider_id="default", expires_at=None, refresh_token="rt-1", id_token=None))
        cm = _GuardCM(guard)
        monkeypatch.setattr(auth_router_mod, "get_token_vault", lambda: _Vault())
        monkeypatch.setattr(auth_router_mod.store, "auth_session_refresh_guard", lambda session_id: cm, raising=False)

        async def _inline(fn, *args):
            return fn(*args)

        monkeypatch.setattr(auth_router_mod, "_run_blocking", _inline)
        client = SimpleNamespace(fetch_access_token=MagicMock(return_value={"access_token": "at-2", "refresh_token": "rt-2", "expires_in": 300}))
        monkeypatch.setattr(auth_router_mod, "_client_for_refresh", lambda provider_id: client)
        return SimpleNamespace(guard=guard, cm=cm, client=client)

    @pytest.mark.asyncio
    async def test_returns_a_fresh_access_token_and_stores_the_rotated_refresh_token(self, setup):
        token = await auth_router_mod.get_idp_access_token("sid-1")

        assert token == "at-2"
        setup.client.fetch_access_token.assert_called_once_with(grant_type="refresh_token", refresh_token="rt-1")
        assert setup.guard.written[0].refresh_token == "rt-2"
        assert setup.cm.exited

    @pytest.mark.asyncio
    async def test_none_without_a_session(self, setup):
        assert await auth_router_mod.get_idp_access_token(None) is None
        setup.client.fetch_access_token.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_when_refresh_tokens_are_off(self, setup, monkeypatch):
        monkeypatch.setattr(auth_router_mod.config, "OIDC_USE_REFRESH_TOKEN", False, raising=False)

        assert await auth_router_mod.get_idp_access_token("sid-1") is None
        setup.client.fetch_access_token.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_and_nothing_written_when_the_idp_refuses(self, setup):
        setup.client.fetch_access_token.side_effect = RuntimeError("invalid_grant")

        assert await auth_router_mod.get_idp_access_token("sid-1") is None
        assert setup.guard.written == []
        assert setup.cm.exited
