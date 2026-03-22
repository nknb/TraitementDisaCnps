from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, QDate, QRect, QRectF
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QLineEdit,
    QComboBox,
    QTableWidgetItem,
    QMessageBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QSplitter,
    QSizePolicy,
    QAbstractItemView,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QStyle,
)

from .home_ui import Ui_Form
from db.connection import get_connection
from db.audit import log_audit, snapshot_traitement_disa
from core.events import get_data_bus
from core.session import get_current_user
from ui.notification_widget import get_notification_manager

# Rôles custom sur la colonne 0 de chaque ligne
_ROLE_IS_TRAITE    = Qt.ItemDataRole.UserRole + 10  # flag TRAITÉ pour le délégué
_ROLE_UPDATED_AT   = Qt.ItemDataRole.UserRole + 11  # timestamp updated_at (détection conflits)
_ROLE_IS_SUSPENDED = Qt.ItemDataRole.UserRole + 12  # flag SUSPENDU pour le délégué
_ROLE_IS_LOCKED    = Qt.ItemDataRole.UserRole + 13  # flag EN COURS (verrouillé par un autre)
_ROLE_LOCKED_BY    = Qt.ItemDataRole.UserRole + 14  # nom de l'utilisateur qui a le verrou


class _ModernRowDelegate(QStyledItemDelegate):
    """Délégué de rendu moderne pour le tableau Accueil.

    - Fond gris (SUSPENDU) / vert pâle (TRAITÉ) / rouge pâle (NON TRAITÉ)
    - Barre indicatrice verticale de 5 px sur la première colonne
    - Badge pill arrondi sur la colonne statut (col 33)
    - Séparateur horizontal subtil entre lignes
    - Overlay CNPS bleu semi-transparent sur la ligne sélectionnée
    """

    _STATUS_COL = 33

    # Palette TRAITÉ
    _TRAITE_BG  = QColor("#ecfdf5")
    _TRAITE_BAR = QColor("#22c55e")
    _TRAITE_FG  = QColor("#166534")

    # Palette NON TRAITÉ
    _NON_BG     = QColor("#fff1f2")
    _NON_BAR    = QColor("#ef4444")
    _NON_FG     = QColor("#991b1b")

    # Palette SUSPENDU (gris)
    _SUSP_BG    = QColor("#e2e8f0")
    _SUSP_BAR   = QColor("#64748b")
    _SUSP_FG    = QColor("#334155")

    # Palette EN COURS (verrouillé par un autre utilisateur) — jaune
    _LOCK_BG    = QColor("#fef9c3")
    _LOCK_BAR   = QColor("#eab308")
    _LOCK_FG    = QColor("#713f12")

    # Divers
    _BAR_W    = 5
    _SEL_OVRL = QColor(0, 119, 200, 40)    # CNPS bleu clair semi-transparent
    _DIVIDER  = QColor(0, 0, 0, 12)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # type: ignore[override]
        row = index.row()
        col = index.column()
        model = index.model()

        # Lire les flags stockés sur la col 0 de la même ligne
        is_suspended = bool(model.index(row, 0).data(_ROLE_IS_SUSPENDED))
        is_locked    = bool(model.index(row, 0).data(_ROLE_IS_LOCKED))
        is_traite    = bool(model.index(row, 0).data(_ROLE_IS_TRAITE))

        # Priorité : EN COURS > SUSPENDU > TRAITÉ > NON TRAITÉ
        if is_locked:
            bg, bar, fg = self._LOCK_BG, self._LOCK_BAR, self._LOCK_FG
        elif is_suspended:
            bg, bar, fg = self._SUSP_BG, self._SUSP_BAR, self._SUSP_FG
        elif is_traite:
            bg, bar, fg = self._TRAITE_BG, self._TRAITE_BAR, self._TRAITE_FG
        else:
            bg, bar, fg = self._NON_BG, self._NON_BAR, self._NON_FG

        # Très légère alternance sur les lignes paires
        if row % 2 == 0:
            bg = bg.darker(103)

        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Fond de la cellule
        painter.fillRect(rect, bg)

        # 2. Barre indicatrice sur la première colonne
        if col == 0:
            painter.fillRect(QRect(rect.left(), rect.top(), self._BAR_W, rect.height()), bar)

        # 3. Séparateur horizontal subtil
        painter.setPen(QPen(self._DIVIDER, 1))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        # 4. Overlay de sélection
        if selected:
            painter.fillRect(rect, self._SEL_OVRL)

        painter.restore()

        # 5. Colonne statut → badge pill compact
        if col == self._STATUS_COL:
            text = index.data(Qt.ItemDataRole.DisplayRole) or ""
            badge_w = max(len(text) * 6 + 14, 90)
            badge_h = min(rect.height() - 6, 16)
            badge_x = rect.left() + (rect.width() - badge_w) // 2
            badge_y = rect.top() + (rect.height() - badge_h) // 2
            badge_rect = QRectF(badge_x, badge_y, badge_w, badge_h)

            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QBrush(bar))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(badge_rect, badge_h / 2, badge_h / 2)

            font = QFont("Segoe UI", 7)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QPen(QColor("white")))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, text)
            painter.restore()
            return  # rendu complet, pas d'appel à super()

        # 6. Texte des autres colonnes — dessin direct pour fiabilité cross-platform
        text = index.data(Qt.ItemDataRole.DisplayRole)
        if text:
            painter.save()
            painter.setFont(QFont("Segoe UI", 8))
            painter.setPen(QPen(fg))
            # Décale le texte pour laisser la place à la barre indicatrice sur col 0
            left_pad = self._BAR_W + 4 if col == 0 else 5
            text_rect = rect.adjusted(left_pad, 0, -3, 0)
            raw_align = index.data(Qt.ItemDataRole.TextAlignmentRole)
            alignment = Qt.AlignmentFlag(int(raw_align)) if raw_align is not None else (
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            painter.drawText(text_rect, alignment, str(text))
            painter.restore()


class HomeWidget(QWidget):
    """Wrapper QWidget pour utiliser Ui_Form comme page Home dans le sidebar.

    Cette classe relie les champs de la page d'accueil à la base SQLite
    (tables identification_employeurs et traitement_disa).
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.ui = Ui_Form()
        self.ui.setupUi(self)

        # Duplique et renomme les champs selon le modèle de données
        self._actions_menees_row: int | None = None
        self._original_td_updated_at: str | None = None   # pour la détection de conflits
        # Pagination
        self._page: int = 0
        self._page_size: int = 150
        self._total_rows: int = 0
        # Filtres
        self._filter_mes_dossiers: bool = False
        # Soft lock
        self._current_locked_td_id: int | None = None  # id traitement_disa verrouillé par nous
        self._duplicate_employer_fields()
        self._duplicate_activity_fields()
        self._duplicate_extra_raison_sociale()
        self._duplicate_extra_periodicite()
        self._rename_first_column_labels()
        self._rename_second_column_labels()
        self._configure_date_and_input_widgets()
        self._setup_actions_menees_field()
        self._setup_search_bar()

        # Design : en-têtes de section + style labels + boutons
        self._add_section_headers()
        self._style_form_labels()
        self._style_action_buttons()

        # ── Tableau moderne ────────────────────────────────────────────────
        table = self.ui.tableWidget
        table.setSelectionBehavior(table.SelectionBehavior.SelectRows)
        table.setSelectionMode(table.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(False)   # géré par le délégué
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setShowGrid(False)

        # Délégué de rendu moderne
        table.setItemDelegate(_ModernRowDelegate(table))

        # Hauteur de ligne compacte
        table.verticalHeader().setDefaultSectionSize(26)
        table.verticalHeader().hide()

        # En-tête horizontal compact
        header_font = QFont("Segoe UI", 8)
        header_font.setBold(True)
        table.horizontalHeader().setFont(header_font)
        table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        table.horizontalHeader().setHighlightSections(False)
        table.horizontalHeader().setStretchLastSection(False)

        # QSS moderne du tableau
        table.setStyleSheet("""
            QTableWidget {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                outline: none;
            }
            QTableWidget::item { padding: 0px 5px; border: none; }
            QTableWidget::item:selected { background: transparent; }
            QHeaderView { background: #003f8a; border: none; }
            QHeaderView::section {
                background: #003f8a;
                color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 8px;
                font-weight: 700;
                letter-spacing: 0.3px;
                padding: 5px 6px;
                border: none;
                border-right: 1px solid #0077c8;
            }
            QHeaderView::section:last { border-right: none; }
            QScrollBar:vertical {
                background: #f1f5f9; width: 6px; border-radius: 3px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #cbd5e1; border-radius: 3px; min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #94a3b8; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar:horizontal {
                background: #f1f5f9; height: 6px; border-radius: 3px; margin: 0;
            }
            QScrollBar::handle:horizontal {
                background: #cbd5e1; border-radius: 3px; min-width: 20px;
            }
            QScrollBar::handle:horizontal:hover { background: #94a3b8; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
        """)

        # Tableau en lecture seule : modifications uniquement via le formulaire
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Masque les colonnes techniques (IDs internes)
        # 23 : ID EMPLOYEUR, 32 : ID TRAITEMENT
        try:
            table.setColumnHidden(23, True)
            table.setColumnHidden(32, True)
        except Exception:
            pass

        # Connexions des boutons (la recherche est automatique via le champ texte)
        self.ui.add_btn.clicked.connect(self.on_add_clicked)
        self.ui.update_btn.clicked.connect(self.on_update_clicked)
        self.ui.clear_btn.clicked.connect(self.on_clear_clicked)
        self.ui.delete_btn.clicked.connect(self.on_delete_clicked)

        # Quand on clique une ligne du tableau, on remplit le formulaire
        self.ui.tableWidget.cellClicked.connect(self.on_table_row_selected)

        # Chargement initial des données
        self._needs_refresh: bool = False
        self.load_data()

        # Actualisation automatique quand la base change depuis un autre onglet
        get_data_bus().data_changed.connect(self.load_data)

        # ── Heartbeat : renouvelle le verrou toutes les 5 minutes ────────
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(5 * 60 * 1000)  # 5 min
        self._heartbeat_timer.timeout.connect(self._renew_lock)
        self._heartbeat_timer.start()

        # ── Rafraîchissement léger des verrous toutes les 8 secondes ─────
        self._lock_refresh_timer = QTimer(self)
        self._lock_refresh_timer.setInterval(8_000)  # 8 s
        self._lock_refresh_timer.timeout.connect(self._refresh_locks_in_table)
        self._lock_refresh_timer.start()

        # ── Polling BD multi-instance toutes les 5 secondes ──────────────
        # Détecte les modifications faites par d'autres postes et recharge.
        self._last_db_updated_at: str = ""
        self._db_poll_timer = QTimer(self)
        self._db_poll_timer.setInterval(5_000)  # 5 s
        self._db_poll_timer.timeout.connect(self._poll_db_changes)
        self._db_poll_timer.start()

        # ── Mise en page compacte : formulaire + table dans un splitter ──
        self._setup_compact_layout()

    def showEvent(self, event) -> None:  # type: ignore[override]
        """Rafraîchit les données si une mise à jour a eu lieu pendant que le widget était caché."""
        super().showEvent(event)
        if self._needs_refresh:
            self.load_data()

    def hideEvent(self, event) -> None:  # type: ignore[override]
        """Libère le verrou dossier quand l'utilisateur quitte la page Accueil."""
        super().hideEvent(event)
        self._unlock_previous_row()
        self._reset_update_btn()

    def _setup_compact_layout(self) -> None:
        """Encapsule le formulaire dans une QScrollArea et utilise un QSplitter
        vertical pour que la table occupe l'espace disponible."""

        main_layout = self.ui.gridLayout_5

        # Récupère les widgets existants (ils restent dans le layout pour l'instant)
        info_frame   = self.ui.info_frame
        func_frame   = self.ui.function_frame
        result_frame = self.ui.result_frame

        # Retire les trois widgets du gridLayout principal
        main_layout.removeWidget(info_frame)
        main_layout.removeWidget(func_frame)
        main_layout.removeWidget(result_frame)

        # ── Scroll area autour du formulaire ──────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: #f1f5f9; width: 6px;
                border-radius: 3px; margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #94a3b8; border-radius: 3px; min-height: 24px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        scroll.setWidget(info_frame)

        # Conteneur formulaire (scroll) + boutons d'action
        top_container = QWidget()
        top_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        top_layout = QFrame(top_container)
        from PySide6.QtWidgets import QVBoxLayout
        tc_layout = QVBoxLayout(top_container)
        tc_layout.setContentsMargins(0, 0, 0, 0)
        tc_layout.setSpacing(8)
        tc_layout.addWidget(scroll)
        tc_layout.addWidget(func_frame)

        # ── Barre de pagination sous le tableau ───────────────────────────
        from PySide6.QtWidgets import QPushButton as _PB, QLabel as _QL, QWidget as _QW, QHBoxLayout as _QHL
        pag_bar = _QW()
        pag_bar.setFixedHeight(34)
        pag_bar.setStyleSheet("background: #f1f5f9; border-top: 1px solid #e2e8f0;")
        pag_lay = _QHL(pag_bar)
        pag_lay.setContentsMargins(8, 2, 8, 2)
        pag_lay.setSpacing(6)

        self._prev_btn = _PB("◀")
        self._next_btn = _PB("▶")
        self._page_label = _QL("— / —")
        self._rows_label = _QL("")

        for btn in (self._prev_btn, self._next_btn):
            btn.setFixedSize(28, 26)
            btn.setStyleSheet(
                "QPushButton { background:#003f8a; color:white; border-radius:4px;"
                " font-size:11px; font-weight:700; border:none; }"
                "QPushButton:hover { background:#0077c8; }"
                "QPushButton:disabled { background:#cbd5e1; color:#94a3b8; }"
            )
        self._page_label.setStyleSheet("font-size:11px; color:#374151; font-weight:600;")
        self._rows_label.setStyleSheet("font-size:10px; color:#6b7280;")

        pag_lay.addStretch()
        pag_lay.addWidget(self._rows_label)
        pag_lay.addSpacing(12)
        pag_lay.addWidget(self._prev_btn)
        pag_lay.addWidget(self._page_label)
        pag_lay.addWidget(self._next_btn)

        self._prev_btn.clicked.connect(self._on_prev_page)
        self._next_btn.clicked.connect(self._on_next_page)

        # Conteneur table + pagination
        from PySide6.QtWidgets import QVBoxLayout as _QVL
        table_container = _QW()
        tc2 = _QVL(table_container)
        tc2.setContentsMargins(0, 0, 0, 0)
        tc2.setSpacing(0)

        # ── Bannière "Dossier TRAITÉ — lecture seule" ────────────────────
        self._traite_banner = _QL()
        self._traite_banner.setFixedHeight(28)
        self._traite_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._traite_banner.setStyleSheet(
            "background:#fef3c7; color:#92400e; font-size:11px; font-weight:600;"
            " padding:4px 8px; border-bottom:1px solid #fbbf24;"
        )
        self._traite_banner.hide()

        # ── Bannière "Mes dossiers" filtrés ──────────────────────────────
        self._mode_banner = _QL()
        self._mode_banner.setFixedHeight(26)
        self._mode_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mode_banner.setStyleSheet(
            "background:#003f8a; color:white; font-size:11px; font-weight:600;"
            " padding:3px 8px;"
        )
        self._mode_banner.hide()

        tc2.addWidget(self._traite_banner)
        tc2.addWidget(self._mode_banner)
        tc2.addWidget(result_frame)
        tc2.addWidget(pag_bar)

        # ── Splitter vertical formulaire / table ──────────────────────────
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(6)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background: #e2e8f0;
                border-radius: 3px;
            }
            QSplitter::handle:hover { background: #94a3b8; }
        """)
        splitter.addWidget(top_container)
        splitter.addWidget(table_container)
        # Formulaire ~35 %, table ~65 % de l'espace disponible
        splitter.setStretchFactor(0, 40)
        splitter.setStretchFactor(1, 60)
        splitter.setSizes([380, 380])

        main_layout.addWidget(splitter, 1, 0, 1, 1)
        main_layout.setRowStretch(1, 1)

    # ------------------------------------------------------------------
    # Méthodes de design visuel
    # ------------------------------------------------------------------

    def _add_section_headers(self) -> None:
        """Insère des en-têtes colorées au-dessus de chaque colonne du formulaire."""

        layout6 = self.ui.gridLayout_6

        # Retire les deux sous-layouts de la ligne 0 pour les passer en ligne 1
        item_emp = layout6.itemAtPosition(0, 0)
        item_trt = layout6.itemAtPosition(0, 1)
        if item_emp is not None:
            layout6.removeItem(item_emp)
        if item_trt is not None:
            layout6.removeItem(item_trt)

        def _make_header(text: str, bg: str) -> QFrame:
            frame = QFrame()
            frame.setStyleSheet(
                f"QFrame {{ background-color: {bg}; border-radius: 5px; }}"
            )
            h = QHBoxLayout(frame)
            h.setContentsMargins(10, 3, 10, 3)
            lbl = QLabel(text)
            lbl.setStyleSheet(
                "color: #ffffff; font-family: 'Segoe UI', Helvetica, Arial, sans-serif; "
                "font-size: 10px; font-weight: 800; letter-spacing: 1px; background: transparent;"
            )
            h.addWidget(lbl)
            return frame

        layout6.addWidget(_make_header("IDENTIFICATION EMPLOYEUR", "#003f8a"), 0, 0, 1, 1)
        layout6.addWidget(_make_header("TRAITEMENT DISA", "#14532d"), 0, 1, 1, 1)
        layout6.addLayout(self.ui.gridLayout_2, 1, 0, 1, 1)
        layout6.addLayout(self.ui.gridLayout_3, 1, 1, 1, 1)

    def _style_form_labels(self) -> None:
        """Applique un style uniforme à tous les labels des deux colonnes."""

        label_style = (
            "color: #374151; font-family: 'Segoe UI', Helvetica, Arial, sans-serif; "
            "font-size: 9px; font-weight: 700;"
        )
        for layout in (self.ui.gridLayout_2, self.ui.gridLayout_3):
            for row in range(layout.rowCount()):
                item = layout.itemAtPosition(row, 0)
                if not item:
                    continue
                widget = item.widget()
                if isinstance(widget, QLabel):
                    widget.setStyleSheet(label_style)

    def _style_action_buttons(self) -> None:
        """Définit le texte et le style des boutons d'action (supprime les icônes SVG doublons)."""
        from PySide6.QtGui import QIcon
        _no_icon = QIcon()
        _btn_base = (
            "QPushButton {{ background:{bg}; color:white; border-radius:5px;"
            " padding:6px 14px; font-weight:600; font-size:12px; }}"
            "QPushButton:hover {{ background:{hov}; }}"
            "QPushButton:pressed {{ background:{prs}; }}"
        )
        _styles = {
            "add":    _btn_base.format(bg="#003f8a", hov="#0077c8", prs="#002d66"),
            "update": _btn_base.format(bg="#15803d", hov="#16a34a", prs="#14532d"),
            "clear":  _btn_base.format(bg="#64748b", hov="#475569", prs="#334155"),
            "delete": _btn_base.format(bg="#b91c1c", hov="#dc2626", prs="#991b1b"),
        }
        _texts = {
            "add":    "＋  Ajouter",
            "update": "↻  Mettre à jour",
            "clear":  "✕  Effacer",
            "delete": "🗑  Supprimer",
        }
        try:
            for key, btn in [
                ("add",    self.ui.add_btn),
                ("update", self.ui.update_btn),
                ("clear",  self.ui.clear_btn),
                ("delete", self.ui.delete_btn),
            ]:
                btn.setIcon(_no_icon)
                btn.setText(_texts[key])
                btn.setStyleSheet(_styles[key])
        except AttributeError:
            pass

    def _duplicate_employer_fields(self) -> None:
        """Duplique deux fois N°, Numéro CNPS, Raison sociale."""

        layout = self.ui.gridLayout_2
        labels = [self.ui.label, self.ui.label_2, self.ui.label_3]
        line_edits = [self.ui.lineEdit, self.ui.lineEdit_2, self.ui.lineEdit_3]

        current_row = 3
        for _ in range(2):  # deux duplications
            for lbl, le in zip(labels, line_edits):
                new_label = QLabel(lbl.text(), self.ui.info_frame)
                new_edit = QLineEdit(self.ui.info_frame)
                new_edit.setObjectName("")
                layout.addWidget(new_label, current_row, 0, 1, 1)
                layout.addWidget(new_edit, current_row, 1, 1, 1)
                current_row += 1

    def _duplicate_activity_fields(self) -> None:
        """Duplique deux fois Secteur d'activité, Effectifs, Périodicité."""

        layout = self.ui.gridLayout_3
        labels = [self.ui.label_4, self.ui.label_5, self.ui.label_6]
        widgets = [self.ui.comboBox, self.ui.comboBox_2, self.ui.lineEdit_4]

        current_row = 3
        for _ in range(2):  # deux duplications
            for lbl, w in zip(labels, widgets):
                new_label = QLabel(lbl.text(), self.ui.info_frame)
                if isinstance(w, QComboBox):
                    new_field = QComboBox(self.ui.info_frame)
                    # copie simple des items existants
                    for i in range(w.count()):
                        new_field.addItem(w.itemText(i))
                else:
                    new_field = QLineEdit(self.ui.info_frame)

                layout.addWidget(new_label, current_row, 0, 1, 1)
                layout.addWidget(new_field, current_row, 1, 1, 1)
                current_row += 1

    def _duplicate_extra_raison_sociale(self) -> None:
        """Ajoute 2 lignes supplémentaires pour le champ Raison sociale."""

        layout = self.ui.gridLayout_2
        current_row = layout.rowCount()
        for _ in range(2):
            new_label = QLabel(self.ui.label_3.text(), self.ui.info_frame)
            new_edit = QLineEdit(self.ui.info_frame)
            new_edit.setObjectName("")
            layout.addWidget(new_label, current_row, 0, 1, 1)
            layout.addWidget(new_edit, current_row, 1, 1, 1)
            current_row += 1

    def _duplicate_extra_periodicite(self) -> None:
        """Ajoute 3 lignes supplémentaires pour le champ Périodicité."""

        layout = self.ui.gridLayout_3
        current_row = layout.rowCount()
        for _ in range(3):
            new_label = QLabel(self.ui.label_6.text(), self.ui.info_frame)
            new_edit = QLineEdit(self.ui.info_frame)
            new_edit.setObjectName("")
            layout.addWidget(new_label, current_row, 0, 1, 1)
            layout.addWidget(new_edit, current_row, 1, 1, 1)
            current_row += 1

    def _setup_actions_menees_field(self) -> None:
        """Insère le champ ACTIONS MENÉES juste après NBRE DE LIGNES REJETEES.

        Le champ est une liste déroulante (MAIL, COURRIER, TÉLÉPHONE).
        """

        layout = self.ui.gridLayout_3

        # Ligne du champ "NBRE DE LIGNES REJETEES" dans la colonne de droite
        insert_after = 6
        insert_row = insert_after + 1

        # Décale toutes les lignes à partir de insert_row vers le bas
        max_row = layout.rowCount() - 1
        for row in range(max_row, insert_row - 1, -1):
            for col in (0, 1):
                item = layout.itemAtPosition(row, col)
                if not item:
                    continue
                widget = item.widget()
                if widget is None:
                    continue
                layout.removeWidget(widget)
                layout.addWidget(widget, row + 1, col, 1, 1)

        # Ajout de la nouvelle ligne "ACTIONS MENÉES"
        label = QLabel("ACTIONS MENÉES", self.ui.info_frame)
        combo = QComboBox(self.ui.info_frame)
        combo.addItems(["", "MAIL", "COURRIER", "TÉLÉPHONE"])

        layout.addWidget(label, insert_row, 0, 1, 1)
        layout.addWidget(combo, insert_row, 1, 1, 1)

        self._actions_menees_row = insert_row

    def _rename_first_column_labels(self) -> None:
        """Renomme les libellés de la première colonne (employeur)."""

        labels = [
            "N° EMPLOYEUR",
            "N° CNPS",
            "RAISON SOCIALE",
            "SECTEUR D'ACTIVITÉ",
            "EFFECTIF",
            "PÉRIODICITÉ",
            "TÉLÉPHONE",
            "EMAIL",
            "LOCALITÉ",
            "EXERCICE",
            "DISA ANTÉRIEURES À RECUEILLIR",
        ]

        layout = self.ui.gridLayout_2
        max_rows = min(layout.rowCount(), len(labels))
        for row in range(max_rows):
            item = layout.itemAtPosition(row, 0)
            if not item:
                continue
            widget = item.widget()
            if isinstance(widget, QLabel):
                widget.setText(labels[row])

    def _rename_second_column_labels(self) -> None:
        """Renomme les libellés de la deuxième colonne (traitement DISA).

        True  = champ obligatoire  → préfixé par « * » en rouge.
        False = champ facultatif.
        """

        labels = [
            ("DATE DE RECEPTION", True),
            ("DATE DE TRAITEMENT", True),
            ("DATE DE VALIDATION", True),
            ("EFFECTIF DISA", True),
            ("NBRE DE LIGNES TRAITEES", True),
            ("NBRE DE LIGNES VALIDEES", True),
            ("NBRE DE LIGNES REJETEES", True),
            ("NBRE DE LIGNES REJETEES TRAITEES", True),
            ("NBRE TOTAL DE LIGNES VALIDEES APRES TRAITEMENT DES REJETS", True),
            ("DATE DE TRAITEMENT REJET", True),
            ("NBRE RESTANT DE REJET", True),
            ("OBSERVATIONS", False),
        ]

        layout = self.ui.gridLayout_3
        max_rows = min(layout.rowCount(), len(labels))
        for row in range(max_rows):
            item = layout.itemAtPosition(row, 0)
            if not item:
                continue
            widget = item.widget()
            if isinstance(widget, QLabel):
                text, required = labels[row]
                if required:
                    widget.setText(
                        f'<span style="color:#ef4444;font-weight:900;">* </span>{text}'
                    )
                else:
                    widget.setText(text)

    # ------------------------------------------------------------------
    # Helpers pour lire/écrire les champs du formulaire
    # ------------------------------------------------------------------

    # Date sentinelle utilisée pour représenter "aucune date saisie"
    _DATE_SENTINEL = "2000-01-01"

    def _get_text_from_layout(self, layout, row: int) -> str:
        item = layout.itemAtPosition(row, 1)
        if not item:
            return ""
        widget = item.widget()
        if isinstance(widget, QLineEdit):
            return widget.text().strip()
        if isinstance(widget, QComboBox):
            return widget.currentText().strip()
        if isinstance(widget, QDateEdit):

            d = widget.date()
            # Si la date est la sentinelle "vide", on renvoie une chaîne vide (NULL en base)
            if d == QDate.fromString(self._DATE_SENTINEL, "yyyy-MM-dd"):
                return ""
            return d.toString("yyyy-MM-dd")
        return ""

    def _set_text_in_layout(self, layout, row: int, value: str) -> None:
        item = layout.itemAtPosition(row, 1)
        if not item:
            return
        widget = item.widget()
        value = "" if value is None else str(value)
        if isinstance(widget, QLineEdit):
            widget.setText(value)
        elif isinstance(widget, QComboBox):
            widget.setCurrentText(value)
        elif isinstance(widget, QDateEdit):

            if value:
                date = QDate.fromString(value, "yyyy-MM-dd")
                if not date.isValid():
                    date = QDate.fromString(self._DATE_SENTINEL, "yyyy-MM-dd")
            else:
                date = QDate.fromString(self._DATE_SENTINEL, "yyyy-MM-dd")
            widget.setDate(date)

    def _set_form_read_only(self, read_only: bool) -> None:
        """Passe tous les champs du formulaire en lecture seule ou en édition.

        Appelé quand un dossier TRAITÉ (non-admin) ou verrouillé par un autre
        utilisateur est sélectionné.
        """
        _ro_style = (
            "background:#f1f5f9; color:#64748b;"
            " border:1px solid #e2e8f0; border-radius:3px;"
        )
        for layout in (self.ui.gridLayout_2, self.ui.gridLayout_3):
            row_count = layout.rowCount()
            for r in range(row_count):
                item = layout.itemAtPosition(r, 1)
                if item is None:
                    continue
                widget = item.widget()
                if widget is None:
                    continue
                if isinstance(widget, QLineEdit):
                    widget.setReadOnly(read_only)
                    widget.setStyleSheet(_ro_style if read_only else "")
                elif isinstance(widget, (QComboBox, QDateEdit)):
                    widget.setEnabled(not read_only)

    def _to_int_or_none(self, value: str):
        value = (value or "").strip()
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # Helpers métiers : lecture du formulaire et calcul du statut
    # ------------------------------------------------------------------

    def _read_form_data(self) -> tuple[dict, dict]:
        """Lit tous les champs du formulaire et renvoie deux dictionnaires.

        Retourne (employeur_data, traitement_data).
        """

        layout2 = self.ui.gridLayout_2
        layout3 = self.ui.gridLayout_3

        # Partie employeur
        employeur_data = {
            "numero": self._to_int_or_none(self._get_text_from_layout(layout2, 0)),
            "numero_cnps": self._get_text_from_layout(layout2, 1),
            "raison_sociale": self._get_text_from_layout(layout2, 2),
            "secteur": self._get_text_from_layout(layout2, 3),
            "effectifs": self._to_int_or_none(self._get_text_from_layout(layout2, 4)),
            "periodicite": self._get_text_from_layout(layout2, 5),
            "telephone": self._get_text_from_layout(layout2, 6),
            "mail": self._get_text_from_layout(layout2, 7),
            "localites": self._get_text_from_layout(layout2, 8),
            "exercice": self._to_int_or_none(self._get_text_from_layout(layout2, 9)),
            "disa_anterieures_a_recueillir": self._get_text_from_layout(layout2, 10),
        }

        # Partie traitement DISA
        traitement_data = {
            "date_reception": self._get_text_from_layout(layout3, 0),
            "date_traitement": self._get_text_from_layout(layout3, 1),
            "date_validation": self._get_text_from_layout(layout3, 2),
            "effectif_disa": self._to_int_or_none(self._get_text_from_layout(layout3, 3)),
            "nbre_traitees": self._to_int_or_none(self._get_text_from_layout(layout3, 4)),
            "nbre_validees": self._to_int_or_none(self._get_text_from_layout(layout3, 5)),
            "nbre_rejetees": self._to_int_or_none(self._get_text_from_layout(layout3, 6)),
            "actions_menees": self._get_text_from_layout(
                layout3, self._actions_menees_row if self._actions_menees_row is not None else 7
            ),
            "nbre_rejetees_traitees": self._to_int_or_none(self._get_text_from_layout(layout3, 8)),
            "nbre_total_validees": self._to_int_or_none(self._get_text_from_layout(layout3, 9)),
            "date_traitement_rejet": self._get_text_from_layout(layout3, 10),
            "nbre_restant": self._to_int_or_none(self._get_text_from_layout(layout3, 11)),
            "observations": self._get_text_from_layout(layout3, 12),
        }

        return employeur_data, traitement_data

    def _compute_statut(self, date_traitement: str | None, date_validation: str | None = None) -> str:
        """Calcule le statut : TRAITÉ si date_de_traitement OU date_de_validation est renseignée."""

        return "TRAITÉ" if (date_traitement or date_validation) else "NON TRAITÉ"

    def _validate_traitement_fields(self, traitement_data: dict) -> str | None:
        """Vérifie les champs obligatoires du traitement DISA.

        Retourne un message d'erreur si un champ est manquant, None sinon.
        """
        required_fields = [
            ("date_reception",        "* Date de réception"),
            ("date_traitement",       "* Date de traitement"),
            ("date_validation",       "* Date de validation"),
            ("effectif_disa",         "* Effectif DISA"),
            ("nbre_traitees",         "* Nbre de lignes traitées"),
            ("nbre_validees",         "* Nbre de lignes validées"),
            ("nbre_rejetees",         "* Nbre de lignes rejetées"),
            ("nbre_rejetees_traitees","* Nbre de lignes rejetées traitées"),
            ("nbre_total_validees",   "* Nbre total de lignes validées"),
            ("date_traitement_rejet", "* Date de traitement rejet"),
            ("nbre_restant",          "* Nbre restant de rejet"),
        ]
        missing = [
            label
            for key, label in required_fields
            if traitement_data.get(key) is None or str(traitement_data.get(key, "")).strip() == ""
        ]
        if missing:
            return "Les champs suivants sont obligatoires :\n" + "\n".join(f"  {m}" for m in missing)
        return None

    def _validate_business_rules(self, traitement_data: dict) -> str | None:
        """Vérifie la cohérence métier des champs numériques du traitement.

        Retourne un message d'erreur descriptif, ou None si tout est valide.
        Les valeurs vides / non numériques sont ignorées (champs optionnels).
        """
        def _int(key: str):
            val = traitement_data.get(key)
            try:
                return int(val) if val is not None and str(val).strip() != "" else None
            except (ValueError, TypeError):
                return None

        traitees  = _int("nbre_traitees")
        validees  = _int("nbre_validees")
        rejetees  = _int("nbre_rejetees")
        rej_trait = _int("nbre_rejetees_traitees")
        total_val = _int("nbre_total_validees")
        restant   = _int("nbre_restant")

        errors: list[str] = []

        # Règle 1 : aucune valeur négative
        for name, val in [
            ("Lignes traitées", traitees),
            ("Lignes validées", validees),
            ("Lignes rejetées", rejetees),
            ("Rejets traités",  rej_trait),
            ("Total validées",  total_val),
            ("Restant rejets",  restant),
        ]:
            if val is not None and val < 0:
                errors.append(f"{name} ne peut pas être négatif ({val})")

        # Règle 2 : validées + rejetées ≤ traitées
        if validees is not None and rejetees is not None and traitees is not None:
            if validees + rejetees > traitees:
                errors.append(
                    f"Lignes validées ({validees}) + rejetées ({rejetees})"
                    f" > traitées ({traitees})"
                )

        # Règle 3 : rejets traités ≤ total rejets
        if rej_trait is not None and rejetees is not None:
            if rej_trait > rejetees:
                errors.append(
                    f"Rejets traités ({rej_trait}) > total rejets ({rejetees})"
                )

        # Règle 4 : restant = rejetées − rejets_traités (avertissement non bloquant)
        if restant is not None and rejetees is not None and rej_trait is not None:
            expected = rejetees - rej_trait
            if restant != expected:
                errors.append(
                    f"Restant ({restant}) ≠ rejetées − rejets traités ({expected})"
                )

        # Règle 5 : total validées ≥ validées initiales
        if total_val is not None and validees is not None:
            if total_val < validees:
                errors.append(
                    f"Total validées après rejets ({total_val}) < validées initiales ({validees})"
                )

        return "\n".join(errors) if errors else None

    def _notify(self, title: str, message: str = "", notif_type: str = "info") -> None:
        """Envoie une notification in-app, ou bascule sur QMessageBox si indisponible."""
        nm = get_notification_manager()
        if nm:
            nm.notify(title, message, notif_type)
        elif notif_type in ("error", "warning"):
            QMessageBox.warning(self, title, message or title)
        else:
            QMessageBox.information(self, title, message or title)

    def _configure_date_and_input_widgets(self) -> None:
        """Configure les champs de date cliquables et remplace les listes déroulantes.

        - Les lignes de date (réception, traitement, validation, traitement rejet)
          deviennent des QDateEdit avec calendrier et icône moderne.
        - Toutes les QComboBox restantes dans la colonne de droite sont remplacées
          par de simples QLineEdit (plus de listes déroulantes).
        """

        layout = self.ui.gridLayout_3

        # Lignes utilisées pour les dates dans la deuxième colonne
        from PySide6.QtCore import QDate
        import os as _os
        _sentinel = QDate.fromString(self._DATE_SENTINEL, "yyyy-MM-dd")

        # Chemin vers l'icône calendrier
        _icons_dir = _os.path.join(_os.path.dirname(__file__), "icons")
        _cal_icon = _os.path.join(_icons_dir, "calendar.svg").replace("\\", "/")

        _date_qss = (
            "QDateEdit {"
            "  border: 1px solid #c5d5e8;"
            "  border-radius: 5px;"
            "  padding: 4px 6px;"
            "  background: #ffffff;"
            "  font-family: 'Segoe UI', Helvetica, Arial, sans-serif;"
            "  font-size: 12px;"
            "  color: #1e293b;"
            "  min-height: 26px;"
            "}"
            "QDateEdit:focus {"
            "  border: 1px solid #0077c8;"
            "  background: #f0f7ff;"
            "}"
            "QDateEdit:disabled {"
            "  background: #f1f5f9;"
            "  color: #94a3b8;"
            "  border-color: #e2e8f0;"
            "}"
            "QDateEdit::drop-down {"
            "  subcontrol-origin: padding;"
            "  subcontrol-position: right center;"
            "  width: 28px;"
            "  border-left: 1px solid #c5d5e8;"
            "  border-top-right-radius: 5px;"
            "  border-bottom-right-radius: 5px;"
            "  background: #e8f1fb;"
            "}"
            "QDateEdit::drop-down:hover {"
            "  background: #cce0f5;"
            "}"
            f"QDateEdit::down-arrow {{"
            f"  image: url({_cal_icon});"
            f"  width: 16px;"
            f"  height: 16px;"
            f"}}"
        )

        date_rows = [0, 1, 2, 9]
        for row in date_rows:
            item = layout.itemAtPosition(row, 1)
            if not item:
                continue
            old_widget = item.widget()
            if old_widget is not None:
                layout.removeWidget(old_widget)
                old_widget.deleteLater()

            date_edit = QDateEdit(self.ui.info_frame)
            date_edit.setCalendarPopup(True)
            date_edit.setDisplayFormat("dd/MM/yyyy")
            # La date minimale sert de sentinelle "non saisie" (affichée comme texte vide)
            date_edit.setMinimumDate(_sentinel)
            date_edit.setDate(_sentinel)
            date_edit.setSpecialValueText("(non définie)")
            date_edit.setStyleSheet(_date_qss)
            layout.addWidget(date_edit, row, 1, 1, 1)

        # Remplace toutes les autres QComboBox de la colonne de droite par des QLineEdit
        rows = layout.rowCount()
        for row in range(rows):
            item = layout.itemAtPosition(row, 1)
            if not item:
                continue
            widget = item.widget()
            if isinstance(widget, QComboBox):
                layout.removeWidget(widget)
                widget.deleteLater()
                new_edit = QLineEdit(self.ui.info_frame)
                layout.addWidget(new_edit, row, 1, 1, 1)

    def _setup_search_bar(self) -> None:
        """Crée un champ de recherche moderne (raison sociale ou N° CNPS).

        - Champ avec bouton de nettoyage intégré
        - Filtrage automatique après une courte pause de saisie
        """

        # On masque uniquement le bouton "Sélectionner" qui n'a pas de handler
        try:
            self.ui.select_btn.hide()
        except AttributeError:
            pass

        # Ajout d'un champ texte de recherche à gauche de "Rechercher"
        layout = getattr(self.ui, "horizontalLayout", None)
        if layout is None:
            return

        from PySide6.QtWidgets import QLineEdit as _QLineEdit  # éviter conflit type hints

        # Champ unique : recherche par raison sociale ou N° CNPS
        self.search_cnps_line = _QLineEdit(self.ui.function_frame)
        self.search_cnps_line.setPlaceholderText("🔍  Recherche (raison sociale ou N° CNPS)")
        self.search_cnps_line.setClearButtonEnabled(True)
        self.search_cnps_line.setMinimumWidth(280)
        self.search_cnps_line.setStyleSheet(
            "QLineEdit {"
            "  border: 1px solid #d1d5db;"
            "  border-radius: 8px;"
            "  padding: 7px 12px;"
            "  font-family: 'Segoe UI', Helvetica, Arial, sans-serif;"
            "  font-size: 12px;"
            "  background-color: #f9fafb;"
            "  color: #374151;"
            "}"
            "QLineEdit:focus {"
            "  border: 2px solid #003f8a;"
            "  background-color: #ffffff;"
            "}"
        )
        layout.insertWidget(0, self.search_cnps_line)

        # Bouton toggle "Mes dossiers"
        from PySide6.QtWidgets import QPushButton as _QPushButton
        self._mes_dossiers_btn = _QPushButton("👤  Mes dossiers")
        self._mes_dossiers_btn.setCheckable(True)
        self._mes_dossiers_btn.setToolTip("Afficher uniquement les dossiers qui me sont assignés ou que j'ai traités")
        self._mes_dossiers_btn.setStyleSheet(
            "QPushButton { background:#e2e8f0; color:#334155; border-radius:6px;"
            " padding:6px 12px; font-size:11px; font-weight:600; border:none; }"
            "QPushButton:checked { background:#003f8a; color:white; }"
            "QPushButton:hover:!checked { background:#cbd5e1; }"
        )
        self._mes_dossiers_btn.toggled.connect(self._on_mes_dossiers_toggled)
        layout.insertWidget(1, self._mes_dossiers_btn)

        # Timer pour appliquer la recherche automatiquement après une pause de saisie
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(400)  # 400 ms
        self._search_timer.timeout.connect(self._apply_search)

        self.search_cnps_line.textChanged.connect(self._on_search_text_changed)

    def _clear_layout_fields(self, layout) -> None:
        """Efface tous les champs (QLineEdit / QComboBox / QDateEdit) d'un layout grille."""

        _sentinel = QDate.fromString(self._DATE_SENTINEL, "yyyy-MM-dd")
        rows = layout.rowCount()
        for row in range(rows):
            item = layout.itemAtPosition(row, 1)
            if not item:
                continue
            widget = item.widget()
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QComboBox):
                widget.setCurrentText("")
            elif isinstance(widget, QDateEdit):
                widget.setDate(_sentinel)

    # ------------------------------------------------------------------
    # Chargement du tableau depuis la base
    # ------------------------------------------------------------------

    def load_data(self, filter_text: str | None = None) -> None:
        """Charge les données employeur + traitement dans le QTableWidget.

        Si ``filter_text`` est renseigné, filtre sur :
        - ``ie.numero_cnps = ?`` (recherche exacte sur N° CNPS)
        - OU ``ie.raison_sociale LIKE %texte%``.
        Les colonnes du tableau sont alignées avec les en-têtes définis
        dans Ui_Form.retranslateUi.
        """
        # Ne pas recharger si le widget n'est pas affiché (évite de bloquer le thread
        # principal lors du polling data_changed toutes les 4 s)
        if not self.isVisible():
            self._needs_refresh = True
            return
        self._needs_refresh = False

        try:
            conn = get_connection()
        except Exception as exc:  # pragma: no cover - affichage UI
            QMessageBox.critical(self, "Erreur BD", f"Impossible d'ouvrir la base : {exc}")
            return

        # Jointure employeurs + traitements DISA.
        # Les 23 premières colonnes correspondent aux en-têtes existants du tableau,
        # puis on ajoute des colonnes supplémentaires pour les champs du schéma
        # (date_debut_activite, forme_juridique, DISA 20xx, localisation, id traitement,
        #  actions_menees, téléphone_2, email_2, email_3, etc.).
        _current_user = get_current_user()
        _username = _current_user.username if _current_user else None

        base_select = """
            SELECT
                ie.id AS employeur_id,
                ie.numero,
                ie.numero_cnps,
                ie.raison_sociale,
                ie.secteur_activite,
                ie.nombre_travailleur,
                ie.periodicite,
                ie.telephone_1,
                ie.email_1,
                ie.localites,
                COALESCE(td.exercice, ie.exercice) AS exercice,
                td.disa_anterieures_a_recueillir,
                td.date_de_reception,
                td.date_de_traitement,
                td.date_de_validation,
                td.effectif_disa,
                td.nbre_de_lignes_traitees,
                td.nbre_de_lignes_validees,
                td.nbre_de_lignes_rejetees,
                td.nbre_de_lignes_rejetees_traitees,
                td.nbre_total_de_lignes_validees_apres_traitement_des_rejets,
                td.date_de_traitement_rejet,
                td.nbre_restant_de_rejet,
                td.observations,
                td.statut,
                ie.date_debut_activite,
                ie.forme_juridique,
                ie.disa_2024,
                ie.disa_2023,
                ie.disa_2022,
                ie.disa_2021,
                ie.disa_anterieures_2010_2020,
                ie.localisation_geographique,
                td.id AS traitement_id,
                td.actions_menees,
                ie.telephone_2,
                ie.email_2,
                ie.email_3,
                td.traite_par,
                COALESCE(td.is_suspended, 0) AS is_suspended,
                td.updated_at,
                td.locked_by
            FROM identification_employeurs ie
            LEFT JOIN traitement_disa td ON td.employeur_id = ie.id
        """
        params: list = []
        where_clauses: list[str] = []

        if filter_text:
            where_clauses.append("(ie.numero_cnps = ? OR ie.raison_sociale LIKE ?)")
            like = f"%{filter_text}%"
            params.extend([filter_text, like])

        if self._filter_mes_dossiers and _username:
            where_clauses.append(
                "(COALESCE(td.traite_par,'') = ? OR COALESCE(td.locked_by,'') = ?)"
            )
            params.extend([_username, _username])

        where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        count_sql = "SELECT COUNT(*) FROM identification_employeurs ie LEFT JOIN traitement_disa td ON td.employeur_id = ie.id" + where_sql
        offset = self._page * self._page_size
        query = base_select + where_sql + " ORDER BY ie.numero LIMIT ? OFFSET ?"

        with conn:
            # Auto-déverrouiller les verrous expirés (> 10 min)
            try:
                conn.execute(
                    "UPDATE traitement_disa SET locked_by = NULL, locked_at = NULL"
                    " WHERE locked_at IS NOT NULL"
                    "   AND (julianday('now') - julianday(locked_at)) * 1440 > 10"
                )
            except Exception:
                pass

            self._total_rows = conn.execute(count_sql, params).fetchone()[0] or 0
            rows = conn.execute(query, params + [self._page_size, offset]).fetchall()

        table = self.ui.tableWidget
        table.setRowCount(len(rows))
        # 23 colonnes existantes + 10 supplémentaires + 5 complémentaires + 1 STATUT + 1 SUSPENDU
        table.setColumnCount(40)
        # Entêtes des colonnes d'extension
        table.setHorizontalHeaderItem(38, QTableWidgetItem("TRAITÉ PAR"))
        table.setHorizontalHeaderItem(39, QTableWidgetItem("SUSPENDU"))

        for row_index, row in enumerate(rows):
            # row[0] = employeur_id
            employeur_id = row[0]

            # 1) Colonnes 0..22 : structure existante (23 colonnes)
            for col in range(1, 24):
                value = row[col]
                item = QTableWidgetItem("" if value is None else str(value))
                if col == 1:
                    # On stocke l'id employeur dans la première cellule (UserRole)
                    item.setData(Qt.ItemDataRole.UserRole, employeur_id)
                table.setItem(row_index, col - 1, item)

            # 2) Colonnes supplémentaires :
            #    23 : id employeur (visible)
            #    24 : date_debut_activite
            #    25 : forme_juridique
            #    26 : disa_2024
            #    27 : disa_2023
            #    28 : disa_2022
            #    29 : disa_2021
            #    30 : disa_anterieures_2010_2020
            #    31 : localisation_geographique
            #    32 : id traitement
            #    34 : actions_menees
            #    35 : téléphone_2
            #    36 : email_2
            #    37 : email_3
            extras = [
                employeur_id,   # id employeur déjà présent en row[0]
                row[25],        # date_debut_activite
                row[26],        # forme_juridique
                row[27],        # disa_2024
                row[28],        # disa_2023
                row[29],        # disa_2022
                row[30],        # disa_2021
                row[31],        # disa_anterieures_2010_2020
                row[32],        # localisation_geographique
                row[33],        # id traitement
                row[34],        # actions_menees
                row[35],        # telephone_2
                row[36],        # email_2
                row[37],        # email_3
                row[38],        # traite_par → col 38
            ]

            for offset, value in enumerate(extras):
                # On laisse la colonne 33 pour le STATUT coloré
                if offset < 10:
                    col_index = 23 + offset
                else:
                    col_index = 24 + offset  # saute la colonne 33
                item = QTableWidgetItem("" if value is None else str(value))
                table.setItem(row_index, col_index, item)

            # Col 39 : SUSPENDU (Oui / Non)
            is_suspended_val = bool(int(row[39] or 0)) if len(row) > 39 else False
            susp_item = QTableWidgetItem("Oui" if is_suspended_val else "Non")
            susp_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            bold_f = QFont("Segoe UI", 7)
            bold_f.setBold(True)
            susp_item.setFont(bold_f)
            if is_suspended_val:
                susp_item.setForeground(QColor("#92400e"))
                susp_item.setBackground(QColor("#fef3c7"))
            else:
                susp_item.setForeground(QColor("#14532d"))
                susp_item.setBackground(QColor("#dcfce7"))
            table.setItem(row_index, 39, susp_item)

            # 3) Colonne statut (col 33) + flag de couleur pour le délégué
            statut_db = (row[24] or "").strip() if len(row) > 24 else ""
            if not statut_db:
                date_validation_val = row[14]
                statut_db = "TRAITÉ" if date_validation_val else "NON TRAITÉ"

            is_traite = statut_db.upper() == "TRAITÉ"

            # Stocker les métadonnées sur la col 0
            locked_by_val = row[41] if len(row) > 41 else None
            is_locked_by_other = bool(locked_by_val and locked_by_val != _username)
            col0_item = table.item(row_index, 0)
            if col0_item is not None:
                col0_item.setData(_ROLE_IS_TRAITE, is_traite)
                col0_item.setData(_ROLE_IS_SUSPENDED, is_suspended_val)
                col0_item.setData(_ROLE_UPDATED_AT, row[40] if len(row) > 40 else None)
                col0_item.setData(_ROLE_IS_LOCKED, is_locked_by_other)
                col0_item.setData(_ROLE_LOCKED_BY, locked_by_val)

            # Badge texte dans la colonne statut (couleur gérée par le délégué)
            if is_suspended_val:
                statut_text = "⊘  SUSPENDU"
            elif is_locked_by_other:
                short_name = (locked_by_val or "")[:10]
                statut_text = f"🔒  {short_name}"
            elif is_traite:
                statut_text = "✔  TRAITÉ"
            else:
                statut_text = "✗  NON TRAITÉ"
            status_item = QTableWidgetItem(statut_text)
            bold_font = QFont("Segoe UI", 7)
            bold_font.setBold(True)
            status_item.setFont(bold_font)
            status_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(row_index, 33, status_item)

        # Ajuste automatiquement la largeur des colonnes comme dans les autres onglets
        table.resizeColumnsToContents()
        self._update_pagination_bar()

        # Déplace visuellement la colonne STATUT (logique 33) en première position
        header = table.horizontalHeader()
        header.moveSection(header.visualIndex(33), 0)

    # ------------------------------------------------------------------
    # Synchronisation tableau <-> formulaire
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    def _update_pagination_bar(self) -> None:
        """Met à jour les labels et l'état des boutons de pagination."""
        if not hasattr(self, "_page_label"):
            return
        total_pages = max(1, (self._total_rows + self._page_size - 1) // self._page_size)
        current_page = self._page + 1
        start = self._page * self._page_size + 1
        end = min(start + self._page_size - 1, self._total_rows)
        self._page_label.setText(f"Page {current_page} / {total_pages}")
        self._rows_label.setText(f"{start}–{end} sur {self._total_rows} dossiers")
        self._prev_btn.setEnabled(self._page > 0)
        self._next_btn.setEnabled(current_page < total_pages)

    def _on_prev_page(self) -> None:
        if self._page > 0:
            self._unlock_previous_row()
            self._page -= 1
            self._apply_search()

    def _on_next_page(self) -> None:
        total_pages = max(1, (self._total_rows + self._page_size - 1) // self._page_size)
        if self._page + 1 < total_pages:
            self._unlock_previous_row()
            self._page += 1
            self._apply_search()

    def _on_mes_dossiers_toggled(self, checked: bool) -> None:
        self._filter_mes_dossiers = checked
        self._page = 0
        if hasattr(self, "_mode_banner"):
            if checked:
                user = get_current_user()
                name = user.username if user else "vous"
                self._mode_banner.setText(
                    f"👤  Vue filtrée — Seuls vos dossiers sont affichés  ·  Connecté : {name}"
                )
                self._mode_banner.show()
            else:
                self._mode_banner.hide()
        self._apply_search()

    def _reset_update_btn(self) -> None:
        """Réactive le bouton Mettre à jour avec son style normal et masque la bannière TRAITÉ."""
        try:
            self.ui.update_btn.setEnabled(True)
            self.ui.update_btn.setToolTip("")
            self.ui.update_btn.setStyleSheet(
                "QPushButton { background:#15803d; color:white; border-radius:5px;"
                " padding:6px 14px; font-weight:600; font-size:12px; }"
                "QPushButton:hover { background:#16a34a; }"
                "QPushButton:pressed { background:#14532d; }"
            )
        except AttributeError:
            pass
        if hasattr(self, "_traite_banner"):
            self._traite_banner.hide()
        self._set_form_read_only(False)

    # ------------------------------------------------------------------
    # Soft lock (verrou souple multi-utilisateurs)
    # ------------------------------------------------------------------

    def _lock_current_row(self, td_id: int) -> None:
        """Verrouille le dossier td_id pour l'utilisateur courant (10 min)."""
        user = get_current_user()
        if not user or not td_id:
            return
        self._unlock_previous_row()
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE traitement_disa"
                    " SET locked_by = ?, locked_at = datetime('now')"
                    " WHERE id = ? AND (locked_by IS NULL OR locked_by = ?)",
                    (user.username, td_id, user.username),
                )
            self._current_locked_td_id = td_id
        except Exception:
            pass

    def _unlock_previous_row(self) -> None:
        """Libère le verrou sur le dossier précédemment sélectionné."""
        if self._current_locked_td_id is None:
            return
        user = get_current_user()
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE traitement_disa"
                    " SET locked_by = NULL, locked_at = NULL"
                    " WHERE id = ? AND locked_by = ?",
                    (self._current_locked_td_id, user.username if user else ""),
                )
        except Exception:
            pass
        self._current_locked_td_id = None

    def _renew_lock(self) -> None:
        """Renouvelle le verrou actif pour éviter l'expiration pendant une longue session."""
        if self._current_locked_td_id is None:
            return
        user = get_current_user()
        if not user:
            return
        try:
            with get_connection() as conn:
                conn.execute(
                    "UPDATE traitement_disa"
                    " SET locked_at = datetime('now')"
                    " WHERE id = ? AND locked_by = ?",
                    (self._current_locked_td_id, user.username),
                )
        except Exception:
            pass

    def _refresh_locks_in_table(self) -> None:
        """Rafraîchit silencieusement le statut des verrous dans le tableau visible.

        Ne recharge pas toutes les données — met à jour seulement les flags
        locked_by / locked_at et redessine les badges de statut.
        """
        table = self.ui.tableWidget
        if not self.isVisible() or table.rowCount() == 0:
            return

        # Collecter les id traitement visibles
        td_pairs: list[tuple[int, int]] = []  # (row_index, td_id)
        for r in range(table.rowCount()):
            item = table.item(r, 32)
            if item and item.text().strip():
                try:
                    td_pairs.append((r, int(item.text())))
                except ValueError:
                    pass
        if not td_pairs:
            return

        try:
            user = get_current_user()
            username = user.username if user else ""
            ph = ",".join("?" * len(td_pairs))
            with get_connection() as conn:
                rows = conn.execute(
                    f"SELECT id, locked_by, locked_at FROM traitement_disa WHERE id IN ({ph})",
                    [t[1] for t in td_pairs],
                ).fetchall()
            lock_map = {r[0]: (r[1], r[2]) for r in rows}

            for row_idx, td_id in td_pairs:
                if td_id not in lock_map:
                    continue
                locked_by, locked_at = lock_map[td_id]

                # Vérifier TTL (> 10 min → verrou expiré)
                is_locked_by_other = False
                if locked_by and locked_by != username:
                    is_locked_by_other = True

                col0 = table.item(row_idx, 0)
                if col0 is None:
                    continue

                old_locked = bool(col0.data(_ROLE_IS_LOCKED))
                col0.setData(_ROLE_IS_LOCKED, is_locked_by_other)
                col0.setData(_ROLE_LOCKED_BY, locked_by)

                # Mettre à jour le badge statut si le statut de verrou a changé
                if old_locked != is_locked_by_other:
                    is_traite  = bool(col0.data(_ROLE_IS_TRAITE))
                    is_susp    = bool(col0.data(_ROLE_IS_SUSPENDED))
                    status_item = table.item(row_idx, 33)
                    if status_item:
                        if is_susp:
                            status_item.setText("⊘  SUSPENDU")
                        elif is_locked_by_other:
                            status_item.setText(f"🔒  {(locked_by or '')[:10]}")
                        elif is_traite:
                            status_item.setText("✔  TRAITÉ")
                        else:
                            status_item.setText("✗  NON TRAITÉ")

            table.viewport().update()
        except Exception:
            pass

    def _poll_db_changes(self) -> None:
        """Détecte les modifications faites sur d'autres postes et recharge si nécessaire.

        Compare MAX(updated_at) de traitement_disa avec la dernière valeur connue.
        Si différent → rechargement complet du tableau (silencieux).
        """
        if not self.isVisible():
            return
        try:
            with get_connection() as conn:
                row = conn.execute(
                    "SELECT MAX(updated_at) FROM traitement_disa"
                ).fetchone()
            latest = (row[0] or "") if row else ""
            if self._last_db_updated_at == "":
                # Première exécution : initialiser sans recharger
                self._last_db_updated_at = latest
            elif latest != self._last_db_updated_at:
                self._last_db_updated_at = latest
                self.load_data()
        except Exception:
            pass

    def on_table_row_selected(self, row: int, column: int) -> None:  # noqa: ARG002
        """Remplit le formulaire à partir de la ligne sélectionnée."""

        table = self.ui.tableWidget
        # Si aucune donnée dans la ligne, on ignore
        first_item = table.item(row, 0)
        if not first_item:
            return

        # Libérer immédiatement le verrou de la ligne précédente
        # (automatique — l'utilisateur n'a pas besoin de cliquer Effacer)
        self._unlock_previous_row()

        # Colonnes 0..10 -> layout_2
        layout2 = self.ui.gridLayout_2
        for col in range(0, 11):
            item = table.item(row, col)
            value = item.text() if item else ""
            self._set_text_in_layout(layout2, col, value)

        # Colonnes 11..22 -> layout_3
        # Après l'insertion d'ACTIONS MENÉES au rang _actions_menees_row (=7),
        # les rangs ≥ 7 sont décalés de +1 dans le layout.
        layout3 = self.ui.gridLayout_3
        for col in range(11, 23):
            item = table.item(row, col)
            value = item.text() if item else ""
            form_row = col - 11
            if self._actions_menees_row is not None and form_row >= self._actions_menees_row:
                form_row += 1
            self._set_text_in_layout(layout3, form_row, value)

        # ACTIONS MENÉES : déjà présente en colonne 34 du tableau — pas de requête BD
        if self._actions_menees_row is not None:
            actions_item = table.item(row, 34)
            actions_val = actions_item.text() if actions_item else ""
            self._set_text_in_layout(layout3, self._actions_menees_row, actions_val)

        # Mémoriser updated_at pour la détection de conflits lors de la sauvegarde
        col0 = table.item(row, 0)
        self._original_td_updated_at = col0.data(_ROLE_UPDATED_AT) if col0 else None

        # ── Vérification TRAITÉ : lecture seule pour les non-admins
        #    sauf si c'est l'agent qui a lui-même traité le dossier ──────
        is_traite = bool(col0.data(_ROLE_IS_TRAITE)) if col0 else False
        user = get_current_user()
        is_admin = (user.role.lower() == "admin") if user else False
        traite_par = (table.item(row, 38).text() if table.item(row, 38) else "") or ""
        is_own_dossier = traite_par == (user.username if user else "")

        if is_traite and not is_admin and not is_own_dossier:
            # Dossier traité par un autre agent → lecture seule
            self.ui.update_btn.setEnabled(False)
            self.ui.update_btn.setToolTip(
                "Dossier traité par un autre agent — seul un administrateur peut le modifier"
            )
            self.ui.update_btn.setStyleSheet(
                "QPushButton { background:#94a3b8; color:white; border-radius:5px;"
                " padding:6px 14px; font-weight:600; font-size:12px; }"
            )
            self._set_form_read_only(True)
            if hasattr(self, "_traite_banner"):
                _par_label = traite_par or "un agent"
                self._traite_banner.setText(
                    f"🔒  Dossier TRAITÉ par {_par_label} — Lecture seule.  "
                    "Seul un administrateur peut modifier ce dossier."
                )
                self._traite_banner.setStyleSheet(
                    "background:#fef3c7; color:#92400e; font-size:11px; font-weight:600;"
                    " padding:4px 8px; border-bottom:1px solid #fbbf24;"
                )
                self._traite_banner.show()
        else:
            # Réactiver le bouton et masquer la bannière
            self._reset_update_btn()

        # Verrouiller le dossier pour éviter l'édition simultanée
        td_id_item = table.item(row, 32)  # colonne traitement_id
        td_id = None
        if td_id_item:
            try:
                td_id = int(td_id_item.text()) if td_id_item.text().strip() else None
            except (ValueError, TypeError):
                td_id = None
        if td_id:
            locked_by = col0.data(_ROLE_LOCKED_BY) if col0 else None
            if locked_by and locked_by != (user.username if user else ""):
                # Dossier ouvert par un autre agent → lecture seule
                self.ui.update_btn.setEnabled(False)
                self.ui.update_btn.setToolTip(
                    f"Dossier en cours d'édition par {locked_by}"
                )
                self.ui.update_btn.setStyleSheet(
                    "QPushButton { background:#eab308; color:white; border-radius:5px;"
                    " padding:6px 14px; font-weight:600; font-size:12px; }"
                )
                self._set_form_read_only(True)
                if hasattr(self, "_traite_banner"):
                    self._traite_banner.setText(
                        f"🔒  Dossier ouvert par {locked_by} — Lecture seule."
                        "  Attendez qu'il libère le dossier pour pouvoir le modifier."
                    )
                    self._traite_banner.setStyleSheet(
                        "background:#fef9c3; color:#713f12; font-size:11px; font-weight:600;"
                        " padding:4px 8px; border-bottom:1px solid #fbbf24;"
                    )
                    self._traite_banner.show()
            else:
                self._lock_current_row(td_id)

    def _get_current_employeur_id(self) -> int | None:
        """Récupère l'id employeur stocké dans la ligne sélectionnée du tableau."""

        table = self.ui.tableWidget
        current_row = table.currentRow()
        if current_row < 0:
            return None
        item = table.item(current_row, 0)
        if not item:
            return None
        emp_id = item.data(Qt.ItemDataRole.UserRole)
        try:
            return int(emp_id) if emp_id is not None else None
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # Actions des boutons
    # ------------------------------------------------------------------

    def _on_search_text_changed(self, text: str) -> None:  # noqa: ARG002
        """Relance le timer dès que le texte change (recherche auto)."""

        if hasattr(self, "_search_timer") and self._search_timer is not None:
            # Si le champ est vidé, on recharge immédiatement toutes les données
            if not self.search_cnps_line.text().strip():
                self._search_timer.stop()
                self.load_data()
                return

            self._search_timer.start()

    def _apply_search(self) -> None:
        """Applique le filtre courant du champ de recherche."""

        filter_text = None
        if hasattr(self, "search_cnps_line") and self.search_cnps_line is not None:
            text_value = self.search_cnps_line.text().strip()
            if text_value:
                # Réinitialiser la page seulement si le filtre change
                if getattr(self, '_last_filter', '') != text_value:
                    self._page = 0
                self._last_filter = text_value
                filter_text = text_value
            else:
                # Réinitialiser la page seulement si on vient d'effacer un filtre actif
                if getattr(self, '_last_filter', '') != '':
                    self._page = 0
                self._last_filter = ""

        self.load_data(filter_text=filter_text)

    def on_search_clicked(self) -> None:
        """Filtre les résultats par raison sociale ou N° CNPS.

        Utilise la même logique que la recherche automatique, mais déclenchée
        explicitement par le clic sur le bouton.
        """

        self._apply_search()

    def on_clear_clicked(self) -> None:
        """Efface le formulaire et désélectionne les lignes du tableau."""

        self._clear_layout_fields(self.ui.gridLayout_2)
        self._clear_layout_fields(self.ui.gridLayout_3)
        self.ui.tableWidget.clearSelection()
        # On vide aussi le champ de recherche s'il existe
        if hasattr(self, "search_cnps_line") and self.search_cnps_line is not None:
            self.search_cnps_line.clear()
            if hasattr(self, "_search_timer") and self._search_timer is not None:
                self._search_timer.stop()
        # Réactiver le bouton Mettre à jour si un dossier TRAITÉ était sélectionné
        self._reset_update_btn()
        # Libérer le verrou puis recharger
        self._unlock_previous_row()
        self.load_data()

    def on_add_clicked(self) -> None:
        """Ajoute un nouvel employeur + traitement DISA à partir du formulaire."""
        employeur_data, traitement_data = self._read_form_data()

        numero = employeur_data["numero"]
        numero_cnps = employeur_data["numero_cnps"]
        raison_sociale = employeur_data["raison_sociale"]
        secteur = employeur_data["secteur"]
        effectifs = employeur_data["effectifs"]
        periodicite = employeur_data["periodicite"]
        telephone = employeur_data["telephone"]
        mail = employeur_data["mail"]
        localites = employeur_data["localites"]
        exercice = employeur_data["exercice"]
        disa_anterieures_a_recueillir = employeur_data["disa_anterieures_a_recueillir"]

        date_reception = traitement_data["date_reception"]
        date_traitement = traitement_data["date_traitement"]
        date_validation = traitement_data["date_validation"]
        effectif_disa = traitement_data["effectif_disa"]
        nbre_traitees = traitement_data["nbre_traitees"]
        nbre_validees = traitement_data["nbre_validees"]
        nbre_rejetees = traitement_data["nbre_rejetees"]
        actions_menees = traitement_data["actions_menees"]
        nbre_rejetees_traitees = traitement_data["nbre_rejetees_traitees"]
        nbre_total_validees = traitement_data["nbre_total_validees"]
        date_traitement_rejet = traitement_data["date_traitement_rejet"]
        nbre_restant = traitement_data["nbre_restant"]
        observations = traitement_data["observations"]

        # Auto-renseigne date_traitement si des données de traitement sont présentes sans date
        has_treatment_data = any([
            effectif_disa, nbre_traitees, nbre_validees, nbre_rejetees, actions_menees,
        ])
        if not date_traitement and not date_validation and has_treatment_data:
            date_traitement = QDate.currentDate().toString("yyyy-MM-dd")
            self._set_text_in_layout(self.ui.gridLayout_3, 1, date_traitement)

        # Statut persistant dans la BD : basé sur la présence de date_de_traitement ou date_de_validation
        statut = self._compute_statut(date_traitement, date_validation)

        if numero is None or not numero_cnps or not raison_sociale:
            QMessageBox.warning(
                self,
                "Champs manquants",
                "Les champs N°, Numéro CNPS et Raison sociale sont obligatoires.",
            )
            return

        # Validation des champs obligatoires du traitement DISA
        traitement_data["date_traitement"] = date_traitement
        err = self._validate_traitement_fields(traitement_data)
        if err:
            QMessageBox.warning(self, "Champs obligatoires manquants", err)
            return

        # Validation des règles métier (cohérence des chiffres)
        err_biz = self._validate_business_rules(traitement_data)
        if err_biz:
            msg = QMessageBox(self)
            msg.setWindowTitle("Incohérence des données")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setText(
                "Les données saisies semblent incohérentes :\n\n"
                + err_biz
                + "\n\nVoulez-vous enregistrer quand même ?"
            )
            msg.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            msg.setDefaultButton(QMessageBox.StandardButton.No)
            if msg.exec() != QMessageBox.StandardButton.Yes:
                return

        try:
            conn = get_connection()
        except Exception as exc:  # pragma: no cover - affichage UI
            QMessageBox.critical(self, "Erreur BD", f"Impossible d'ouvrir la base : {exc}")
            return

        _user = get_current_user()
        _traite_par = _user.username if _user else None

        with conn:
            cur = conn.cursor()

            # Insertion dans identification_employeurs
            cur.execute(
                """
                INSERT INTO identification_employeurs (
                    numero, numero_cnps, raison_sociale, secteur_activite,
                    date_debut_activite, forme_juridique, nombre_travailleur,
                    disa_2024, disa_2023, disa_2022, disa_2021, disa_anterieures_2010_2020,
                    periodicite, telephone_1, email_1, localisation_geographique,
                    localites, exercice
                ) VALUES (?, ?, ?, ?, NULL, NULL, ?, NULL, NULL, NULL, NULL, NULL,
                          ?, ?, ?, NULL, ?, ?)
                """,
                (
                    numero, numero_cnps, raison_sociale, secteur, effectifs,
                    periodicite, telephone, mail, localites, exercice,
                ),
            )
            employeur_id = cur.lastrowid

            # Insertion dans traitement_disa
            cur.execute(
                """
                INSERT INTO traitement_disa (
                    employeur_id, exercice, disa_anterieures_a_recueillir,
                    date_de_reception, date_de_traitement, date_de_validation,
                    effectif_disa, nbre_de_lignes_traitees, nbre_de_lignes_validees,
                    nbre_de_lignes_rejetees, actions_menees, nbre_de_lignes_rejetees_traitees,
                    nbre_total_de_lignes_validees_apres_traitement_des_rejets,
                    date_de_traitement_rejet, nbre_restant_de_rejet, observations,
                    statut, traite_par
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    employeur_id, exercice, disa_anterieures_a_recueillir,
                    date_reception, date_traitement, date_validation,
                    effectif_disa, nbre_traitees, nbre_validees, nbre_rejetees,
                    actions_menees, nbre_rejetees_traitees, nbre_total_validees,
                    date_traitement_rejet, nbre_restant, observations,
                    statut, _traite_par,
                ),
            )
            td_id = cur.lastrowid

            # Audit log
            log_audit(conn, _traite_par, "INSERT", "identification_employeurs", employeur_id,
                      new_values={"numero_cnps": numero_cnps, "raison_sociale": raison_sociale,
                                  "exercice": exercice})
            log_audit(conn, _traite_par, "INSERT", "traitement_disa", td_id,
                      new_values={"statut": statut, "exercice": exercice,
                                  "employeur_id": employeur_id})

        self.load_data()
        self._notify("Enregistrement ajouté", f"{raison_sociale} — {exercice}", "success")

        # Notifie les autres onglets qu'une modification a eu lieu
        get_data_bus().notify()

    def on_update_clicked(self) -> None:
        """Met à jour l'employeur + traitement DISA sélectionnés."""

        employeur_id = self._get_current_employeur_id()
        if employeur_id is None:
            QMessageBox.warning(self, "Sélection", "Veuillez d'abord sélectionner une ligne dans le tableau.")
            return

        employeur_data, traitement_data = self._read_form_data()

        numero = employeur_data["numero"]
        numero_cnps = employeur_data["numero_cnps"]
        raison_sociale = employeur_data["raison_sociale"]
        secteur = employeur_data["secteur"]
        effectifs = employeur_data["effectifs"]
        periodicite = employeur_data["periodicite"]
        telephone = employeur_data["telephone"]
        mail = employeur_data["mail"]
        localites = employeur_data["localites"]
        exercice = employeur_data["exercice"]
        disa_anterieures_a_recueillir = employeur_data["disa_anterieures_a_recueillir"]

        date_reception = traitement_data["date_reception"]
        date_traitement = traitement_data["date_traitement"]
        date_validation = traitement_data["date_validation"]
        effectif_disa = traitement_data["effectif_disa"]
        nbre_traitees = traitement_data["nbre_traitees"]
        nbre_validees = traitement_data["nbre_validees"]
        nbre_rejetees = traitement_data["nbre_rejetees"]
        actions_menees = traitement_data["actions_menees"]
        nbre_rejetees_traitees = traitement_data["nbre_rejetees_traitees"]
        nbre_total_validees = traitement_data["nbre_total_validees"]
        date_traitement_rejet = traitement_data["date_traitement_rejet"]
        nbre_restant = traitement_data["nbre_restant"]
        observations = traitement_data["observations"]

        # Si l'agent a rempli des données de traitement mais n'a pas saisi de date,
        # on auto-renseigne date_traitement à aujourd'hui pour déclencher le statut TRAITÉ.
        has_treatment_data = any([
            effectif_disa, nbre_traitees, nbre_validees, nbre_rejetees, actions_menees,
        ])
        if not date_traitement and not date_validation and has_treatment_data:
            date_traitement = QDate.currentDate().toString("yyyy-MM-dd")
            self._set_text_in_layout(self.ui.gridLayout_3, 1, date_traitement)

        # Statut persistant dans la BD : basé sur la présence de date_de_traitement ou date_de_validation
        statut = self._compute_statut(date_traitement, date_validation)

        if numero is None or not numero_cnps or not raison_sociale or exercice is None:
            QMessageBox.warning(
                self,
                "Champs manquants",
                "Les champs N°, Numéro CNPS, Raison sociale et Exercice sont obligatoires pour la mise à jour.",
            )
            return

        # Validation des champs obligatoires du traitement DISA
        traitement_data["date_traitement"] = date_traitement
        err = self._validate_traitement_fields(traitement_data)
        if err:
            QMessageBox.warning(self, "Champs obligatoires manquants", err)
            return

        # Validation des règles métier (cohérence des chiffres)
        err_biz = self._validate_business_rules(traitement_data)
        if err_biz:
            msg = QMessageBox(self)
            msg.setWindowTitle("Incohérence des données")
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setText(
                "Les données saisies semblent incohérentes :\n\n"
                + err_biz
                + "\n\nVoulez-vous enregistrer quand même ?"
            )
            msg.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            msg.setDefaultButton(QMessageBox.StandardButton.No)
            if msg.exec() != QMessageBox.StandardButton.Yes:
                return

        # ── Vérification TRAITÉ : seul l'admin (ou l'agent qui a traité) peut modifier
        _current_user = get_current_user()
        _is_admin = (_current_user.role.lower() == "admin") if _current_user else False
        if not _is_admin:
            try:
                with get_connection() as _chk0:
                    _r0 = _chk0.execute(
                        "SELECT statut, traite_par FROM traitement_disa "
                        "WHERE employeur_id = ? AND exercice = ?",
                        (employeur_id, exercice),
                    ).fetchone()
                if _r0 and (_r0[0] or "").upper() == "TRAITÉ":
                    _par = _r0[1] or ""
                    # L'agent qui a lui-même traité le dossier peut le modifier
                    _is_own = _par == (_current_user.username if _current_user else "")
                    if not _is_own:
                        QMessageBox.warning(
                            self, "Dossier protégé",
                            f"Ce dossier a déjà été <b>traité</b> par <b>{_par or 'un agent'}</b>.<br><br>"
                            "Seul un <b>administrateur</b> ou l'agent qui a traité ce dossier peut le modifier."
                        )
                        return
            except Exception:
                pass
        # ─────────────────────────────────────────────────────────────────────

        # ── Vérification anti-conflit ─────────────────────────────────────────
        # Un autre utilisateur a-t-il modifié ce dossier depuis qu'on l'a ouvert ?
        if self._original_td_updated_at is not None:
            try:
                with get_connection() as _chk:
                    _chk_row = _chk.execute(
                        "SELECT updated_at, traite_par FROM traitement_disa "
                        "WHERE employeur_id = ? AND exercice = ?",
                        (employeur_id, exercice),
                    ).fetchone()
                current_updated_at = _chk_row["updated_at"] if _chk_row else None
                last_user = (_chk_row["traite_par"] or "un autre utilisateur") if _chk_row else "un autre utilisateur"
            except Exception:
                current_updated_at = None
                last_user = "un autre utilisateur"

            if current_updated_at and current_updated_at != self._original_td_updated_at:
                msg = QMessageBox(self)
                msg.setWindowTitle("Conflit de modification")
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setText(
                    f"⚠  Ce dossier a été modifié par <b>{last_user}</b> "
                    f"depuis que vous l'avez ouvert.<br><br>"
                    "Vos modifications <b>écraseront</b> les siennes.<br>"
                    "Voulez-vous continuer quand même ?"
                )
                msg.setStandardButtons(
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                msg.setDefaultButton(QMessageBox.StandardButton.No)
                if msg.exec() != QMessageBox.StandardButton.Yes:
                    return
        # ─────────────────────────────────────────────────────────────────────

        try:
            conn = get_connection()
        except Exception as exc:  # pragma: no cover - affichage UI
            QMessageBox.critical(self, "Erreur BD", f"Impossible d'ouvrir la base : {exc}")
            return

        _user = get_current_user()
        _traite_par = _user.username if _user else None

        with conn:
            cur = conn.cursor()

            # Lire les anciennes valeurs pour l'audit et le snapshot
            _old_td = cur.execute(
                "SELECT * FROM traitement_disa WHERE employeur_id = ? AND exercice = ?",
                (employeur_id, exercice),
            ).fetchone()
            _td_id = _old_td["id"] if _old_td else None

            # Snapshot de l'état précédent avant modification
            if _td_id:
                snapshot_traitement_disa(conn, _td_id, _traite_par)

            # Mise à jour de l'employeur
            # updated_at inclus si la colonne existe (migration 5 appliquée)
            cur.execute("PRAGMA table_info(identification_employeurs)")
            _ie_cols = {r[1] for r in cur.fetchall()}
            _ie_has_updated_at = "updated_at" in _ie_cols

            _ie_sql = """
                UPDATE identification_employeurs
                SET numero = ?, numero_cnps = ?, raison_sociale = ?,
                    secteur_activite = ?, nombre_travailleur = ?,
                    periodicite = ?, telephone_1 = ?, email_1 = ?,
                    localites = ?, exercice = ?{updated_at_clause}
                WHERE id = ?
            """.format(
                updated_at_clause=", updated_at = datetime('now')" if _ie_has_updated_at else ""
            )
            cur.execute(
                _ie_sql,
                (
                    numero,
                    numero_cnps,
                    raison_sociale,
                    secteur,
                    effectifs,
                    periodicite,
                    telephone,
                    mail,
                    localites,
                    exercice,
                    employeur_id,
                ),
            )

            # INSERT OR UPDATE dans traitement_disa via ON CONFLICT (en incluant STATUT et TRAITÉ PAR)
            cur.execute(
                """
                INSERT INTO traitement_disa (
                    employeur_id, exercice, disa_anterieures_a_recueillir,
                    date_de_reception, date_de_traitement, date_de_validation,
                    effectif_disa, nbre_de_lignes_traitees, nbre_de_lignes_validees,
                    nbre_de_lignes_rejetees, actions_menees, nbre_de_lignes_rejetees_traitees,
                    nbre_total_de_lignes_validees_apres_traitement_des_rejets,
                    date_de_traitement_rejet, nbre_restant_de_rejet, observations,
                    statut, traite_par
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(employeur_id, exercice) DO UPDATE SET
                    disa_anterieures_a_recueillir = excluded.disa_anterieures_a_recueillir,
                    date_de_reception = excluded.date_de_reception,
                    date_de_traitement = excluded.date_de_traitement,
                    date_de_validation = excluded.date_de_validation,
                    effectif_disa = excluded.effectif_disa,
                    nbre_de_lignes_traitees = excluded.nbre_de_lignes_traitees,
                    nbre_de_lignes_validees = excluded.nbre_de_lignes_validees,
                    nbre_de_lignes_rejetees = excluded.nbre_de_lignes_rejetees,
                    actions_menees = excluded.actions_menees,
                    nbre_de_lignes_rejetees_traitees = excluded.nbre_de_lignes_rejetees_traitees,
                    nbre_total_de_lignes_validees_apres_traitement_des_rejets = excluded.nbre_total_de_lignes_validees_apres_traitement_des_rejets,
                    date_de_traitement_rejet = excluded.date_de_traitement_rejet,
                    nbre_restant_de_rejet = excluded.nbre_restant_de_rejet,
                    observations = excluded.observations,
                    statut = excluded.statut,
                    traite_par = excluded.traite_par,
                    updated_at = datetime('now')
                """,
                (
                    employeur_id,
                    exercice,
                    disa_anterieures_a_recueillir,
                    date_reception,
                    date_traitement,
                    date_validation,
                    effectif_disa,
                    nbre_traitees,
                    nbre_validees,
                    nbre_rejetees,
                    actions_menees,
                    nbre_rejetees_traitees,
                    nbre_total_validees,
                    date_traitement_rejet,
                    nbre_restant,
                    observations,
                    statut,
                    _traite_par,
                ),
            )

            # Audit log UPDATE
            _new_td_row = cur.execute(
                "SELECT id FROM traitement_disa WHERE employeur_id = ? AND exercice = ?",
                (employeur_id, exercice),
            ).fetchone()
            _final_td_id = _new_td_row["id"] if _new_td_row else _td_id
            log_audit(conn, _traite_par, "UPDATE", "traitement_disa", _final_td_id,
                      old_values={"statut": _old_td["statut"] if _old_td else None,
                                  "traite_par": _old_td["traite_par"] if _old_td else None},
                      new_values={"statut": statut, "traite_par": _traite_par,
                                  "exercice": exercice})
            log_audit(conn, _traite_par, "UPDATE", "identification_employeurs", employeur_id,
                      new_values={"numero_cnps": numero_cnps, "raison_sociale": raison_sociale})

        # Rechargement des données et resélection de la ligne mise à jour
        self.load_data()

        table = self.ui.tableWidget
        for row_index in range(table.rowCount()):
            item = table.item(row_index, 0)
            if not item:
                continue
            row_emp_id = item.data(Qt.ItemDataRole.UserRole)
            try:
                row_emp_id = int(row_emp_id) if row_emp_id is not None else None
            except (TypeError, ValueError):
                row_emp_id = None

            if row_emp_id == employeur_id:
                table.setCurrentCell(row_index, 0)
                self.on_table_row_selected(row_index, 0)
                break

        self._notify("Dossier mis à jour", f"{raison_sociale} — {exercice}", "success")

        self._current_locked_td_id = None  # le dossier sauvegardé n'est plus verrouillé par nous
        # Notifie les autres onglets qu'une modification a eu lieu
        get_data_bus().notify()

    def on_delete_clicked(self) -> None:
        """Supprime l'employeur (et ses traitements DISA via CASCADE)."""

        employeur_id = self._get_current_employeur_id()
        if employeur_id is None:
            QMessageBox.warning(self, "Sélection", "Veuillez d'abord sélectionner une ligne dans le tableau.")
            return

        reply = QMessageBox.question(
            self,
            "Confirmation",
            "Voulez-vous vraiment supprimer cet employeur et ses traitements DISA ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            conn = get_connection()
        except Exception as exc:  # pragma: no cover - affichage UI
            QMessageBox.critical(self, "Erreur BD", f"Impossible d'ouvrir la base : {exc}")
            return

        self._unlock_previous_row()
        _user = get_current_user()
        _actor = _user.username if _user else None

        with conn:
            # Lire les infos avant suppression pour l'audit
            _emp_row = conn.execute(
                "SELECT numero_cnps, raison_sociale FROM identification_employeurs WHERE id = ?",
                (employeur_id,),
            ).fetchone()
            _td_rows = conn.execute(
                "SELECT id, exercice, statut FROM traitement_disa WHERE employeur_id = ?",
                (employeur_id,),
            ).fetchall()

            conn.execute("DELETE FROM identification_employeurs WHERE id = ?", (employeur_id,))

            # Audit log suppression
            _rs = _emp_row["raison_sociale"] if _emp_row else ""
            log_audit(conn, _actor, "DELETE", "identification_employeurs", employeur_id,
                      old_values={"numero_cnps": _emp_row["numero_cnps"] if _emp_row else None,
                                  "raison_sociale": _rs})
            for _td in _td_rows:
                log_audit(conn, _actor, "DELETE", "traitement_disa", _td["id"],
                          old_values={"exercice": _td["exercice"], "statut": _td["statut"]})

        self.on_clear_clicked()
        self._notify("Employeur supprimé",
                     (_emp_row["raison_sociale"] if _emp_row else "") or "", "info")

        # Notifie les autres onglets qu'une modification a eu lieu
        get_data_bus().notify()

    # ------------------------------------------------------------------
    # Suspension d'entreprise
    # ------------------------------------------------------------------

