from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Durée de validité d'une session (8 heures)
SESSION_TIMEOUT = timedelta(hours=8)


@dataclass
class CurrentUser:
    id: int
    username: str
    role: str
    logged_in_at: datetime = field(default_factory=datetime.now)

    @property
    def is_session_valid(self) -> bool:
        """Retourne False si la session a expiré (> 8 h d'inactivité)."""
        return datetime.now() - self.logged_in_at < SESSION_TIMEOUT

    def touch(self) -> None:
        """Renouvelle le timestamp d'activité de la session."""
        self.logged_in_at = datetime.now()


_current_user: Optional[CurrentUser] = None


def set_current_user(user_id: int, username: str, role: str) -> None:
    global _current_user
    _current_user = CurrentUser(id=int(user_id), username=str(username), role=str(role))
    logger.info("Connexion : utilisateur '%s' (rôle=%s)", username, role)


def get_current_user() -> Optional[CurrentUser]:
    """Retourne l'utilisateur connecté, ou None si la session a expiré."""
    if _current_user is not None and not _current_user.is_session_valid:
        logger.warning("Session expirée pour '%s'", _current_user.username)
        clear_current_user()
        return None
    return _current_user


def clear_current_user() -> None:
    """Invalide la session courante (déconnexion ou expiration)."""
    global _current_user
    if _current_user:
        logger.info("Déconnexion : utilisateur '%s'", _current_user.username)
    _current_user = None
