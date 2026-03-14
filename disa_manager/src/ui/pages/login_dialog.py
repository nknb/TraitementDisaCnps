from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
)

from db.connection import get_connection
from core.session import set_current_user


class LoginDialog(QDialog):
    """Boîte de dialogue de connexion simple (login / mot de passe)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Connexion - Traitement DiSA")
        self.setModal(True)
        self.resize(320, 180)

        self.username_edit = QLineEdit(self)
        self.username_edit.setPlaceholderText("Identifiant utilisateur")

        self.password_edit = QLineEdit(self)
        self.password_edit.setPlaceholderText("Mot de passe")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self.info_label = QLabel("Veuillez saisir vos identifiants.", self)
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        form_layout = QFormLayout()
        form_layout.addRow("Utilisateur :", self.username_edit)
        form_layout.addRow("Mot de passe :", self.password_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            orientation=Qt.Orientation.Horizontal,
            parent=self,
        )
        buttons.accepted.connect(self.handle_login)
        buttons.rejected.connect(self.reject)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.info_label)
        main_layout.addLayout(form_layout)
        main_layout.addWidget(buttons)

    def handle_login(self) -> None:
        """Valide les identifiants via la base SQLite et ferme si OK."""

        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "Connexion", "Veuillez renseigner les deux champs.")
            return

        try:
            with get_connection() as conn:
                cur = conn.execute(
                    "SELECT id, username, password, role FROM utilisateurs WHERE username = ?",
                    (username,),
                )
                row = cur.fetchone()
        except Exception as exc:  # pragma: no cover - message utilisateur
            QMessageBox.critical(self, "Connexion", f"Erreur base de données : {exc}")
            return

        if row is None or row["password"] != password:
            QMessageBox.critical(self, "Connexion", "Identifiants incorrects.")
            return

        # Mémoriser l'utilisateur connecté pour le reste de l'application
        set_current_user(user_id=row["id"], username=row["username"], role=row["role"])

        self.accept()
