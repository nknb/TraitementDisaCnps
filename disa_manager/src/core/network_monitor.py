"""
network_monitor.py — Surveillance réseau non-bloquante pour DisaManager
=======================================================================

Rôle :
  - Vérifie la disponibilité de la base réseau toutes les 10 secondes
    dans un QThread séparé (jamais dans le thread UI).
  - Émet ``status_changed(bool)`` quand l'état réseau change.
  - Quand le réseau se rétablit :
      1. Rejoue automatiquement la file d'attente des écritures.
      2. Émet ``data_changed`` via le DataBus pour que toutes les pages
         se rafraîchissent.
  - Expose ``is_available`` pour que l'UI affiche un indicateur de statut.

Intégration :
    Dans main_window.py (ou app.py) :
    ::

        from core.network_monitor import get_network_monitor
        mon = get_network_monitor()
        mon.status_changed.connect(my_slot)
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal, QTimer

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# WORKER DE VÉRIFICATION (thread secondaire)
# ─────────────────────────────────────────────────────────────────────────────

class _HealthWorker(QThread):
    """Tente une connexion rapide à la base (2 s max) dans un thread séparé.

    Émet ``result(True)`` si la base est accessible, ``result(False)`` sinon.
    Ne bloque jamais le thread principal.

    Détecte deux cas d'indisponibilité :
    - Fichier DB absent (supprimé ou partage réseau déconnecté)
    - Connexion impossible (timeout réseau)
    """

    result = Signal(bool)

    def run(self) -> None:
        try:
            from db.connection import _raw_connect, _configure_conn, DB_PATH
            # _raw_connect lève FileNotFoundError si le fichier n'existe pas,
            # ce qui évite la création silencieuse d'une base vide.
            conn = _raw_connect()
            _configure_conn(conn)
            conn.execute("SELECT 1").fetchone()
            conn.close()
            self.result.emit(True)
        except Exception as exc:
            logger.debug("Vérification base : inaccessible — %s", exc)
            self.result.emit(False)


# ─────────────────────────────────────────────────────────────────────────────
# MONITEUR RÉSEAU (singleton QObject)
# ─────────────────────────────────────────────────────────────────────────────

class NetworkMonitor(QObject):
    """Surveille la disponibilité de la base réseau et gère la reconnexion.

    Signaux
    -------
    status_changed(bool)
        Émis quand l'état change :
        - True  = base redevenue accessible (reconnexion)
        - False = base devenue inaccessible (perte réseau)
    """

    status_changed = Signal(bool)   # True = disponible, False = indisponible

    CHECK_INTERVAL_MS = 10_000      # vérification toutes les 10 s

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._available: bool = True  # on suppose disponible au démarrage
        self._worker: Optional[_HealthWorker] = None

        self._timer = QTimer(self)
        self._timer.setInterval(self.CHECK_INTERVAL_MS)
        self._timer.timeout.connect(self._start_check)
        self._timer.start()

        # Vérification immédiate dès l'ouverture de la fenêtre (sans attendre 10 s)
        QTimer.singleShot(300, self._start_check)

    # ── Vérification ─────────────────────────────────────────────────────────

    def _start_check(self) -> None:
        """Lance une vérification dans un thread séparé (non-bloquant)."""
        if self._worker and self._worker.isRunning():
            return  # la vérification précédente n'est pas encore terminée
        self._worker = _HealthWorker()
        self._worker.result.connect(self._on_check_result)
        self._worker.start()

    def _on_check_result(self, available: bool) -> None:
        """Appelé dans le thread UI quand la vérification est terminée."""
        was_available = self._available
        self._available = available

        if not was_available and available:
            # Réseau rétabli → rejouer les écritures en attente.
            # NB : data_changed est émis par _ReplayWorker après la fin du replay,
            #      pas ici, pour éviter que l'UI se rafraîchisse avant que les
            #      écritures soient effectivement rejouées (race condition).
            logger.info("Réseau rétabli — replay de la file d'attente.")
            self._replay_write_queue()

        if was_available != available:
            self.status_changed.emit(available)
            if available:
                logger.info("Base de données : DISPONIBLE")
            else:
                logger.warning("Base de données : INACCESSIBLE (réseau instable)")

    def _replay_write_queue(self) -> None:
        """Rejoue la file d'attente dans un thread pour ne pas bloquer l'UI."""
        from db.connection import get_write_queue, _raw_connect, _configure_conn
        queue = get_write_queue()
        if queue.is_empty:
            return

        class _ReplayWorker(QThread):
            def run(self) -> None:
                try:
                    conn = _raw_connect()
                    _configure_conn(conn)
                    replayed = queue.replay(conn)
                    conn.close()
                    if replayed:
                        logger.info("%d écriture(s) rejouée(s).", replayed)
                        import contextlib
                        with contextlib.suppress(Exception):
                            from core.events import get_data_bus
                            get_data_bus().data_changed.emit()
                except Exception as e:
                    logger.warning("Replay de la file d'attente échoué : %s", e)

        worker = _ReplayWorker(self)
        worker.start()

    # ── Propriétés publiques ──────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        """True si la base réseau est accessible."""
        return self._available

    @property
    def pending_writes(self) -> int:
        """Nombre d'écritures en attente de replay."""
        from db.connection import get_write_queue
        return len(get_write_queue())


# ─────────────────────────────────────────────────────────────────────────────
# SINGLETON
# ─────────────────────────────────────────────────────────────────────────────

_MONITOR: Optional[NetworkMonitor] = None


def get_network_monitor() -> NetworkMonitor:
    """Retourne l'instance unique du moniteur réseau (créée si nécessaire)."""
    global _MONITOR
    if _MONITOR is None:
        _MONITOR = NetworkMonitor()
    return _MONITOR
