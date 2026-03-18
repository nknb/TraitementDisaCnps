from PySide6.QtCore import Qt, QMargins, QPropertyAnimation, QEasingCurve, QTimer
from PySide6.QtGui import QPainter, QColor, QFont, QCursor
from PySide6.QtCharts import (
    QBarCategoryAxis,
    QBarSeries,
    QBarSet,
    QChart,
    QChartView,
    QHorizontalBarSeries,
    QPieSeries,
    QValueAxis,
)
from PySide6.QtWidgets import (
    QGridLayout,
    QLabel,
    QFrame,
    QVBoxLayout,
    QDialog,
    QGraphicsOpacityEffect,
)

from db.connection import get_connection
from core.events import get_data_bus

# ── Palette sombre CNPS DiSA ──────────────────────────────────────────────────
_BG_DEEP   = "#0d1520"   # fond de page (plus sombre)
_BG_CARD   = "#182233"   # fond des cartes
_BG_HDR    = "#111d2e"   # en-tête des cartes
_BORDER    = "#243147"   # bordure des cartes
_TXT1      = "#e2e8f0"   # texte principal
_TXT2      = "#94a3b8"   # texte secondaire
_TXT3      = "#64748b"   # texte tertiaire / axe
_GRID      = "#1e3a5f"   # lignes de grille des graphiques

# Accents lumineux pour fond sombre
_C_NAVY    = "#3b82f6"   # bleu clair
_C_GREEN   = "#10b981"   # vert émeraude
_C_AMBER   = "#f59e0b"   # ambre
_C_BLUE    = "#60a5fa"   # bleu vif

# Palette utilisateurs (camembert)
_USER_COLORS = ["#3b82f6", "#10b981", "#f59e0b", "#f87171",
                "#a78bfa", "#22d3ee", "#84cc16", "#fb923c"]


def _truncate(text: str, max_chars: int = 22) -> str:
    """Tronque un libellé trop long pour les axes de graphiques."""
    return text if len(text) <= max_chars else text[:max_chars - 1] + "…"


