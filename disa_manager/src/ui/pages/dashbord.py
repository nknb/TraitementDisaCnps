from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QFont, QCursor
from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QValueAxis,
)
from PySide6.QtWidgets import QGridLayout, QLabel, QFrame, QVBoxLayout, QDialog

from db.connection import get_connection
from core.events import get_data_bus


class ChartWidget:
    def __init__(self, widget):
        super().__init__()
        self.widget = widget
        # Layout cible (grid de la page_2)
        # On y dépose nos cartes + graphiques

        # Liste des labels dont la taille de police doit être réajustée dynamiquement
        # (label, taille_de_base)
        self._responsive_label_specs: list[tuple[QLabel, int]] = []

        # Fenêtre de détail affichée au survol d'une barre
        self._detail_dialog: QDialog | None = None
        self._detail_label: QLabel | None = None

        # Se réactualise automatiquement quand la base change
        get_data_bus().data_changed.connect(self.refresh)

    def refresh(self) -> None:
        """Recharge complètement les graphiques du dashboard."""

        # On réutilise simplement la logique existante
        self.add_chart()

    def add_chart(self):
        """Construit le dashboard selon le besoin métier.

        1. Carte : nombre total d'employeurs enregistrés
        2. Camembert : lignes DISA traitées vs non traitées (global)
        3. Histogramme : DISA restantes à traiter et DISA traitées par localité
        """

        layout: QGridLayout = self.widget

        # Réinitialise la liste des labels responsifs pour éviter les fuites mémoire
        self._responsive_label_specs = []

        # Nettoie le layout pour reconstruire le contenu
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        total_employeurs = 0

        # Données pour le camembert
        lignes_traitees = 0
        lignes_non_traitees = 0

        # Données pour l'histogramme par localité
        localites: list[str] = []
        disa_restantes: list[int] = []
        disa_traitees: list[int] = []

        try:
            conn = get_connection()
            with conn:
                cur = conn.cursor()

                # Utilise la même jointure que la vue join_employeur_traitement
                base_from = (
                    " FROM identification_employeurs ie "
                    "LEFT JOIN traitement_disa td ON td.employeur_id = ie.id"
                )

                # 1) Volume global d'employeurs (distinction par id employeur)
                cur.execute("SELECT COUNT(DISTINCT ie.id)" + base_from)
                total_employeurs = cur.fetchone()[0] or 0

                # 2) Nombre de DISA traitées / non traitées
                #    On compte les lignes de traitement_disa via la jointure.
                cur.execute(
                    """
                    SELECT COALESCE(td.statut, 'NON TRAITÉ') AS s,
                           COUNT(*) AS nb
                    """
                    + base_from
                    + " GROUP BY COALESCE(td.statut, 'NON TRAITÉ')"
                )
                for statut, nb in cur.fetchall():
                    statut_u = str(statut or '').upper()
                    nb_i = int(nb or 0)
                    if 'NON' in statut_u and 'TRAIT' in statut_u:
                        lignes_non_traitees += nb_i
                    else:
                        lignes_traitees += nb_i

                # 3) Nombre de DISA restantes / traitées par localité
                #    On compte les enregistrements (DISA) selon le statut,
                #    à partir de la même jointure employeur + DISA.
                cur.execute(
                    """
                    SELECT
                        COALESCE(ie.localites, 'NON RENSEIGNÉE') AS localite,
                        SUM(CASE WHEN COALESCE(td.statut, 'NON TRAITÉ') = 'NON TRAITÉ' THEN 1 ELSE 0 END) AS restant,
                        SUM(CASE WHEN COALESCE(td.statut, 'NON TRAITÉ') <> 'NON TRAITÉ' THEN 1 ELSE 0 END) AS traite
                    FROM identification_employeurs ie
                    LEFT JOIN traitement_disa td ON td.employeur_id = ie.id
                    GROUP BY COALESCE(ie.localites, 'NON RENSEIGNÉE')
                    ORDER BY restant DESC, traite DESC
                    """
                )
                for loc, restant, traite in cur.fetchall():
                    localites.append(str(loc))
                    disa_restantes.append(int(restant or 0))
                    disa_traitees.append(int(traite or 0))
        except Exception:
            # En cas d'erreur BD, on laisse les valeurs par défaut (zéro partout).
            total_employeurs = 0
            lignes_traitees = 0
            lignes_non_traitees = 0
            localites = []
            disa_restantes = []
            disa_traitees = []

        # Configuration de base du grid pour ressembler à des "cases"
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(16)
        layout.setContentsMargins(10, 10, 10, 10)

        # --- Cartes KPI en haut (3 cartes) ---

        def make_card(title: str, value: str, subtitle: str, color: str) -> QFrame:
            frame = QFrame()
            frame.setStyleSheet(
                f"background-color: {color}; border-radius: 10px; padding: 14px;"
            )
            vbox = QVBoxLayout(frame)
            title_lbl = QLabel(title)
            title_lbl.setStyleSheet("color: #f5f5f5; font-weight: 600;")
            value_lbl = QLabel(value)
            value_lbl.setStyleSheet("color: white; font-weight: 800;")
            subtitle_lbl = QLabel(subtitle)
            subtitle_lbl.setStyleSheet("color: #f5f5f5;")
            vbox.addWidget(title_lbl)
            vbox.addWidget(value_lbl)
            vbox.addWidget(subtitle_lbl)
            vbox.addStretch(1)

            # Enregistrer ces labels pour ajuster leur taille de police plus tard
            self._responsive_label_specs.extend(
                [
                    (title_lbl, 11),
                    (value_lbl, 18),
                    (subtitle_lbl, 11),
                ]
            )
            return frame

        # Carte 1 : Employeurs
        card_employeurs = make_card(
            "Employeurs enregistrés",
            str(total_employeurs),
            "Enregistrés dans la base",
            "#2ecc71",
        )
        # Carte 2 : Lignes DISA traitées
        card_traitees = make_card(
            "Lignes DISA traitées",
            str(lignes_traitees),
            "Total des lignes validées",
            "#f1c40f",
        )
        # Carte 3 : Lignes DISA non traitées
        card_non_traitees = make_card(
            "Lignes DISA non traitées",
            str(lignes_non_traitees),
            "Lignes restantes à traiter",
            "#1abc9c",
        )

        # Disposition des 3 cartes sur la première ligne
        layout.addWidget(card_employeurs, 0, 0, 1, 1)
        layout.addWidget(card_traitees, 0, 1, 1, 1)
        layout.addWidget(card_non_traitees, 0, 2, 1, 1)

        # --- Histogramme DISA restantes / traitées par localité ---
        chart_bar = QChart()
        chart_bar.setTheme(QChart.ChartTheme.ChartThemeDark)
        chart_bar.setTitle("DISA restantes et traitées par localité")

        # Titre plus lisible
        title_font = chart_bar.titleFont()
        title_font.setPointSize(14)
        chart_bar.setTitleFont(title_font)

        series_bar = QBarSeries()
        # Barres plus larges et labels visibles
        series_bar.setBarWidth(0.7)
        series_bar.setLabelsVisible(True)

        set_restantes = QBarSet("DISA restantes")
        set_restantes.setColor(QColor("#e67e22"))
        set_traitees = QBarSet("DISA traitées")
        set_traitees.setColor(QColor("#3498db"))

        if localites:
            for r in disa_restantes:
                set_restantes.append(r)
            for t in disa_traitees:
                set_traitees.append(t)
        else:
            # Aucune donnée -> une barre vide
            localites = ["Aucune donnée"]
            set_restantes.append(0)
            set_traitees.append(0)

        series_bar.append(set_restantes)
        series_bar.append(set_traitees)

        chart_bar.addSeries(series_bar)

        axis_x = QBarCategoryAxis()
        axis_x.append(localites)
        axis_x.setLabelsAngle(-35)
        axis_x_font = axis_x.labelsFont()
        axis_x_font.setPointSize(9)
        axis_x.setLabelsFont(axis_x_font)
        chart_bar.addAxis(axis_x, Qt.AlignBottom)
        series_bar.attachAxis(axis_x)

        max_y = max(
            [max(disa_restantes or [0]), max(disa_traitees or [0])]
        )
        axis_y = QValueAxis()
        axis_y.setRange(0, max_y * 1.2 if max_y > 0 else 1)
        axis_y_font = axis_y.labelsFont()
        axis_y_font.setPointSize(9)
        axis_y.setLabelsFont(axis_y_font)
        chart_bar.addAxis(axis_y, Qt.AlignLeft)
        series_bar.attachAxis(axis_y)

        chart_bar.legend().setVisible(True)
        chart_bar.legend().setAlignment(Qt.AlignBottom)
        legend_font = chart_bar.legend().font()
        legend_font.setPointSize(9)
        chart_bar.legend().setFont(legend_font)

        # Affichage des détails dans une petite fenêtre au survol des barres
        def show_detail(status: bool, index: int, serie: str) -> None:
            if not status or index < 0 or index >= len(localites):
                if self._detail_dialog is not None:
                    self._detail_dialog.hide()
                return

            localite = localites[index]
            restantes_val = disa_restantes[index]
            traitees_val = disa_traitees[index]

            if self._detail_dialog is None:
                self._detail_dialog = QDialog()
                self._detail_dialog.setWindowTitle("Détail DISA par localité")
                self._detail_dialog.setModal(False)
                vbox = QVBoxLayout(self._detail_dialog)
                self._detail_label = QLabel()
                self._detail_label.setStyleSheet(
                    "font-size: 14px; font-weight: 600; padding: 8px;"
                )
                vbox.addWidget(self._detail_label)

            if self._detail_label is not None:
                self._detail_label.setText(
                    f"<b>Localité :</b> {localite}<br>"
                    f"<b>DISA restantes :</b> {restantes_val}<br>"
                    f"<b>DISA traitées :</b> {traitees_val}"
                )

            # Style popup léger, proche du curseur
            self._detail_dialog.setWindowFlags(Qt.ToolTip)
            self._detail_dialog.adjustSize()
            pos = QCursor.pos()
            self._detail_dialog.move(pos.x() + 15, pos.y() + 15)
            self._detail_dialog.show()

        # Connexion des événements de survol
        try:
            set_restantes.hovered.connect(
                lambda status, index: show_detail(status, index, "restantes")
            )
            set_traitees.hovered.connect(
                lambda status, index: show_detail(status, index, "traitees")
            )
        except Exception:
            # Si l'API hovered n'est pas disponible, on ignore simplement.
            pass

        view_bar = QChartView(chart_bar)
        view_bar.setRenderHint(QPainter.Antialiasing)
        # Histogramme plus dominant en hauteur
        view_bar.setMinimumHeight(420)
        view_bar.setMaximumHeight(600)
        # Histogramme sur la deuxième ligne, occupe toute la largeur
        layout.addWidget(view_bar, 1, 0, 1, 3)

    def update_font_sizes(self, scale: float) -> None:
        """Met à l'échelle les polices des labels et des titres de graphiques.

        scale est un facteur basé sur la largeur de la fenêtre (autour de 1.0).
        """

        # Bornes raisonnables pour garder une bonne lisibilité
        def _clamp(size: int, min_size: int = 8, max_size: int = 26) -> int:
            return max(min_size, min(max_size, size))

        # Ajuster les labels des cartes KPI
        for lbl, base_size in self._responsive_label_specs:
            new_size = _clamp(int(base_size * scale))
            font = QFont(lbl.font())
            font.setPointSize(new_size)
            lbl.setFont(font)

        # Nota : si on veut ajuster aussi les titres de graphiques, il faudra
        # conserver des références aux QChart créés dans add_chart.
