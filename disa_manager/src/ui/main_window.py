import contextlib
import logging
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QMainWindow, QScrollArea, QWidget, QGridLayout, QFrame, QLabel,
    QVBoxLayout, QHBoxLayout, QGraphicsBlurEffect,
)

from .ui_sidebar import Ui_MainWindow
from . import resource_rc  # noqa: F401  # importe les ressources (icônes)
from .notification_widget import NotificationManager, set_notification_manager
from .pages.home.home_widget import HomeWidget
from .pages.dashbord import ChartWidget
from .pages.agent_dashboard import AgentChartWidget
from .pages.traitement_widget import TraitementWidget
from .pages.database_widget import EmployersDatabaseWidget
from .pages.users_widget import UsersWidget
from core.session import get_current_user
from core.network_monitor import get_network_monitor

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Fenêtre principale basée sur le layout de ui_sidebar."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.resize(1280, 750)
        self._apply_stylesheet()
        self._apply_cnps_logo()
        self._init_sidebar_state()
        self._setup_home_page()
        self._setup_traitement_page()
        self._setup_dashboard_page()
        self._setup_database_page()
        self._setup_users_page()
        self._setup_navigation()
        self._apply_role_restrictions()
        self._setup_network_indicator()
        self._build_db_overlay()
        self._setup_notifications()
        # Permet de rendre les polices du dashboard réactives au redimensionnement
        with contextlib.suppress(AttributeError):
            self.ui.page_2.installEventFilter(self)

    def _apply_stylesheet(self) -> None:
        """Applique le style défini dans style.qss si présent."""

        qss_path = Path(__file__).resolve().parent / "style.qss"
        if not qss_path.exists():
            return

        try:
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Erreur de chargement du fichier style.qss")

    def _apply_cnps_logo(self) -> None:
        """Remplace le logo R-Disa par le logo officiel CNPS dans la sidebar et la barre de titre."""

        logo_path = Path(__file__).resolve().parent / "images" / "cnps_logo.jpeg"
        if not logo_path.exists():
            return

        pixmap = QPixmap(str(logo_path))
        if pixmap.isNull():
            return

        with contextlib.suppress(AttributeError):
            self._apply_logo_to_widgets(pixmap, logo_path)

    def _apply_logo_to_widgets(self, pixmap: QPixmap, logo_path: Path) -> None:
        """Applique le pixmap CNPS aux labels de la sidebar et à l'icône de fenêtre."""
        self.ui.logo_label_1.setPixmap(pixmap)
        self.ui.logo_label_1.setScaledContents(True)
        self.ui.logo_label_2.setPixmap(pixmap)
        self.ui.logo_label_2.setScaledContents(True)
        self.ui.logo_label_3.setText("CNPS")
        self.setWindowIcon(QIcon(str(logo_path)))
        self.setWindowTitle("Traitement DiSA — CNPS")

    def _init_sidebar_state(self) -> None:
        """Corrige l'état initial du sidebar (plein vs réduit)."""

        # On démarre avec le menu complet visible et la version icône seule cachée.
        try:
            self.ui.full_menu_widget.show()
            self.ui.icon_only_widget.hide()
            self.ui.change_btn.setChecked(False)
        except AttributeError:
            logger.warning("Structure UI inattendue dans _init_sidebar_state")

        # Masque le champ de recherche global de la barre latérale
        try:
            self.ui.search_input.hide()
            self.ui.search_btn.hide()
        except AttributeError:
            logger.debug("Champs search_input/search_btn absents du layout")

    def _setup_home_page(self) -> None:
        """Remplace la page Home par l'interface définie dans home_ui."""

        try:
            container = self.ui.page
            layout = self.ui.gridLayout_2
            label = self.ui.label_4
        except AttributeError:
            # Si la structure a changé, on ne fait rien.
            return

        # Retirer l'ancien label "Home Page".
        layout.removeWidget(label)
        label.deleteLater()

        # Ajouter notre widget Home à la place.
        self.home_widget = HomeWidget(container)
        layout.addWidget(self.home_widget, 0, 0, 1, 1)
        self.ui.stackedWidget.setCurrentWidget(container)

    def _setup_dashboard_page(self) -> None:
        """Installe les graphiques du tableau de bord sur la page_2 dans une zone défilante."""

        try:
            outer_layout = self.ui.gridLayout_3  # layout de page_2
            label = self.ui.label_5
        except AttributeError:
            return

        # Retirer le label placeholder
        outer_layout.removeWidget(label)
        label.deleteLater()

        # Supprimer les marges du layout parent pour que la scroll area remplisse toute la page
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Zone défilante : le contenu peut défiler verticalement si trop grand
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setStyleSheet(
            "QScrollArea { background: #0d1520; border: none; }"
            "QScrollArea > QWidget > QWidget { background: #0d1520; }"
        )

        # Widget conteneur à l'intérieur de la scroll area
        dashboard_container = QWidget()
        dashboard_container.setStyleSheet("background: #0d1520;")
        dashboard_grid = QGridLayout(dashboard_container)

        scroll_area.setWidget(dashboard_container)
        outer_layout.addWidget(scroll_area, 0, 0, 1, 1)

        # Construction du tableau de bord selon le rôle de l'utilisateur
        # - admin  → dashboard global (ChartWidget)
        # - agent  → dashboard personnel (AgentChartWidget)
        user = get_current_user()
        if user is not None and user.role == "admin":
            self.dashboard_chart = ChartWidget(dashboard_grid)
        else:
            self.dashboard_chart = AgentChartWidget(dashboard_grid)

        self.dashboard_chart.add_chart()

        # Premier calcul de la taille des polices en fonction de la largeur actuelle
        with contextlib.suppress(Exception):
            page_width = self.ui.page_2.width() or 900
            scale = max(0.7, min(1.4, page_width / 900.0))
            if hasattr(self.dashboard_chart, "update_font_sizes"):
                self.dashboard_chart.update_font_sizes(scale)

    def _setup_traitement_page(self) -> None:
        """Installe l'onglet Traitement (import Excel) sur la page_3."""

        try:
            container = self.ui.page_3
            layout = self.ui.gridLayout_4
            label = self.ui.label_6
        except AttributeError:
            return

        # Retirer le label placeholder "Orders Page"
        layout.removeWidget(label)
        label.deleteLater()

        # Ajouter notre widget Traitement
        self.traitement_widget = TraitementWidget(container)
        layout.addWidget(self.traitement_widget, 0, 0, 1, 1)

    def _setup_database_page(self) -> None:
        """Installe l'onglet Base de données (employeurs) sur la page_4."""

        try:
            container = self.ui.page_4
            layout = self.ui.gridLayout_5
            label = self.ui.label_7
        except AttributeError:
            return

        # Retirer le label placeholder "Product Page"
        layout.removeWidget(label)
        label.deleteLater()

        # Ajouter notre widget Base de données (employeurs)
        self.database_widget = EmployersDatabaseWidget(container)
        layout.addWidget(self.database_widget, 0, 0, 1, 1)

    def _setup_users_page(self) -> None:
        """Installe l'onglet Assuré (gestion des utilisateurs) sur la page_5."""

        try:
            container = self.ui.page_5
            layout = self.ui.gridLayout_6
            label = self.ui.label_8
        except AttributeError:
            return

        # Retirer le label placeholder "Customers Page"
        layout.removeWidget(label)
        label.deleteLater()

        # Ajouter notre widget de gestion des utilisateurs
        self.users_widget = UsersWidget(container)
        layout.addWidget(self.users_widget, 0, 0, 1, 1)

    def _apply_role_restrictions(self) -> None:
        """Masque les pages non autorisées selon le rôle de l'utilisateur connecté.

        - admin : accès complet (aucune restriction)
        - agent : accès uniquement à Accueil et Tableau de bord personnel
        """
        user = get_current_user()
        if user is None or user.role != "agent":
            return

        # Boutons à masquer pour le rôle "agent"
        restricted_buttons = [
            "traitement_btn_1", "traitement_btn_2",      # Traitement
            "database_btn_1", "database_btn_2",   # Base de données
            "users_btn_1", "users_btn_2", # Assurés / Utilisateurs
        ]
        try:
            for btn_name in restricted_buttons:
                btn = getattr(self.ui, btn_name, None)
                if btn is not None:
                    btn.hide()
        except Exception:
            logger.exception("Erreur dans _apply_role_restrictions")

        # S'assurer que la page affichée par défaut est l'Accueil
        try:
            self.ui.stackedWidget.setCurrentWidget(self.ui.page)
            self.ui.home_btn_2.setChecked(True)
        except AttributeError:
            logger.warning("Impossible de définir la page par défaut pour le rôle agent")

    def eventFilter(self, obj, event):  # type: ignore[override]
        """Ajuste dynamiquement les polices du dashboard quand la fenêtre est redimensionnée."""

        try:
            if obj is self.ui.page_2 and event.type() == QEvent.Resize:
                page_width = obj.width() or 900
                scale = max(0.7, min(1.4, page_width / 900.0))

                if hasattr(self, "dashboard_chart") and hasattr(
                    self.dashboard_chart, "update_font_sizes"
                ):
                    self.dashboard_chart.update_font_sizes(scale)
        except AttributeError:
            logger.debug("eventFilter: page_2 ou dashboard_chart indisponible")

        return super().eventFilter(obj, event)

    def _setup_network_indicator(self) -> None:
        """Ajoute un indicateur de statut réseau discret dans la barre de titre."""
        try:
            self._net_indicator = QLabel("● Réseau OK", self)
            self._net_indicator.setStyleSheet(
                "QLabel { color: #22c55e; font-size: 11px; font-weight: 600;"
                " background: transparent; padding: 2px 8px; }"
            )
            self._net_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)

            # Injecter dans le header_widget s'il existe, sinon dans la status bar
            try:
                header = self.ui.header_widget
                from PySide6.QtWidgets import QHBoxLayout
                if header.layout():
                    header.layout().addWidget(self._net_indicator)
                else:
                    lay = QHBoxLayout(header)
                    lay.addWidget(self._net_indicator)
            except AttributeError:
                self.statusBar().addPermanentWidget(self._net_indicator)

            # Connecter au moniteur réseau
            monitor = get_network_monitor()
            monitor.status_changed.connect(self._on_network_status_changed)

        except Exception as e:
            logger.debug("Indicateur réseau non disponible : %s", e)

    def _on_network_status_changed(self, available: bool) -> None:
        """Met à jour l'indicateur visuel et le titre de la fenêtre."""
        with contextlib.suppress(Exception):
            pending = get_network_monitor().pending_writes
            if available:
                txt = f"● Réseau OK  ({pending} en attente)" if pending else "● Réseau OK"
                color = "#22c55e"
                title = "Traitement DiSA — CNPS"
            else:
                txt = "⚠ Réseau indisponible — mode hors ligne"
                color = "#f59e0b"
                title = "Traitement DiSA — CNPS  [HORS LIGNE]"
            self._net_indicator.setText(txt)
            self._net_indicator.setStyleSheet(
                f"QLabel {{ color: {color}; font-size: 11px; font-weight: 600;"
                " background: transparent; padding: 2px 8px; }"
            )
            self.setWindowTitle(title)

    def _setup_navigation(self) -> None:
        """Relie les boutons de menu aux pages du stackedWidget."""

        try:  # noqa: SIM105  # structure UI générée — AttributeError possible en cas de changement
            # Accueil
            self.ui.home_btn_1.toggled.connect(
                lambda checked: checked and self.ui.stackedWidget.setCurrentWidget(self.ui.page)
            )
            self.ui.home_btn_2.toggled.connect(
                lambda checked: checked and self.ui.stackedWidget.setCurrentWidget(self.ui.page)
            )

            # Tableau de bord
            self.ui.dashborad_btn_1.toggled.connect(
                lambda checked: checked and self.ui.stackedWidget.setCurrentWidget(self.ui.page_2)
            )
            self.ui.dashborad_btn_2.toggled.connect(
                lambda checked: checked and self.ui.stackedWidget.setCurrentWidget(self.ui.page_2)
            )

            # Traitement (réutilise l'onglet "Orders")
            self.ui.traitement_btn_1.toggled.connect(
                lambda checked: checked and self.ui.stackedWidget.setCurrentWidget(self.ui.page_3)
            )
            self.ui.traitement_btn_2.toggled.connect(
                lambda checked: checked and self.ui.stackedWidget.setCurrentWidget(self.ui.page_3)
            )

            # Base de données (employeurs) sur page_4
            self.ui.database_btn_1.toggled.connect(
                lambda checked: checked and self.ui.stackedWidget.setCurrentWidget(self.ui.page_4)
            )
            self.ui.database_btn_2.toggled.connect(
                lambda checked: checked and self.ui.stackedWidget.setCurrentWidget(self.ui.page_4)
            )

            # Assurés / Utilisateurs sur page_5
            self.ui.users_btn_1.toggled.connect(
                lambda checked: checked and self.ui.stackedWidget.setCurrentWidget(self.ui.page_5)
            )
            self.ui.users_btn_2.toggled.connect(
                lambda checked: checked and self.ui.stackedWidget.setCurrentWidget(self.ui.page_5)
            )
            # Marquer le bouton Accueil comme actif au démarrage
            self.ui.home_btn_2.setChecked(True)

        except AttributeError:
            logger.exception("_setup_navigation : bouton de navigation manquant dans le UI")

    # ── Overlay « Base de données inaccessible » ──────────────────────────────

    def _build_db_overlay(self) -> None:
        """Construit le widget d'overlay affiché quand la base est inaccessible.

        L'overlay est un enfant direct de QMainWindow (pas du centralWidget) afin
        que le blur appliqué au centralWidget ne l'affecte pas.
        """
        self._db_overlay = QWidget(self)
        self._db_overlay.setObjectName("db_overlay")
        self._db_overlay.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._db_overlay.setStyleSheet(
            "QWidget#db_overlay { background: rgba(15, 23, 42, 180); }"
        )
        self._db_overlay.hide()

        root = QVBoxLayout(self._db_overlay)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # ── Carte centrale blanche ────────────────────────────────────────────
        card = QFrame()
        card.setObjectName("db_card")
        card.setFixedWidth(480)
        card.setStyleSheet("""
            QFrame#db_card {
                background: #ffffff;
                border-radius: 18px;
                border: 2px solid #e5e7eb;
            }
        """)
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(44, 38, 44, 38)
        card_lay.setSpacing(14)

        # Icône cadenas
        icon_lbl = QLabel("🔒")
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            "font-size: 54px; background: transparent; border: none;"
        )
        card_lay.addWidget(icon_lbl)

        # Titre
        title_lbl = QLabel("Base de données inaccessible")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(
            "font-size: 19px; font-weight: 700; color: #b91c1c;"
            " background: transparent; border: none;"
            " font-family: 'Segoe UI', Helvetica, Arial, sans-serif;"
        )
        card_lay.addWidget(title_lbl)

        # Séparateur
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background: #e5e7eb; border: none;")
        card_lay.addWidget(sep)

        # Message descriptif
        msg_lbl = QLabel(
            "Impossible d'accéder à la base de données.\n"
            "Le fichier a peut-être été supprimé, déplacé\n"
            "ou le partage réseau est indisponible.\n\n"
            "L'application est en attente de rétablissement."
        )
        msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(
            "font-size: 13px; color: #374151; line-height: 1.6;"
            " background: transparent; border: none;"
            " font-family: 'Segoe UI', Helvetica, Arial, sans-serif;"
        )
        card_lay.addWidget(msg_lbl)

        # Bloc contact
        contact = QFrame()
        contact.setObjectName("contact_frame")
        contact.setStyleSheet("""
            QFrame#contact_frame {
                background: #fef9ee;
                border-radius: 10px;
                border: 1px solid #fde68a;
            }
        """)
        c_lay = QVBoxLayout(contact)
        c_lay.setContentsMargins(20, 14, 20, 14)
        c_lay.setSpacing(6)

        lbl_contact_title = QLabel("Veuillez contacter l'administrateur :")
        lbl_contact_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_contact_title.setStyleSheet(
            "font-size: 11px; color: #92400e; background: transparent; border: none;"
            " font-family: 'Segoe UI', Helvetica, Arial, sans-serif;"
        )
        c_lay.addWidget(lbl_contact_title)

        lbl_name = QLabel("N'GUESSAN Kouakou N'Goran Blanchard")
        lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_name.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #78350f;"
            " background: transparent; border: none;"
            " font-family: 'Segoe UI', Helvetica, Arial, sans-serif;"
        )
        c_lay.addWidget(lbl_name)

        lbl_phone = QLabel("📞  07 77 14 51 87")
        lbl_phone.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_phone.setStyleSheet(
            "font-size: 18px; font-weight: 700; color: #003f8a;"
            " letter-spacing: 1px; background: transparent; border: none;"
            " font-family: 'Segoe UI', Helvetica, Arial, sans-serif;"
        )
        c_lay.addWidget(lbl_phone)

        card_lay.addWidget(contact)
        root.addWidget(card)

        # Connecter au moniteur réseau
        monitor = get_network_monitor()
        monitor.status_changed.connect(self._on_db_availability_changed)

    def _show_db_overlay(self) -> None:
        """Applique le flou sur le contenu et affiche l'overlay."""
        with contextlib.suppress(Exception):
            blur = QGraphicsBlurEffect()
            blur.setBlurRadius(12)
            self.centralWidget().setGraphicsEffect(blur)

        self._db_overlay.setGeometry(self.rect())
        self._db_overlay.show()
        self._db_overlay.raise_()
        logger.warning("Overlay DB inaccessible affiché.")

    def _hide_db_overlay(self) -> None:
        """Retire le flou et cache l'overlay."""
        with contextlib.suppress(Exception):
            self.centralWidget().setGraphicsEffect(None)

        self._db_overlay.hide()
        logger.info("Overlay DB inaccessible masqué — base restaurée.")

    def _on_db_availability_changed(self, available: bool) -> None:
        """Réagit aux changements de disponibilité de la base."""
        if available:
            self._hide_db_overlay()
        else:
            self._show_db_overlay()

    def _setup_notifications(self) -> None:
        """Installe le gestionnaire de notifications flottant."""
        self._notif_manager = NotificationManager(parent=self)
        set_notification_manager(self._notif_manager)
        self._notif_manager.reposition(self.rect())
        self._notif_manager.show()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        """Redimensionne l'overlay et les notifications quand la fenêtre change de taille."""
        super().resizeEvent(event)
        with contextlib.suppress(AttributeError):
            if self._db_overlay.isVisible():
                self._db_overlay.setGeometry(self.rect())
        with contextlib.suppress(AttributeError):
            self._notif_manager.reposition(self.rect())
