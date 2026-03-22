"""notification_widget.py — Notifications in-app non bloquantes.

Utilisation :
    from ui.notification_widget import get_notification_manager
    nm = get_notification_manager()
    if nm:
        nm.notify("Succès", "Enregistrement ajouté.", "success")

Types : "success" | "warning" | "error" | "info"
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QTimer, Qt, QRect
from PySide6.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
)

logger = logging.getLogger(__name__)

_MAX_VISIBLE = 4          # nombre maximal de cartes simultanées
_AUTO_DISMISS_MS = 5_000  # durée avant fermeture automatique (ms)
_CARD_WIDTH = 320
_MARGIN_RIGHT = 16
_MARGIN_BOTTOM = 16

_COLORS: dict[str, dict[str, str]] = {
    "success": {"bg": "#f0fdf4", "border": "#86efac", "title": "#15803d", "bar": "#22c55e"},
    "error":   {"bg": "#fef2f2", "border": "#fca5a5", "title": "#b91c1c", "bar": "#ef4444"},
    "warning": {"bg": "#fffbeb", "border": "#fcd34d", "title": "#92400e", "bar": "#f59e0b"},
    "info":    {"bg": "#eff6ff", "border": "#93c5fd", "title": "#1d4ed8", "bar": "#3b82f6"},
}

_ICONS: dict[str, str] = {
    "success": "✔",
    "error":   "✖",
    "warning": "⚠",
    "info":    "ℹ",
}


class _NotificationCard(QFrame):
    """Carte de notification individuelle avec auto-fermeture et animation."""

    def __init__(
        self,
        title: str,
        message: str,
        notif_type: str,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        notif_type = notif_type if notif_type in _COLORS else "info"
        c = _COLORS[notif_type]

        self.setFixedWidth(_CARD_WIDTH)
        self.setObjectName("notif_card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"QFrame#notif_card {{"
            f"  background: {c['bg']};"
            f"  border: 1px solid {c['border']};"
            f"  border-left: 4px solid {c['bar']};"
            f"  border-radius: 8px;"
            f"}}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 10, 10)
        outer.setSpacing(4)

        # ── En-tête : icône + titre + bouton fermeture ──────────────────
        header = QHBoxLayout()
        header.setSpacing(6)

        icon_lbl = QLabel(_ICONS[notif_type])
        icon_lbl.setStyleSheet(
            f"color: {c['bar']}; font-size: 14px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        header.addWidget(icon_lbl)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"color: {c['title']}; font-size: 12px; font-weight: 700;"
            " background: transparent; border: none;"
            " font-family: 'Segoe UI', Helvetica, Arial, sans-serif;"
        )
        header.addWidget(title_lbl, 1)

        close_btn = QPushButton("×")
        close_btn.setFixedSize(18, 18)
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #9ca3af;"
            " font-size: 14px; font-weight: 700; padding: 0; }"
            "QPushButton:hover { color: #374151; }"
        )
        close_btn.clicked.connect(self._dismiss)
        header.addWidget(close_btn)

        outer.addLayout(header)

        # ── Message ──────────────────────────────────────────────────────
        if message:
            msg_lbl = QLabel(message)
            msg_lbl.setWordWrap(True)
            msg_lbl.setStyleSheet(
                "color: #374151; font-size: 11px; background: transparent; border: none;"
                " font-family: 'Segoe UI', Helvetica, Arial, sans-serif;"
            )
            outer.addWidget(msg_lbl)

        self.adjustSize()

        # ── Timer auto-dismiss ───────────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(_AUTO_DISMISS_MS)
        self._timer.timeout.connect(self._dismiss)
        self._timer.start()

    def _dismiss(self) -> None:
        """Anime la disparition puis se détruit."""
        self._timer.stop()
        anim = QPropertyAnimation(self, b"maximumHeight", self)
        anim.setDuration(250)
        anim.setStartValue(self.height())
        anim.setEndValue(0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(self.deleteLater)
        anim.start()


class NotificationManager(QWidget):
    """Conteneur flottant ancré en bas à droite de la fenêtre parente.

    Les cartes s'empilent verticalement (la plus récente en bas).
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setStyleSheet("background: transparent;")

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._layout.addStretch(1)

        self.setFixedWidth(_CARD_WIDTH)
        self.raise_()

    def notify(self, title: str, message: str = "", notif_type: str = "info") -> None:
        """Affiche une nouvelle notification."""
        # Limiter le nombre de cartes visibles
        cards = [
            self._layout.itemAt(i).widget()
            for i in range(self._layout.count())
            if self._layout.itemAt(i).widget() is not None
        ]
        if len(cards) >= _MAX_VISIBLE:
            oldest = cards[0]
            oldest.deleteLater()

        card = _NotificationCard(title, message, notif_type, self)
        self._layout.addWidget(card)
        self.adjustSize()
        self.raise_()

    def reposition(self, parent_rect: QRect) -> None:
        """Replace le manager en bas à droite de la fenêtre parente."""
        self.adjustSize()
        x = parent_rect.width() - _CARD_WIDTH - _MARGIN_RIGHT
        y = parent_rect.height() - self.height() - _MARGIN_BOTTOM
        self.setGeometry(x, y, _CARD_WIDTH, self.height())
        self.raise_()


# ── Singleton global ──────────────────────────────────────────────────────────

_MANAGER: Optional[NotificationManager] = None


def set_notification_manager(manager: NotificationManager) -> None:
    global _MANAGER
    _MANAGER = manager


def get_notification_manager() -> Optional[NotificationManager]:
    return _MANAGER
