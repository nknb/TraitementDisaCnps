from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
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
)

from db.connection import get_connection
from core.session import get_current_user


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
        self.setWindowTitle("Utilisateur - Assurés")
        self._with_password = with_password

        self.username_edit = QLineEdit(self)
        self.username_edit.setText(username)
        self.username_edit.setPlaceholderText("Identifiant (username)")

        self.password_edit = QLineEdit(self)
        self.password_edit.setPlaceholderText(
            "Mot de passe" if with_password else "Laisser vide pour ne pas changer"
        )
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.role_combo = QComboBox(self)
        self.role_combo.addItems(["admin", "agent"])
        index = self.role_combo.findText(role or "agent")
        if index >= 0:
            self.role_combo.setCurrentIndex(index)

        form = QFormLayout()
        form.addRow("Utilisateur :", self.username_edit)
        form.addRow("Rôle :", self.role_combo)
        if with_password:
            form.addRow("Mot de passe :", self.password_edit)
        else:
            form.addRow("Nouveau mot de passe :", self.password_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            orientation=Qt.Orientation.Horizontal,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def get_data(self) -> tuple[str, Optional[str], str]:
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()
        role = self.role_combo.currentText().strip() or "agent"
        if not username:
            raise ValueError("Le nom d'utilisateur est obligatoire.")
        if self._with_password and not password:
            raise ValueError("Le mot de passe est obligatoire.")
        return username, (password or None), role


class UsersWidget(QWidget):
    """Onglet Assuré : gestion moderne des utilisateurs (table utilisateurs)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._users: list[tuple[int, str, str]] = []  # (id, username, role)

        self._build_ui()
        self._refresh_table()

    # ------------------------------------------------------------------
    # Construction UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("Gestion des utilisateurs / Assurés")
        title.setStyleSheet("color: black; font-size: 16px; font-weight: 600;")
        layout.addWidget(title)

        # Barre de recherche + filtre de rôle
        filters_row = QHBoxLayout()

        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText("Rechercher un utilisateur (nom ou rôle)...")
        self.search_edit.textChanged.connect(self._on_filters_changed)
        filters_row.addWidget(self.search_edit, 2)

        self.role_filter = QComboBox(self)
        self.role_filter.addItem("Tous les rôles", None)
        self.role_filter.addItem("Administrateurs", "admin")
        self.role_filter.addItem("Agents", "agent")
        self.role_filter.currentIndexChanged.connect(self._on_filters_changed)
        filters_row.addWidget(self.role_filter, 1)

        layout.addLayout(filters_row)

        # Boutons d'action
        actions_row = QHBoxLayout()

        self.add_btn = QPushButton("Ajouter")
        self.add_btn.setIcon(QIcon(":/icon/icon/product-32.ico"))
        self.add_btn.setStyleSheet(
            "QPushButton { background-color: #2c3e50; color: white; border-radius: 4px; padding: 4px 10px; }"
            "QPushButton:hover { background-color: #34495e; }"
        )
        self.add_btn.clicked.connect(self._on_add_clicked)
        actions_row.addWidget(self.add_btn)

        self.edit_btn = QPushButton("Modifier")
        self.edit_btn.setIcon(QIcon(":/icon/icon/activity-feed-32.ico"))
        self.edit_btn.setStyleSheet(
            "QPushButton { background-color: #16a085; color: white; border-radius: 4px; padding: 4px 10px; }"
            "QPushButton:hover { background-color: #1abc9c; }"
        )
        self.edit_btn.clicked.connect(self._on_edit_clicked)
        actions_row.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Supprimer")
        self.delete_btn.setIcon(QIcon(":/icon/icon/close-window-64.ico"))
        self.delete_btn.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; border-radius: 4px; padding: 4px 10px; }"
            "QPushButton:hover { background-color: #e74c3c; }"
        )
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        actions_row.addWidget(self.delete_btn)

        self.reset_pwd_btn = QPushButton("Réinitialiser le mot de passe")
        self.reset_pwd_btn.setIcon(QIcon(":/icon/icon/dashboard-5-32.ico"))
        self.reset_pwd_btn.setStyleSheet(
            "QPushButton { background-color: #7f8c8d; color: white; border-radius: 4px; padding: 4px 10px; }"
            "QPushButton:hover { background-color: #95a5a6; }"
        )
        self.reset_pwd_btn.clicked.connect(self._on_reset_password_clicked)
        actions_row.addWidget(self.reset_pwd_btn)

        actions_row.addStretch(1)
        layout.addLayout(actions_row)

        # Tableau principal
        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["ID", "Utilisateur", "Rôle"])
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table, 1)

        # On cache la colonne ID pour une vue plus propre
        self.table.setColumnHidden(0, True)

    # ------------------------------------------------------------------
    # Chargement / filtrage
    # ------------------------------------------------------------------

    def _load_users_from_db(self) -> None:
        """Charge tous les utilisateurs depuis SQLite."""

        self._users.clear()

        try:
            conn = get_connection()
            with conn:
                cur = conn.cursor()
                cur.execute("SELECT id, username, role FROM utilisateurs ORDER BY id DESC")
                for user_id, username, role in cur.fetchall():
                    self._users.append((int(user_id), str(username), str(role)))
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(
                self,
                "Erreur base de données",
                f"Impossible de charger les utilisateurs :\n{exc}",
            )

    def _apply_filters(self) -> list[tuple[int, str, str]]:
        search = self.search_edit.text().strip().lower()
        role_filter = self.role_filter.currentData()

        result: list[tuple[int, str, str]] = []
        for user_id, username, role in self._users:
            if role_filter is not None and role != role_filter:
                continue
            if search and (search not in username.lower() and search not in role.lower()):
                continue
            result.append((user_id, username, role))
        return result

    def _refresh_table(self) -> None:
        self._load_users_from_db()
        filtered = self._apply_filters()

        self.table.setRowCount(len(filtered))
        for row_index, (user_id, username, role) in enumerate(filtered):
            id_item = QTableWidgetItem(str(user_id))
            id_item.setTextAlignment(Qt.AlignCenter)
            user_item = QTableWidgetItem(username)
            role_item = QTableWidgetItem(role)

            self.table.setItem(row_index, 0, id_item)
            self.table.setItem(row_index, 1, user_item)
            self.table.setItem(row_index, 2, role_item)

        self.table.resizeColumnsToContents()

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

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_add_clicked(self) -> None:
        dialog = UserFormDialog(self, with_password=True)
        if dialog.exec() != QDialog.Accepted:
            return

        try:
            username, password, role = dialog.get_data()
        except ValueError as exc:
            QMessageBox.warning(self, "Utilisateur", str(exc))
            return

        try:
            conn = get_connection()
            with conn:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO utilisateurs (username, password, role) VALUES (?, ?, ?)",
                    (username, password, role),
                )
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(
                self,
                "Utilisateur",
                f"Impossible d'ajouter l'utilisateur :\n{exc}",
            )
            return

        self._refresh_table()

    def _on_edit_clicked(self) -> None:
        user_id = self._get_selected_user_id()
        if user_id is None:
            QMessageBox.information(
                self,
                "Modification",
                "Sélectionnez d'abord un utilisateur à modifier.",
            )
            return

        try:
            conn = get_connection()
            with conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT username, role FROM utilisateurs WHERE id = ?",
                    (user_id,),
                )
                row = cur.fetchone()
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(
                self,
                "Utilisateur",
                f"Impossible de lire l'utilisateur :\n{exc}",
            )
            return

        if row is None:
            QMessageBox.warning(
                self,
                "Modification",
                "L'utilisateur sélectionné n'existe plus.",
            )
            return

        username, role = row

        # Protection : empêcher de retirer le dernier admin de son rôle via édition
        is_target_admin = str(role) == "admin"
        admin_count = None
        if is_target_admin:
            try:
                conn = get_connection()
                with conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT COUNT(*) FROM utilisateurs WHERE role = 'admin'",
                    )
                    (admin_count,) = cur.fetchone() or (0,)
            except Exception:
                admin_count = None
        dialog = UserFormDialog(self, username=str(username), role=str(role), with_password=False)
        if dialog.exec() != QDialog.Accepted:
            return

        try:
            new_username, new_password, new_role = dialog.get_data()
        except ValueError as exc:
            # En mode édition sans mot de passe obligatoire, on ignore l'erreur "mot de passe obligatoire"
            # et on laisse passer un mot de passe vide.
            if "mot de passe" in str(exc).lower():
                new_password = None
                new_username = dialog.username_edit.text().strip()
                new_role = dialog.role_combo.currentText().strip() or "agent"
            else:
                QMessageBox.warning(self, "Utilisateur", str(exc))
                return

        # Si on essaie de retirer le rôle admin au dernier administrateur, on bloque
        if is_target_admin and admin_count is not None and int(admin_count) <= 1 and new_role != "admin":
            QMessageBox.warning(
                self,
                "Rôle",
                "Vous ne pouvez pas retirer le rôle administrateur au dernier admin de l'application.",
            )
            return

        # Construction dynamique de la requête UPDATE
        set_parts = ["username = ?", "role = ?"]
        params: list[object] = [new_username, new_role]
        if new_password:
            set_parts.append("password = ?")
            params.append(new_password)
        params.append(user_id)

        sql = "UPDATE utilisateurs SET " + ", ".join(set_parts) + " WHERE id = ?"

        try:
            conn = get_connection()
            with conn:
                cur = conn.cursor()
                cur.execute(sql, params)
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(
                self,
                "Utilisateur",
                f"Impossible de modifier l'utilisateur :\n{exc}",
            )
            return

        self._refresh_table()

    def _on_delete_clicked(self) -> None:
        user_id = self._get_selected_user_id()
        if user_id is None:
            QMessageBox.information(
                self,
                "Suppression",
                "Sélectionnez d'abord un utilisateur à supprimer.",
            )
            return

        current = get_current_user()

        # Empêcher un utilisateur de se supprimer lui-même
        if current is not None and current.id == user_id:
            QMessageBox.warning(
                self,
                "Suppression",
                "Vous ne pouvez pas supprimer votre propre compte pendant que vous êtes connecté.",
            )
            return

        # Vérifier si l'utilisateur à supprimer est un admin et s'il est le dernier
        try:
            conn = get_connection()
            with conn:
                cur = conn.cursor()

                # Rôle de l'utilisateur ciblé
                cur.execute(
                    "SELECT role FROM utilisateurs WHERE id = ?",
                    (user_id,),
                )
                row = cur.fetchone()
                if row is None:
                    QMessageBox.warning(
                        self,
                        "Suppression",
                        "L'utilisateur sélectionné n'existe plus.",
                    )
                    return

                target_role = str(row[0] or "")

                if target_role == "admin":
                    # Combien d'admins au total ?
                    cur.execute(
                        "SELECT COUNT(*) FROM utilisateurs WHERE role = 'admin'",
                    )
                    (admin_count,) = cur.fetchone() or (0,)
                    if int(admin_count) <= 1:
                        QMessageBox.warning(
                            self,
                            "Suppression",
                            "Vous ne pouvez pas supprimer le dernier administrateur de l'application.",
                        )
                        return

        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(
                self,
                "Utilisateur",
                f"Erreur lors du contrôle des administrateurs :\n{exc}",
            )
            return

        reply = QMessageBox.question(
            self,
            "Confirmer la suppression",
            "Voulez-vous vraiment supprimer cet utilisateur ?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            conn = get_connection()
            with conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM utilisateurs WHERE id = ?", (user_id,))
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(
                self,
                "Utilisateur",
                f"Impossible de supprimer l'utilisateur :\n{exc}",
            )
            return

        self._refresh_table()

    def _on_reset_password_clicked(self) -> None:
        user_id = self._get_selected_user_id()
        if user_id is None:
            QMessageBox.information(
                self,
                "Mot de passe",
                "Sélectionnez d'abord un utilisateur.",
            )
            return

        # Charger username / rôle pour information
        try:
            conn = get_connection()
            with conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT username, role FROM utilisateurs WHERE id = ?",
                    (user_id,),
                )
                row = cur.fetchone()
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(
                self,
                "Mot de passe",
                f"Impossible de lire l'utilisateur :\n{exc}",
            )
            return

        if row is None:
            QMessageBox.warning(
                self,
                "Mot de passe",
                "L'utilisateur sélectionné n'existe plus.",
            )
            return

        username, role = row
        dialog = UserFormDialog(
            self,
            username=str(username),
            role=str(role),
            with_password=True,
        )
        dialog.setWindowTitle("Réinitialiser le mot de passe")
        if dialog.exec() != QDialog.Accepted:
            return

        try:
            _username, new_password, _role = dialog.get_data()
        except ValueError as exc:
            QMessageBox.warning(self, "Mot de passe", str(exc))
            return

        try:
            conn = get_connection()
            with conn:
                cur = conn.cursor()
                cur.execute(
                    "UPDATE utilisateurs SET password = ? WHERE id = ?",
                    (new_password, user_id),
                )
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(
                self,
                "Mot de passe",
                f"Impossible de mettre à jour le mot de passe :\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Mot de passe",
            "Le mot de passe a été mis à jour.",
        )
        self._refresh_table()
