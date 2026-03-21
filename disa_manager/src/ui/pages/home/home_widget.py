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
from core.events import get_data_bus
from core.session import get_current_user

# Rôle custom pour stocker le flag is_traite sur la colonne 0 de chaque ligne
_ROLE_IS_TRAITE = Qt.ItemDataRole.UserRole + 10


class _ModernRowDelegate(QStyledItemDelegate):
    """Délégué de rendu moderne pour le tableau Accueil.

    - Fond coloré selon le statut : vert pâle (TRAITÉ) / rouge pâle (NON TRAITÉ)
    - Barre indicatrice verticale de 5 px sur la première colonne
    - Badge pill arrondi sur la colonne statut (col 33)
    - Séparateur horizontal subtil entre lignes
    - Overlay indigo semi-transparent sur la ligne sélectionnée
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

    # Divers
    _BAR_W    = 5
    _SEL_OVRL = QColor(99, 102, 241, 40)   # indigo semi-transparent
    _DIVIDER  = QColor(0, 0, 0, 12)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:  # type: ignore[override]
        row = index.row()
        col = index.column()
        model = index.model()

        # Lire le flag is_traite stocké sur la col 0 de la même ligne
        is_traite = bool(model.index(row, 0).data(_ROLE_IS_TRAITE))

        bg  = self._TRAITE_BG  if is_traite else self._NON_BG
        bar = self._TRAITE_BAR if is_traite else self._NON_BAR
        fg  = self._TRAITE_FG  if is_traite else self._NON_FG

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
            QHeaderView { background: #1e3a5f; border: none; }
            QHeaderView::section {
                background: #1e3a5f;
                color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 8px;
                font-weight: 700;
                letter-spacing: 0.3px;
                padding: 5px 6px;
                border: none;
                border-right: 1px solid #2a4f80;
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

        # ── Mise en page compacte : formulaire + table dans un splitter ──
        self._setup_compact_layout()

    def showEvent(self, event) -> None:  # type: ignore[override]
        """Rafraîchit les données si une mise à jour a eu lieu pendant que le widget était caché."""
        super().showEvent(event)
        if self._needs_refresh:
            self.load_data()

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
        splitter.addWidget(result_frame)
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

        layout6.addWidget(_make_header("IDENTIFICATION EMPLOYEUR", "#1e3a5f"), 0, 0, 1, 1)
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
            "add":    _btn_base.format(bg="#1e3a5f", hov="#2a4f80", prs="#16294a"),
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

    def _configure_date_and_input_widgets(self) -> None:
        """Configure les champs de date cliquables et remplace les listes déroulantes.

        - Les lignes de date (réception, traitement, validation, traitement rejet)
          deviennent des QDateEdit avec calendrier.
        - Toutes les QComboBox restantes dans la colonne de droite sont remplacées
          par de simples QLineEdit (plus de listes déroulantes).
        """

        layout = self.ui.gridLayout_3

        # Lignes utilisées pour les dates dans la deuxième colonne
        from PySide6.QtCore import QDate
        _sentinel = QDate.fromString(self._DATE_SENTINEL, "yyyy-MM-dd")

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
            date_edit.setDisplayFormat("yyyy-MM-dd")
            # La date minimale sert de sentinelle "non saisie" (affichée comme texte vide)
            date_edit.setMinimumDate(_sentinel)
            date_edit.setDate(_sentinel)
            date_edit.setSpecialValueText("(non définie)")
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
            "  border: 2px solid #2563eb;"
            "  background-color: #ffffff;"
            "}"
        )
        layout.insertWidget(0, self.search_cnps_line)

        # Timer pour appliquer la recherche automatiquement après une pause de saisie
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(400)  # 400 ms
        self._search_timer.timeout.connect(self._apply_search)

        self.search_cnps_line.textChanged.connect(self._on_search_text_changed)

    def _clear_layout_fields(self, layout) -> None:
        """Efface tous les champs (QLineEdit / QComboBox) d'un layout grille."""

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
        query = """
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
                -- Champs supplémentaires de identification_employeurs
                ie.date_debut_activite,
                ie.forme_juridique,
                ie.disa_2024,
                ie.disa_2023,
                ie.disa_2022,
                ie.disa_2021,
                ie.disa_anterieures_2010_2020,
                ie.localisation_geographique,
                -- Id du traitement DISA
                td.id AS traitement_id,
                -- Champs complémentaires de la jointure
                td.actions_menees,
                ie.telephone_2,
                ie.email_2,
                ie.email_3,
                td.traite_par,
                COALESCE(td.is_suspended, 0) AS is_suspended
            FROM identification_employeurs ie
            LEFT JOIN traitement_disa td ON td.employeur_id = ie.id
        """
        params: list = []

        if filter_text:
            query += " WHERE ie.numero_cnps = ? OR ie.raison_sociale LIKE ?"
            like = f"%{filter_text}%"
            params.extend([filter_text, like])

        query += " ORDER BY ie.numero"

        with conn:
            rows = conn.execute(query, params).fetchall()

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

            # Stocker le flag sur la col 0 pour que le délégué colorise toute la ligne
            col0_item = table.item(row_index, 0)
            if col0_item is not None:
                col0_item.setData(_ROLE_IS_TRAITE, is_traite)

            # Badge texte dans la colonne statut (couleur gérée par le délégué)
            statut_text = "✔  TRAITÉ" if is_traite else "✗  NON TRAITÉ"
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

        # Déplace visuellement la colonne STATUT (logique 33) en première position
        header = table.horizontalHeader()
        header.moveSection(header.visualIndex(33), 0)

    # ------------------------------------------------------------------
    # Synchronisation tableau <-> formulaire
    # ------------------------------------------------------------------

    def on_table_row_selected(self, row: int, column: int) -> None:  # noqa: ARG002
        """Remplit le formulaire à partir de la ligne sélectionnée."""

        table = self.ui.tableWidget
        # Si aucune donnée dans la ligne, on ignore
        first_item = table.item(row, 0)
        if not first_item:
            return

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
                filter_text = text_value

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
        # On recharge toutes les données (sans filtre)
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

        try:
            conn = get_connection()
        except Exception as exc:  # pragma: no cover - affichage UI
            QMessageBox.critical(self, "Erreur BD", f"Impossible d'ouvrir la base : {exc}")
            return

        with conn:
            cur = conn.cursor()

            # Insertion dans identification_employeurs (on laisse plusieurs champs optionnels à NULL)
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
                ),
            )

            employeur_id = cur.lastrowid

            # Utilisateur courant
            _user = get_current_user()
            _traite_par = _user.username if _user else None

            # Insertion dans traitement_disa (avec STATUT persistant et TRAITÉ PAR)
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

        self.load_data()
        QMessageBox.information(self, "Succès", "Enregistrement ajouté avec succès.")

        # Notifie les autres onglets qu'une modification a eu lieu
        get_data_bus().data_changed.emit()

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

        try:
            conn = get_connection()
        except Exception as exc:  # pragma: no cover - affichage UI
            QMessageBox.critical(self, "Erreur BD", f"Impossible d'ouvrir la base : {exc}")
            return

        with conn:
            cur = conn.cursor()

            # Mise à jour de l'employeur
            cur.execute(
                """
                UPDATE identification_employeurs
                SET numero = ?, numero_cnps = ?, raison_sociale = ?,
                    secteur_activite = ?, nombre_travailleur = ?,
                    periodicite = ?, telephone_1 = ?, email_1 = ?,
                    localites = ?, exercice = ?
                WHERE id = ?
                """,
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

            # Utilisateur courant
            _user = get_current_user()
            _traite_par = _user.username if _user else None

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

        QMessageBox.information(self, "Succès", "Enregistrement mis à jour avec succès.")

        # Notifie les autres onglets qu'une modification a eu lieu
        get_data_bus().data_changed.emit()

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

        with conn:
            conn.execute("DELETE FROM identification_employeurs WHERE id = ?", (employeur_id,))

        self.on_clear_clicked()
        QMessageBox.information(self, "Succès", "Employeur supprimé avec succès.")

        # Notifie les autres onglets qu'une modification a eu lieu
        get_data_bus().data_changed.emit()

    # ------------------------------------------------------------------
    # Suspension d'entreprise
    # ------------------------------------------------------------------

