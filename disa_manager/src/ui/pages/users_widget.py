from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
    QMessageBox,
    QFrame,
    QHeaderView,
    QSizePolicy,
    QTabWidget,
    QRadioButton,
    QButtonGroup,
    QFileDialog,
    QGroupBox,
)

from db.connection import get_connection
from core.session import get_current_user
import db.connection as _db_conn
from ui.dashboard_theme import (
    BTN_PRIMARY as _BTN_PRIMARY,
    BTN_SUCCESS as _BTN_SUCCESS,
    BTN_DANGER as _BTN_DANGER,
    BTN_NEUTRAL as _BTN_NEUTRAL,
    BTN_WARNING as _BTN_WARNING,
    INPUT_STYLE as _INPUT_STYLE,
)

# Chemin réseau par défaut proposé
_DEFAULT_NETWORK_PATH = r"\\srvgagnoa\prod\datagagnoa\accueil\disa.db"
# Chemin réseau alternatif (sous-dossier réseau)
_DEFAULT_NETWORK_PATH2 = r"\\srvgagnoa\prod\datagagnoa\reseau\disa.db"


# ── Dialogue formulaire ──────────────────────────────────────────────────────

class UserFormDialog(QDialog):
    """Dialogue pour ajouter / modifier un utilisateur."""

    def __init__(
        self,
        parent: QWidget,
        username: str = "",
        role: str = "agent",
        with_password: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Utilisateur")
        self.setMinimumWidth(360)
        self._with_password = with_password

        self.username_edit = QLineEdit(self)
        self.username_edit.setText(username)
        self.username_edit.setPlaceholderText("Identifiant (username)")
        self.username_edit.setStyleSheet(_INPUT_STYLE)

        self.password_edit = QLineEdit(self)
        self.password_edit.setPlaceholderText(
            "Mot de passe" if with_password else "Laisser vide pour ne pas changer"
        )
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setStyleSheet(_INPUT_STYLE)

        self.role_combo = QComboBox(self)
        self.role_combo.addItems(["admin", "agent"])
        self.role_combo.setStyleSheet(_INPUT_STYLE)
        idx = self.role_combo.findText(role or "agent")
        if idx >= 0:
            self.role_combo.setCurrentIndex(idx)

        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.addRow("Utilisateur :", self.username_edit)
        form.addRow("Rôle :", self.role_combo)
        lbl_pwd = "Mot de passe :" if with_password else "Nouveau mot de passe :"
        form.addRow(lbl_pwd, self.password_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            orientation=Qt.Orientation.Horizontal,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(_BTN_PRIMARY)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(_BTN_NEUTRAL)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        main = QVBoxLayout(self)
        main.setContentsMargins(20, 18, 20, 16)
        main.setSpacing(14)
        main.addLayout(form)
        main.addWidget(buttons)

    def get_data(self) -> tuple[str, Optional[str], str]:
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()
        role = self.role_combo.currentText().strip() or "agent"
        if not username:
            raise ValueError("Le nom d'utilisateur est obligatoire.")
        if self._with_password and not password:
            raise ValueError("Le mot de passe est obligatoire.")
        return username, (password or None), role


# ── Widget principal ─────────────────────────────────────────────────────────

class UsersWidget(QWidget):
    """Page Utilisateurs : onglet gestion des comptes + onglet configuration BDD."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._users: list[tuple[int, str, str]] = []
        self._build_ui()
        self._refresh_table()

    # ── Construction UI ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        tabs = QTabWidget(self)
        tabs.setStyleSheet(
            "QTabWidget::pane { border: none; background: #f8fafc; }"
            "QTabBar::tab {"
            "  background: #e2e8f0; color: #374151; border: none;"
            "  padding: 8px 20px; font-size: 12px; font-weight: 600;"
            "  border-top-left-radius: 6px; border-top-right-radius: 6px;"
            "  margin-right: 2px;"
            "}"
            "QTabBar::tab:selected { background: #1e3a5f; color: white; }"
            "QTabBar::tab:hover:!selected { background: #cbd5e1; }"
        )

        # ── Onglet 1 : Gestion des utilisateurs ──────────────────────────
        users_tab = QWidget()
        self._build_users_tab(users_tab)
        tabs.addTab(users_tab, "👤  Utilisateurs")

        # ── Onglet 2 : Configuration base de données ──────────────────────
        db_tab = QWidget()
        self._build_db_config_tab(db_tab)
        tabs.addTab(db_tab, "🗄  Base de données")

        root.addWidget(tabs)

    # ── Onglet Utilisateurs ───────────────────────────────────────────────────

    def _build_users_tab(self, container: QWidget) -> None:
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Bandeau en-tête
        header = QFrame()
        header.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #1e3a5f, stop:1 #2a4f80); }"
        )
        h_box = QHBoxLayout(header)
        h_box.setContentsMargins(20, 14, 20, 14)
        h_box.setSpacing(16)

        lbl_title = QLabel("👤  Gestion des utilisateurs")
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        lbl_title.setFont(f)
        lbl_title.setStyleSheet("color: white; background: transparent;")

        self._stat_total = QLabel("Total : 0")
        self._stat_admin = QLabel("Admins : 0")
        self._stat_agent = QLabel("Agents : 0")
        for lbl in (self._stat_total, self._stat_admin, self._stat_agent):
            lbl.setStyleSheet(
                "color: #93c5fd; font-size: 12px; font-weight: 600;"
                " background: transparent;"
            )

        h_box.addWidget(lbl_title)
        h_box.addStretch(1)
        h_box.addWidget(self._stat_total)
        h_box.addWidget(self._stat_admin)
        h_box.addWidget(self._stat_agent)
        root.addWidget(header)

        # Corps
        body = QFrame()
        body.setStyleSheet("QFrame { background: #f8fafc; }")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 14, 16, 14)
        body_layout.setSpacing(10)

        # Barre recherche + filtre + bouton Ajouter
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.search_edit = QLineEdit(container)
        self.search_edit.setPlaceholderText("🔍  Rechercher un utilisateur…")
        self.search_edit.setStyleSheet(_INPUT_STYLE)
        self.search_edit.textChanged.connect(self._on_filters_changed)
        top_bar.addWidget(self.search_edit, 3)

        self.role_filter = QComboBox(container)
        self.role_filter.setStyleSheet(_INPUT_STYLE)
        self.role_filter.addItem("Tous les rôles", None)
        self.role_filter.addItem("Administrateurs", "admin")
        self.role_filter.addItem("Agents", "agent")
        self.role_filter.currentIndexChanged.connect(self._on_filters_changed)
        top_bar.addWidget(self.role_filter, 1)

        self.add_btn = QPushButton("＋  Ajouter")
        self.add_btn.setStyleSheet(_BTN_PRIMARY)
        self.add_btn.setMinimumHeight(34)
        self.add_btn.clicked.connect(self._on_add_clicked)
        top_bar.addWidget(self.add_btn)

        body_layout.addLayout(top_bar)

        # Tableau
        self.table = QTableWidget(container)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["ID", "Utilisateur", "Rôle"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setColumnHidden(0, True)
        self.table.setStyleSheet(
            "QTableWidget {"
            "  background: white; border: 1px solid #e5e7eb;"
            "  border-radius: 8px; font-size: 13px; color: #1f2937;"
            "}"
            "QTableWidget::item { padding: 8px 12px; border: none; }"
            "QTableWidget::item:selected {"
            "  background: #dbeafe; color: #1e3a5f; border: none;"
            "}"
            "QHeaderView::section {"
            "  background: #1e3a5f; color: white; font-weight: 700;"
            "  font-size: 12px; padding: 8px 12px; border: none;"
            "}"
            "QTableWidget QTableCornerButton::section { background: #1e3a5f; }"
            "QTableWidget::item:alternate { background: #f1f5f9; }"
        )
        self.table.verticalHeader().setDefaultSectionSize(42)
        header_h = self.table.horizontalHeader()
        header_h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header_h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        body_layout.addWidget(self.table, 1)

        # Barre d'actions (bas)
        actions_bar = QHBoxLayout()
        actions_bar.setSpacing(8)

        self.edit_btn = QPushButton("✏  Modifier")
        self.edit_btn.setStyleSheet(_BTN_SUCCESS)
        self.edit_btn.setMinimumHeight(34)
        self.edit_btn.clicked.connect(self._on_edit_clicked)

        self.delete_btn = QPushButton("🗑  Supprimer")
        self.delete_btn.setStyleSheet(_BTN_DANGER)
        self.delete_btn.setMinimumHeight(34)
        self.delete_btn.clicked.connect(self._on_delete_clicked)

        self.reset_pwd_btn = QPushButton("🔑  Réinitialiser mot de passe")
        self.reset_pwd_btn.setStyleSheet(_BTN_NEUTRAL)
        self.reset_pwd_btn.setMinimumHeight(34)
        self.reset_pwd_btn.clicked.connect(self._on_reset_password_clicked)

        actions_bar.addWidget(self.edit_btn)
        actions_bar.addWidget(self.delete_btn)
        actions_bar.addWidget(self.reset_pwd_btn)
        actions_bar.addStretch(1)

        body_layout.addLayout(actions_bar)
        root.addWidget(body, 1)

    # ── Onglet Configuration BDD ──────────────────────────────────────────────

    def _build_db_config_tab(self, container: QWidget) -> None:
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Bandeau en-tête
        header = QFrame()
        header.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #1e3a5f, stop:1 #2a4f80); }"
        )
        h_box = QHBoxLayout(header)
        h_box.setContentsMargins(20, 14, 20, 14)

        lbl_title = QLabel("🗄  Configuration de la base de données")
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        lbl_title.setFont(f)
        lbl_title.setStyleSheet("color: white; background: transparent;")
        h_box.addWidget(lbl_title)
        h_box.addStretch(1)
        root.addWidget(header)

        # Corps
        body = QFrame()
        body.setStyleSheet("QFrame { background: #f8fafc; }")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(24, 20, 24, 20)
        body_layout.setSpacing(16)

        # ── Chemin actif + statut ─────────────────────────────────────────
        self._active_frame = QFrame()
        active_layout = QHBoxLayout(self._active_frame)
        active_layout.setContentsMargins(12, 10, 12, 10)
        active_layout.setSpacing(10)

        self._lbl_active_icon = QLabel("●")
        self._lbl_active_icon.setStyleSheet(
            "font-size: 16px; background: transparent; border: none;"
        )
        self._lbl_active_icon.setFixedWidth(18)

        info_col = QVBoxLayout()
        info_col.setSpacing(2)

        lbl_active_title = QLabel("Chemin actif :")
        lbl_active_title.setStyleSheet(
            "color: #374151; font-weight: 700; font-size: 11px;"
            " background: transparent; border: none;"
        )
        self._lbl_active_path = QLabel(str(_db_conn.DB_PATH))
        self._lbl_active_path.setStyleSheet(
            "font-size: 12px; font-family: monospace;"
            " background: transparent; border: none;"
        )
        self._lbl_active_path.setWordWrap(True)

        self._lbl_active_status = QLabel("")
        self._lbl_active_status.setStyleSheet(
            "font-size: 11px; background: transparent; border: none;"
        )

        info_col.addWidget(lbl_active_title)
        info_col.addWidget(self._lbl_active_path)
        info_col.addWidget(self._lbl_active_status)

        active_layout.addWidget(self._lbl_active_icon)
        active_layout.addLayout(info_col, 1)
        body_layout.addWidget(self._active_frame)

        # Vérification automatique du chemin actif au démarrage
        self._check_active_path()

        # ── Groupe : Serveur partagé ──────────────────────────────────────
        self._radio_group = QButtonGroup(container)

        network_group = QGroupBox("Serveur partagé (réseau)")
        network_group.setStyleSheet(
            "QGroupBox { font-weight: 700; font-size: 13px; color: #1e3a5f;"
            " border: 1px solid #cbd5e1; border-radius: 8px; margin-top: 8px;"
            " background: white; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px;"
            " padding: 0 6px; }"
        )
        net_layout = QVBoxLayout(network_group)
        net_layout.setContentsMargins(16, 14, 16, 14)
        net_layout.setSpacing(8)

        self._radio_network = QRadioButton("Utiliser le serveur partagé")
        self._radio_network.setStyleSheet("font-size: 12px; color: #374151;")
        self._radio_group.addButton(self._radio_network, 0)
        net_layout.addWidget(self._radio_network)

        # Chemin réseau
        net_path_row = QHBoxLayout()
        lbl_net = QLabel("Chemin :")
        lbl_net.setStyleSheet("color: #374151; font-size: 12px; min-width: 60px;")
        self._network_path_edit = QLineEdit()
        self._network_path_edit.setStyleSheet(_INPUT_STYLE)
        self._network_path_edit.setPlaceholderText(
            r"\\serveur\partage\dossier\disa.db"
        )
        self._network_path_edit.setText(_DEFAULT_NETWORK_PATH)

        btn_browse_net = QPushButton("📂")
        btn_browse_net.setFixedWidth(36)
        btn_browse_net.setMinimumHeight(32)
        btn_browse_net.setStyleSheet(_BTN_NEUTRAL)
        btn_browse_net.setToolTip("Parcourir…")
        btn_browse_net.clicked.connect(self._browse_network_path)

        net_path_row.addWidget(lbl_net)
        net_path_row.addWidget(self._network_path_edit, 1)
        net_path_row.addWidget(btn_browse_net)
        net_layout.addLayout(net_path_row)

        # Suggestions rapides
        quick_row = QHBoxLayout()
        lbl_quick = QLabel("Raccourcis :")
        lbl_quick.setStyleSheet("color: #6b7280; font-size: 11px; min-width: 60px;")
        btn_accueil = QPushButton("accueil")
        btn_reseau = QPushButton("reseau")
        for btn in (btn_accueil, btn_reseau):
            btn.setStyleSheet(
                "QPushButton { background: #e0e7ff; color: #3730a3; border-radius: 4px;"
                " padding: 3px 10px; font-size: 11px; font-weight: 600; }"
                "QPushButton:hover { background: #c7d2fe; }"
            )
            btn.setMaximumHeight(26)
        btn_accueil.clicked.connect(
            lambda: self._network_path_edit.setText(_DEFAULT_NETWORK_PATH)
        )
        btn_reseau.clicked.connect(
            lambda: self._network_path_edit.setText(_DEFAULT_NETWORK_PATH2)
        )
        quick_row.addWidget(lbl_quick)
        quick_row.addWidget(btn_accueil)
        quick_row.addWidget(btn_reseau)
        quick_row.addStretch(1)
        net_layout.addLayout(quick_row)

        body_layout.addWidget(network_group)

        # ── Groupe : Local ────────────────────────────────────────────────
        local_group = QGroupBox("Local (sur cet ordinateur)")
        local_group.setStyleSheet(
            "QGroupBox { font-weight: 700; font-size: 13px; color: #1e3a5f;"
            " border: 1px solid #cbd5e1; border-radius: 8px; margin-top: 8px;"
            " background: white; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px;"
            " padding: 0 6px; }"
        )
        loc_layout = QVBoxLayout(local_group)
        loc_layout.setContentsMargins(16, 14, 16, 14)
        loc_layout.setSpacing(8)

        self._radio_local = QRadioButton("Utiliser la base locale")
        self._radio_local.setStyleSheet("font-size: 12px; color: #374151;")
        self._radio_group.addButton(self._radio_local, 1)
        loc_layout.addWidget(self._radio_local)

        loc_path_row = QHBoxLayout()
        lbl_loc = QLabel("Chemin :")
        lbl_loc.setStyleSheet("color: #374151; font-size: 12px; min-width: 60px;")
        self._local_path_edit = QLineEdit()
        self._local_path_edit.setStyleSheet(_INPUT_STYLE)
        self._local_path_edit.setText(str(_db_conn._DEFAULT_DB_PATH))

        btn_browse_loc = QPushButton("📂")
        btn_browse_loc.setFixedWidth(36)
        btn_browse_loc.setMinimumHeight(32)
        btn_browse_loc.setStyleSheet(_BTN_NEUTRAL)
        btn_browse_loc.setToolTip("Parcourir…")
        btn_browse_loc.clicked.connect(self._browse_local_path)

        loc_path_row.addWidget(lbl_loc)
        loc_path_row.addWidget(self._local_path_edit, 1)
        loc_path_row.addWidget(btn_browse_loc)
        loc_layout.addLayout(loc_path_row)

        body_layout.addWidget(local_group)

        # ── Boutons d'action ──────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_test = QPushButton("🔌  Tester la connexion")
        btn_test.setStyleSheet(_BTN_WARNING)
        btn_test.setMinimumHeight(36)
        btn_test.clicked.connect(self._on_test_connection)

        btn_save = QPushButton("💾  Enregistrer et appliquer")
        btn_save.setStyleSheet(_BTN_PRIMARY)
        btn_save.setMinimumHeight(36)
        btn_save.clicked.connect(self._on_save_db_config)

        btn_row.addStretch(1)
        btn_row.addWidget(btn_test)
        btn_row.addWidget(btn_save)
        body_layout.addLayout(btn_row)

        # ── Statut ────────────────────────────────────────────────────────
        self._lbl_db_status = QLabel("")
        self._lbl_db_status.setWordWrap(True)
        self._lbl_db_status.setStyleSheet(
            "QLabel { font-size: 12px; padding: 8px 12px;"
            " border-radius: 6px; background: transparent; }"
        )
        body_layout.addWidget(self._lbl_db_status)

        body_layout.addStretch(1)
        root.addWidget(body, 1)

        # ── Initialisation de l'état des boutons radio ────────────────────
        current = str(_db_conn.DB_PATH)
        if current.startswith("\\\\") or current.startswith("//"):
            self._radio_network.setChecked(True)
            self._network_path_edit.setText(current)
        else:
            self._radio_local.setChecked(True)
            self._local_path_edit.setText(current)

    # ── Logique configuration BDD ─────────────────────────────────────────────

    def _selected_db_path(self) -> str:
        """Retourne le chemin sélectionné selon le bouton radio actif."""
        if self._radio_network.isChecked():
            return self._network_path_edit.text().strip()
        return self._local_path_edit.text().strip()

    def _browse_network_path(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Choisir le fichier de base de données", "", "SQLite (*.db *.sqlite)"
        )
        if path:
            self._network_path_edit.setText(path)
            self._radio_network.setChecked(True)

    def _browse_local_path(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Choisir le fichier de base de données",
            self._local_path_edit.text(), "SQLite (*.db *.sqlite)"
        )
        if path:
            self._local_path_edit.setText(path)
            self._radio_local.setChecked(True)

    # ── Test de connexion ────────────────────────────────────────────────────

    def _diagnose_path(self, path_str: str) -> str | None:
        """Retourne un message d'erreur précis si le chemin pose problème, sinon None."""
        p = Path(path_str)

        # Chemin vide
        if not path_str:
            return "Le chemin est vide."

        # Chemin réseau : vérifier si le dossier parent est accessible
        is_net = path_str.startswith("\\\\") or path_str.startswith("//")
        if is_net:
            parent = p.parent
            try:
                parent.stat()
            except FileNotFoundError:
                return (
                    f"Le dossier réseau est introuvable : {parent}\n"
                    "Vérifiez que le serveur est accessible et que le partage existe."
                )
            except PermissionError:
                return (
                    f"Accès refusé au dossier réseau : {parent}\n"
                    "Vérifiez vos droits d'accès sur ce partage."
                )
            except OSError as e:
                return f"Erreur réseau : {e}"
        else:
            # Chemin local : vérifier que le dossier parent existe
            if not p.parent.exists():
                return (
                    f"Le dossier n'existe pas : {p.parent}\n"
                    "Créez ce dossier ou choisissez un autre emplacement."
                )
            if not p.parent.is_dir():
                return f"Le chemin parent n'est pas un dossier : {p.parent}"

        # Si le fichier existe, vérifier que c'est bien une base SQLite
        if p.exists():
            if not p.is_file():
                return f"Le chemin pointe vers un dossier, pas un fichier : {path_str}"
            try:
                with open(p, "rb") as fh:
                    header = fh.read(16)
                if header[:6] != b"SQLite":
                    return (
                        "Le fichier existe mais n'est pas une base SQLite valide.\n"
                        "Vérifiez que vous avez sélectionné le bon fichier."
                    )
            except PermissionError:
                return (
                    f"Accès refusé en lecture : {path_str}\n"
                    "Vérifiez les droits sur ce fichier."
                )
            except OSError as e:
                return f"Impossible de lire le fichier : {e}"

        return None  # Aucun problème détecté

    def _try_connect(self, path_str: str, timeout: float = 5.0) -> tuple[bool, str]:
        """Tente une connexion SQLite. Retourne (succès, message)."""
        result: list = [None, None]  # [bool ok, str msg]

        def _worker():
            try:
                conn = sqlite3.connect(path_str, timeout=timeout)
                conn.execute("SELECT 1")
                conn.close()
                result[0] = True
                result[1] = "OK"
            except sqlite3.DatabaseError as exc:
                result[0] = False
                result[1] = f"Fichier corrompu ou invalide : {exc}"
            except PermissionError as exc:
                result[0] = False
                result[1] = f"Accès refusé : {exc}"
            except OSError as exc:
                result[0] = False
                result[1] = f"Erreur système : {exc}"
            except Exception as exc:
                result[0] = False
                result[1] = str(exc)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join(timeout=timeout + 1)

        if t.is_alive():
            return False, (
                "Délai de connexion dépassé — le serveur ne répond pas.\n"
                "Vérifiez que le réseau est disponible et que le chemin est correct."
            )
        return bool(result[0]), result[1]

    def _on_test_connection(self) -> None:
        """Teste la connexion vers le chemin sélectionné sans l'enregistrer."""
        path_str = self._selected_db_path()
        if not path_str:
            self._set_status("⚠  Veuillez saisir un chemin.", error=True)
            return

        self._set_status("⏳  Test de connexion en cours…", error=False, neutral=True)

        # Diagnostic rapide avant de tenter la connexion
        diag = self._diagnose_path(path_str)
        if diag:
            self._set_status(f"✗  Base de données non trouvée\n\n{diag}", error=True)
            return

        # Tentative de connexion réelle
        ok, msg = self._try_connect(path_str)
        if ok:
            p = Path(path_str)
            size_info = ""
            try:
                if p.exists():
                    kb = p.stat().st_size / 1024
                    size_info = f"  —  {kb:.1f} Ko"
            except Exception:
                pass
            self._set_status(
                f"✔  Connexion réussie{size_info}\n{path_str}",
                error=False,
            )
        else:
            self._set_status(
                f"✗  Impossible de se connecter à la base de données\n\n{msg}\n\nChemin : {path_str}",
                error=True,
            )

    def _check_active_path(self) -> None:
        """Vérifie silencieusement le chemin actif et colore le bandeau en conséquence."""
        path_str = str(_db_conn.DB_PATH)

        def _worker():
            diag = self._diagnose_path(path_str)
            if diag:
                return False, diag
            ok, msg = self._try_connect(path_str, timeout=3.0)
            return ok, msg

        result: list = [None, None]

        def run():
            result[0], result[1] = _worker()

        t = threading.Thread(target=run, daemon=True)
        t.start()
        t.join(timeout=4)

        if t.is_alive() or result[0] is None:
            ok, msg = False, "Vérification expirée — serveur inaccessible."
        else:
            ok, msg = result[0], result[1]

        self._apply_active_frame_state(ok, msg)

    def _apply_active_frame_state(self, ok: bool, msg: str) -> None:
        """Met à jour visuellement le bandeau du chemin actif."""
        if ok:
            self._active_frame.setStyleSheet(
                "QFrame { background: #dcfce7; border: 1px solid #86efac;"
                " border-radius: 8px; }"
            )
            self._lbl_active_icon.setStyleSheet(
                "color: #16a34a; font-size: 16px; background: transparent; border: none;"
            )
            self._lbl_active_path.setStyleSheet(
                "color: #166534; font-size: 12px; font-family: monospace;"
                " background: transparent; border: none;"
            )
            self._lbl_active_status.setText("✔  Base de données accessible")
            self._lbl_active_status.setStyleSheet(
                "color: #15803d; font-size: 11px; font-weight: 600;"
                " background: transparent; border: none;"
            )
        else:
            self._active_frame.setStyleSheet(
                "QFrame { background: #fee2e2; border: 2px solid #f87171;"
                " border-radius: 8px; }"
            )
            self._lbl_active_icon.setStyleSheet(
                "color: #dc2626; font-size: 16px; background: transparent; border: none;"
            )
            self._lbl_active_path.setStyleSheet(
                "color: #991b1b; font-size: 12px; font-family: monospace;"
                " background: transparent; border: none;"
            )
            self._lbl_active_status.setText(f"✗  {msg.splitlines()[0]}")
            self._lbl_active_status.setStyleSheet(
                "color: #b91c1c; font-size: 11px; font-weight: 600;"
                " background: transparent; border: none;"
            )

    # ── Enregistrement ───────────────────────────────────────────────────────

    def _on_save_db_config(self) -> None:
        """Teste, enregistre le chemin dans disa.conf et met à jour DB_PATH en mémoire."""
        path_str = self._selected_db_path()
        if not path_str:
            self._set_status("⚠  Veuillez saisir un chemin.", error=True)
            return

        # Test préalable avant enregistrement
        self._set_status("⏳  Vérification avant enregistrement…", error=False, neutral=True)
        diag = self._diagnose_path(path_str)
        if diag:
            self._set_status(
                f"✗  Enregistrement annulé — base de données non trouvée\n\n{diag}",
                error=True,
            )
            return

        ok, msg = self._try_connect(path_str)
        if not ok:
            # Avertir mais laisser l'option de forcer l'enregistrement
            reply = QMessageBox.warning(
                self,
                "Connexion échouée",
                f"La base de données est inaccessible :\n\n{msg}\n\n"
                "Voulez-vous enregistrer ce chemin quand même ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._set_status(
                    f"✗  Enregistrement annulé — base inaccessible\n\n{msg}",
                    error=True,
                )
                return

        import contextlib
        lines: list[str] = []
        if (conf_path := _db_conn.PROJECT_ROOT / "disa.conf").exists():
            with contextlib.suppress(Exception):
                lines = conf_path.read_text(encoding="utf-8").splitlines()

        new_lines: list[str] = [
            ln for ln in lines if not ln.strip().startswith("DB_PATH=")
        ]
        new_lines.append(f"DB_PATH={path_str}")

        try:
            conf_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        except Exception as exc:
            self._set_status(f"✗  Impossible d'écrire disa.conf : {exc}", error=True)
            return

        # Mettre à jour DB_PATH en mémoire
        _db_conn.DB_PATH = Path(path_str)
        self._lbl_active_path.setText(path_str)
        self._check_active_path()

        self._set_status(
            f"✔  Configuration enregistrée avec succès.\n"
            f"   Chemin actif : {path_str}\n"
            "   Redémarrez l'application pour que tous les modules utilisent ce chemin.",
            error=False,
        )

    def _set_status(self, msg: str, *, error: bool, neutral: bool = False) -> None:
        self._lbl_db_status.setText(msg)
        if neutral:
            style = (
                "QLabel { font-size: 12px; padding: 10px 14px; border-radius: 6px;"
                " background: #fef9c3; color: #713f12; border: 1px solid #fde68a; }"
            )
        elif error:
            style = (
                "QLabel { font-size: 12px; padding: 10px 14px; border-radius: 6px;"
                " background: #fee2e2; color: #7f1d1d; border: 2px solid #f87171;"
                " font-weight: 500; }"
            )
        else:
            style = (
                "QLabel { font-size: 12px; padding: 10px 14px; border-radius: 6px;"
                " background: #dcfce7; color: #14532d; border: 1px solid #86efac;"
                " font-weight: 500; }"
            )
        self._lbl_db_status.setStyleSheet(style)

    # ── Données utilisateurs ──────────────────────────────────────────────────

    def _load_users_from_db(self) -> None:
        self._users.clear()
        try:
            conn = get_connection()
            with conn:
                cur = conn.cursor()
                cur.execute("SELECT id, username, role FROM utilisateurs ORDER BY id DESC")
                for uid, uname, urole in cur.fetchall():
                    self._users.append((int(uid), str(uname), str(urole)))
        except Exception as exc:
            QMessageBox.critical(self, "Erreur base de données",
                                 f"Impossible de charger les utilisateurs :\n{exc}")

    def _apply_filters(self) -> list[tuple[int, str, str]]:
        search = self.search_edit.text().strip().lower()
        role_filter = self.role_filter.currentData()
        result = []
        for user_id, username, role in self._users:
            if role_filter is not None and role != role_filter:
                continue
            if search and search not in username.lower() and search not in role.lower():
                continue
            result.append((user_id, username, role))
        return result

    def _refresh_table(self) -> None:
        self._load_users_from_db()
        filtered = self._apply_filters()

        all_roles = [r for _, _, r in self._users]
        self._stat_total.setText(f"Total : {len(self._users)}")
        self._stat_admin.setText(f"Admins : {all_roles.count('admin')}")
        self._stat_agent.setText(f"Agents : {all_roles.count('agent')}")

        current = get_current_user()
        current_id = current.id if current else None

        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(filtered))

        for row_idx, (user_id, username, role) in enumerate(filtered):
            is_me = current_id is not None and user_id == current_id

            id_item = QTableWidgetItem(str(user_id))
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 0, id_item)

            display_name = f"★  {username}  (vous)" if is_me else f"   {username}"
            user_item = QTableWidgetItem(display_name)
            if is_me:
                f = user_item.font()
                f.setBold(True)
                user_item.setFont(f)
                user_item.setForeground(QColor("#1e3a5f"))
            self.table.setItem(row_idx, 1, user_item)

            role_item = QTableWidgetItem(f"  {role.upper()}  ")
            role_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            rf = role_item.font()
            rf.setBold(True)
            rf.setPointSize(10)
            role_item.setFont(rf)
            if role == "admin":
                role_item.setForeground(QColor("#ffffff"))
                role_item.setBackground(QColor("#1e3a5f"))
            else:
                role_item.setForeground(QColor("#ffffff"))
                role_item.setBackground(QColor("#15803d"))
            self.table.setItem(row_idx, 2, role_item)

        self.table.setSortingEnabled(True)
        self.table.resizeColumnToContents(2)

    def _on_filters_changed(self) -> None:
        self._refresh_table()

    def _get_selected_user_id(self) -> Optional[int]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        try:
            return int(item.text())
        except ValueError:
            return None

    # ── Actions utilisateurs ──────────────────────────────────────────────────

    def _on_add_clicked(self) -> None:
        dialog = UserFormDialog(self, with_password=True)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            username, password, role = dialog.get_data()
        except ValueError as exc:
            QMessageBox.warning(self, "Utilisateur", str(exc))
            return
        try:
            conn = get_connection()
            with conn:
                conn.cursor().execute(
                    "INSERT INTO utilisateurs (username, password, role) VALUES (?, ?, ?)",
                    (username, password, role),
                )
        except Exception as exc:
            QMessageBox.critical(self, "Utilisateur",
                                 f"Impossible d'ajouter l'utilisateur :\n{exc}")
            return
        self._refresh_table()

    def _on_edit_clicked(self) -> None:
        user_id = self._get_selected_user_id()
        if user_id is None:
            QMessageBox.information(self, "Modification",
                                    "Sélectionnez d'abord un utilisateur à modifier.")
            return
        try:
            conn = get_connection()
            with conn:
                row = conn.cursor().execute(
                    "SELECT username, role FROM utilisateurs WHERE id = ?", (user_id,)
                ).fetchone()
        except Exception as exc:
            QMessageBox.critical(self, "Utilisateur",
                                 f"Impossible de lire l'utilisateur :\n{exc}")
            return
        if row is None:
            QMessageBox.warning(self, "Modification", "L'utilisateur n'existe plus.")
            return

        username, role = row
        is_admin = str(role) == "admin"
        admin_count: Optional[int] = None
        if is_admin:
            try:
                conn = get_connection()
                with conn:
                    (admin_count,) = conn.cursor().execute(
                        "SELECT COUNT(*) FROM utilisateurs WHERE role = 'admin'"
                    ).fetchone() or (0,)
            except Exception:
                admin_count = None

        dialog = UserFormDialog(self, username=str(username), role=str(role), with_password=False)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            new_username, new_password, new_role = dialog.get_data()
        except ValueError as exc:
            if "mot de passe" in str(exc).lower():
                new_password = None
                new_username = dialog.username_edit.text().strip()
                new_role = dialog.role_combo.currentText().strip() or "agent"
            else:
                QMessageBox.warning(self, "Utilisateur", str(exc))
                return

        if is_admin and admin_count is not None and int(admin_count) <= 1 and new_role != "admin":
            QMessageBox.warning(
                self, "Rôle",
                "Vous ne pouvez pas retirer le rôle administrateur au dernier admin."
            )
            return

        set_parts = ["username = ?", "role = ?"]
        params: list[object] = [new_username, new_role]
        if new_password:
            set_parts.append("password = ?")
            params.append(new_password)
        params.append(user_id)

        try:
            conn = get_connection()
            with conn:
                conn.cursor().execute(
                    "UPDATE utilisateurs SET " + ", ".join(set_parts) + " WHERE id = ?",
                    params,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Utilisateur",
                                 f"Impossible de modifier l'utilisateur :\n{exc}")
            return
        self._refresh_table()

    def _on_delete_clicked(self) -> None:
        user_id = self._get_selected_user_id()
        if user_id is None:
            QMessageBox.information(self, "Suppression",
                                    "Sélectionnez d'abord un utilisateur à supprimer.")
            return

        current = get_current_user()
        if current is not None and current.id == user_id:
            QMessageBox.warning(self, "Suppression",
                                "Vous ne pouvez pas supprimer votre propre compte.")
            return

        try:
            conn = get_connection()
            with conn:
                cur = conn.cursor()
                row = cur.execute(
                    "SELECT role FROM utilisateurs WHERE id = ?", (user_id,)
                ).fetchone()
                if row is None:
                    QMessageBox.warning(self, "Suppression", "L'utilisateur n'existe plus.")
                    return
                if str(row[0]) == "admin":
                    (admin_count,) = cur.execute(
                        "SELECT COUNT(*) FROM utilisateurs WHERE role = 'admin'"
                    ).fetchone() or (0,)
                    if int(admin_count) <= 1:
                        QMessageBox.warning(
                            self, "Suppression",
                            "Vous ne pouvez pas supprimer le dernier administrateur."
                        )
                        return
        except Exception as exc:
            QMessageBox.critical(self, "Utilisateur",
                                 f"Erreur lors du contrôle :\n{exc}")
            return

        reply = QMessageBox.question(
            self, "Confirmer la suppression",
            "Voulez-vous vraiment supprimer cet utilisateur ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            conn = get_connection()
            with conn:
                conn.cursor().execute(
                    "DELETE FROM utilisateurs WHERE id = ?", (user_id,)
                )
        except Exception as exc:
            QMessageBox.critical(self, "Utilisateur",
                                 f"Impossible de supprimer l'utilisateur :\n{exc}")
            return
        self._refresh_table()

    def _on_reset_password_clicked(self) -> None:
        user_id = self._get_selected_user_id()
        if user_id is None:
            QMessageBox.information(self, "Mot de passe",
                                    "Sélectionnez d'abord un utilisateur.")
            return
        try:
            conn = get_connection()
            with conn:
                row = conn.cursor().execute(
                    "SELECT username, role FROM utilisateurs WHERE id = ?", (user_id,)
                ).fetchone()
        except Exception as exc:
            QMessageBox.critical(self, "Mot de passe",
                                 f"Impossible de lire l'utilisateur :\n{exc}")
            return
        if row is None:
            QMessageBox.warning(self, "Mot de passe", "L'utilisateur n'existe plus.")
            return

        username, role = row
        dialog = UserFormDialog(self, username=str(username), role=str(role), with_password=True)
        dialog.setWindowTitle("Réinitialiser le mot de passe")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            _u, new_password, _r = dialog.get_data()
        except ValueError as exc:
            QMessageBox.warning(self, "Mot de passe", str(exc))
            return

        try:
            conn = get_connection()
            with conn:
                conn.cursor().execute(
                    "UPDATE utilisateurs SET password = ? WHERE id = ?",
                    (new_password, user_id),
                )
        except Exception as exc:
            QMessageBox.critical(self, "Mot de passe",
                                 f"Impossible de mettre à jour :\n{exc}")
            return

        QMessageBox.information(self, "Mot de passe", "Le mot de passe a été mis à jour.")
        self._refresh_table()
