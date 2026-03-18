from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QMainWindow, QScrollArea, QWidget, QGridLayout, QFrame

from .ui_sidebar import Ui_MainWindow
from . import resource_rc  # noqa: F401  # importe les ressources (icônes)
from .pages.home.home_widget import HomeWidget
from .pages.dashbord import ChartWidget
from .pages.agent_dashboard import AgentChartWidget
from .pages.traitement_widget import TraitementWidget
from .pages.database_widget import EmployersDatabaseWidget
from .pages.users_widget import UsersWidget
from core.session import get_current_user


class MainWindow(QMainWindow):
    """Fenêtre principale basée sur le layout de ui_sidebar."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        # Augmente légèrement la largeur initiale de la fenêtre (~ +20 %)
        try:
            current_width = self.width() or 1000
            current_height = self.height() or 700
            # Largeur augmentée d'environ 40 % par rapport à la valeur UI
            # (deux incréments successifs de +20 % ≈ 1.44)
            new_width = int(current_width * 1.44)
            self.resize(new_width, current_height)
        except Exception:
            pass
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
        # Permet de rendre les polices du dashboard réactives au redimensionnement
        try:
            self.ui.page_2.installEventFilter(self)
        except AttributeError:
            pass

    def _apply_stylesheet(self) -> None:
        """Applique le style défini dans style.qss si présent."""

        qss_path = Path(__file__).resolve().parent / "style.qss"
        if not qss_path.exists():
            return

        try:
            self.setStyleSheet(qss_path.read_text(encoding="utf-8"))
        except Exception:
            # En cas d'erreur de lecture ou de parsing du QSS, on ignore simplement.
            pass

    def _apply_cnps_logo(self) -> None:
        """Remplace le logo R-Disa par le logo officiel CNPS dans la sidebar et la barre de titre."""

        logo_path = Path(__file__).resolve().parent / "images" / "cnps_logo.jpeg"
        if not logo_path.exists():
            return

        pixmap = QPixmap(str(logo_path))
        if pixmap.isNull():
            return

        try:
            # Logo sidebar icônes seules — setScaledContents(True) laisse Qt
            # adapter le pixmap à la taille exacte du label sans rogner les bords.
            self.ui.logo_label_1.setPixmap(pixmap)
            self.ui.logo_label_1.setScaledContents(True)

            # Logo sidebar menu complet
            self.ui.logo_label_2.setPixmap(pixmap)
            self.ui.logo_label_2.setScaledContents(True)

            # Texte à côté du logo dans la sidebar complète
            self.ui.logo_label_3.setText("CNPS")

            # Icône de la barre de titre de la fenêtre
            self.setWindowIcon(QIcon(str(logo_path)))
            self.setWindowTitle("Traitement DiSA — CNPS")

        except AttributeError:
            pass

    def _init_sidebar_state(self) -> None:
        """Corrige l'état initial du sidebar (plein vs réduit)."""

        # On démarre avec le menu complet visible et la version icône seule cachée.
        try:
            self.ui.full_menu_widget.show()
            self.ui.icon_only_widget.hide()
            self.ui.change_btn.setChecked(False)
        except AttributeError:
            # Si la structure change dans le futur, on évite de casser l'appli.
            pass

        # Masque le champ de recherche global de la barre latérale
        try:
            self.ui.search_input.hide()
            self.ui.search_btn.hide()
        except AttributeError:
            pass

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
        try:
            page_width = self.ui.page_2.width() or 900
            scale = max(0.7, min(1.4, page_width / 900.0))
            if hasattr(self.dashboard_chart, "update_font_sizes"):
                self.dashboard_chart.update_font_sizes(scale)
        except Exception:
            pass

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
            "orders_btn_1", "orders_btn_2",      # Traitement
            "products_btn_1", "products_btn_2",   # Base de données
            "customers_btn_1", "customers_btn_2", # Assurés / Utilisateurs
        ]
        try:
            for btn_name in restricted_buttons:
                btn = getattr(self.ui, btn_name, None)
                if btn is not None:
                    btn.hide()
        except Exception:
            pass

        # S'assurer que la page affichée par défaut est l'Accueil
        try:
            self.ui.stackedWidget.setCurrentWidget(self.ui.page)
            self.ui.home_btn_2.setChecked(True)
        except AttributeError:
            pass

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
            pass

        return super().eventFilter(obj, event)

    def _setup_navigation(self) -> None:
        """Relie les boutons de menu aux pages du stackedWidget."""

        try:
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
            self.ui.orders_btn_1.toggled.connect(
                lambda checked: checked and self.ui.stackedWidget.setCurrentWidget(self.ui.page_3)
            )
            self.ui.orders_btn_2.toggled.connect(
                lambda checked: checked and self.ui.stackedWidget.setCurrentWidget(self.ui.page_3)
            )

            # Base de données (employeurs) sur page_4
            self.ui.products_btn_1.toggled.connect(
                lambda checked: checked and self.ui.stackedWidget.setCurrentWidget(self.ui.page_4)
            )
            self.ui.products_btn_2.toggled.connect(
                lambda checked: checked and self.ui.stackedWidget.setCurrentWidget(self.ui.page_4)
            )

            # Assurés / Utilisateurs sur page_5
            self.ui.customers_btn_1.toggled.connect(
                lambda checked: checked and self.ui.stackedWidget.setCurrentWidget(self.ui.page_5)
            )
            self.ui.customers_btn_2.toggled.connect(
                lambda checked: checked and self.ui.stackedWidget.setCurrentWidget(self.ui.page_5)
            )
        except AttributeError:
            # Si la structure du UI change un jour, on évite de tout casser.
            pass
