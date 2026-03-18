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
)

from db.connection import get_connection
from core.session import get_current_user


# ── Styles partagés ──────────────────────────────────────────────────────────

_BTN_PRIMARY = (
    "QPushButton { background:#1e3a5f; color:white; border-radius:5px;"
    " padding:6px 14px; font-weight:600; font-size:12px; }"
    "QPushButton:hover { background:#2a4f80; }"
    "QPushButton:pressed { background:#16294a; }"
)
_BTN_SUCCESS = (
    "QPushButton { background:#15803d; color:white; border-radius:5px;"
    " padding:6px 14px; font-weight:600; font-size:12px; }"
    "QPushButton:hover { background:#16a34a; }"
    "QPushButton:pressed { background:#0f5c2c; }"
)
_BTN_DANGER = (
    "QPushButton { background:#b91c1c; color:white; border-radius:5px;"
    " padding:6px 14px; font-weight:600; font-size:12px; }"
    "QPushButton:hover { background:#dc2626; }"
    "QPushButton:pressed { background:#991b1b; }"
)
_BTN_NEUTRAL = (
    "QPushButton { background:#64748b; color:white; border-radius:5px;"
    " padding:6px 14px; font-weight:600; font-size:12px; }"
    "QPushButton:hover { background:#475569; }"
    "QPushButton:pressed { background:#334155; }"
)
_INPUT_STYLE = (
    "QLineEdit, QComboBox { border:1px solid #d1d5db; border-radius:5px;"
    " padding:6px 10px; font-size:12px; background:white; color:#111827; }"
    "QLineEdit:focus, QComboBox:focus { border:2px solid #1e3a5f; }"
)


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

        # ── Champs ──
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

        # ── Layout ──
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
    """Onglet Utilisateurs : gestion des comptes avec design amélioré."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._users: list[tuple[int, str, str]] = []  # (id, username, role)
        self._build_ui()
        self._refresh_table()

    # ── Construction UI ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Bandeau en-tête ──────────────────────────────────────────────
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

        # ── Corps ────────────────────────────────────────────────────────
        body = QFrame()
        body.setStyleSheet("QFrame { background: #f8fafc; }")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 14, 16, 14)
        body_layout.setSpacing(10)

        # Barre recherche + filtre + bouton Ajouter
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("🔍  Rechercher un utilisateur…")
        self.search_edit.setStyleSheet(_INPUT_STYLE)
        self.search_edit.textChanged.connect(self._on_filters_changed)
        top_bar.addWidget(self.search_edit, 3)

        self.role_filter = QComboBox(self)
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
        self.table = QTableWidget(self)
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

    # ── Données ──────────────────────────────────────────────────────────────

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

        # Mise à jour des stats en-tête
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

            # Col 0 : ID (caché)
            id_item = QTableWidgetItem(str(user_id))
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 0, id_item)

            # Col 1 : Nom utilisateur
            display_name = f"★  {username}  (vous)" if is_me else f"   {username}"
            user_item = QTableWidgetItem(display_name)
            if is_me:
                f = user_item.font()
                f.setBold(True)
                user_item.setFont(f)
                user_item.setForeground(QColor("#1e3a5f"))
            self.table.setItem(row_idx, 1, user_item)

            # Col 2 : Rôle (badge coloré)
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

    # ── Actions ──────────────────────────────────────────────────────────────

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