class ChartWidget:
    def __init__(self, widget):
        super().__init__()
        self.widget = widget
        self._responsive_label_specs: list[tuple[QLabel, int]] = []
        self._detail_dialog: QDialog | None = None
        self._detail_label: QLabel | None = None
        # Références aux animations pour éviter le garbage collection
        self._animations: list[QPropertyAnimation] = []
        get_data_bus().data_changed.connect(self.refresh)

    def refresh(self) -> None:
        self._animations.clear()
        self.add_chart()

    # ── Helpers UI ────────────────────────────────────────────────────────────

    def _fade_in(self, widget, delay_ms: int = 0) -> None:
        """Anime l'apparition en fondu d'un widget (stocké pour éviter le GC)."""
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)

        def _start() -> None:
            anim = QPropertyAnimation(effect, b"opacity")
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setDuration(550)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
            self._animations.append(anim)

        if delay_ms > 0:
            QTimer.singleShot(delay_ms, _start)
        else:
            _start()

    def _make_kpi_card(
        self,
        title: str,
        value: str,
        subtitle: str,
        accent: str,
        delay_ms: int = 0,
    ) -> QFrame:
        """Carte KPI sombre avec bordure supérieure colorée et animation."""
        frame = QFrame()
        frame.setStyleSheet(
            f"""
            QFrame {{
                background-color: {_BG_CARD};
                border-radius: 12px;
                border: 1px solid {_BORDER};
                border-top: 3px solid {accent};
            }}
            """
        )
        frame.setMinimumHeight(90)

        vbox = QVBoxLayout(frame)
        vbox.setContentsMargins(14, 10, 14, 10)
        vbox.setSpacing(2)

        lbl_title = QLabel(title.upper())
        lbl_title.setStyleSheet(
            f"color: {_TXT3}; font-weight: 600; letter-spacing: 0.7px;"
            " border: none; background: transparent;"
        )
        lbl_value = QLabel(value)
        lbl_value.setStyleSheet(
            f"color: {accent}; font-weight: 800;"
            " border: none; background: transparent;"
        )
        lbl_sub = QLabel(subtitle)
        lbl_sub.setStyleSheet(
            f"color: {_TXT3}; border: none; background: transparent;"
        )

        vbox.addWidget(lbl_title)
        vbox.addWidget(lbl_value)
        vbox.addWidget(lbl_sub)
        vbox.addStretch(1)

        self._responsive_label_specs.extend([
            (lbl_title, 9),
            (lbl_value, 24),
            (lbl_sub, 9),
        ])

        self._fade_in(frame, delay_ms)
        return frame

    def _make_chart_card(
        self, title: str, subtitle: str, delay_ms: int = 0
    ) -> tuple["QFrame", "QVBoxLayout"]:
        """Carte graphique sombre avec en-tête et animation."""
        card = QFrame()
        card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {_BG_CARD};
                border-radius: 12px;
                border: 1px solid {_BORDER};
            }}
            """
        )
        outer = QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        hdr = QFrame()
        hdr.setStyleSheet(
            f"""
            QFrame {{
                background-color: {_BG_HDR};
                border: none;
                border-radius: 12px;
                border-bottom-left-radius: 0;
                border-bottom-right-radius: 0;
                border-bottom: 1px solid {_BORDER};
            }}
            """
        )
        hdr_lay = QVBoxLayout(hdr)
        hdr_lay.setContentsMargins(18, 11, 18, 9)
        hdr_lay.setSpacing(2)

        lbl_t = QLabel(title)
        lbl_t.setStyleSheet(
            f"color: {_TXT1}; font-weight: 700; font-size: 12px;"
            " border: none; background: transparent;"
        )
        lbl_s = QLabel(subtitle)
        lbl_s.setStyleSheet(
            f"color: {_TXT2}; font-size: 10px; border: none; background: transparent;"
        )
        hdr_lay.addWidget(lbl_t)
        hdr_lay.addWidget(lbl_s)
        outer.addWidget(hdr)

        self._fade_in(card, delay_ms)
        return card, outer

    def _base_chart(self, bg: str = _BG_CARD) -> QChart:
        """QChart avec thème sombre, fond de carte et animations activées."""
        chart = QChart()
        chart.setTheme(QChart.ChartTheme.ChartThemeDark)
        chart.setTitle("")
        chart.setBackgroundBrush(QColor(bg))
        chart.setBackgroundRoundness(0)
        chart.setMargins(QMargins(10, 6, 10, 6))
        chart.setAnimationOptions(QChart.AnimationOption.AllAnimations)
        chart.setAnimationDuration(700)
        # Masquer le titre (géré par l'en-tête de la carte)
        tf = chart.titleFont()
        tf.setPointSize(1)
        chart.setTitleFont(tf)
        return chart

    @staticmethod
    def _styled_chart_view(chart: QChart, min_h: int = 220) -> QChartView:
        view = QChartView(chart)
        view.setRenderHint(QPainter.Antialiasing)
        view.setStyleSheet("background: transparent; border: none;")
        view.setMinimumHeight(min_h)
        return view

    def _style_legend(self, chart: QChart) -> None:
        chart.legend().setVisible(True)
        chart.legend().setAlignment(Qt.AlignBottom)
        lf = chart.legend().font()
        lf.setPointSize(9)
        chart.legend().setFont(lf)
        chart.legend().setColor(QColor(_TXT1))
        chart.legend().setLabelColor(QColor(_TXT2))

    def _style_axis(self, axis: QBarCategoryAxis | QValueAxis) -> None:
        lf = axis.labelsFont()
        lf.setPointSize(9)
        axis.setLabelsFont(lf)
        axis.setLabelsColor(QColor(_TXT2))
        if isinstance(axis, QValueAxis):
            axis.setGridLineColor(QColor(_GRID))

    # ── Construction principale ───────────────────────────────────────────────

    def add_chart(self):
        layout: QGridLayout = self.widget
        self._responsive_label_specs = []
        self._animations.clear()

        # Nettoyer le layout
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        # ── Fond sombre de la page ────────────────────────────────────
        parent = layout.parentWidget()
        if parent is not None:
            parent.setStyleSheet(f"background-color: {_BG_DEEP};")

        # ── Récupération des données ──────────────────────────────────
        total_employeurs = 0
        lignes_traitees = 0
        lignes_non_traitees = 0
        localites: list[str] = []
        disa_restantes: list[int] = []
        disa_traitees_loc: list[int] = []
        secteurs: list[str] = []
        secteurs_nb: list[int] = []
        traite_par_users: list[str] = []
        traite_par_nb: list[int] = []

        try:
            conn = get_connection()
            with conn:
                cur = conn.cursor()
                base_from = (
                    " FROM identification_employeurs ie "
                    "LEFT JOIN traitement_disa td ON td.employeur_id = ie.id"
                )

                cur.execute("SELECT COUNT(DISTINCT ie.id)" + base_from)
                total_employeurs = cur.fetchone()[0] or 0

                cur.execute(
                    "SELECT COALESCE(td.statut, 'NON TRAITÉ') AS s, COUNT(*) AS nb"
                    + base_from
                    + " GROUP BY COALESCE(td.statut, 'NON TRAITÉ')"
                )
                for statut, nb in cur.fetchall():
                    statut_u = str(statut or "").upper()
                    nb_i = int(nb or 0)
                    if "NON" in statut_u and "TRAIT" in statut_u:
                        lignes_non_traitees += nb_i
                    else:
                        lignes_traitees += nb_i

                cur.execute(
                    """
                    SELECT
                        COALESCE(ie.localites, 'NON RENSEIGNÉE') AS localite,
                        SUM(CASE WHEN COALESCE(td.statut,'NON TRAITÉ')='NON TRAITÉ'
                                 THEN 1 ELSE 0 END),
                        SUM(CASE WHEN COALESCE(td.statut,'NON TRAITÉ')<>'NON TRAITÉ'
                                 THEN 1 ELSE 0 END)
                    FROM identification_employeurs ie
                    LEFT JOIN traitement_disa td ON td.employeur_id = ie.id
                    GROUP BY COALESCE(ie.localites,'NON RENSEIGNÉE')
                    ORDER BY 2 DESC, 3 DESC
                    """
                )
                for loc, restant, traite in cur.fetchall():
                    localites.append(str(loc))
                    disa_restantes.append(int(restant or 0))
                    disa_traitees_loc.append(int(traite or 0))

                cur.execute(
                    """
                    SELECT COALESCE(secteur_activite,'NON RENSEIGNÉ') AS secteur,
                           COUNT(*) AS nb
                    FROM identification_employeurs
                    GROUP BY COALESCE(secteur_activite,'NON RENSEIGNÉ')
                    ORDER BY nb DESC LIMIT 8
                    """
                )
                for sect, nb in cur.fetchall():
                    secteurs.append(str(sect))
                    secteurs_nb.append(int(nb or 0))

                cur.execute(
                    """
                    SELECT COALESCE(traite_par, 'Non renseigné') AS utilisateur,
                           COUNT(*) AS nb
                    FROM traitement_disa
                    WHERE COALESCE(statut, 'NON TRAITÉ') <> 'NON TRAITÉ'
                    GROUP BY COALESCE(traite_par, 'Non renseigné')
                    ORDER BY nb DESC
                    """
                )
                for user, nb in cur.fetchall():
                    traite_par_users.append(str(user))
                    traite_par_nb.append(int(nb or 0))
        except Exception:
            pass

        # ── Grille 4 colonnes ─────────────────────────────────────────
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)
        layout.setContentsMargins(14, 12, 14, 12)
        for col in range(4):
            layout.setColumnStretch(col, 1)

        # ── LIGNE 0 : 4 cartes KPI ────────────────────────────────────
        total_disa = lignes_traitees + lignes_non_traitees
        taux = int(lignes_traitees / total_disa * 100) if total_disa > 0 else 0

        kpi_data = [
            ("Employeurs enregistrés", str(total_employeurs), "Dans la base de données", _C_NAVY),
            ("DISA traitées",          str(lignes_traitees),  "Lignes validées",         _C_GREEN),
            ("DISA non traitées",      str(lignes_non_traitees), "Restantes à traiter",  _C_AMBER),
            ("Taux de traitement",     f"{taux} %",           "DISA validées / total",   _C_BLUE),
        ]
        for col, (title, value, sub, accent) in enumerate(kpi_data):
            layout.addWidget(
                self._make_kpi_card(title, value, sub, accent, delay_ms=col * 80),
                0, col,
            )

        # ── LIGNE 1 : Camembert statut | Camembert par utilisateur ────

        # Camembert statut global
        pie_card, pie_card_lay = self._make_chart_card(
            "Statut global des DISA", "Lignes traitées vs non traitées", delay_ms=100,
        )
        pie_series = QPieSeries()
        s_traite = pie_series.append(
            f"Traitées  ({lignes_traitees})", max(lignes_traitees, 1)
        )
        s_non = pie_series.append(
            f"Non traitées  ({lignes_non_traitees})", max(lignes_non_traitees, 1)
        )
        s_traite.setColor(QColor(_C_BLUE));   s_traite.setBorderColor(QColor(_C_BLUE))
        s_non.setColor(QColor(_C_AMBER));     s_non.setBorderColor(QColor(_C_AMBER))
        s_traite.setExploded(True);           s_traite.setExplodeDistanceFactor(0.05)

        pie_chart = self._base_chart()
        pie_chart.addSeries(pie_series)
        pie_chart.setMargins(QMargins(8, 4, 8, 4))
        self._style_legend(pie_chart)
        pie_card_lay.addWidget(self._styled_chart_view(pie_chart, min_h=200))
        layout.addWidget(pie_card, 1, 0, 1, 2)

        # Camembert DISA par utilisateur
        user_pie_card, user_pie_card_lay = self._make_chart_card(
            "DISA traitées par utilisateur",
            "Contribution de chaque agent au traitement",
            delay_ms=180,
        )
        user_pie_series = QPieSeries()
        if traite_par_users:
            for i, (user, nb) in enumerate(zip(traite_par_users, traite_par_nb)):
                sl = user_pie_series.append(f"{user}  ({nb})", nb)
                c = _USER_COLORS[i % len(_USER_COLORS)]
                sl.setColor(QColor(c)); sl.setBorderColor(QColor(c))
                if i == 0:
                    sl.setExploded(True); sl.setExplodeDistanceFactor(0.05)
        else:
            sl = user_pie_series.append("Aucune donnée", 1)
            sl.setColor(QColor(_BORDER)); sl.setBorderColor(QColor(_BORDER))

        user_pie_chart = self._base_chart()
        user_pie_chart.addSeries(user_pie_series)
        user_pie_chart.setMargins(QMargins(8, 4, 8, 4))
        self._style_legend(user_pie_chart)
        user_pie_card_lay.addWidget(self._styled_chart_view(user_pie_chart, min_h=200))
        layout.addWidget(user_pie_card, 1, 2, 1, 2)

        # ── LIGNE 2 : Histogramme DISA par localité ───────────────────
        bar_card, bar_card_lay = self._make_chart_card(
            "DISA restantes et traitées par localité",
            "Comparaison du volume de traitement par localité d'employeur",
            delay_ms=260,
        )

        chart_bar = self._base_chart()
        chart_bar.setMargins(QMargins(12, 8, 12, 8))

        series_bar = QBarSeries()
        series_bar.setBarWidth(0.65)
        series_bar.setLabelsVisible(True)

        set_restantes = QBarSet("DISA restantes")
        set_restantes.setColor(QColor(_C_AMBER))
        set_restantes.setBorderColor(QColor(_C_AMBER))

        set_traitees_bar = QBarSet("DISA traitées")
        set_traitees_bar.setColor(QColor(_C_BLUE))
        set_traitees_bar.setBorderColor(QColor(_C_BLUE))

        if localites:
            for r in disa_restantes:
                set_restantes.append(r)
            for t in disa_traitees_loc:
                set_traitees_bar.append(t)
        else:
            localites = ["Aucune donnée"]
            set_restantes.append(0)
            set_traitees_bar.append(0)

        series_bar.append(set_restantes)
        series_bar.append(set_traitees_bar)
        chart_bar.addSeries(series_bar)

        axis_x_bar = QBarCategoryAxis()
        axis_x_bar.append([_truncate(loc, 18) for loc in localites])
        axis_x_bar.setLabelsAngle(-30)
        self._style_axis(axis_x_bar)
        chart_bar.addAxis(axis_x_bar, Qt.AlignBottom)
        series_bar.attachAxis(axis_x_bar)

        max_y = max([max(disa_restantes or [0]), max(disa_traitees_loc or [0])])
        axis_y_bar = QValueAxis()
        axis_y_bar.setRange(0, max_y * 1.2 if max_y > 0 else 1)
        self._style_axis(axis_y_bar)
        chart_bar.addAxis(axis_y_bar, Qt.AlignLeft)
        series_bar.attachAxis(axis_y_bar)

        self._style_legend(chart_bar)

        # Popup de survol
        def show_detail(status: bool, index: int, _serie: str) -> None:
            if not status or index < 0 or index >= len(localites):
                if self._detail_dialog is not None:
                    self._detail_dialog.hide()
                return
            loc_name = localites[index]
            r_val = disa_restantes[index]
            t_val = disa_traitees_loc[index]
            if self._detail_dialog is None:
                self._detail_dialog = QDialog()
                self._detail_dialog.setWindowTitle("Détail DISA par localité")
                self._detail_dialog.setModal(False)
                vb = QVBoxLayout(self._detail_dialog)
                self._detail_label = QLabel()
                self._detail_label.setStyleSheet(
                    "font-size: 13px; font-weight: 600; padding: 8px;"
                )
                vb.addWidget(self._detail_label)
            if self._detail_label is not None:
                self._detail_label.setText(
                    f"<b>Localité :</b> {loc_name}<br>"
                    f"<b>DISA restantes :</b> {r_val}<br>"
                    f"<b>DISA traitées :</b> {t_val}"
                )
            self._detail_dialog.setWindowFlags(Qt.ToolTip)
            self._detail_dialog.adjustSize()
            pos = QCursor.pos()
            self._detail_dialog.move(pos.x() + 15, pos.y() + 15)
            self._detail_dialog.show()

        try:
            set_restantes.hovered.connect(
                lambda s, i: show_detail(s, i, "restantes")
            )
            set_traitees_bar.hovered.connect(
                lambda s, i: show_detail(s, i, "traitees")
            )
        except Exception:
            pass

        view_bar = self._styled_chart_view(chart_bar, min_h=320)
        view_bar.setMaximumHeight(480)
        bar_card_lay.addWidget(view_bar)
        layout.addWidget(bar_card, 2, 0, 1, 4)

        # ── LIGNE 3 : Barres horizontales par secteur ─────────────────
        sect_card, sect_card_lay = self._make_chart_card(
            "Employeurs par secteur d'activité",
            "Top secteurs — nombre d'employeurs enregistrés",
            delay_ms=340,
        )

        if not secteurs:
            secteurs = ["Aucune donnée"]
            secteurs_nb = [0]

        # Tronquer les libellés de secteur pour éviter le "..."
        secteurs_display = [_truncate(s, 24) for s in secteurs]

        sect_set = QBarSet("Employeurs")
        sect_set.setColor(QColor(_C_NAVY))
        sect_set.setBorderColor(QColor(_C_NAVY))
        for n in secteurs_nb:
            sect_set.append(n)

        sect_series = QHorizontalBarSeries()
        sect_series.append(sect_set)
        sect_series.setBarWidth(0.55)
        sect_series.setLabelsVisible(True)

        sect_chart = self._base_chart()
        sect_chart.addSeries(sect_series)
        sect_chart.setMargins(QMargins(8, 4, 24, 4))

        axis_y_sect = QBarCategoryAxis()
        axis_y_sect.append(secteurs_display)
        self._style_axis(axis_y_sect)
        sect_chart.addAxis(axis_y_sect, Qt.AlignLeft)
        sect_series.attachAxis(axis_y_sect)

        max_sect = max(secteurs_nb) if secteurs_nb else 1
        axis_x_sect = QValueAxis()
        axis_x_sect.setRange(0, max_sect * 1.3)
        axis_x_sect.setLabelFormat("%d")
        axis_x_sect.setTickCount(5)
        self._style_axis(axis_x_sect)
        sect_chart.addAxis(axis_x_sect, Qt.AlignBottom)
        sect_series.attachAxis(axis_x_sect)

        sect_chart.legend().setVisible(False)

        # Hauteur adaptée au nombre de secteurs
        min_h_sect = max(200, len(secteurs) * 32 + 60)
        sect_card_lay.addWidget(self._styled_chart_view(sect_chart, min_h=min_h_sect))
        layout.addWidget(sect_card, 3, 0, 1, 4)

    # ── Responsive fonts ──────────────────────────────────────────────────────

    def update_font_sizes(self, scale: float) -> None:
        def _clamp(size: int, lo: int = 8, hi: int = 26) -> int:
            return max(lo, min(hi, size))

        for lbl, base_size in self._responsive_label_specs:
            new_size = _clamp(int(base_size * scale))
            font = QFont(lbl.font())
            font.setPointSize(new_size)
            lbl.setFont(font)
