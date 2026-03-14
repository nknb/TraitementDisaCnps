from dataclasses import dataclass
from typing import Optional


@dataclass
class CurrentUser:
    id: int
    username: str
    role: str


_current_user: Optional[CurrentUser] = None


def set_current_user(user_id: int, username: str, role: str) -> None:
    global _current_user
    _current_user = CurrentUser(id=int(user_id), username=str(username), role=str(role))


def get_current_user() -> Optional[CurrentUser]:
    return _current_user
