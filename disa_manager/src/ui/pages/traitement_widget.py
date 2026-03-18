from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
	QWidget,
	QVBoxLayout,
	QHBoxLayout,
	QLabel,
	QPushButton,
	QLineEdit,
	QComboBox,
	QTableWidget,
	QTableWidgetItem,
	QFileDialog,
	QMessageBox,
)

from db.connection import get_connection
from services.excel_importer import insert_rows
from core.events import get_data_bus


class TraitementWidget(QWidget):
	"""Onglet Traitement : import Excel -> SQLite avec mapping de colonnes.

	Fonctionnalités :
	- Choix d'un fichier Excel
	- Détection des colonnes non vides
	- Récupération des colonnes de la table SQLite cible
	- Interface de mapping (combo box) DB <-> Excel
	- Import des données en base avec rapport (nb lignes / erreurs)
	"""

	def __init__(self, parent: QWidget | None = None) -> None:
		super().__init__(parent)

		self._excel_path: Path | None = None
		self._excel_columns: list[str] = []
		self._db_columns: list[str] = []
		self._df = None  # pandas.DataFrame, chargé à la demande

		main_layout = QVBoxLayout(self)
		main_layout.setContentsMargins(12, 12, 12, 12)
		main_layout.setSpacing(10)

		title = QLabel("Import / Traitement DISA - Fichier Excel")
		title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
		title.setStyleSheet("color: black; font-size: 16px; font-weight: 600;")
		main_layout.addWidget(title)

		# Ligne : champ chemin fichier + bouton parcourir
		file_row = QHBoxLayout()
		self.file_edit = QLineEdit()
		self.file_edit.setReadOnly(True)
		self.file_edit.setPlaceholderText("Choisir un fichier Excel (.xlsx, .xls)...")
		browse_btn = QPushButton("Parcourir...")
		browse_btn.clicked.connect(self._on_browse_clicked)

		file_row.addWidget(self.file_edit)
		file_row.addWidget(browse_btn)
		main_layout.addLayout(file_row)

		# Ligne : choix de la table cible
		table_row = QHBoxLayout()
		table_label = QLabel("Table cible dans la base :")
		table_label.setStyleSheet("color: black;")
		self.table_combo = QComboBox()
		table_row.addWidget(table_label)
		table_row.addWidget(self.table_combo, 1)
		main_layout.addLayout(table_row)

		# Boutons d'action
		actions_row = QHBoxLayout()
		self.analyze_btn = QPushButton("Préparer le mapping des colonnes")
		self.analyze_btn.clicked.connect(self._on_prepare_mapping)
		self.import_btn = QPushButton("Importer les données")
		self.import_btn.clicked.connect(self._on_import_clicked)
		self.import_btn.setEnabled(False)
		actions_row.addWidget(self.analyze_btn)
		actions_row.addWidget(self.import_btn)
		main_layout.addLayout(actions_row)

		# Tableau de mapping : colonnes BD / colonnes Excel (combo box)
		self.mapping_table = QTableWidget(0, 2)
		self.mapping_table.setHorizontalHeaderLabels([
			"Colonne BD",
			"Colonne Excel (fichier)",
		])
		self.mapping_table.horizontalHeader().setStretchLastSection(True)
		main_layout.addWidget(self.mapping_table, 1)

		self._load_db_tables()

	# ------------------------------------------------------------------
	# Chargement des tables de la base
	# ------------------------------------------------------------------

	def _load_db_tables(self) -> None:
		try:
			conn = get_connection()
			with conn:
				cur = conn.cursor()
				cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
				tables = [row[0] for row in cur.fetchall()]
		except Exception:
			tables = []

		self.table_combo.clear()
		for name in tables:
			# On ignore les tables internes SQLite
			if name.startswith("sqlite_"):
				continue
			self.table_combo.addItem(name)

	# ------------------------------------------------------------------
	# Gestion du fichier Excel
	# ------------------------------------------------------------------

	def _on_browse_clicked(self) -> None:
		file_path, _ = QFileDialog.getOpenFileName(
			self,
			"Sélectionner un fichier Excel",
			"",
			"Fichiers Excel (*.xlsx *.xls)",
		)
		if not file_path:
			return

		self._excel_path = Path(file_path)
		self.file_edit.setText(str(self._excel_path))
		self._df = None
		self._excel_columns = []
		self.mapping_table.setRowCount(0)
		self.import_btn.setEnabled(False)

	# ------------------------------------------------------------------
	# Lecture Excel et détection des colonnes non vides
	# ------------------------------------------------------------------

	def _load_excel_dataframe(self) -> bool:
		"""Charge le fichier Excel complet dans un DataFrame pandas.

		Retourne True en cas de succès, False sinon.
		"""

		if not self._excel_path:
			QMessageBox.warning(self, "Fichier manquant", "Veuillez d'abord choisir un fichier Excel.")
			return False

		try:
			import pandas as pd
		except ImportError:
			QMessageBox.critical(
				self,
				"Module manquant",
				"Le module 'pandas' est requis pour lire les fichiers Excel.\n"
				"Installez-le avec : pip install pandas openpyxl",
			)
			return False

		try:
			self._df = pd.read_excel(self._excel_path)
		except Exception as exc:
			QMessageBox.critical(
				self,
				"Erreur de lecture Excel",
				f"Impossible de lire le fichier Excel : {exc}",
			)
			self._df = None
			return False

		# Détection des colonnes non vides : au moins une valeur non nulle / non vide
		non_empty_cols: list[str] = []
		for col in self._df.columns:
			serie = self._df[col]
			# On supprime les NaN puis on retire les chaînes vides ou espaces
			non_na = serie.dropna()
			has_value = False
			if not non_na.empty:
				if non_na.dtype == object:
					# Pour les chaînes, on teste qu'il reste au moins un texte non vide
					trimmed = non_na.astype(str).str.strip()
					has_value = (trimmed != "").any()
				else:
					# Pour les numériques/dates, la présence d'au moins une valeur suffit
					has_value = True
			if has_value:
				non_empty_cols.append(str(col))

		if not non_empty_cols:
			QMessageBox.warning(
				self,
				"Colonnes vides",
				"Aucune colonne non vide n'a été trouvée dans le fichier Excel.",
			)
			return False

		self._excel_columns = non_empty_cols
		return True

	def _read_db_columns(self, table_name: str) -> list[str]:
		try:
			conn = get_connection()
			with conn:
				cur = conn.cursor()
				cur.execute(f"PRAGMA table_info({table_name})")
				return [str(row[1]) for row in cur.fetchall()]
		except Exception:
			return []

	# ------------------------------------------------------------------
	# Préparation du mapping colonnes BD / Excel
	# ------------------------------------------------------------------

	def _on_prepare_mapping(self) -> None:
		if not self._load_excel_dataframe():
			return

		table_name = self.table_combo.currentText().strip()
		if not table_name:
			QMessageBox.warning(self, "Table manquante", "Veuillez sélectionner une table dans la base.")
			return

		db_cols = self._read_db_columns(table_name)
		if not db_cols:
			QMessageBox.warning(
				self,
				"Colonnes BD introuvables",
				"Impossible de récupérer les colonnes de la table SQLite.",
			)
			return

		self._db_columns = db_cols

		# Construction du tableau de mapping : 1 ligne par colonne BD
		self.mapping_table.setRowCount(len(db_cols))
		for row_idx, db_col in enumerate(db_cols):
			# Colonne BD (non éditable)
			item = QTableWidgetItem(db_col)
			item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
			item.setForeground(QColor("black"))
			self.mapping_table.setItem(row_idx, 0, item)

			# Colonne Excel : combo box
			combo = QComboBox()
			combo.addItem("(Ignorer)")
			for col in self._excel_columns:
				combo.addItem(col)

			# Pré-sélection : si un nom de colonne Excel matche (insensible à la casse)
			lower_db = db_col.lower()
			matched_index = 0
			for idx, col in enumerate(self._excel_columns, start=1):
				if col.lower() == lower_db:
					matched_index = idx
					break
			combo.setCurrentIndex(matched_index)

			self.mapping_table.setCellWidget(row_idx, 1, combo)

		self.import_btn.setEnabled(True)

		QMessageBox.information(
			self,
			"Mapping prêt",
			"Les colonnes de la base et du fichier Excel sont chargées.\n"
			"Utilisez les menus déroulants pour lier les colonnes, puis cliquez sur\n"
			"'Importer les données'.",
		)

	# ------------------------------------------------------------------
	# Import des données vers SQLite
	# ------------------------------------------------------------------

	def _on_import_clicked(self) -> None:
		if self._df is None:
			QMessageBox.warning(
				self,
				"Données Excel manquantes",
				"Veuillez d'abord préparer le mapping (lecture du fichier Excel).",
			)
			return

		table_name = self.table_combo.currentText().strip()
		if not table_name:
			QMessageBox.warning(self, "Table manquante", "Veuillez sélectionner une table dans la base.")
			return

		# Récupération du mapping DB -> Excel à partir du tableau
		mapped_db_cols: list[str] = []
		mapped_excel_cols: list[str] = []
		for row in range(self.mapping_table.rowCount()):
			db_item = self.mapping_table.item(row, 0)
			combo = self.mapping_table.cellWidget(row, 1)
			if db_item is None or not isinstance(combo, QComboBox):
				continue
			db_col = db_item.text()
			excel_col = combo.currentText().strip()
			if not excel_col or excel_col == "(Ignorer)":
				continue
			mapped_db_cols.append(db_col)
			mapped_excel_cols.append(excel_col)

		if not mapped_db_cols:
			QMessageBox.warning(
				self,
				"Mapping incomplet",
				"Aucune colonne n'a été liée.\n"
				"Veuillez choisir au moins une correspondance entre BD et Excel.",
			)
			return

		# Préparation des lignes à insérer : liste de séquences de valeurs
		try:
			import pandas as pd  # pour isna
		except ImportError:  # ne devrait pas arriver si _load_excel_dataframe a réussi
			QMessageBox.critical(
				self,
				"Module manquant",
				"Le module 'pandas' est requis pour l'import des données.",
			)
			return

		# Cas particulier simple : table identification_employeurs
		# -> on peut générer automatiquement "numero" si besoin
		db_cols_for_insert = list(mapped_db_cols)
		add_generated_numero = False
		numero_index = -1

		if table_name == "identification_employeurs":
			if "numero" in mapped_db_cols:
				numero_index = mapped_db_cols.index("numero")
			else:
				# On ajoutera une colonne numero générée
				add_generated_numero = True
				db_cols_for_insert.insert(0, "numero")

		# Préparer le prochain numero si nécessaire
		next_numero = None

		def get_next_numero() -> int:
			nonlocal next_numero
			if next_numero is None:
				try:
					conn = get_connection()
					with conn:
						cur = conn.cursor()
						cur.execute("SELECT COALESCE(MAX(numero), 0) FROM identification_employeurs")
						raw = cur.fetchone()[0]
						# SQLite peut renvoyer un str, on force en entier
						max_num = int(raw) if raw is not None else 0
				except Exception:
					max_num = 0
				next_numero = max_num + 1
			value = next_numero
			next_numero += 1
			return value

		rows_to_insert = []
		for _, row in self._df.iterrows():
			values = []
			for idx, excel_col in enumerate(mapped_excel_cols):
				val = row.get(excel_col)
				if pd.isna(val):
					val = None
				# Si numero est mappé mais vide, on le génère
				if (
					table_name == "identification_employeurs"
					and numero_index >= 0
					and idx == numero_index
					and (val is None or str(val).strip() == "")
				):
					val = get_next_numero()
				values.append(val)

			# Si numero n'est pas mappé du tout mais qu'on est sur identification_employeurs,
			# on le génère et on l'ajoute en tête
			if table_name == "identification_employeurs" and add_generated_numero:
				numero_val = get_next_numero()
				values.insert(0, numero_val)

			rows_to_insert.append(values)

		if not rows_to_insert:
			QMessageBox.warning(
				self,
				"Aucune ligne",
				"Le fichier Excel ne contient aucune ligne à importer.",
			)
			return

		# Insertion en base via le service excel_importer
		try:
			result = insert_rows(table_name, db_cols_for_insert, rows_to_insert)
		except Exception as exc:
			QMessageBox.critical(
				self,
				"Erreur d'import",
				f"Une erreur est survenue pendant l'import des données : {exc}",
			)
			return

		# Affichage du résumé
		message = [
			f"Lignes insérées : {result.inserted}",
			f"Lignes en erreur : {result.errors}",
		]
		if result.error_messages:
			message.append("\nExemples d'erreurs :")
			for err in result.error_messages[:5]:
				message.append(f"- {err}")

		QMessageBox.information(
			self,
			"Import terminé",
			"\n".join(message),
		)

		# Notifie les autres onglets (Accueil, Base de données, Dashboard...)
		# qu'un import a modifié la base.
		get_data_bus().data_changed.emit()

