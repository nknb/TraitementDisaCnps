from typing import List, Optional, Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QDialog,
    QFormLayout,
    QDialogButtonBox,
    QMessageBox,
)

from db.connection import get_connection
from core.events import get_data_bus


class EmployeurFormDialog(QDialog):
    """Dialogue générique pour ajouter / modifier un employeur.

    Le formulaire est construit dynamiquement à partir de la liste des colonnes.
    La colonne "id" (clé primaire) est ignorée dans le formulaire.
    """

    def __init__(
        self,
        parent: QWidget,
        columns: List[str],
        data: Optional[Dict[str, Optional[str]]] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Employeur - Base de données")
        self._columns = [c for c in columns if c != "id"]
        self._editors: Dict[str, QLineEdit] = {}

        layout = QVBoxLayout(self)

        form = QFormLayout()
        for col in self._columns:
            editor = QLineEdit(self)
            if data and col in data and data[col] is not None:
                editor.setText(str(data[col]))
            form.addRow(col, editor)
            self._editors[col] = editor

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_values(self) -> Dict[str, Optional[str]]:
        values: Dict[str, Optional[str]] = {}
        for col, editor in self._editors.items():
            text = editor.text().strip()
            values[col] = text if text != "" else None
        return values


class EmployersDatabaseWidget(QWidget):
    """Onglet "Base de données" pour gérer la table identification_employeurs.

    - Affiche toutes les colonnes de la table
    - Filtres (recherche + combos) sur quelques champs clés
    - CRUD basique (Ajouter, Modifier, Supprimer)
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Dans cette version, l'onglet Base de données n'affiche plus
        # que la vue jointe Employeurs + Traitement DISA.
        self._table_name: str = "join_employeur_traitement"
        self._columns: List[str] = []
        self._id_index: int = -1
        self._page_size: int = 50
        self._current_page: int = 1
        self._total_rows: int = 0

        self._build_ui()
        self._init_table_combo()
        self._load_structure()
        self._load_filters()
        self._refresh_table()

        # Actualisation automatique quand la base change depuis un autre onglet
        get_data_bus().data_changed.connect(self._refresh_table)

    # ------------------------------------------------------------------
    # Construction de l'UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        title = QLabel("Base de données")
        title.setStyleSheet("color: black; font-size: 16px; font-weight: 600;")
        main_layout.addWidget(title)

        # Ligne de sélection de la table
        table_row = QHBoxLayout()
        table_label = QLabel("Table :")
        self.table_combo = QComboBox()
        self.table_combo.currentIndexChanged.connect(self._on_table_changed)
        table_row.addWidget(table_label)
        table_row.addWidget(self.table_combo, 1)
        main_layout.addLayout(table_row)

        # Ligne de filtres
        filters_row = QHBoxLayout()

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "Rechercher (colonnes principales selon la table)"
        )
        self.search_edit.textChanged.connect(self._on_filters_changed)
        filters_row.addWidget(self.search_edit, 2)

        self.localite_combo = QComboBox()
        self.localite_combo.currentIndexChanged.connect(self._on_filters_changed)
        filters_row.addWidget(self.localite_combo, 1)

        self.exercice_combo = QComboBox()
        self.exercice_combo.currentIndexChanged.connect(self._on_filters_changed)
        filters_row.addWidget(self.exercice_combo, 1)

        self.secteur_combo = QComboBox()
        self.secteur_combo.currentIndexChanged.connect(self._on_filters_changed)
        filters_row.addWidget(self.secteur_combo, 1)

        main_layout.addLayout(filters_row)

        # Ligne de filtre par date (principalement pour traitement_disa)
        dates_row = QHBoxLayout()
        dates_label = QLabel("Date réception DISA :")
        self.date_from_edit = QLineEdit()
        self.date_from_edit.setPlaceholderText("Du (YYYY-MM-DD)")
        self.date_to_edit = QLineEdit()
        self.date_to_edit.setPlaceholderText("Au (YYYY-MM-DD)")
        self.date_from_edit.textChanged.connect(self._on_filters_changed)
        self.date_to_edit.textChanged.connect(self._on_filters_changed)
        dates_row.addWidget(dates_label)
        dates_row.addWidget(self.date_from_edit)
        dates_row.addWidget(self.date_to_edit)
        dates_row.addStretch(1)
        main_layout.addLayout(dates_row)

        # Ligne de compteurs de statuts (pour Traitements DISA)
        status_row = QHBoxLayout()
        status_title = QLabel("Dossiers par statut :")
        self.status_non_traite_lbl = QLabel("Non traités : 0")
        self.status_valide_lbl = QLabel("Validés : 0")
        self.status_rejet_lbl = QLabel("Avec rejets : 0")
        status_row.addWidget(status_title)
        status_row.addWidget(self.status_non_traite_lbl)
        status_row.addWidget(self.status_valide_lbl)
        status_row.addWidget(self.status_rejet_lbl)
        status_row.addStretch(1)
        main_layout.addLayout(status_row)

        # Ligne des boutons d'action
        actions_row = QHBoxLayout()

        self.add_btn = QPushButton("Ajouter")
        self.add_btn.setIcon(QIcon(":/icon/icon/product-32.ico"))
        self.add_btn.setStyleSheet(
            "QPushButton { background-color: #2c3e50; color: white; border-radius: 4px; padding: 4px 10px; }"
            "QPushButton:hover { background-color: #34495e; }"
        )
        self.add_btn.clicked.connect(self._on_add_clicked)
        actions_row.addWidget(self.add_btn)

        self.edit_btn = QPushButton("Modifier")
        self.edit_btn.setIcon(QIcon(":/icon/icon/activity-feed-32.ico"))
        self.edit_btn.setStyleSheet(
            "QPushButton { background-color: #16a085; color: white; border-radius: 4px; padding: 4px 10px; }"
            "QPushButton:hover { background-color: #1abc9c; }"
        )
        self.edit_btn.clicked.connect(self._on_edit_clicked)
        actions_row.addWidget(self.edit_btn)

        self.delete_btn = QPushButton("Supprimer")
        self.delete_btn.setIcon(QIcon(":/icon/icon/close-window-64.ico"))
        self.delete_btn.setStyleSheet(
            "QPushButton { background-color: #c0392b; color: white; border-radius: 4px; padding: 4px 10px; }"
            "QPushButton:hover { background-color: #e74c3c; }"
        )
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        actions_row.addWidget(self.delete_btn)

        self.refresh_btn = QPushButton("Rafraîchir")
        self.refresh_btn.setIcon(QIcon(":/icon/icon/dashboard-5-32.ico"))
        self.refresh_btn.setStyleSheet(
            "QPushButton { background-color: #7f8c8d; color: white; border-radius: 4px; padding: 4px 10px; }"
            "QPushButton:hover { background-color: #95a5a6; }"
        )
        self.refresh_btn.clicked.connect(self._refresh_table)
        actions_row.addWidget(self.refresh_btn)

        actions_row.addStretch(1)

        main_layout.addLayout(actions_row)

        # Tableau principal
        self.table = QTableWidget(self)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(self.table.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(self.table.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        main_layout.addWidget(self.table, 1)

        # Pagination + taille de page
        pagination_row = QHBoxLayout()
        self.prev_page_btn = QPushButton("Précédent")
        self.next_page_btn = QPushButton("Suivant")
        self.prev_page_btn.clicked.connect(self._on_prev_page)
        self.next_page_btn.clicked.connect(self._on_next_page)
        size_label = QLabel("Lignes / page :")
        self.page_size_combo = QComboBox()
        self.page_size_combo.addItems(["10", "25", "50", "100"])
        self.page_size_combo.setCurrentText("50")
        self.page_size_combo.currentIndexChanged.connect(self._on_page_size_changed)
        self.page_label = QLabel("Page 1 / 1")
        pagination_row.addWidget(self.prev_page_btn)
        pagination_row.addWidget(self.next_page_btn)
        pagination_row.addWidget(size_label)
        pagination_row.addWidget(self.page_size_combo)
        pagination_row.addStretch(1)
        pagination_row.addWidget(self.page_label)
        main_layout.addLayout(pagination_row)

        # Légende pour les couleurs de statut (traitement_disa)
        legend_row = QHBoxLayout()
        legend_label = QLabel("Légende statuts DISA :")

        def _make_legend_badge(text: str, color: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"background-color: {color}; color: white; border-radius: 4px; padding: 2px 6px;"
            )
            return lbl

        badge_non_traite = _make_legend_badge("NON TRAITÉ", "#c0392b")
        badge_valide = _make_legend_badge("VALIDÉ", "#27ae60")
        badge_rejet = _make_legend_badge("AVEC REJETS", "#e67e22")

        legend_row.addWidget(legend_label)
        legend_row.addWidget(badge_non_traite)
        legend_row.addWidget(badge_valide)
        legend_row.addWidget(badge_rejet)
        legend_row.addStretch(1)
        main_layout.addLayout(legend_row)

    def _init_table_combo(self) -> None:
        """Initialise la liste des tables gérées dans cet onglet."""

        self.table_combo.blockSignals(True)
        self.table_combo.clear()
        # On ne garde que la vue jointe Employeurs + Traitement DISA
        self.table_combo.addItem("Vue Employeurs + DISA", "join_employeur_traitement")
        self.table_combo.setCurrentIndex(0)
        self.table_combo.blockSignals(False)

    def _on_filters_changed(self) -> None:
        """Remet la pagination à la première page et recharge."""

        self._current_page = 1
        self._refresh_table()

    def _on_table_changed(self) -> None:
        table = self.table_combo.currentData()
        if not table:
            return
        self._table_name = str(table)

        self._load_structure()
        self._load_filters()
        self._refresh_table()

    # ------------------------------------------------------------------
    # Chargement de la structure et des filtres
    # ------------------------------------------------------------------

    def _load_structure(self) -> None:
        """Récupère la liste des colonnes de la table sélectionnée."""

        # Réinitialiser l'index d'ID
        self._id_index = -1

        if self._table_name == "join_employeur_traitement":
            # Construction dynamique : toutes les colonnes des deux tables
            try:
                conn = get_connection()
                with conn:
                    cur = conn.cursor()
                    cur.execute("PRAGMA table_info(identification_employeurs)")
                    emp_rows = cur.fetchall()
                    cur.execute("PRAGMA table_info(traitement_disa)")
                    td_rows = cur.fetchall()
            except Exception as exc:  # pragma: no cover - affichage simple
                QMessageBox.critical(
                    self,
                    "Erreur base de données",
                    f"Impossible de lire la structure des tables de la vue jointe :\n{exc}",
                )
                return

            emp_cols = [r[1] for r in emp_rows]
            td_cols = [r[1] for r in td_rows]
            duplicates = set(emp_cols) & set(td_cols)

            columns: list[str] = []

            # Identifiant employeur explicite
            columns.append("id_employeur")
            # Toutes les colonnes employeur (sauf id déjà traité)
            for name in emp_cols:
                if name == "id":
                    continue
                columns.append(name)

            # Identifiant traitement explicite
            columns.append("id_traitement")
            # Toutes les colonnes traitement (sauf id déjà traité)
            for name in td_cols:
                if name == "id":
                    continue
                if name in duplicates:
                    # En cas de doublon (exercice, etc.), on suffixe côté DISA
                    # pour garder une colonne distincte.
                    if name == "statut":
                        alias = "statut"
                    else:
                        alias = f"{name}_disa"
                else:
                    alias = name
                columns.append(alias)

            self._columns = columns
        else:
            try:
                conn = get_connection()
                with conn:
                    cur = conn.cursor()
                    cur.execute(f"PRAGMA table_info({self._table_name})")
                    rows = cur.fetchall()
            except Exception as exc:  # pragma: no cover - affichage simple
                QMessageBox.critical(
                    self,
                    "Erreur base de données",
                    f"Impossible de lire la structure de la table {self._table_name} :\n{exc}",
                )
                return

            self._columns = [r[1] for r in rows]  # r[1] = name

        # Colonnes visuelles : pour traitement_disa et la vue jointe on ajoute une colonne "État" dédiée
        if self._table_name in ("traitement_disa", "join_employeur_traitement"):
            headers = list(self._columns) + ["État"]
            self.table.setColumnCount(len(headers))
            self.table.setHorizontalHeaderLabels(headers)
        else:
            self.table.setColumnCount(len(self._columns))
            self.table.setHorizontalHeaderLabels(self._columns)

        if "id" in self._columns:
            self._id_index = self._columns.index("id")
            # On cache l'ID pour une vue plus lisible mais on le garde pour le CRUD
            self.table.setColumnHidden(self._id_index, True)

    def _load_filters(self) -> None:
        """Charge les valeurs possibles pour les combos de filtre."""

        # Valeurs par défaut
        self.localite_combo.blockSignals(True)
        self.exercice_combo.blockSignals(True)
        self.secteur_combo.blockSignals(True)

        self.localite_combo.clear()
        self.exercice_combo.clear()
        self.secteur_combo.clear()

        # Si on est sur la table employeurs, on chargerait les filtres avancés
        # (cas non utilisé dans la version actuelle qui ne garde que la vue jointe)
        if self._table_name == "identification_employeurs":
            self.localite_combo.setEnabled(True)
            self.exercice_combo.setEnabled(True)
            self.secteur_combo.setEnabled(True)

            self.localite_combo.addItem("Toutes les localités", None)
            self.exercice_combo.addItem("Tous les exercices", None)
            self.secteur_combo.addItem("Tous les secteurs", None)

            try:
                conn = get_connection()
                with conn:
                    cur = conn.cursor()

                    # Localités
                    cur.execute(
                        "SELECT DISTINCT localites FROM identification_employeurs WHERE localites IS NOT NULL ORDER BY localites"
                    )
                    for (val,) in cur.fetchall():
                        if val is None or str(val).strip() == "":
                            continue
                        self.localite_combo.addItem(str(val), str(val))

                    # Exercices
                    cur.execute(
                        "SELECT DISTINCT exercice FROM identification_employeurs WHERE exercice IS NOT NULL ORDER BY exercice"
                    )
                    for (val,) in cur.fetchall():
                        if val is None or str(val).strip() == "":
                            continue
                        self.exercice_combo.addItem(str(val), str(val))

                    # Secteurs
                    cur.execute(
                        "SELECT DISTINCT secteur_activite FROM identification_employeurs WHERE secteur_activite IS NOT NULL ORDER BY secteur_activite"
                    )
                    for (val,) in cur.fetchall():
                        if val is None or str(val).strip() == "":
                            continue
                        self.secteur_combo.addItem(str(val), str(val))
            finally:
                self.localite_combo.blockSignals(False)
                self.exercice_combo.blockSignals(False)
                self.secteur_combo.blockSignals(False)
        else:
            # Pour traitement_disa et la vue jointe, on propose des filtres spécifiques
            # (localité via jointure, exercice, statut)
            self.localite_combo.setEnabled(True)
            self.exercice_combo.setEnabled(True)
            self.secteur_combo.setEnabled(True)

            self.localite_combo.addItem("Toutes les localités", None)
            self.exercice_combo.addItem("Tous les exercices", None)
            self.secteur_combo.addItem("Tous les statuts", None)

            try:
                conn = get_connection()
                with conn:
                    cur = conn.cursor()

                    # Localités issues de la jointure employeur
                    cur.execute(
                        """
                        SELECT DISTINCT COALESCE(ie.localites, 'NON RENSEIGNÉE')
                        FROM traitement_disa td
                        JOIN identification_employeurs ie ON ie.id = td.employeur_id
                        WHERE ie.localites IS NOT NULL
                        ORDER BY ie.localites
                        """
                    )
                    for (val,) in cur.fetchall():
                        if val is None or str(val).strip() == "":
                            continue
                        self.localite_combo.addItem(str(val), str(val))

                    # Exercices saisies dans traitement_disa
                    cur.execute(
                        "SELECT DISTINCT exercice FROM traitement_disa WHERE exercice IS NOT NULL ORDER BY exercice"
                    )
                    for (val,) in cur.fetchall():
                        if val is None or str(val).strip() == "":
                            continue
                        self.exercice_combo.addItem(str(val), str(val))

                    # Statuts
                    cur.execute(
                        "SELECT DISTINCT statut FROM traitement_disa WHERE statut IS NOT NULL ORDER BY statut"
                    )
                    for (val,) in cur.fetchall():
                        if val is None or str(val).strip() == "":
                            continue
                        self.secteur_combo.addItem(str(val), str(val))
            finally:
                self.localite_combo.blockSignals(False)
                self.exercice_combo.blockSignals(False)
                self.secteur_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # Rafraîchissement du tableau
    # ------------------------------------------------------------------

    def _build_filters_sql(self) -> tuple[str, list]:
        """Construit la clause WHERE et les paramètres en fonction des filtres."""

        clauses: list[str] = []
        params: list = []

        # Texte de recherche global
        search = self.search_edit.text().strip()
        if search:
            like = f"%{search}%"
            if self._table_name == "identification_employeurs":
                clauses.append(
                    "(numero LIKE ? OR numero_cnps LIKE ? OR raison_sociale LIKE ? OR localites LIKE ?)"
                )
                params.extend([like, like, like, like])
            elif self._table_name == "traitement_disa":
                clauses.append(
                    "(exercice LIKE ? OR statut LIKE ? OR observations LIKE ?)"
                )
                params.extend([like, like, like])
            elif self._table_name == "join_employeur_traitement":
                clauses.append(
                    "(ie.numero LIKE ? OR ie.numero_cnps LIKE ? OR ie.raison_sociale LIKE ? OR ie.localites LIKE ? OR td.exercice LIKE ? OR td.statut LIKE ? OR td.observations LIKE ?)"
                )
                params.extend([like, like, like, like, like, like, like])

        # Filtres avancés pour la table employeurs
        if self._table_name == "identification_employeurs":
            # Localité
            loc_val = self.localite_combo.currentData()
            if loc_val is not None:
                clauses.append("localites = ?")
                params.append(loc_val)

            # Exercice
            ex_val = self.exercice_combo.currentData()
            if ex_val is not None:
                clauses.append("exercice = ?")
                params.append(ex_val)

            # Secteur
            sec_val = self.secteur_combo.currentData()
            if sec_val is not None:
                clauses.append("secteur_activite = ?")
                params.append(sec_val)

        # Filtres avancés pour la table traitement_disa
        elif self._table_name == "traitement_disa":
            # Localité (via jointure sur les employeurs)
            loc_val = self.localite_combo.currentData()
            if loc_val is not None:
                clauses.append(
                    "employeur_id IN (SELECT id FROM identification_employeurs WHERE localites = ?)"
                )
                params.append(loc_val)

            # Exercice DISA
            ex_val = self.exercice_combo.currentData()
            if ex_val is not None:
                clauses.append("exercice = ?")
                params.append(ex_val)

            # Statut DISA
            statut_val = self.secteur_combo.currentData()
            if statut_val is not None:
                clauses.append("statut = ?")
                params.append(statut_val)

            # Filtre de dates sur date_de_reception
            date_from = self.date_from_edit.text().strip()
            date_to = self.date_to_edit.text().strip()
            if date_from and date_to:
                clauses.append("date_de_reception BETWEEN ? AND ?")
                params.extend([date_from, date_to])
            elif date_from:
                clauses.append("date_de_reception >= ?")
                params.append(date_from)
            elif date_to:
                clauses.append("date_de_reception <= ?")
                params.append(date_to)

        # Filtres avancés pour la vue join_employeur_traitement
        elif self._table_name == "join_employeur_traitement":
            # Localité (via employeurs)
            loc_val = self.localite_combo.currentData()
            if loc_val is not None:
                clauses.append("ie.localites = ?")
                params.append(loc_val)

            # Exercice DISA (côté traitement)
            ex_val = self.exercice_combo.currentData()
            if ex_val is not None:
                clauses.append("td.exercice = ?")
                params.append(ex_val)

            # Statut DISA
            statut_val = self.secteur_combo.currentData()
            if statut_val is not None:
                clauses.append("td.statut = ?")
                params.append(statut_val)

            # Filtre de dates sur date_de_reception (côté traitement)
            date_from = self.date_from_edit.text().strip()
            date_to = self.date_to_edit.text().strip()
            if date_from and date_to:
                clauses.append("td.date_de_reception BETWEEN ? AND ?")
                params.extend([date_from, date_to])
            elif date_from:
                clauses.append("td.date_de_reception >= ?")
                params.append(date_from)
            elif date_to:
                clauses.append("td.date_de_reception <= ?")
                params.append(date_to)

        if not clauses:
            return "", []

        where = " WHERE " + " AND ".join(clauses)
        return where, params

    def _refresh_table(self) -> None:
        """Recharge les données de la table courante selon les filtres + pagination."""

        if not self._columns:
            return

        where, params = self._build_filters_sql()

        # FROM / JOIN selon le mode
        if self._table_name == "join_employeur_traitement":
            base_from = (
                " FROM identification_employeurs ie "
                "LEFT JOIN traitement_disa td ON td.employeur_id = ie.id"
            )
        else:
            base_from = f" FROM {self._table_name}"

        # Nombre total de lignes pour la pagination
        count_sql = "SELECT COUNT(*)" + base_from + where

        try:
            conn = get_connection()
            with conn:
                cur = conn.cursor()
                # Nombre total (avec les mêmes filtres)
                cur.execute(count_sql, params)
                (self._total_rows,) = cur.fetchone() or (0,)

                # Compteurs par statut pour traitement_disa et la vue jointe
                if self._table_name in ("traitement_disa", "join_employeur_traitement"):
                    if self._table_name == "traitement_disa":
                        group_sql = f"SELECT statut, COUNT(*){base_from}{where} GROUP BY statut"
                    else:
                        # Vue jointe : on compte les statuts côté traitement
                        # et on remplace les valeurs NULL par "NON TRAITÉ" pour
                        # les employeurs sans fichier DISA.
                        group_sql = (
                            "SELECT COALESCE(td.statut, 'NON TRAITÉ') AS statut, COUNT(*)"
                            + base_from
                            + where
                            + " GROUP BY COALESCE(td.statut, 'NON TRAITÉ')"
                        )

                    cur.execute(group_sql, params)
                    non_traite = 0
                    valide = 0
                    rejet = 0
                    for statut, nb in cur.fetchall():
                        txt = str(statut).upper()
                        nb_i = int(nb or 0)
                        if "NON" in txt and "TRAIT" in txt:
                            non_traite += nb_i
                        elif "REJET" in txt:
                            rejet += nb_i
                        else:
                            # Tout autre statut (TRAITÉ, VALIDÉ, etc.) est compté comme "Validé/Traité"
                            valide += nb_i
                    self.status_non_traite_lbl.setText(f"Non traités : {non_traite}")
                    self.status_valide_lbl.setText(f"Validés : {valide}")
                    self.status_rejet_lbl.setText(f"Avec rejets : {rejet}")
                else:
                    # Pour les autres tables, on remet à zéro
                    self.status_non_traite_lbl.setText("Non traités : 0")
                    self.status_valide_lbl.setText("Validés : 0")
                    self.status_rejet_lbl.setText("Avec rejets : 0")

                total_pages = max(1, (self._total_rows + self._page_size - 1) // self._page_size)
                if self._current_page > total_pages:
                    self._current_page = total_pages

                offset = (self._current_page - 1) * self._page_size

                if self._table_name == "join_employeur_traitement":
                    # Sélection dynamique de toutes les colonnes employeur + DISA,
                    # en cohérence avec _load_structure.

                    # On relit la structure des deux tables pour construire
                    # les alias de colonnes dans le même ordre.
                    cur.execute("PRAGMA table_info(identification_employeurs)")
                    emp_rows = cur.fetchall()
                    cur.execute("PRAGMA table_info(traitement_disa)")
                    td_rows = cur.fetchall()
                    emp_cols = [r[1] for r in emp_rows]
                    td_cols = [r[1] for r in td_rows]
                    duplicates = set(emp_cols) & set(td_cols)

                    select_parts: list[str] = []

                    # id_employeur
                    select_parts.append("ie.id AS id_employeur")
                    # Colonnes employeur (sauf id déjà utilisé)
                    for name in emp_cols:
                        if name == "id":
                            continue
                        select_parts.append(f"ie.{name} AS {name}")

                    # id_traitement
                    select_parts.append("td.id AS id_traitement")
                    # Colonnes traitement (sauf id déjà utilisé)
                    for name in td_cols:
                        if name == "id":
                            continue
                        if name in duplicates:
                            if name == "statut":
                                alias = "statut"
                            else:
                                alias = f"{name}_disa"
                        else:
                            alias = name

                        if name == "statut":
                            expr = "COALESCE(td.statut, 'NON TRAITÉ')"
                        else:
                            expr = f"td.{name}"

                        select_parts.append(f"{expr} AS {alias}")

                    sql = (
                        "SELECT "
                        + ", ".join(select_parts)
                        + base_from
                        + where
                        + " ORDER BY ie.id DESC LIMIT ? OFFSET ?"
                    )
                else:
                    sql = (
                        "SELECT "
                        + ", ".join(self._columns)
                        + base_from
                        + where
                        + " ORDER BY id DESC LIMIT ? OFFSET ?"
                    )
                cur.execute(sql, params + [self._page_size, offset])
                rows = cur.fetchall()
        except Exception as exc:  # pragma: no cover - affichage simple
            QMessageBox.critical(
                self,
                "Erreur base de données",
                f"Impossible de charger les enregistrements :\n{exc}",
            )
            return

        self.table.setRowCount(len(rows))

        statut_col_index = -1
        if self._table_name in ("traitement_disa", "join_employeur_traitement") and "statut" in self._columns:
            statut_col_index = self._columns.index("statut")

        for row_index, row in enumerate(rows):
            # Prépare les infos de statut (texte, couleurs, icône) pour traitement_disa
            row_statut = None
            bg_color = None
            fg_color = QColor("white")
            etat_text = ""
            etat_icon: QIcon | None = None

            if self._table_name in ("traitement_disa", "join_employeur_traitement") and statut_col_index != -1:
                try:
                    row_statut = str(row[statut_col_index] or "")
                except Exception:
                    row_statut = ""

                upper = row_statut.upper() if row_statut is not None else ""
                if "NON" in upper and "TRAIT" in upper:
                    bg_color = QColor("#c0392b")  # rouge
                    etat_text = "Non traité"
                    etat_icon = QIcon(":/icon/icon/close-window-64.ico")
                elif "REJET" in upper:
                    bg_color = QColor("#e67e22")  # orange
                    etat_text = "Avec rejets"
                    etat_icon = QIcon(":/icon/icon/activity-feed-32.ico")
                elif "VALID" in upper or "TRAIT" in upper:
                    # Statuts TRAITÉ / VALIDÉ : on les regroupe visuellement
                    bg_color = QColor("#27ae60")  # vert
                    etat_text = "Validé / Traité"
                    etat_icon = QIcon(":/icon/icon/dashboard-5-32.ico")
                else:
                    etat_text = row_statut or ""

            # Colonnes issues de la base
            for col_index, value in enumerate(row):
                text = "" if value is None else str(value)
                item = QTableWidgetItem(text)
                # Alignement à gauche par défaut, mais on force l'ID à être centré
                if self._id_index != -1 and col_index == self._id_index:
                    item.setTextAlignment(Qt.AlignCenter)

                # Coloration conditionnelle pour traitement_disa en fonction du statut
                if self._table_name in ("traitement_disa", "join_employeur_traitement") and bg_color is not None:
                    item.setBackground(bg_color)
                    item.setForeground(fg_color)

                self.table.setItem(row_index, col_index, item)

            # Colonne visuelle "État" pour traitement_disa et la vue jointe
            if self._table_name in ("traitement_disa", "join_employeur_traitement"):
                etat_item = QTableWidgetItem(etat_text)
                if etat_icon is not None:
                    etat_item.setIcon(etat_icon)
                if bg_color is not None:
                    etat_item.setBackground(bg_color)
                    etat_item.setForeground(fg_color)
                etat_col = len(self._columns)
                self.table.setItem(row_index, etat_col, etat_item)

        self.table.resizeColumnsToContents()

        # Mise à jour de l'affichage de pagination
        total_pages = max(1, (self._total_rows + self._page_size - 1) // self._page_size)
        self.page_label.setText(
            f"Page {self._current_page} / {total_pages} (total : {self._total_rows})"
        )
        self.prev_page_btn.setEnabled(self._current_page > 1)
        self.next_page_btn.setEnabled(self._current_page < total_pages)

    def _on_prev_page(self) -> None:
        if self._current_page > 1:
            self._current_page -= 1
            self._refresh_table()

    def _on_next_page(self) -> None:
        total_pages = max(1, (self._total_rows + self._page_size - 1) // self._page_size)
        if self._current_page < total_pages:
            self._current_page += 1
            self._refresh_table()

    def _on_page_size_changed(self) -> None:
        """Change la taille de page (10/25/50/100) et repart de la page 1."""

        try:
            new_size = int(self.page_size_combo.currentText())
        except ValueError:
            return
        if new_size <= 0:
            return
        self._page_size = new_size
        self._current_page = 1
        self._refresh_table()

    # ------------------------------------------------------------------
    # Actions CRUD
    # ------------------------------------------------------------------

    def _get_selected_employeur_id(self) -> Optional[int]:
        """Renvoie l'id employeur de la ligne sélectionnée dans la vue jointe."""

        row = self.table.currentRow()
        if row < 0:
            return None
        if "id_employeur" not in self._columns:
            return None
        col_index = self._columns.index("id_employeur")
        item = self.table.item(row, col_index)
        if item is None:
            return None
        try:
            return int(item.text())
        except ValueError:
            return None

    def _get_selected_id(self) -> Optional[int]:
        row = self.table.currentRow()
        if row < 0 or self._id_index == -1:
            return None
        item = self.table.item(row, self._id_index)
        if item is None:
            return None
        try:
            return int(item.text())
        except ValueError:
            return None

    def _collect_row_data(self, row: int) -> Dict[str, Optional[str]]:
        data: Dict[str, Optional[str]] = {}
        for col_index, col_name in enumerate(self._columns):
            item = self.table.item(row, col_index)
            if item is None:
                data[col_name] = None
            else:
                text = item.text().strip()
                data[col_name] = text if text != "" else None
        return data

    def _on_add_clicked(self) -> None:
        if not self._columns:
            return

        # En vue jointe, on ajoute un employeur dans la table
        # identification_employeurs, pas dans une "table" de jointure.
        if self._table_name == "join_employeur_traitement":
            try:
                conn = get_connection()
                with conn:
                    cur = conn.cursor()
                    cur.execute("PRAGMA table_info(identification_employeurs)")
                    rows = cur.fetchall()
            except Exception as exc:  # pragma: no cover
                QMessageBox.critical(
                    self,
                    "Erreur base de données",
                    f"Impossible de lire la structure de identification_employeurs :\n{exc}",
                )
                return

            emp_cols = [r[1] for r in rows if r[1] != "id"]

            dialog = EmployeurFormDialog(self, emp_cols)
            if dialog.exec() == QDialog.Accepted:
                values = dialog.get_values()
                cols = list(values.keys())
                params = [values[c] for c in cols]

                placeholders = ", ".join(["?" for _ in cols])
                sql = (
                    "INSERT INTO identification_employeurs ("
                    + ", ".join(cols)
                    + ") VALUES ("
                    + placeholders
                    + ")"
                )
                try:
                    conn = get_connection()
                    with conn:
                        cur = conn.cursor()
                        cur.execute(sql, params)
                except Exception as exc:  # pragma: no cover
                    QMessageBox.critical(
                        self,
                        "Erreur base de données",
                        f"Impossible d'ajouter l'employeur :\n{exc}",
                    )
                    return

                self._load_filters()
                self._refresh_table()
                # Notifie les autres onglets qu'une modification a eu lieu
                get_data_bus().data_changed.emit()
                return

        # Comportement générique (non utilisé dans la configuration actuelle)
        dialog = EmployeurFormDialog(self, self._columns)
        if dialog.exec() == QDialog.Accepted:
            values = dialog.get_values()
            cols = list(values.keys())
            params = [values[c] for c in cols]

            placeholders = ", ".join(["?" for _ in cols])
            sql = (
                f"INSERT INTO {self._table_name} (" + ", ".join(cols) + ") VALUES (" + placeholders + ")"
            )
            try:
                conn = get_connection()
                with conn:
                    cur = conn.cursor()
                    cur.execute(sql, params)
            except Exception as exc:  # pragma: no cover
                QMessageBox.critical(
                    self,
                    "Erreur base de données",
                    f"Impossible d'ajouter l'enregistrement :\n{exc}",
                )
                return

            self._load_filters()
            self._refresh_table()

    def _on_edit_clicked(self) -> None:
        if not self._columns:
            return

        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Modification", "Sélectionnez d'abord une ligne à modifier.")
            return

        # En vue jointe, on modifie l'employeur dans identification_employeurs.
        if self._table_name == "join_employeur_traitement":
            emp_id = self._get_selected_employeur_id()
            if emp_id is None:
                QMessageBox.warning(
                    self,
                    "Modification",
                    "Impossible de récupérer l'identifiant de l'employeur.",
                )
                return

            try:
                conn = get_connection()
                with conn:
                    cur = conn.cursor()
                    cur.execute("PRAGMA table_info(identification_employeurs)")
                    rows = cur.fetchall()
                    emp_cols = [r[1] for r in rows if r[1] != "id"]

                    # Charger les valeurs actuelles de l'employeur
                    cur.execute(
                        "SELECT " + ", ".join(emp_cols) + " FROM identification_employeurs WHERE id = ?",
                        (emp_id,),
                    )
                    db_row = cur.fetchone()
            except Exception as exc:  # pragma: no cover
                QMessageBox.critical(
                    self,
                    "Erreur base de données",
                    f"Impossible de lire l'employeur :\n{exc}",
                )
                return

            if db_row is None:
                QMessageBox.warning(
                    self,
                    "Modification",
                    "L'employeur sélectionné n'existe plus dans la base.",
                )
                return

            current_data: Dict[str, Optional[str]] = {}
            for col_name, value in zip(emp_cols, db_row):
                current_data[col_name] = None if value is None else str(value)

            dialog = EmployeurFormDialog(self, emp_cols, current_data)
            if dialog.exec() == QDialog.Accepted:
                values = dialog.get_values()
                set_clauses = []
                params = []
                for col, val in values.items():
                    set_clauses.append(f"{col} = ?")
                    params.append(val)
                params.append(emp_id)

                sql = (
                    "UPDATE identification_employeurs SET "
                    + ", ".join(set_clauses)
                    + " WHERE id = ?"
                )
                try:
                    conn = get_connection()
                    with conn:
                        cur = conn.cursor()
                        cur.execute(sql, params)
                except Exception as exc:  # pragma: no cover
                    QMessageBox.critical(
                        self,
                        "Erreur base de données",
                        f"Impossible de modifier l'employeur :\n{exc}",
                    )
                    return

                self._load_filters()
                self._refresh_table()
                # Notifie les autres onglets qu'une modification a eu lieu
                get_data_bus().data_changed.emit()
            return

        # Comportement générique (non utilisé dans la configuration actuelle)
        emp_id = self._get_selected_id()
        if emp_id is None:
            QMessageBox.warning(self, "Modification", "Impossible de récupérer l'identifiant de la ligne.")
            return

        current_data = self._collect_row_data(row)
        dialog = EmployeurFormDialog(self, self._columns, current_data)
        if dialog.exec() == QDialog.Accepted:
            values = dialog.get_values()
            set_clauses = []
            params = []
            for col, val in values.items():
                set_clauses.append(f"{col} = ?")
                params.append(val)
            params.append(emp_id)

            sql = f"UPDATE {self._table_name} SET " + ", ".join(set_clauses) + " WHERE id = ?"
            try:
                conn = get_connection()
                with conn:
                    cur = conn.cursor()
                    cur.execute(sql, params)
            except Exception as exc:  # pragma: no cover
                QMessageBox.critical(
                    self,
                    "Erreur base de données",
                    f"Impossible de modifier l'enregistrement :\n{exc}",
                )
                return

            self._load_filters()
            self._refresh_table()

    def _on_delete_clicked(self) -> None:
        """Supprime un enregistrement (employeur ou ligne générique)."""

        if not self._columns:
            return

        # En vue jointe, on supprime l'employeur dans identification_employeurs.
        if self._table_name == "join_employeur_traitement":
            emp_id = self._get_selected_employeur_id()
            if emp_id is None:
                QMessageBox.information(
                    self,
                    "Suppression",
                    "Sélectionnez d'abord une ligne à supprimer.",
                )
                return

            reply = QMessageBox.question(
                self,
                "Confirmer la suppression",
                "Voulez-vous vraiment supprimer cet employeur ?\n(Cette action est irréversible)",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

            try:
                conn = get_connection()
                with conn:
                    cur = conn.cursor()
                    cur.execute(
                        "DELETE FROM identification_employeurs WHERE id = ?",
                        (emp_id,),
                    )
            except Exception as exc:  # pragma: no cover
                QMessageBox.critical(
                    self,
                    "Erreur base de données",
                    f"Impossible de supprimer l'employeur :\n{exc}",
                )
                return

            self._load_filters()
            self._refresh_table()
            # Notifie les autres onglets qu'une modification a eu lieu
            get_data_bus().data_changed.emit()
            return

        # Comportement générique (non utilisé dans la configuration actuelle)
        emp_id = self._get_selected_id()
        if emp_id is None:
            QMessageBox.information(
                self,
                "Suppression",
                "Sélectionnez d'abord une ligne à supprimer.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Confirmer la suppression",
            "Voulez-vous vraiment supprimer cet employeur ?\n(Cette action est irréversible)",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        try:
            conn = get_connection()
            with conn:
                cur = conn.cursor()
                cur.execute(f"DELETE FROM {self._table_name} WHERE id = ?", (emp_id,))
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(
                self,
                "Erreur base de données",
                f"Impossible de supprimer l'enregistrement :\n{exc}",
            )
            return

        self._load_filters()
        self._refresh_table()
        # Notifie les autres onglets qu'une modification a eu lieu
        get_data_bus().data_changed.emit()
