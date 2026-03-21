# Palette sombre et styles partagés entre ChartWidget (admin) et AgentChartWidget (agent).
# Contient également la palette claire réutilisable par tous les widgets de pages.

_BG_DEEP  = "#0d1520"
_BG_CARD  = "#182233"
_BG_HDR   = "#111d2e"
_BORDER   = "#243147"
_TXT1     = "#e2e8f0"
_TXT2     = "#94a3b8"
_TXT3     = "#64748b"
_GRID     = "#1e3a5f"
_C_NAVY   = "#3b82f6"
_C_GREEN  = "#10b981"
_C_AMBER  = "#f59e0b"
_C_BLUE   = "#60a5fa"
_C_VIOLET = "#a78bfa"

_USER_COLORS = [
    "#3b82f6", "#10b981", "#f59e0b", "#f87171",
    "#a78bfa", "#22d3ee", "#84cc16", "#fb923c",
]

DATE_EDIT_QSS = f"""
QDateEdit {{
    background-color: {_BG_CARD};
    color: {_TXT1};
    border: 1px solid {_BORDER};
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 11px;
    min-width: 108px;
}}
QDateEdit::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 26px;
    background-color: {_C_NAVY};
    border-left: 1px solid {_BORDER};
    border-top-right-radius: 5px;
    border-bottom-right-radius: 5px;
    image: none;
}}
QDateEdit::drop-down:hover {{
    background-color: #2563eb;
}}
QCalendarWidget QWidget {{
    background-color: {_BG_HDR};
    color: {_TXT1};
    alternate-background-color: {_BG_CARD};
}}
QCalendarWidget QAbstractItemView {{
    background: {_BG_HDR};
    color: {_TXT1};
    selection-background-color: {_C_NAVY};
    selection-color: #ffffff;
}}
QCalendarWidget QToolButton {{
    color: {_TXT1};
    background: {_BG_HDR};
}}
"""

BTN_QSS = f"""
QPushButton {{
    background-color: {_BORDER};
    color: {_TXT1};
    border: none;
    border-radius: 5px;
    padding: 5px 12px;
    font-size: 11px;
}}
QPushButton:hover {{
    background-color: {_C_NAVY};
}}
QPushButton:pressed {{
    background-color: #1d4ed8;
}}
"""


def truncate(text: str, max_len: int = 22) -> str:
    """Tronque une chaîne pour l'affichage dans les axes de graphiques."""
    return text if len(text) <= max_len else f"{text[:max_len - 1]}…"


# ── Palette claire — widgets de pages (formulaires, tables, dialogs) ──────────

BTN_PRIMARY = (
    "QPushButton { background:#1e3a5f; color:white; border-radius:5px;"
    " padding:6px 14px; font-weight:600; font-size:12px; }"
    "QPushButton:hover { background:#2a4f80; }"
    "QPushButton:pressed { background:#16294a; }"
    "QPushButton:disabled { background:#9ca3af; }"
)
BTN_SUCCESS = (
    "QPushButton { background:#15803d; color:white; border-radius:5px;"
    " padding:6px 14px; font-weight:600; font-size:12px; }"
    "QPushButton:hover { background:#16a34a; }"
    "QPushButton:pressed { background:#0f5c2c; }"
)
BTN_DANGER = (
    "QPushButton { background:#b91c1c; color:white; border-radius:5px;"
    " padding:6px 14px; font-weight:600; font-size:12px; }"
    "QPushButton:hover { background:#dc2626; }"
    "QPushButton:pressed { background:#991b1b; }"
)
BTN_NEUTRAL = (
    "QPushButton { background:#64748b; color:white; border-radius:5px;"
    " padding:6px 14px; font-weight:600; font-size:12px; }"
    "QPushButton:hover { background:#475569; }"
    "QPushButton:pressed { background:#334155; }"
)
BTN_WARNING = (
    "QPushButton { background:#b45309; color:white; border-radius:5px;"
    " padding:6px 14px; font-weight:600; font-size:12px; }"
    "QPushButton:hover { background:#d97706; }"
    "QPushButton:pressed { background:#92400e; }"
)
INPUT_STYLE = (
    "QLineEdit, QComboBox { border:1px solid #d1d5db; border-radius:5px;"
    " padding:6px 10px; font-size:12px; background:white; color:#111827; }"
    "QLineEdit:focus, QComboBox:focus { border:2px solid #1e3a5f; }"
    "QLineEdit:disabled, QComboBox:disabled { background:#f3f4f6; color:#9ca3af; }"
)
