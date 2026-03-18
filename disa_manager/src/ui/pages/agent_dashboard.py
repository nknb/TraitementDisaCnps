"""Tableau de bord personnalisé pour les utilisateurs avec le rôle « agent ».

Affiche uniquement les statistiques liées à l'agent connecté (traite_par = username).
"""

from PySide6.QtCore import Qt, QMargins, QPropertyAnimation, QEasingCurve, QTimer, QDate
from PySide6.QtGui import QPainter, QColor, QFont
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
    QHBoxLayout,
    QGraphicsOpacityEffect,
    QPushButton,
    QDateEdit,
)

from db.connection import get_connection
from core.events import get_data_bus
from core.session import get_current_user
from ui.dashboard_theme import (
    _BG_DEEP, _BG_CARD, _BG_HDR, _BORDER,
    _TXT1, _TXT2, _TXT3, _GRID,
    _C_NAVY, _C_GREEN, _C_AMBER, _C_BLUE, _C_VIOLET,
    DATE_EDIT_QSS as _DATE_EDIT_QSS, BTN_QSS as _BTN_QSS,
    truncate as _truncate,
)


class AgentChartWidget:
    """Dashboard personnalisé : statistiques propres à l'agent connecté."""

    def __init__(self, widget: QGridLayout) -> None:
        self.widget = widget
        self._responsive_label_specs: list[tuple[QLabel, int]] = []
        self._animations: list[QPropertyAnimation] = []

        # Filtres actifs (plage de dates — défaut : année en cours)
        _y = QDate.currentDate().year()
        self._filter_date_from: str = f"{_y}-01-01"
        self._filter_date_to:   str = f"{_y}-12-31"

        get_data_bus().data_changed.connect(self.refresh)

    def refresh(self) -> None:
        self._animations.clear()
        self.add_chart()

    # ── Filtres ───────────────────────────────────────────────────────────────

    def _date_conditions(self) -> tuple[str, str, list]:
        """Renvoie (join_cond, and_cond, params) pour la plage de dates active.

        Filtre sur COALESCE(updated_at, created_at) pour inclure les
        enregistrements modifiés même s'ils ont été créés dans une autre année.
        """
        date_col = "COALESCE(td.updated_at, td.created_at)"
        join_cond = f"AND date({date_col}) BETWEEN ? AND ?"
        and_cond  = f"AND date({date_col}) BETWEEN ? AND ?"
        return join_cond, and_cond, [self._filter_date_from, self._filter_date_to]

    def _make_filter_bar(self) -> QFrame:
        """Barre de filtres sombre (plage de dates : Du … Au …)."""
        bar = QFrame()
        bar.setStyleSheet(
            f"""
            QFrame {{
                background-color: {_BG_HDR};
                border-radius: 10px;
                border: 1px solid {_BORDER};
            }}
            QLabel {{
                color: {_TXT2};
                font-size: 11px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
            """
        )
        bar.setMinimumHeight(46)

        hbox = QHBoxLayout(bar)
        hbox.setContentsMargins(16, 8, 16, 8)
        hbox.setSpacing(10)

        icon = QLabel("🗓")
        icon.setStyleSheet("font-size: 14px; border: none; background: transparent;")
        hbox.addWidget(icon)

        def _make_date_edit(stored_value: str) -> QDateEdit:
            de = QDateEdit()
            de.setCalendarPopup(True)
            de.setDisplayFormat("dd/MM/yyyy")
            de.setStyleSheet(_DATE_EDIT_QSS)
            de.setDate(QDate.fromString(stored_value, "yyyy-MM-dd"))
            return de

        hbox.addWidget(QLabel("Du :"))
        date_from = _make_date_edit(self._filter_date_from)
        date_from.dateChanged.connect(self._on_date_from_changed)
        hbox.addWidget(date_from)

        hbox.addWidget(QLabel("  Au :"))
        date_to = _make_date_edit(self._filter_date_to)
        date_to.dateChanged.connect(self._on_date_to_changed)
        hbox.addWidget(date_to)

        hbox.addStretch(1)

        reset_btn = QPushButton("↺  Réinitialiser")
        reset_btn.setStyleSheet(_BTN_QSS)
        reset_btn.clicked.connect(self._on_filter_reset)
        hbox.addWidget(reset_btn)

        return bar

    def _on_date_from_changed(self, date: QDate) -> None:
        self._filter_date_from = date.toString("yyyy-MM-dd")
        self.refresh()

    def _on_date_to_changed(self, date: QDate) -> None:
        self._filter_date_to = date.toString("yyyy-MM-dd")
        self.refresh()

    def _on_filter_reset(self) -> None:
        _y = QDate.currentDate().year()
        self._filter_date_from = f"{_y}-01-01"
        self._filter_date_to   = f"{_y}-12-31"
        self.refresh()

    # ── Helpers (réutilisent la même palette sombre) ──────────────────────────

    def _fade_in(self, widget, delay_ms: int = 0) -> None:
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
            f"color: {accent}; font-weight: 800; border: none; background: transparent;"
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
            (lbl_title, 9), (lbl_value, 24), (lbl_sub, 9),
        ])
        self._fade_in(frame, delay_ms)
        return frame

    def _make_chart_card(
        self, title: str, subtitle: str, delay_ms: int = 0
    ) -> tuple[QFrame, QVBoxLayout]:
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

    @staticmethod
    def _base_chart(bg: str = _BG_CARD) -> QChart:
        chart = QChart()
        chart.setTheme(QChart.ChartTheme.ChartThemeDark)
        chart.setTitle("")
        chart.setBackgroundBrush(QColor(bg))
        chart.setBackgroundRoundness(0)
        chart.setMargins(QMargins(10, 6, 10, 6))
        chart.setAnimationOptions(QChart.AnimationOption.AllAnimations)
        chart.setAnimationDuration(700)
        tf = chart.titleFont()
        tf.setPointSize(1)
        chart.setTitleFont(tf)
        return chart

    @staticmethod
    def _chart_view(chart: QChart, min_h: int = 200) -> QChartView:
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

    def _style_axis(self, axis) -> None:
        lf = axis.labelsFont()
        lf.setPointSize(9)
        axis.setLabelsFont(lf)
        axis.setLabelsColor(QColor(_TXT2))
        if isinstance(axis, QValueAxis):
            axis.setGridLineColor(QColor(_GRID))

    # ── Bannière d'accueil agent ──────────────────────────────────────────────

    def _make_welcome_banner(self, username: str) -> QFrame:
        """Bannière de bienvenue personnalisée pour l'agent."""
        banner = QFrame()
        banner.setStyleSheet(
            f"""
            QFrame {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 {_BG_HDR}, stop:1 #1a2f4a
                );
                border-radius: 12px;
                border: 1px solid {_BORDER};
                border-left: 4px solid {_C_BLUE};
            }}
            """
        )
        banner.setMinimumHeight(60)
        hbox = QHBoxLayout(banner)
        hbox.setContentsMargins(20, 12, 20, 12)
        hbox.setSpacing(12)

        icon_lbl = QLabel("👤")
        icon_lbl.setStyleSheet("border: none; background: transparent; font-size: 22px;")

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        greet = QLabel(f"Bonjour, {username.capitalize()} 👋")
        greet.setStyleSheet(
            f"color: {_TXT1}; font-weight: 700; font-size: 14px;"
            " border: none; background: transparent;"
        )
        sub = QLabel("Voici vos statistiques personnelles de traitement DiSA")
        sub.setStyleSheet(
            f"color: {_TXT2}; font-size: 11px; border: none; background: transparent;"
        )
        text_layout.addWidget(greet)
        text_layout.addWidget(sub)

        hbox.addWidget(icon_lbl)
        hbox.addLayout(text_layout)
        hbox.addStretch(1)

        self._fade_in(banner, delay_ms=0)
        return banner

    # ── Construction principale ───────────────────────────────────────────────

    def add_chart(self) -> None:
        """Construit le dashboard agent :
        - Ligne 0 : Barre de filtres
        - Ligne 1 : Bannière personnalisée
        - Ligne 2 : 4 KPI propres à l'agent
        - Ligne 3 : Camembert (mes statuts) | Barres (mes traitements par localité)
        - Ligne 4 : Barres (mes traitements par exercice)
        """
        layout: QGridLayout = self.widget
        self._responsive_label_specs = []
        self._animations.clear()

        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

        # Fond sombre
        parent = layout.parentWidget()
        if parent is not None:
            parent.setStyleSheet(f"background-color: {_BG_DEEP};")

        # Récupérer l'utilisateur courant
        user = get_current_user()
        username = user.username if user else "agent"

        # ── Filtres ────────────────────────────────────────────────────
        _join_cond, and_cond, dparams = self._date_conditions()

        # ── Données ───────────────────────────────────────────────────
        mes_traitees       = 0
        mes_ce_mois        = 0
        mes_employeurs     = 0
        total_global       = 0
        mes_localites: list[str] = []
        mes_restantes_loc: list[int] = []
        mes_traitees_loc: list[int] = []
        mes_exercices: list[str] = []
        mes_traitees_ex: list[int] = []

        try:
            conn = get_connection()
            with conn:
                cur = conn.cursor()

                # 1) Total de mes DISA traitées (filtrées)
                cur.execute(
                    f"""
                    SELECT COUNT(*) FROM traitement_disa td
                    WHERE td.traite_par = ?
                      AND COALESCE(td.statut, 'NON TRAITÉ') <> 'NON TRAITÉ'
                      {and_cond}
                    """,
                    (username, *dparams),
                )
                mes_traitees = cur.fetchone()[0] or 0

                # 2) Mes traitements du mois courant (dans la plage filtrée)
                cur.execute(
                    f"""
                    SELECT COUNT(*) FROM traitement_disa td
                    WHERE td.traite_par = ?
                      AND COALESCE(td.statut, 'NON TRAITÉ') <> 'NON TRAITÉ'
                      AND strftime('%Y-%m', td.created_at) = strftime('%Y-%m', 'now')
                      {and_cond}
                    """,
                    (username, *dparams),
                )
                mes_ce_mois = cur.fetchone()[0] or 0

                # 3) Nombre d'employeurs distincts que j'ai traités (filtrés)
                cur.execute(
                    f"""
                    SELECT COUNT(DISTINCT td.employeur_id) FROM traitement_disa td
                    WHERE td.traite_par = ?
                      AND COALESCE(td.statut, 'NON TRAITÉ') <> 'NON TRAITÉ'
                      {and_cond}
                    """,
                    (username, *dparams),
                )
                mes_employeurs = cur.fetchone()[0] or 0

                # 4) Total global pour calculer ma contribution (filtrés)
                cur.execute(
                    f"""
                    SELECT COUNT(*) FROM traitement_disa td
                    WHERE COALESCE(td.statut, 'NON TRAITÉ') <> 'NON TRAITÉ'
                      {and_cond}
                    """,
                    dparams,
                )
                total_global = cur.fetchone()[0] or 0

                # 5) Mes traitements par localité (filtrés via AND dans WHERE)
                cur.execute(
                    f"""
                    SELECT COALESCE(ie.localites, 'NON RENSEIGNÉE') AS loc,
                           SUM(CASE WHEN COALESCE(td.statut,'NON TRAITÉ')='NON TRAITÉ'
                                    THEN 1 ELSE 0 END) AS restant,
                           SUM(CASE WHEN COALESCE(td.statut,'NON TRAITÉ')<>'NON TRAITÉ'
                                    THEN 1 ELSE 0 END) AS traite
                    FROM traitement_disa td
                    JOIN identification_employeurs ie ON ie.id = td.employeur_id
                    WHERE td.traite_par = ?
                      {and_cond}
                    GROUP BY COALESCE(ie.localites, 'NON RENSEIGNÉE')
                    ORDER BY traite DESC
                    """,
                    (username, *dparams),
                )
                for loc, restant, traite in cur.fetchall():
                    mes_localites.append(str(loc))
                    mes_restantes_loc.append(int(restant or 0))
                    mes_traitees_loc.append(int(traite or 0))

                # 6) Mes traitements par exercice (filtrés)
                cur.execute(
                    f"""
                    SELECT CAST(td.exercice AS TEXT) AS ex, COUNT(*) AS nb
                    FROM traitement_disa td
                    WHERE td.traite_par = ?
                      AND COALESCE(td.statut, 'NON TRAITÉ') <> 'NON TRAITÉ'
                      AND td.exercice IS NOT NULL
                      {and_cond}
                    GROUP BY td.exercice
                    ORDER BY td.exercice
                    """,
                    (username, *dparams),
                )
                for ex, nb in cur.fetchall():
                    mes_exercices.append(str(ex))
                    mes_traitees_ex.append(int(nb or 0))

        except Exception as _exc:
            import traceback
            traceback.print_exc()

        # ── Grille 4 colonnes ─────────────────────────────────────────
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)
        layout.setContentsMargins(14, 12, 14, 12)
        for col in range(4):
            layout.setColumnStretch(col, 1)

        # ── LIGNE 0 : Barre de filtres (pleine largeur) ───────────────
        layout.addWidget(self._make_filter_bar(), 0, 0, 1, 4)

        # ── LIGNE 1 : Bannière de bienvenue (pleine largeur) ──────────
        layout.addWidget(self._make_welcome_banner(username), 1, 0, 1, 4)

        # ── LIGNE 2 : 4 KPI ──────────────────────────────────────────
        contrib = int(mes_traitees / total_global * 100) if total_global > 0 else 0

        kpis = [
            ("Mes DISA traitées",   str(mes_traitees),   "Total personnel (période)",  _C_BLUE),
            ("Ce mois-ci",          str(mes_ce_mois),    "Mois en cours",              _C_GREEN),
            ("Employeurs traités",  str(mes_employeurs), "Employeurs distincts",        _C_NAVY),
            ("Ma contribution",     f"{contrib} %",      "Part du total global",        _C_VIOLET),
        ]
        for col, (title, value, sub, accent) in enumerate(kpis):
            layout.addWidget(
                self._make_kpi_card(title, value, sub, accent, delay_ms=80 + col * 80),
                2, col,
            )

        # ── LIGNE 3 : Camembert statut | Barres par localité ─────────

        pie_card, pie_lay = self._make_chart_card(
            "Mes DISA — statut global",
            "Traitées par moi vs total non traité (période)",
            delay_ms=180,
        )
        pie_series = QPieSeries()
        s_t = pie_series.append(f"Traitées par moi  ({mes_traitees})", max(mes_traitees, 1))
        non_traitees_global = max(total_global - mes_traitees, 0)
        s_n = pie_series.append(f"Reste global  ({non_traitees_global})", max(non_traitees_global, 1))
        s_t.setColor(QColor(_C_GREEN));  s_t.setBorderColor(QColor(_C_GREEN))
        s_n.setColor(QColor(_C_AMBER));  s_n.setBorderColor(QColor(_C_AMBER))
        s_t.setExploded(True);           s_t.setExplodeDistanceFactor(0.06)

        pie_chart = self._base_chart()
        pie_chart.addSeries(pie_series)
        pie_chart.setMargins(QMargins(8, 4, 8, 4))
        self._style_legend(pie_chart)
        pie_lay.addWidget(self._chart_view(pie_chart, min_h=200))
        layout.addWidget(pie_card, 3, 0, 1, 2)

        # Barres horizontales : mes traitements par localité
        loc_card, loc_lay = self._make_chart_card(
            "Mes traitements par localité",
            "DISA que j'ai traitées — par localité d'employeur (période)",
            delay_ms=260,
        )
        if not mes_localites:
            mes_localites = ["Aucune donnée"]
            mes_traitees_loc = [0]

        loc_set = QBarSet("Mes traitements")
        loc_set.setColor(QColor(_C_BLUE))
        loc_set.setBorderColor(QColor(_C_BLUE))
        for n in mes_traitees_loc:
            loc_set.append(n)

        loc_series = QHorizontalBarSeries()
        loc_series.append(loc_set)
        loc_series.setBarWidth(0.55)
        loc_series.setLabelsVisible(True)

        loc_chart = self._base_chart()
        loc_chart.addSeries(loc_series)
        loc_chart.setMargins(QMargins(8, 4, 20, 4))

        ax_y_loc = QBarCategoryAxis()
        ax_y_loc.append([_truncate(l, 22) for l in mes_localites])
        self._style_axis(ax_y_loc)
        loc_chart.addAxis(ax_y_loc, Qt.AlignLeft)
        loc_series.attachAxis(ax_y_loc)

        max_loc = max(mes_traitees_loc) if mes_traitees_loc else 1
        ax_x_loc = QValueAxis()
        ax_x_loc.setRange(0, max_loc * 1.3)
        ax_x_loc.setLabelFormat("%d")
        ax_x_loc.setTickCount(5)
        self._style_axis(ax_x_loc)
        loc_chart.addAxis(ax_x_loc, Qt.AlignBottom)
        loc_series.attachAxis(ax_x_loc)
        loc_chart.legend().setVisible(False)

        min_h_loc = max(180, len(mes_localites) * 30 + 60)
        loc_lay.addWidget(self._chart_view(loc_chart, min_h=min_h_loc))
        layout.addWidget(loc_card, 3, 2, 1, 2)

        # ── LIGNE 4 : Évolution par exercice (pleine largeur) ─────────
        ex_card, ex_lay = self._make_chart_card(
            "Mes traitements par exercice",
            "Nombre de DISA que j'ai traitées — par exercice fiscal (période)",
            delay_ms=340,
        )

        if not mes_exercices:
            mes_exercices = ["—"]
            mes_traitees_ex = [0]

        ex_set = QBarSet("DISA traitées")
        ex_set.setColor(QColor(_C_VIOLET))
        ex_set.setBorderColor(QColor(_C_VIOLET))
        for n in mes_traitees_ex:
            ex_set.append(n)

        ex_series = QBarSeries()
        ex_series.append(ex_set)
        ex_series.setBarWidth(0.6)
        ex_series.setLabelsVisible(True)

        ex_chart = self._base_chart()
        ex_chart.addSeries(ex_series)
        ex_chart.setMargins(QMargins(12, 8, 12, 8))

        ax_x_ex = QBarCategoryAxis()
        ax_x_ex.append(mes_exercices)
        self._style_axis(ax_x_ex)
        ex_chart.addAxis(ax_x_ex, Qt.AlignBottom)
        ex_series.attachAxis(ax_x_ex)

        max_ex = max(mes_traitees_ex) if mes_traitees_ex else 1
        ax_y_ex = QValueAxis()
        ax_y_ex.setRange(0, max_ex * 1.2)
        ax_y_ex.setLabelFormat("%d")
        ax_y_ex.setTickCount(5)
        self._style_axis(ax_y_ex)
        ex_chart.addAxis(ax_y_ex, Qt.AlignLeft)
        ex_series.attachAxis(ax_y_ex)

        self._style_legend(ex_chart)

        ex_lay.addWidget(self._chart_view(ex_chart, min_h=240))
        layout.addWidget(ex_card, 4, 0, 1, 4)

    # ── Responsive fonts ──────────────────────────────────────────────────────

    def update_font_sizes(self, scale: float) -> None:
        def _clamp(size: int, lo: int = 8, hi: int = 26) -> int:
            return max(lo, min(hi, size))

        for lbl, base_size in self._responsive_label_specs:
            new_size = _clamp(int(base_size * scale))
            font = QFont(lbl.font())
            font.setPointSize(new_size)
            lbl.setFont(font)
