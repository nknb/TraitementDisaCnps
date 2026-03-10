PRAGMA foreign_keys = ON;

-- Table 1 : Identification des employeurs
CREATE TABLE IF NOT EXISTS identification_employeurs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero INTEGER NOT NULL,                            -- N° d'enregistrement interne
    numero_cnps TEXT NOT NULL,                          -- Numéro CNPS
    raison_sociale TEXT NOT NULL,                       -- RAISON_SOCIALE
    secteur_activite TEXT,                              -- SECTEUR_D_ACTIVITE
    date_debut_activite TEXT,                           -- DATE_DEBUT_ACTIVITE (format ISO AAAA-MM-JJ conseillé)
    forme_juridique TEXT,                               -- FORME_JURIDIQUE
    nombre_travailleur INTEGER,                         -- NOMBRE_TRAVAILLEUR
    disa_2024 INTEGER,                                  -- DISA_2024 (0/1 ou nombre)
    disa_2023 INTEGER,                                  -- DISA_2023
    disa_2022 INTEGER,                                  -- DISA_2022
    disa_2021 INTEGER,                                  -- DISA_2021
    disa_anterieures_2010_2020 INTEGER,                 -- DISA_ANTERIEURES_2010_2020 (compteur ou indicateur)
    periodicite TEXT,                                   -- PERIODICITE
    telephone_1 TEXT,                                   -- TELEPHONE_1
    email_1 TEXT,                                       -- EMAIL_1
    localisation_geographique TEXT,                     -- LOCALISATION_GEOGRAPHIQUE
    localites TEXT,                                     -- LOCALITES
    exercice INTEGER,                                   -- EXERCICE (année courante de suivi)
    created_at TEXT DEFAULT (datetime('now'))
);

-- Table 2 : Traitement des DiSA
CREATE TABLE IF NOT EXISTS traitement_disa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employeur_id INTEGER NOT NULL,                      -- Référence à identification_employeurs.id
    exercice INTEGER NOT NULL,                          -- Année de la DiSA
    disa_anterieures_a_recueillir TEXT,                 -- DiSA antérieures à recueillir
    date_de_reception TEXT,                             -- DATE_DE_RECEPTION
    date_de_traitement TEXT,                            -- DATE_DE_TRAITEMENT
    date_de_validation TEXT,                            -- DATE_DE_VALIDATION
    effectif_disa INTEGER,                              -- EFFECTIF_DISA
    nbre_de_lignes_traitees INTEGER,                    -- NBRE_DE_LIGNES_TRAITEES
    nbre_de_lignes_validees INTEGER,                    -- NBRE_DE_LIGNES_VALIDEES
    nbre_de_lignes_rejetees INTEGER,                    -- NBRE_DE_LIGNES_REJETEES
    nbre_de_lignes_rejetees_traitees INTEGER,           -- NBRE_DE_LIGNES_REJETEES_TRAITEES
    nbre_total_de_lignes_validees_apres_traitement_des_rejets INTEGER, -- NBRE_TOTAL_DE_LIGNES_VALIDEES_APRES_TRAITEMENT_DES_REJETS
    date_de_traitement_rejet TEXT,                      -- DATE_DE_TRAITEMENT_REJET
    nbre_restant_de_rejet INTEGER,                      -- NBRE_RESTANT_DE_REJET
    observations TEXT,                                  -- OBSERVATIONS de l'agent
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (employeur_id) REFERENCES identification_employeurs(id) ON DELETE CASCADE,
    UNIQUE (employeur_id, exercice)
);
