# Guide — Dashboard, Utilisateurs & Base de données
> Code exact extrait de TraitementDisaCnps — prêt à adapter dans le projet **Accueil**.

---

## Sommaire

1. [Dashboard (ChartWidget)](#1-dashboard-chartwidget)
2. [Widget Utilisateurs (UsersWidget)](#2-widget-utilisateurs-userswidget)
3. [Widget Base de données (EmployersDatabaseWidget)](#3-widget-base-de-données)
4. [Styles partagés (copier-coller)](#4-styles-partagés)

---

## 1. Dashboard (ChartWidget)

### Imports nécessaires

```python
from __future__ import annotations

from PySide6.QtCore import Qt, QMargins, QPropertyAnimation, QEasingCurve, QTimer, QDate
from PySide6.QtGui import QPainter, QColor, QFont, QCursor
from PySide6.QtCharts import (
    QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView,
    QHorizontalBarSeries, QPieSeries, QValueAxis,
)
from PySide6.QtWidgets import (
    QGridLayout, QLabel, QFrame, QVBoxLayout, QHBoxLayout,
    QDialog, QGraphicsOpacityEffect, QPushButton, QDateEdit,
)
```

### Constantes de couleurs (dashboard_theme.py)

```python
# Fonds
_BG_DEEP  = "#0d1520"
_BG_CARD  = "#182233"
_BG_HDR   = "#111d2e"

# Bordures & grille
_BORDER   = "#243147"
_GRID     = "#1e3a5f"

# Textes
_TXT1     = "#e2e8f0"
_TXT2     = "#94a3b8"
_TXT3     = "#64748b"

# Accents
_C_NAVY   = "#3b82f6"
_C_GREEN  = "#10b981"
_C_AMBER  = "#f59e0b"
_C_BLUE   = "#60a5fa"
_C_VIOLET = "#a78bfa"

# Palette multi-utilisateurs (pour camembert par user)
_USER_COLORS = [
    "#3b82f6", "#10b981", "#f59e0b", "#f87171",
    "#a78bfa", "#22d3ee", "#84cc16", "#fb923c",
]

def truncate(text: str, max_len: int = 20) -> str:
    return text if len(text) <= max_len else text[:max_len - 1] + "…"

# QSS du filtre de dates
DATE_EDIT_QSS = f"""
QDateEdit {{
    background: {_BG_CARD}; color: {_TXT1};
    border: 1px solid {_BORDER}; border-radius: 6px;
    padding: 4px 8px; min-width: 100px;
}}
QDateEdit::drop-down {{
    background: {_C_NAVY}; border-radius: 4px; width: 24px;
}}
QCalendarWidget QAbstractItemView {{
    background: {_BG_CARD}; color: {_TXT1};
    selection-background-color: {_C_NAVY};
}}
"""

# QSS bouton reset
BTN_QSS = f"""
QPushButton {{
    background: {_BORDER}; color: {_TXT1};
    border: none; border-radius: 6px; padding: 5px 14px; font-weight: 600;
}}
QPushButton:hover   {{ background: {_C_NAVY}; }}
QPushButton:pressed {{ background: #1d4ed8; }}
"""
```

### Structure du ChartWidget

Le dashboard n'est **pas** un QWidget — c'est une classe utilitaire qui reçoit
un `QGridLayout` comme cible de rendu. Il se reconstruit entièrement à chaque `refresh()`.

```
ChartWidget(widget=grid_layout)
├── _make_filter_bar()       → barre Du … Au … + bouton Réinitialiser
├── _make_kpi_card()         → carte KPI (titre, valeur, sous-titre, couleur)
├── _make_chart_card()       → carte graphique (header sombre + zone contenu)
├── _base_chart()            → QChart avec thème sombre
├── _styled_chart_view()     → QChartView avec fond transparent
├── _style_legend()          → légende en bas, texte clair
├── _style_axis()            → axes avec couleurs du thème
├── _fade_in()               → animation opacité 0→1 avec délai
└── add_chart()              → reconstruit toute la grille
```

### Initialisation

```python
class ChartWidget:
    def __init__(self, widget):
        # widget = le QGridLayout de la page dashboard
        self.widget = widget
        self._responsive_label_specs: list[tuple[QLabel, int]] = []
        self._detail_dialog = None
        self._detail_label  = None
        self._animations: list[QPropertyAnimation] = []

        # Filtre date — défaut : année en cours
        _y = QDate.currentDate().year()
        self._filter_date_from = f"{_y}-01-01"
        self._filter_date_to   = f"{_y}-12-31"

        get_data_bus().data_changed.connect(self.refresh)

    def refresh(self) -> None:
        self._animations.clear()
        self.add_chart()
```

### Barre de filtres (dates)

```python
def _make_filter_bar(self) -> QFrame:
    bar = QFrame()
    bar.setStyleSheet(f"""
        QFrame {{ background-color: {_BG_HDR}; border-radius: 10px;
                  border: 1px solid {_BORDER}; }}
        QLabel {{ color: {_TXT2}; font-size: 11px; font-weight: 600;
                  background: transparent; border: none; }}
    """)
    bar.setMinimumHeight(46)

    hbox = QHBoxLayout(bar)
    hbox.setContentsMargins(16, 8, 16, 8)
    hbox.setSpacing(10)

    hbox.addWidget(QLabel("🗓"))

    def _make_date_edit(stored_value: str) -> QDateEdit:
        de = QDateEdit()
        de.setCalendarPopup(True)
        de.setDisplayFormat("dd/MM/yyyy")
        de.setStyleSheet(DATE_EDIT_QSS)
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
    reset_btn.setStyleSheet(BTN_QSS)
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
```

### Carte KPI

```python
def _make_kpi_card(self, title: str, value: str,
                   subtitle: str, accent: str, delay_ms: int = 0) -> QFrame:
    frame = QFrame()
    frame.setStyleSheet(f"""
        QFrame {{
            background-color: {_BG_CARD};
            border-radius: 12px;
            border: 1px solid {_BORDER};
            border-top: 3px solid {accent};   /* ← barre de couleur en haut */
        }}
    """)
    frame.setMinimumHeight(110)

    vbox = QVBoxLayout(frame)
    vbox.setContentsMargins(14, 10, 14, 10)
    vbox.setSpacing(4)

    lbl_title = QLabel(title.upper())
    lbl_title.setStyleSheet(
        f"color: {_TXT3}; font-weight: 600; letter-spacing: 0.7px;"
        " border: none; background: transparent;"
    )
    lbl_value = QLabel(value)
    lbl_value.setStyleSheet(
        f"color: {accent}; font-size: 20px; font-weight: 800;"
        " border: none; background: transparent;"
    )
    lbl_sub = QLabel(subtitle)
    lbl_sub.setStyleSheet(f"color: {_TXT3}; border: none; background: transparent;")

    vbox.addWidget(lbl_title)
    vbox.addWidget(lbl_value)
    vbox.addWidget(lbl_sub)
    vbox.addStretch(1)

    self._fade_in(frame, delay_ms)
    return frame
```

### Carte graphique (conteneur)

```python
def _make_chart_card(self, title: str, subtitle: str,
                     delay_ms: int = 0) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setStyleSheet(f"""
        QFrame {{
            background-color: {_BG_CARD};
            border-radius: 12px;
            border: 1px solid {_BORDER};
        }}
    """)
    outer = QVBoxLayout(card)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    # En-tête de la carte
    hdr = QFrame()
    hdr.setStyleSheet(f"""
        QFrame {{
            background-color: {_BG_HDR};
            border: none; border-radius: 12px;
            border-bottom-left-radius: 0; border-bottom-right-radius: 0;
            border-bottom: 1px solid {_BORDER};
        }}
    """)
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
    return card, outer   # outer = layout où ajouter le QChartView
```

### Graphiques de base

```python
def _base_chart(self) -> QChart:
    chart = QChart()
    chart.setTheme(QChart.ChartTheme.ChartThemeDark)
    chart.setTitle("")
    chart.setBackgroundBrush(QColor(_BG_CARD))
    chart.setBackgroundRoundness(0)
    chart.setMargins(QMargins(10, 6, 10, 6))
    chart.setAnimationOptions(QChart.AnimationOption.AllAnimations)
    chart.setAnimationDuration(700)
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

def _style_axis(self, axis) -> None:
    lf = axis.labelsFont()
    lf.setPointSize(9)
    axis.setLabelsFont(lf)
    axis.setLabelsColor(QColor(_TXT2))
    if isinstance(axis, QValueAxis):
        axis.setGridLineColor(QColor(_GRID))
```

### Fade-in des cartes

```python
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
        self._animations.append(anim)   # garder une référence sinon GC tue l'anim

    if delay_ms > 0:
        QTimer.singleShot(delay_ms, _start)
    else:
        _start()
```

### Construction complète de la grille (add_chart)

```python
def add_chart(self):
    layout: QGridLayout = self.widget
    self._responsive_label_specs = []
    self._animations.clear()

    # Vider le layout
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()

    # Fond sombre de la page
    parent = layout.parentWidget()
    if parent is not None:
        parent.setStyleSheet(f"background-color: {_BG_DEEP};")

    # ── Charger les données depuis la BDD ────────────────────────────
    join_cond, and_cond, dparams = self._date_conditions()
    total, traites, non_traites = 0, 0, 0
    localites, restantes, traitees_loc = [], [], []
    secteurs, secteurs_nb = [], []
    users, users_nb = [], []

    # … (vos requêtes SQL ici) …

    # ── Grille ───────────────────────────────────────────────────────
    layout.setHorizontalSpacing(10)
    layout.setVerticalSpacing(10)
    layout.setContentsMargins(14, 12, 14, 12)
    for col in range(4):
        layout.setColumnStretch(col, 1)

    # Ligne 0 — barre filtres
    layout.addWidget(self._make_filter_bar(), 0, 0, 1, 4)

    # Ligne 1 — 4 cartes KPI
    kpi_data = [
        ("Titre 1", str(total),    "Sous-titre 1", _C_NAVY),
        ("Titre 2", str(traites),  "Sous-titre 2", _C_GREEN),
        ("Titre 3", str(non_traites), "Sous-titre 3", _C_AMBER),
        ("Taux",   f"{taux} %",   "Sous-titre 4", _C_BLUE),
    ]
    for col, (title, value, sub, accent) in enumerate(kpi_data):
        layout.addWidget(
            self._make_kpi_card(title, value, sub, accent, delay_ms=col * 80),
            1, col,
        )

    # Ligne 2 — camembert statut (gauche) | camembert par user (droite)
    pie_card, pie_lay = self._make_chart_card("Statut global", "Traitées vs Non traitées", 100)
    pie_series = QPieSeries()
    s1 = pie_series.append(f"Traitées ({traites})", max(traites, 1))
    s2 = pie_series.append(f"Non traitées ({non_traites})", max(non_traites, 1))
    s1.setColor(QColor(_C_BLUE));  s1.setBorderColor(QColor(_C_BLUE))
    s2.setColor(QColor(_C_AMBER)); s2.setBorderColor(QColor(_C_AMBER))
    s1.setExploded(True); s1.setExplodeDistanceFactor(0.05)
    pie_chart = self._base_chart()
    pie_chart.addSeries(pie_series)
    self._style_legend(pie_chart)
    pie_lay.addWidget(self._styled_chart_view(pie_chart, min_h=200))
    layout.addWidget(pie_card, 2, 0, 1, 2)

    # Ligne 2 — camembert par utilisateur (droite)
    user_card, user_lay = self._make_chart_card("Par utilisateur", "Contribution agents", 180)
    user_series = QPieSeries()
    for i, (u, nb) in enumerate(zip(users, users_nb)):
        sl = user_series.append(f"{u} ({nb})", nb)
        c = _USER_COLORS[i % len(_USER_COLORS)]
        sl.setColor(QColor(c)); sl.setBorderColor(QColor(c))
        if i == 0:
            sl.setExploded(True); sl.setExplodeDistanceFactor(0.05)
    user_chart = self._base_chart()
    user_chart.addSeries(user_series)
    self._style_legend(user_chart)
    user_lay.addWidget(self._styled_chart_view(user_chart, min_h=200))
    layout.addWidget(user_card, 2, 2, 1, 2)

    # Ligne 3 — barres groupées par localité
    bar_card, bar_lay = self._make_chart_card("Par localité", "DISA restantes vs traitées", 260)
    chart_bar = self._base_chart()
    series_bar = QBarSeries()
    series_bar.setBarWidth(0.65)
    series_bar.setLabelsVisible(True)

    set_r = QBarSet("Restantes"); set_r.setColor(QColor(_C_AMBER)); set_r.setBorderColor(QColor(_C_AMBER))
    set_t = QBarSet("Traitées");  set_t.setColor(QColor(_C_BLUE));  set_t.setBorderColor(QColor(_C_BLUE))
    for r in restantes:       set_r.append(r)
    for t in traitees_loc:    set_t.append(t)
    series_bar.append(set_r); series_bar.append(set_t)
    chart_bar.addSeries(series_bar)

    ax_x = QBarCategoryAxis()
    ax_x.append([truncate(l, 18) for l in localites])
    ax_x.setLabelsAngle(-30); self._style_axis(ax_x)
    chart_bar.addAxis(ax_x, Qt.AlignBottom); series_bar.attachAxis(ax_x)

    ax_y = QValueAxis()
    max_y = max([max(restantes or [0]), max(traitees_loc or [0])])
    ax_y.setRange(0, max_y * 1.2 if max_y > 0 else 1)
    self._style_axis(ax_y)
    chart_bar.addAxis(ax_y, Qt.AlignLeft); series_bar.attachAxis(ax_y)
    self._style_legend(chart_bar)

    bar_lay.addWidget(self._styled_chart_view(chart_bar, min_h=320))
    layout.addWidget(bar_card, 3, 0, 1, 4)

    # Ligne 4 — barres horizontales par secteur
    sect_card, sect_lay = self._make_chart_card("Par secteur", "Top 8 secteurs d'activité", 340)
    sect_set = QBarSet("Employeurs")
    sect_set.setColor(QColor(_C_NAVY)); sect_set.setBorderColor(QColor(_C_NAVY))
    for n in secteurs_nb: sect_set.append(n)

    sect_series = QHorizontalBarSeries()
    sect_series.append(sect_set)
    sect_series.setBarWidth(0.55); sect_series.setLabelsVisible(True)

    sect_chart = self._base_chart()
    sect_chart.addSeries(sect_series)

    ax_y_s = QBarCategoryAxis()
    ax_y_s.append([truncate(s, 24) for s in secteurs]); self._style_axis(ax_y_s)
    sect_chart.addAxis(ax_y_s, Qt.AlignLeft); sect_series.attachAxis(ax_y_s)

    ax_x_s = QValueAxis()
    ax_x_s.setRange(0, (max(secteurs_nb) if secteurs_nb else 1) * 1.3)
    ax_x_s.setLabelFormat("%d"); ax_x_s.setTickCount(5); self._style_axis(ax_x_s)
    sect_chart.addAxis(ax_x_s, Qt.AlignBottom); sect_series.attachAxis(ax_x_s)
    sect_chart.legend().setVisible(False)

    sect_lay.addWidget(self._styled_chart_view(sect_chart, min_h=220))
    layout.addWidget(sect_card, 4, 0, 1, 4)
```

### Filtre de dates (requête SQL)

```python
def _date_conditions(self) -> tuple[str, str, list]:
    """
    Retourne (join_cond, and_cond, params).
    join_cond : à placer dans la clause ON du LEFT JOIN
    and_cond  : à placer dans un WHERE existant (avec AND)
    """
    date_col = "COALESCE(td.updated_at, td.created_at)"
    join_cond = f"AND date({date_col}) BETWEEN ? AND ?"
    and_cond  = f"AND date({date_col}) BETWEEN ? AND ?"
    return join_cond, and_cond, [self._filter_date_from, self._filter_date_to]

# Utilisation :
# join_cond, and_cond, dparams = self._date_conditions()
#
# Requête avec JOIN filtré :
# f"""SELECT ... FROM table1
#      LEFT JOIN traitement_disa td ON td.fk = table1.id {join_cond}
#      GROUP BY ...""", dparams
#
# Requête avec WHERE filtré :
# f"""SELECT ... FROM traitement_disa td
#      WHERE statut <> 'NON TRAITÉ' {and_cond}
#      GROUP BY ...""", dparams
```

### Intégration dans MainWindow

```python
# Dans __init__ de MainWindow :
from PySide6.QtWidgets import QScrollArea, QWidget, QGridLayout

# Créer une zone scrollable pour le dashboard
scroll = QScrollArea()
scroll.setWidgetResizable(True)
scroll.setFrameShape(QFrame.Shape.NoFrame)

container = QWidget()
grid_layout = QGridLayout(container)
scroll.setWidget(container)

# Instancier le widget dashboard
self.chart_widget = ChartWidget(widget=grid_layout)
self.chart_widget.add_chart()

# Ajouter la scroll area à la page du StackedWidget
self.stacked.addWidget(scroll)

# Responsive : recalculer les fonts au resize
scroll.installEventFilter(self)

def eventFilter(self, obj, event):
    if obj is scroll and event.type() == QEvent.Type.Resize:
        self.chart_widget._update_fonts(obj.width())
    return super().eventFilter(obj, event)
```

---

## 2. Widget Utilisateurs (UsersWidget)

### Styles (copier-coller en haut du fichier)

```python
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
```

### UserFormDialog (dialogue Ajouter / Modifier)

```python
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QDialogButtonBox, QVBoxLayout,
    QLineEdit, QComboBox,
)
from PySide6.QtCore import Qt

class UserFormDialog(QDialog):
    def __init__(self, parent, username="", role="agent", with_password=True):
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
            orientation=Qt.Orientation.Horizontal, parent=self,
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

    def get_data(self) -> tuple[str, str | None, str]:
        username = self.username_edit.text().strip()
        password = self.password_edit.text().strip()
        role = self.role_combo.currentText().strip() or "agent"
        if not username:
            raise ValueError("Le nom d'utilisateur est obligatoire.")
        if self._with_password and not password:
            raise ValueError("Le mot de passe est obligatoire.")
        return username, (password or None), role
```

### UsersWidget — construction UI

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QTableWidget, QTableWidgetItem,
    QFrame, QHeaderView,
)
from PySide6.QtGui import QColor, QFont
from PySide6.QtCore import Qt

class UsersWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._users = []   # liste de (id, username, role)
        self._build_ui()
        self._refresh_table()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Bandeau titre avec dégradé ────────────────────────────────
        header = QFrame()
        header.setStyleSheet(
            "QFrame { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #1e3a5f, stop:1 #2a4f80); }"
        )
        h_box = QHBoxLayout(header)
        h_box.setContentsMargins(20, 14, 20, 14)
        h_box.setSpacing(16)

        lbl_title = QLabel("👤  Gestion des utilisateurs")
        f = QFont(); f.setPointSize(14); f.setBold(True)
        lbl_title.setFont(f)
        lbl_title.setStyleSheet("color: white; background: transparent;")

        # Compteurs rapides dans l'en-tête
        self._stat_total = QLabel("Total : 0")
        self._stat_admin = QLabel("Admins : 0")
        self._stat_agent = QLabel("Agents : 0")
        for lbl in (self._stat_total, self._stat_admin, self._stat_agent):
            lbl.setStyleSheet(
                "color: #93c5fd; font-size: 12px; font-weight: 600; background: transparent;"
            )

        h_box.addWidget(lbl_title)
        h_box.addStretch(1)
        h_box.addWidget(self._stat_total)
        h_box.addWidget(self._stat_admin)
        h_box.addWidget(self._stat_agent)
        root.addWidget(header)

        # ── Corps ────────────────────────────────────────────────────
        body = QFrame()
        body.setStyleSheet("QFrame { background: #f8fafc; }")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(16, 14, 16, 14)
        body_layout.setSpacing(10)

        # Barre : recherche + filtre rôle + bouton Ajouter
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
        self.table.setColumnHidden(0, True)   # masquer colonne ID
        self.table.setStyleSheet(
            "QTableWidget { background: white; border: 1px solid #e5e7eb;"
            " border-radius: 8px; font-size: 13px; color: #1f2937; }"
            "QTableWidget::item { padding: 8px 12px; border: none; }"
            "QTableWidget::item:selected { background: #dbeafe; color: #1e3a5f; }"
            "QHeaderView::section { background: #1e3a5f; color: white;"
            " font-weight: 700; font-size: 12px; padding: 8px 12px; border: none; }"
            "QTableWidget::item:alternate { background: #f1f5f9; }"
        )
        self.table.verticalHeader().setDefaultSectionSize(42)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
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
```

### Remplissage du tableau (badges rôle)

```python
def _refresh_table(self) -> None:
    # Charger depuis la BDD
    conn = get_connection()
    with conn:
        rows = conn.execute(
            "SELECT id, username, role FROM utilisateurs ORDER BY id DESC"
        ).fetchall()
    self._users = [(int(r[0]), str(r[1]), str(r[2])) for r in rows]

    # Stats en-tête
    all_roles = [r for _, _, r in self._users]
    self._stat_total.setText(f"Total : {len(self._users)}")
    self._stat_admin.setText(f"Admins : {all_roles.count('admin')}")
    self._stat_agent.setText(f"Agents : {all_roles.count('agent')}")

    # Appliquer filtres
    search = self.search_edit.text().strip().lower()
    role_filter = self.role_filter.currentData()
    filtered = [
        (uid, uname, role) for uid, uname, role in self._users
        if (role_filter is None or role == role_filter)
        and (not search or search in uname.lower())
    ]

    current_id = get_current_user().id if get_current_user() else None
    self.table.setSortingEnabled(False)
    self.table.setRowCount(len(filtered))

    for i, (uid, uname, role) in enumerate(filtered):
        is_me = current_id is not None and uid == current_id

        # Col 0 — ID caché
        id_item = QTableWidgetItem(str(uid))
        self.table.setItem(i, 0, id_item)

        # Col 1 — Nom (★ si c'est l'utilisateur connecté)
        display = f"★  {uname}  (vous)" if is_me else f"   {uname}"
        user_item = QTableWidgetItem(display)
        if is_me:
            f = user_item.font(); f.setBold(True); user_item.setFont(f)
            user_item.setForeground(QColor("#1e3a5f"))
        self.table.setItem(i, 1, user_item)

        # Col 2 — Rôle (badge coloré fond bleu ou vert)
        role_item = QTableWidgetItem(f"  {role.upper()}  ")
        role_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        rf = role_item.font(); rf.setBold(True); rf.setPointSize(10)
        role_item.setFont(rf)
        if role == "admin":
            role_item.setForeground(QColor("#ffffff"))
            role_item.setBackground(QColor("#1e3a5f"))
        else:
            role_item.setForeground(QColor("#ffffff"))
            role_item.setBackground(QColor("#15803d"))
        self.table.setItem(i, 2, role_item)

    self.table.setSortingEnabled(True)
    self.table.resizeColumnToContents(2)
```

### Protections intégrées (suppressions / rôles)

```python
# ① Ne pas supprimer son propre compte
if get_current_user() and get_current_user().id == user_id:
    QMessageBox.warning(self, "Suppression",
                        "Vous ne pouvez pas supprimer votre propre compte.")
    return

# ② Ne pas supprimer / dégrader le dernier admin
if role == "admin":
    (admin_count,) = conn.execute(
        "SELECT COUNT(*) FROM utilisateurs WHERE role='admin'"
    ).fetchone()
    if int(admin_count) <= 1:
        QMessageBox.warning(self, "Suppression",
                            "Vous ne pouvez pas supprimer le dernier administrateur.")
        return

# ③ Confirmation avant suppression
reply = QMessageBox.question(
    self, "Confirmer la suppression",
    "Voulez-vous vraiment supprimer cet utilisateur ?",
    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
    QMessageBox.StandardButton.No,
)
if reply != QMessageBox.StandardButton.Yes:
    return
```

---

## 3. Widget Base de données

### Styles spécifiques (en plus des boutons communs)

```python
_STYLE_BTN_EXPORT = (
    "QPushButton { background-color: #0369a1; color: white; border-radius: 5px; "
    "padding: 6px 14px; font-weight: 600; font-size: 12px; }"
    "QPushButton:hover { background-color: #0284c7; }"
    "QPushButton:pressed { background-color: #075985; }"
)
_STYLE_BTN_SUSPEND = (
    "QPushButton { background-color: #92400e; color: white; border-radius: 5px; "
    "padding: 6px 14px; font-weight: 600; font-size: 12px; }"
    "QPushButton:hover { background-color: #b45309; }"
    "QPushButton:pressed { background-color: #78350f; }"
)
_STYLE_INPUT = (
    "QLineEdit { border: 1px solid #d1d5db; border-radius: 4px; padding: 5px 8px; "
    "font-size: 12px; background: white; color: #1f2937; }"
    "QLineEdit:focus { border-color: #1e3a5f; border-width: 2px; }"
)
_STYLE_COMBO = (
    "QComboBox { border: 1px solid #d1d5db; border-radius: 4px; padding: 5px 24px 5px 8px; "
    "font-size: 12px; background: white; color: #1f2937; }"
    "QComboBox:focus { border-color: #1e3a5f; border-width: 2px; }"
    "QComboBox:hover { border-color: #93c5fd; }"
    "QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: right center; "
    "width: 20px; border: none; }"
    "QComboBox QAbstractItemView { border: 1px solid #d1d5db; background: white; "
    "selection-background-color: #dbeafe; selection-color: #1e3a5f; }"
)
_STYLE_TABLE = (
    "QTableWidget { border: 1px solid #e2e8f0; gridline-color: #f1f5f9; font-size: 12px; }"
    "QTableWidget::item { padding: 5px 8px; }"
    "QTableWidget::item:selected { background-color: #dbeafe; color: #1e3a5f; }"
    "QHeaderView::section { background-color: #1e3a5f; color: white; font-weight: 700; "
    "padding: 7px 8px; border: none; border-right: 1px solid #2a4f80; }"
    "QTableWidget::item:alternate { background-color: #f8fafc; }"
)
```

### En-tête avec badges de statut

```python
def _make_badge(self, text: str, color: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"background-color: {color}; color: white; border-radius: 10px;"
        " padding: 3px 10px; font-size: 11px; font-weight: 700;"
    )
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return lbl

# Dans _build_ui :
header_frame = QFrame()
header_frame.setStyleSheet(
    "background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
    "stop:0 #1e3a5f, stop:1 #2a4f80);"
    "border-radius: 8px; padding: 10px 16px;"
)
header_layout = QHBoxLayout(header_frame)
header_layout.setContentsMargins(16, 10, 16, 10)

title_lbl = QLabel("Base de données — Employeurs & DISA")
title_font = QFont(); title_font.setPointSize(14); title_font.setBold(True)
title_lbl.setFont(title_font)
title_lbl.setStyleSheet("color: white; background: transparent;")
header_layout.addWidget(title_lbl)
header_layout.addStretch(1)

self.status_non_traite_lbl = self._make_badge("Non traités : 0", "#dc2626")
self.status_valide_lbl     = self._make_badge("Validés : 0",     "#15803d")
self.status_rejet_lbl      = self._make_badge("Avec rejets : 0", "#d97706")
header_layout.addWidget(self.status_non_traite_lbl)
header_layout.addWidget(self.status_valide_lbl)
header_layout.addWidget(self.status_rejet_lbl)
```

### Barre de filtres avancée

```python
# Frame conteneur des filtres
filters_frame = QFrame()
filters_frame.setStyleSheet(
    "QFrame { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }"
)
filters_outer = QVBoxLayout(filters_frame)
filters_outer.setContentsMargins(14, 10, 14, 10)
filters_outer.setSpacing(8)

# Barre titre + badge count actif + bouton reset
filters_title_lbl = QLabel("FILTRES")
filters_title_lbl.setStyleSheet(
    "font-size: 11px; font-weight: 800; color: #374151; letter-spacing: 1px;"
)
self._filter_count_badge = QLabel()
self._filter_count_badge.setStyleSheet(
    "background-color: #1e3a5f; color: white; border-radius: 8px;"
    " padding: 1px 8px; font-size: 10px; font-weight: 700;"
)
self._filter_count_badge.hide()

reset_btn = QPushButton("↺  Réinitialiser")
reset_btn.setStyleSheet(_STYLE_BTN_NEUTRAL)
reset_btn.setFixedHeight(26); reset_btn.setMaximumWidth(120)
reset_btn.clicked.connect(self._reset_filters)

# Champ de recherche avec bouton ✕ intégré
self.search_edit = QLineEdit()
self.search_edit.setPlaceholderText("Rechercher par n°, raison sociale, localité…")
self.search_edit.setStyleSheet(_STYLE_INPUT)
self.search_edit.setFixedHeight(30)
self.search_edit.textChanged.connect(self._on_filters_changed)

self._search_clear_btn = QPushButton("✕")
self._search_clear_btn.setFixedSize(30, 30)
self._search_clear_btn.setStyleSheet(
    "QPushButton { background: #e5e7eb; color: #6b7280; border-radius: 4px; "
    "font-weight: 700; border: none; }"
    "QPushButton:hover { background: #dc2626; color: white; }"
)
self._search_clear_btn.hide()
self._search_clear_btn.clicked.connect(self.search_edit.clear)
self.search_edit.textChanged.connect(
    lambda t: self._search_clear_btn.setVisible(bool(t))
)
```

### EmployeurFormDialog (formulaire dynamique)

```python
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox,
    QLineEdit, QLabel,
)
from PySide6.QtCore import Qt

class EmployeurFormDialog(QDialog):
    """Formulaire généré dynamiquement depuis la liste des colonnes."""

    def __init__(self, parent, columns: list[str],
                 data: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Employeur — Base de données")
        self.setMinimumWidth(420)
        self._columns = [c for c in columns if c != "id"]
        self._editors = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 16)

        header = QLabel("Informations employeur")
        header.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #1e3a5f; padding-bottom: 4px;"
        )
        layout.addWidget(header)

        form = QFormLayout()
        form.setSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        for col in self._columns:
            editor = QLineEdit(self)
            editor.setStyleSheet(_STYLE_INPUT)
            if data and col in data and data[col] is not None:
                editor.setText(str(data[col]))
            label = QLabel(col.replace("_", " ").title())
            label.setStyleSheet("font-size: 12px; color: #374151; font-weight: 600;")
            form.addRow(label, editor)
            self._editors[col] = editor

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Enregistrer")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setStyleSheet(_STYLE_BTN_PRIMARY)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setStyleSheet(_STYLE_BTN_NEUTRAL)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self) -> dict:
        return {
            col: (editor.text().strip() or None)
            for col, editor in self._editors.items()
        }
```

### Pagination

```python
# Variables d'état
self._page_size    = 50
self._current_page = 1
self._total_rows   = 0

def _refresh_table(self) -> None:
    offset = (self._current_page - 1) * self._page_size
    conn = get_connection()
    with conn:
        # Compter le total
        self._total_rows = conn.execute(
            "SELECT COUNT(*) FROM ma_table WHERE " + self._build_where()
        ).fetchone()[0]

        # Charger la page
        rows = conn.execute(
            "SELECT * FROM ma_table WHERE "
            + self._build_where()
            + f" LIMIT {self._page_size} OFFSET {offset}"
        ).fetchall()

    self._fill_table(rows)
    self._update_pagination_label()

def _update_pagination_label(self) -> None:
    total_pages = max(1, (self._total_rows + self._page_size - 1) // self._page_size)
    self.page_label.setText(f"Page {self._current_page} / {total_pages}  ({self._total_rows} lignes)")
    self.prev_btn.setEnabled(self._current_page > 1)
    self.next_btn.setEnabled(self._current_page < total_pages)

def _on_prev(self) -> None:
    if self._current_page > 1:
        self._current_page -= 1
        self._refresh_table()

def _on_next(self) -> None:
    total_pages = max(1, (self._total_rows + self._page_size - 1) // self._page_size)
    if self._current_page < total_pages:
        self._current_page += 1
        self._refresh_table()
```

### Export CSV

```python
import csv
from PySide6.QtWidgets import QFileDialog

def _on_export_clicked(self) -> None:
    path, _ = QFileDialog.getSaveFileName(
        self, "Exporter en CSV", "", "Fichiers CSV (*.csv)"
    )
    if not path:
        return

    conn = get_connection()
    with conn:
        rows = conn.execute(
            "SELECT * FROM ma_table WHERE " + self._build_where()
        ).fetchall()

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(self._columns)   # en-têtes
        for row in rows:
            writer.writerow([str(v) if v is not None else "" for v in row])

    QMessageBox.information(self, "Export", f"{len(rows)} lignes exportées.")
```

---

## 4. Styles partagés

```python
# ── Boutons ────────────────────────────────────────────────────────────────
_BTN_PRIMARY  = "QPushButton{background:#1e3a5f;color:white;border-radius:5px;padding:6px 14px;font-weight:600;font-size:12px;}QPushButton:hover{background:#2a4f80;}QPushButton:pressed{background:#16294a;}QPushButton:disabled{background:#9ca3af;}"
_BTN_SUCCESS  = "QPushButton{background:#15803d;color:white;border-radius:5px;padding:6px 14px;font-weight:600;font-size:12px;}QPushButton:hover{background:#16a34a;}QPushButton:pressed{background:#14532d;}"
_BTN_DANGER   = "QPushButton{background:#b91c1c;color:white;border-radius:5px;padding:6px 14px;font-weight:600;font-size:12px;}QPushButton:hover{background:#dc2626;}QPushButton:pressed{background:#991b1b;}"
_BTN_NEUTRAL  = "QPushButton{background:#64748b;color:white;border-radius:5px;padding:6px 14px;font-weight:600;font-size:12px;}QPushButton:hover{background:#475569;}QPushButton:pressed{background:#334155;}"
_BTN_EXPORT   = "QPushButton{background:#0369a1;color:white;border-radius:5px;padding:6px 14px;font-weight:600;font-size:12px;}QPushButton:hover{background:#0284c7;}QPushButton:pressed{background:#075985;}"
_BTN_SUSPEND  = "QPushButton{background:#92400e;color:white;border-radius:5px;padding:6px 14px;font-weight:600;font-size:12px;}QPushButton:hover{background:#b45309;}QPushButton:pressed{background:#78350f;}"

# ── Champs de saisie ──────────────────────────────────────────────────────
_INPUT_STYLE = (
    "QLineEdit{border:1px solid #d1d5db;border-radius:5px;padding:6px 10px;"
    "font-size:12px;background:white;color:#111827;}"
    "QLineEdit:focus{border:2px solid #1e3a5f;}"
)

# ── Tableau standard (thème clair) ────────────────────────────────────────
_TABLE_STYLE = (
    "QTableWidget{border:1px solid #e2e8f0;gridline-color:#f1f5f9;font-size:12px;}"
    "QTableWidget::item{padding:5px 8px;}"
    "QTableWidget::item:selected{background-color:#dbeafe;color:#1e3a5f;}"
    "QHeaderView::section{background-color:#1e3a5f;color:white;font-weight:700;"
    "padding:7px 8px;border:none;border-right:1px solid #2a4f80;}"
    "QTableWidget::item:alternate{background-color:#f8fafc;}"
)

# ── Utilitaire : créer un bouton en une ligne ─────────────────────────────
def _make_btn(label: str, style: str) -> QPushButton:
    btn = QPushButton(label)
    btn.setStyleSheet(style)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn

# ── Séparateur vertical entre boutons ─────────────────────────────────────
def _make_separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setFrameShadow(QFrame.Shadow.Sunken)
    sep.setStyleSheet("color: #e2e8f0;")
    return sep
```

---

*Extrait de TraitementDisaCnps — 2026-03-21*
