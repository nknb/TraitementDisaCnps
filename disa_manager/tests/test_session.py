"""Tests unitaires pour core/session.py."""
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

import core.session as session_mod  # noqa: E402
from core.session import CurrentUser, get_current_user, set_current_user  # noqa: E402


@pytest.fixture(autouse=True)
def reset_session():
    """Remet la session à None avant chaque test."""
    session_mod._current_user = None
    yield
    session_mod._current_user = None


class TestSession:
    def test_get_current_user_retourne_none_par_defaut(self):
        assert get_current_user() is None

    def test_set_et_get_current_user(self):
        set_current_user(user_id=1, username="admin", role="admin")
        user = get_current_user()
        assert user is not None
        assert user.id == 1
        assert user.username == "admin"
        assert user.role == "admin"

    def test_set_current_user_convertit_types(self):
        set_current_user(user_id="42", username=123, role="agent")  # types incorrects
        user = get_current_user()
        assert isinstance(user.id, int)
        assert user.id == 42
        assert isinstance(user.username, str)
        assert user.username == "123"

    def test_current_user_est_dataclass(self):
        set_current_user(1, "agent1", "agent")
        user = get_current_user()
        assert isinstance(user, CurrentUser)

    def test_set_current_user_ecrase_precedent(self):
        set_current_user(1, "user1", "agent")
        set_current_user(2, "user2", "admin")
        user = get_current_user()
        assert user.id == 2
        assert user.username == "user2"
