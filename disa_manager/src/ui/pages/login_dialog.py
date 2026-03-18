"""Login dialog — thème CNPS avec photo du bâtiment."""
from pathlib import Path

from PySide6.QtCore import Qt, QRect, QSize
from PySide6.QtGui import (
    QIcon, QPixmap, QFont, QColor, QPainter,
    QLinearGradient, QBrush, QImageReader,
)
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QFrame, QWidget,
)

from db.connection import get_connection
from core.session import set_current_user

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
        band_h = 64
        band_grad = QLinearGradient(0, h - band_h, 0, h)
        band_grad.setColorAt(0.0, QColor(0, 31, 77, 0))
        band_grad.setColorAt(1.0, QColor(0, 31, 77, 220))
        p.fillRect(QRect(0, h - band_h, w, band_h), QBrush(band_grad))

        p.setPen(QColor(255, 255, 255, 230))
        p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        p.drawText(
            QRect(0, h - 42, w, 20),
            Qt.AlignmentFlag.AlignCenter,
            "IPS-CNPS — Agence de Gagnoa",
        )
        p.setFont(QFont("Segoe UI", 8))
        p.setPen(QColor(255, 255, 255, 170))
        p.drawText(
            QRect(0, h - 22, w, 18),
            Qt.AlignmentFlag.AlignCenter,
            "Traitement DiSA",
        )


class LoginDialog(QDialog):
    """Boîte de dialogue de connexion — charte CNPS."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
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

    # ------------------------------------------------------------------

    def handle_login(self) -> None:
        """Valide les identifiants via la base SQLite."""
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()

        if not username or not password:
            self.info_label.setText("Veuillez renseigner les deux champs.")
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

        if row is None or row["password"] != password:
            self.info_label.setText("Identifiants incorrects.")
            self.password_edit.clear()
            self.password_edit.setFocus()
            return

        set_current_user(user_id=row["id"], username=row["username"], role=row["role"])
        self.accept()
