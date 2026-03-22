"""Login dialog — thème CNPS avec photo du bâtiment."""
from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import (
    QIcon, QPixmap, QFont, QColor, QPainter,
    QLinearGradient, QBrush, QImageReader,
)
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QWidget, QCheckBox,
)

import logging
from datetime import datetime
from typing import Optional

from db.connection import get_connection
from core.session import set_current_user

# ── Persistance "Se souvenir de moi" ─────────────────────────────────────────
if getattr(sys, "frozen", False):
    _DATA_DIR = Path(sys.executable).parent / "data"
else:
    _DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data"

_REMEMBER_FILE = _DATA_DIR / "remember_me.json"
_XOR_KEY = b"CNPS-DiSA-2025"   # clé d'obfuscation locale (non cryptographique)


def _xor_obfuscate(data: bytes, key: bytes) -> bytes:
    """XOR cyclique — obfuscation légère, empêche la lecture directe du fichier."""
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _save_credentials(username: str, password: str) -> None:
    """Sauvegarde username + password obfusqué dans data/remember_me.json."""
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        obf = base64.b64encode(_xor_obfuscate(password.encode(), _XOR_KEY)).decode()
        _REMEMBER_FILE.write_text(
            json.dumps({"username": username, "password_obf": obf}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def _load_credentials() -> tuple[str, str] | None:
    """Charge les identifiants mémorisés. Retourne (username, password) ou None."""
    try:
        if not _REMEMBER_FILE.exists():
            return None
        data = json.loads(_REMEMBER_FILE.read_text(encoding="utf-8"))
        username = data.get("username", "")
        obf = data.get("password_obf", "")
        if not username or not obf:
            return None
        password = _xor_obfuscate(base64.b64decode(obf.encode()), _XOR_KEY).decode()
        return username, password
    except Exception:
        return None


def _clear_credentials() -> None:
    """Supprime le fichier de mémorisation."""
    try:
        _REMEMBER_FILE.unlink(missing_ok=True)
    except Exception:
        pass

logger = logging.getLogger(__name__)

_IMAGES_DIR  = Path(__file__).resolve().parent.parent / "images"
_LOGO_PATH   = _IMAGES_DIR / "cnps_logo.jpeg"
_BUILDING_PATH = _IMAGES_DIR / "cnps_building.jpeg"

# ── Couleurs CNPS ──────────────────────────────────────────────────────────
_C_BLUE   = "#003f8a"   # bleu profond CNPS
_C_BLUE2  = "#0077c8"   # bleu clair CNPS
_C_ORANGE = "#e8710a"   # orange CNPS
_C_BG     = "#f0f4fb"   # fond panneau droit

_FIELD_QSS = f"""
QLineEdit {{
    background-color: #ffffff;
    border: 1.5px solid #c7d4e8;
    border-radius: 7px;
    padding: 6px 10px;
    font-size: 11px;
    color: #1e2d42;
    font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
    min-height: 20px;
}}
QLineEdit:focus {{
    border-color: {_C_BLUE};
    background-color: #f0f6ff;
}}
QLineEdit:hover {{
    border-color: {_C_BLUE2};
}}
"""

_BTN_QSS = f"""
QPushButton {{
    background-color: {_C_BLUE};
    color: white;
    border: none;
    border-radius: 7px;
    font-size: 12px;
    font-weight: 600;
    font-family: 'Segoe UI', Helvetica, Arial, sans-serif;
    padding: 0 16px;
    min-height: 34px;
}}
QPushButton:hover  {{ background-color: {_C_BLUE2}; }}
QPushButton:pressed {{ background-color: #002d66; }}
"""


class _BuildingPanel(QWidget):
    """Panneau gauche : photo du bâtiment CNPS (ou dégradé bleu en fallback)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        if _BUILDING_PATH.exists():
            # QImageReader applique automatiquement la rotation EXIF (photos téléphone)
            reader = QImageReader(str(_BUILDING_PATH))
            reader.setAutoTransform(True)
            img = reader.read()
            if not img.isNull():
                self._pixmap = QPixmap.fromImage(img)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        if self._pixmap and not self._pixmap.isNull():
            # Recadrage centre de l'image pour remplir le panneau
            scaled = self._pixmap.scaled(
                QSize(w, h),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x_off = (scaled.width()  - w) // 2
            y_off = (scaled.height() - h) // 2
            p.drawPixmap(0, 0, scaled, x_off, y_off, w, h)
            # Voile sombre pour lisibilité du texte
            p.fillRect(self.rect(), QColor(0, 0, 0, 90))
        else:
            # Dégradé bleu CNPS en fallback
            grad = QLinearGradient(0, 0, 0, h)
            grad.setColorAt(0.0, QColor("#001f4d"))
            grad.setColorAt(0.5, QColor("#003f8a"))
            grad.setColorAt(1.0, QColor("#0077c8"))
            p.fillRect(self.rect(), QBrush(grad))

        # Bandeau bas avec logo + nom agence
        band_h = 82
        band_grad = QLinearGradient(0, h - band_h, 0, h)
        band_grad.setColorAt(0.0, QColor(0, 31, 77, 0))
        band_grad.setColorAt(1.0, QColor(0, 31, 77, 220))
        p.fillRect(QRect(0, h - band_h, w, band_h), QBrush(band_grad))

        p.setPen(QColor(255, 255, 255, 230))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(
            QRect(0, h - 58, w, 20),
            Qt.AlignmentFlag.AlignCenter,
            "IPS-CNPS — Agence de Gagnoa",
        )
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(255, 255, 255, 170))
        p.drawText(
            QRect(0, h - 38, w, 18),
            Qt.AlignmentFlag.AlignCenter,
            "Traitement DiSA",
        )
        p.setFont(QFont("Segoe UI", 7))
        p.setPen(QColor(255, 255, 255, 120))
        p.drawText(
            QRect(0, h - 20, w, 16),
            Qt.AlignmentFlag.AlignCenter,
            "Créé par N'GUESSAN Kouakou N'goran Blanchard",
        )


class LoginDialog(QDialog):
    """Boîte de dialogue de connexion — charte CNPS."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._failed_attempts: int = 0
        self._lockout_until: Optional[datetime] = None
        self.setWindowTitle("Connexion — Traitement DiSA CNPS")
        self.setModal(True)
        # Taille réduite de 30 % par rapport à l'ancienne version (740×460)
        self.setFixedSize(518, 322)

        if _LOGO_PATH.exists():
            self.setWindowIcon(QIcon(str(_LOGO_PATH)))

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Panneau gauche : photo bâtiment ───────────────────────────────
        self._building = _BuildingPanel(self)
        root.addWidget(self._building, stretch=42)

        # ── Panneau droit : formulaire ────────────────────────────────────
        right = QFrame(self)
        right.setStyleSheet(f"QFrame {{ background-color: {_C_BG}; }}")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(28, 20, 28, 20)
        rl.setSpacing(8)

        # Logo CNPS
        if _LOGO_PATH.exists():
            logo_lbl = QLabel()
            pix = QPixmap(str(_LOGO_PATH)).scaled(
                48, 48,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            logo_lbl.setPixmap(pix)
            logo_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            rl.addWidget(logo_lbl)

        # Titre
        title = QLabel("Connectez-vous")
        title.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {_C_BLUE};"
            "font-family: 'Segoe UI', Helvetica, Arial, sans-serif;"
        )
        rl.addWidget(title, alignment=Qt.AlignmentFlag.AlignCenter)

        sub = QLabel("Accès réservé au personnel CNPS")
        sub.setStyleSheet(
            f"font-size: 10px; color: {_C_BLUE2};"
            "font-family: 'Segoe UI', Helvetica, Arial, sans-serif;"
        )
        rl.addWidget(sub, alignment=Qt.AlignmentFlag.AlignCenter)

        # Séparateur orange
        sep = QFrame()
        sep.setFixedHeight(2)
        sep.setStyleSheet(f"background-color: {_C_ORANGE}; border-radius: 1px;")
        rl.addWidget(sep)

        # Champ identifiant
        user_lbl = QLabel("Identifiant")
        user_lbl.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {_C_BLUE};"
            "font-family: 'Segoe UI', Helvetica, Arial, sans-serif;"
        )
        rl.addWidget(user_lbl)
        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("Nom d'utilisateur")
        self.username_edit.setStyleSheet(_FIELD_QSS)
        rl.addWidget(self.username_edit)

        # Champ mot de passe
        pwd_lbl = QLabel("Mot de passe")
        pwd_lbl.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {_C_BLUE};"
            "font-family: 'Segoe UI', Helvetica, Arial, sans-serif;"
        )
        rl.addWidget(pwd_lbl)
        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("••••••••")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setStyleSheet(_FIELD_QSS)
        rl.addWidget(self.password_edit)

        # Case "Se souvenir de moi"
        self.remember_check = QCheckBox("Se souvenir de moi")
        self.remember_check.setStyleSheet(
            f"QCheckBox {{ font-size: 10px; color: {_C_BLUE};"
            " font-family: 'Segoe UI', Helvetica, Arial, sans-serif; spacing: 6px; }}"
        )
        rl.addWidget(self.remember_check)

        # Message d'erreur
        self.info_label = QLabel("")
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label.setStyleSheet(
            "color: #c0392b; font-size: 10px; min-height: 14px;"
            "font-family: 'Segoe UI', Helvetica, Arial, sans-serif;"
        )
        rl.addWidget(self.info_label)

        # Bouton Connexion
        self.login_btn = QPushButton("  Se connecter")
        self.login_btn.setStyleSheet(_BTN_QSS)
        self.login_btn.clicked.connect(self.handle_login)
        rl.addWidget(self.login_btn)

        self.password_edit.returnPressed.connect(self.handle_login)
        self.username_edit.returnPressed.connect(self.handle_login)

        rl.addStretch(1)
        root.addWidget(right, stretch=58)

        # ── Pré-remplissage si identifiants mémorisés ─────────────────────
        self._prefill_remembered()

    # ------------------------------------------------------------------

    def _prefill_remembered(self) -> None:
        """Pré-remplit les champs si des identifiants ont été mémorisés."""
        creds = _load_credentials()
        if creds:
            username, password = creds
            self.username_edit.setText(username)
            self.password_edit.setText(password)
            self.remember_check.setChecked(True)

    def handle_login(self) -> None:
        """Valide les identifiants via la base SQLite."""
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()

        if not username or not password:
            self.info_label.setText("Veuillez renseigner les deux champs.")
            return

        # Rate-limiting : max 5 tentatives, puis blocage 30 s
        from datetime import timedelta
        if self._lockout_until and datetime.now() < self._lockout_until:
            remaining = int((self._lockout_until - datetime.now()).total_seconds())
            self.info_label.setText(f"Trop de tentatives. Réessayez dans {remaining} s.")
            return

        try:
            with get_connection() as conn:
                cur = conn.execute(
                    "SELECT id, username, password, role FROM utilisateurs WHERE username = ?",
                    (username,),
                )
                row = cur.fetchone()
        except Exception as exc:
            self.info_label.setText(f"Erreur base de données : {exc}")
            return

        from db.init_db import verify_password
        if row is None or not verify_password(password, row["password"]):
            self._failed_attempts += 1
            if self._failed_attempts >= 5:
                self._lockout_until = datetime.now() + timedelta(seconds=30)
                self._failed_attempts = 0
                self.info_label.setText("Trop de tentatives. Compte bloqué 30 s.")
            else:
                remaining_tries = 5 - self._failed_attempts
                self.info_label.setText(
                    f"Identifiant ou mot de passe incorrect. ({remaining_tries} essai(s) restant(s))"
                )
            self.password_edit.clear()
            self.password_edit.setFocus()
            return

        # Succès : réinitialiser le compteur
        self._failed_attempts = 0
        self._lockout_until = None

        # Mémorisation des identifiants selon la case cochée
        if self.remember_check.isChecked():
            _save_credentials(username, password)
        else:
            _clear_credentials()

        set_current_user(user_id=row["id"], username=row["username"], role=row["role"])
        self.accept()
