PRAGMA foreign_keys = ON;

-- Table de versioning du schéma (migrations numérotées)
CREATE TABLE IF NOT EXISTS schema_version (
    version  INTEGER PRIMARY KEY,
    applied_at TEXT DEFAULT (datetime('now'))
);

-- Table des utilisateurs pour la connexion à l'application
CREATE TABLE IF NOT EXISTS utilisateurs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    role TEXT NOT NULL
);

-- Utilisateurs par défaut
INSERT OR IGNORE INTO utilisateurs (id, username, password, role) VALUES
    (1, 'admin', 'admin', 'admin'),
    (2, 'agent', 'agent', 'agent');


-- Table 1 : Identification des employeurs (même structure que db/schema.sql à la racine)
CREATE TABLE IF NOT EXISTS identification_employeurs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero INTEGER NOT NULL,
    numero_cnps TEXT NOT NULL,
    raison_sociale TEXT NOT NULL,
    secteur_activite TEXT,
    date_debut_activite TEXT,
    forme_juridique TEXT,
    nombre_travailleur INTEGER,
    disa_2024 INTEGER,
    disa_2023 INTEGER,
    disa_2022 INTEGER,
    disa_2021 INTEGER,
    disa_anterieures_2010_2020 INTEGER,
    periodicite TEXT,
    telephone_1 TEXT,
    telephone_2 TEXT,
    email_1 TEXT,
    email_2 TEXT,
    email_3 TEXT,
    localisation_geographique TEXT,
    localites TEXT,
    exercice INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Table 2 : Traitement des DiSA
CREATE TABLE IF NOT EXISTS traitement_disa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employeur_id INTEGER NOT NULL,
    exercice INTEGER NOT NULL,
    disa_anterieures_a_recueillir TEXT,
    date_de_reception TEXT,
    date_de_traitement TEXT,
    date_de_validation TEXT,
    effectif_disa INTEGER,
    nbre_de_lignes_traitees INTEGER,
    nbre_de_lignes_validees INTEGER,
    nbre_de_lignes_rejetees INTEGER,
    actions_menees TEXT,
    nbre_de_lignes_rejetees_traitees INTEGER,
    nbre_total_de_lignes_validees_apres_traitement_des_rejets INTEGER,
    date_de_traitement_rejet TEXT,
    nbre_restant_de_rejet INTEGER,
    observations TEXT,
    statut TEXT,
    traite_par TEXT,
    is_suspended INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (employeur_id) REFERENCES identification_employeurs(id) ON DELETE CASCADE,
    UNIQUE (employeur_id, exercice)
);


