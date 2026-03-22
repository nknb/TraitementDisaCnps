from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer


class _DataBus(QObject):
    """Bus d'événements central pour l'application.

    Rôles :
    1. Diffuser des notifications internes (``data_changed``) quand **ce processus**
       modifie la base (Ajouter / Mettre à jour / Supprimer / Importer).
    2. Détecter automatiquement les modifications effectuées par **d'autres processus**
       (autres utilisateurs sur le même fichier .db partagé) grâce à un polling
       léger toutes les 4 secondes — et émettre ``data_changed`` pour que chaque
       widget rafraîchisse ses données.

    Debounce :
    Plusieurs appels rapides à ``notify()`` (ex. import par lots, CRUD enchaînés)
    ne déclenchent qu'un seul ``data_changed`` après 100 ms de silence.
    Cela évite le double-rechargement BDD observable quand database_widget émet
    ``notify()`` alors qu'il est lui-même abonné au signal.
    """

    data_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._last_signature: str | None = None

        # Timer de debounce : plusieurs notify() rapides → 1 seul data_changed
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(100)   # 100 ms de silence avant émission
        self._debounce.timeout.connect(self.data_changed.emit)

        # Démarre le polling inter-processus (10 secondes)
        # Intervalle plus long = moins de connexions simultanées sur la base réseau
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(10_000)
        self._poll_timer.timeout.connect(self._poll_db_changes)
        self._poll_timer.start()

    # ------------------------------------------------------------------
    # Polling : détection des modifications venant d'autres postes
    # ------------------------------------------------------------------

    def _get_db_signature(self) -> str | None:
        """Calcule une empreinte légère de l'état courant de la base.

        Combine le nombre de lignes et la date de dernière modification
        des deux tables métier.  Si la signature change entre deux appels,
        c'est qu'un autre processus a écrit dans la base.
        """
        try:
            from db.connection import get_connection
            conn = get_connection()
            with conn:
                row = conn.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) || '|' || COALESCE(MAX(updated_at), '')
                         FROM traitement_disa)                                          AS t,
                        (SELECT COUNT(*) || '|' || COALESCE(MAX(updated_at), MAX(rowid), '')
                         FROM identification_employeurs)                                AS e
                    """
                ).fetchone()
            if row is None:
                return None
            return f"{row[0]}::{row[1]}"
        except Exception:
            return None

    def notify(self) -> None:
        """Demande un refresh global — plusieurs appels rapides = 1 seul signal après 100 ms.

        Remplace ``get_data_bus().data_changed.emit()`` dans tout le code applicatif.
        """
        self._debounce.start()   # restart si déjà actif → repart de zéro

    def _poll_db_changes(self) -> None:
        """Appelé toutes les 10 s. Émet data_changed si la base a changé."""
        sig = self._get_db_signature()
        if sig is None:
            return
        if self._last_signature is not None and sig != self._last_signature:
            self.notify()
        self._last_signature = sig


_BUS: Optional[_DataBus] = None


def get_data_bus() -> _DataBus:
    """Retourne l'instance unique du bus d'événements."""

    global _BUS
    if _BUS is None:
        _BUS = _DataBus()
    return _BUS
