from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
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
)

from .home_ui import Ui_Form
from db.connection import get_connection
from core.events import get_data_bus
from core.session import get_current_user


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

        # Harmonise la table avec les autres onglets (sélection, alternance des lignes)
        table = self.ui.tableWidget
        table.setSelectionBehavior(table.SelectionBehavior.SelectRows)
        table.setSelectionMode(table.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setShowGrid(False)

        # Police de l'en-tête
        header_font = QFont("Segoe UI", 10)
        header_font.setBold(True)
        table.horizontalHeader().setFont(header_font)
        table.horizontalHeader().setDefaultAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        # Masque les colonnes techniques pour une vue plus claire
        # 23 : ID EMPLOYEUR, 32 : ID TRAITEMENT (voir home_ui)
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
        self.load_data()

        # Actualisation automatique quand la base change depuis un autre onglet
        get_data_bus().data_changed.connect(self.load_data)

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
                f"QFrame {{ background-color: {bg}; border-radius: 7px; }}"
            )
            h = QHBoxLayout(frame)
            h.setContentsMargins(14, 7, 14, 7)
            lbl = QLabel(text)
            lbl.setStyleSheet(
                "color: #ffffff; font-family: 'Segoe UI', Helvetica, Arial, sans-serif; "
                "font-size: 11px; font-weight: 800; letter-spacing: 1px; background: transparent;"
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
            "font-size: 10px; font-weight: 700;"
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
        """Ajoute un préfixe symbolique aux boutons d'action."""

        try:
            self.ui.add_btn.setText("＋  Ajouter")
            self.ui.update_btn.setText("↻  Mettre à jour")
            self.ui.clear_btn.setText("✕  Effacer")
            self.ui.delete_btn.setText("🗑  Supprimer")
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
        """Renomme les libellés de la deuxième colonne (traitement DISA)."""

        labels = [
            "DATE DE RECEPTION",
            "DATE DE TRAITEMENT",
            "DATE DE VALIDATION",
            "EFFECTIF DISA",
            "NBRE DE LIGNES TRAITEES",
            "NBRE DE LIGNES VALIDEES",
            "NBRE DE LIGNES REJETEES",
            "NBRE DE LIGNES REJETEES TRAITEES",
            "NBRE TOTAL DE LIGNES VALIDEES APRES TRAITEMENT DES REJETS",
            "DATE DE TRAITEMENT REJET",
            "NBRE RESTANT DE REJET",
            "OBSERVATIONS",
        ]

        layout = self.ui.gridLayout_3
        max_rows = min(layout.rowCount(), len(labels))
        for row in range(max_rows):
            item = layout.itemAtPosition(row, 0)
            if not item:
                continue
            widget = item.widget()
            if isinstance(widget, QLabel):
                widget.setText(labels[row])

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
            from PySide6.QtCore import QDate
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
            from PySide6.QtCore import QDate
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

    def _compute_statut(self, date_validation: str | None) -> str:
        """Calcule le statut métier à partir de la date de validation."""

        return "TRAITÉ" if date_validation else "NON TRAITÉ"

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
                td.traite_par
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
        # 23 colonnes existantes + 10 colonnes supplémentaires + 5 colonnes complémentaires + 1 colonne "STATUT"
        table.setColumnCount(39)

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

            # 3) Colonne de statut (33) + couleur de ligne (2 statuts, très visibles)
            statut_db = (row[24] or "").strip() if len(row) > 24 else ""

            # Sécurise : si le statut n'est pas encore renseigné, on le déduit de la date de validation
            if not statut_db:
                date_validation_val = row[14]
                statut_db = "TRAITÉ" if date_validation_val else "NON TRAITÉ"

            if statut_db.upper() == "TRAITÉ":
                statut = "✔  TRAITÉ"
                bg_color = QColor("#dcfce7")   # vert clair (pastel)
                fg_color = QColor("#166534")   # texte vert foncé
            else:
                statut = "✗  NON TRAITÉ"
                bg_color = QColor("#fee2e2")   # rouge clair (pastel)
                fg_color = QColor("#991b1b")   # texte rouge foncé

            status_item = QTableWidgetItem(statut)
            status_item.setBackground(bg_color)
            status_item.setForeground(fg_color)
            bold_font = QFont("Segoe UI", 10)
            bold_font.setBold(True)
            status_item.setFont(bold_font)
            status_item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(row_index, 33, status_item)

        # Ajuste automatiquement la largeur des colonnes comme dans les autres onglets
        table.resizeColumnsToContents()

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
        layout3 = self.ui.gridLayout_3
        for col in range(11, 23):
            item = table.item(row, col)
            value = item.text() if item else ""
            self._set_text_in_layout(layout3, col - 11, value)

        # Champ supplémentaire : ACTIONS MENÉES (récupéré directement depuis la BD)
        try:
            employeur_id = self._get_current_employeur_id()
            exercice_item = table.item(row, 9)
            exercice_val = exercice_item.text().strip() if exercice_item else ""
            exercice = int(exercice_val) if exercice_val else None
        except ValueError:
            employeur_id = None
            exercice = None

        if employeur_id is not None and exercice is not None:
            try:
                conn = get_connection()
                with conn:
                    cur = conn.cursor()
                    cur.execute(
                        "SELECT actions_menees FROM traitement_disa WHERE employeur_id = ? AND exercice = ?",
                        (employeur_id, exercice),
                    )
                    row_db = cur.fetchone()
                    if row_db:
                        actions_val = row_db[0] or ""
                        if self._actions_menees_row is not None:
                            self._set_text_in_layout(layout3, self._actions_menees_row, actions_val)
            except Exception:
                pass

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

        # Statut persistant dans la BD : basé sur la présence de date_de_validation
        statut = self._compute_statut(date_validation)

        if numero is None or not numero_cnps or not raison_sociale:
            QMessageBox.warning(
                self,
                "Champs manquants",
                "Les champs N°, Numéro CNPS et Raison sociale sont obligatoires.",
            )
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

        # Statut persistant dans la BD : basé sur la présence de date_de_validation
        statut = self._compute_statut(date_validation)

        if numero is None or not numero_cnps or not raison_sociale or exercice is None:
            QMessageBox.warning(
                self,
                "Champs manquants",
                "Les champs N°, Numéro CNPS, Raison sociale et Exercice sont obligatoires pour la mise à jour.",
            )
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
                    traite_par = excluded.traite_par
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
