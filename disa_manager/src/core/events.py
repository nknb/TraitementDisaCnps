from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal


class _DataBus(QObject):
    """Bus d'événements central pour l'application.

    Permet de diffuser des notifications (par ex. "les données ont changé")
    à tous les widgets intéressés sans couplage direct entre eux.
    """

    data_changed = Signal()


_BUS: Optional[_DataBus] = None


def get_data_bus() -> _DataBus:
    """Retourne l'instance unique du bus d'événements."""

    global _BUS
    if _BUS is None:
        _BUS = _DataBus()
    return _BUS
