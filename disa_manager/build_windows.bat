@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul

REM ============================================================
REM  CNPS Traitement DiSA — Script de build production Windows
REM  Usage : double-cliquer ou lancer dans un terminal
REM ============================================================

set APP_NAME=Traitement DiSA CNPS
set APP_VERSION=1.0.0
set EXE_NAME=DisaManager
set DIST_DIR=dist\%EXE_NAME%
set INSTALLER_DIR=dist\installer

echo.
echo ============================================================
echo  %APP_NAME% — Build de production v%APP_VERSION%
echo ============================================================
echo.

REM ── Répertoire de travail ────────────────────────────────────
cd /d "%~dp0"

REM ================================================================
REM  ETAPE 0 — Vérifications préalables
REM ================================================================
echo [0/5] Vérifications préalables...

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installé ou absent du PATH.
    goto :error
)
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo       Python : !PY_VER!

pyinstaller --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] PyInstaller n'est pas installé.
    echo          Installez-le avec : pip install pyinstaller
    goto :error
)
for /f "tokens=*" %%v in ('pyinstaller --version 2^>^&1') do set PI_VER=%%v
echo       PyInstaller : !PI_VER!

REM Détecter Inno Setup (optionnel — pour générer le .exe installeur)
set ISCC=""
if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
    set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
) else if exist "C:\Program Files\Inno Setup 6\ISCC.exe" (
    set ISCC="C:\Program Files\Inno Setup 6\ISCC.exe"
)
if %ISCC%=="" (
    echo       Inno Setup : NON TROUVÉ ^(le setup.exe ne sera pas généré^)
    echo       → Télécharger sur https://jrsoftware.org/isdl.php
) else (
    echo       Inno Setup : OK
)

echo.

REM ================================================================
REM  ETAPE 1 — Installation / mise à jour des dépendances
REM ================================================================
echo [1/5] Installation des dépendances Python...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERREUR] Echec de l'installation des dépendances.
    goto :error
)

REM Pillow : nécessaire uniquement pour la conversion de l'icône
pip install Pillow --quiet
echo       OK

echo.

REM ================================================================
REM  ETAPE 2 — Génération de l'icône .ico
REM ================================================================
echo [2/5] Génération de l'icône Windows...

if exist "src\ui\images\cnps_logo.jpeg" (
    python make_icon.py
    if errorlevel 1 (
        echo       [AVERTISSEMENT] Conversion icône échouée — build sans icône personnalisée.
    )
) else (
    echo       [AVERTISSEMENT] cnps_logo.jpeg introuvable — build sans icône.
)

echo.

REM ================================================================
REM  ETAPE 3 — Compilation PyInstaller
REM ================================================================
echo [3/5] Compilation PyInstaller...
echo       Cette étape peut prendre plusieurs minutes...
echo.

pyinstaller disa_manager.spec --noconfirm --clean
if errorlevel 1 (
    echo [ERREUR] La compilation PyInstaller a échoué.
    echo          Consultez les messages ci-dessus pour diagnostiquer.
    goto :error
)

echo.
echo       Compilation réussie → %DIST_DIR%\
echo.

REM ================================================================
REM  ETAPE 4 — Copie des fichiers de déploiement
REM ================================================================
echo [4/5] Copie des fichiers de déploiement...

REM disa.conf (vide = base locale ; à renseigner pour réseau partagé)
copy /Y disa.conf "%DIST_DIR%\disa.conf" >nul
echo       disa.conf copié.

REM Créer le dossier data/ à côté de l'exe
if not exist "%DIST_DIR%\data" mkdir "%DIST_DIR%\data"

REM Créer le dossier logs/
if not exist "%DIST_DIR%\logs" mkdir "%DIST_DIR%\logs"

REM Copier la base existante si présente
if exist "data\disa.db" (
    copy /Y "data\disa.db" "%DIST_DIR%\data\disa.db" >nul
    echo       Base de données copiée depuis data\disa.db
) else (
    echo       Pas de base source — elle sera créée au premier lancement.
)

echo.

REM ================================================================
REM  ETAPE 5 — Génération du setup.exe (Inno Setup)
REM ================================================================
echo [5/5] Génération de l'installeur Windows...

if %ISCC%=="" (
    echo       Inno Setup absent — étape ignorée.
    echo       Pour générer le setup.exe, installez Inno Setup 6 et relancez ce script.
    goto :done
)

REM Créer le dossier de sortie pour l'installeur
if not exist "%INSTALLER_DIR%" mkdir "%INSTALLER_DIR%"

%ISCC% installer.iss
if errorlevel 1 (
    echo [ERREUR] La génération de l'installeur a échoué.
    goto :error
)

echo       Setup généré → %INSTALLER_DIR%\TraitementDisaCNPS_Setup_v%APP_VERSION%.exe

REM ================================================================
REM  BILAN FINAL
REM ================================================================
:done
echo.
echo ============================================================
echo  BUILD TERMINÉ AVEC SUCCÈS
echo ============================================================
echo.
echo  Exécutable portable  : %DIST_DIR%\%EXE_NAME%.exe
if not %ISCC%=="" (
    echo  Installeur Windows   : %INSTALLER_DIR%\TraitementDisaCNPS_Setup_v%APP_VERSION%.exe
)
echo.
echo  DÉPLOIEMENT PORTABLE (sans installeur)
echo  ─────────────────────────────────────
echo  1. Copier tout le dossier %DIST_DIR%\ sur le poste cible
echo  2. Lancer %EXE_NAME%.exe
echo  3. Connexion par défaut : admin / admin
echo     → CHANGER le mot de passe immédiatement après la première connexion
echo.
echo  DÉPLOIEMENT VIA INSTALLEUR
echo  ──────────────────────────
echo  1. Transférer le fichier setup.exe sur le poste cible
echo  2. Double-cliquer et suivre l'assistant
echo  3. Un raccourci est créé dans le menu Démarrer
echo.
echo  MODE MULTI-POSTES (base partagée réseau)
echo  ─────────────────────────────────────────
echo  1. Copier disa.db dans un dossier réseau accessible par tous les postes
echo  2. Sur chaque poste, éditer disa.conf et renseigner :
echo     DB_PATH=\\SERVEUR\Partages\CNPS\disa.db
echo.
echo ============================================================
pause
goto :eof

REM ── Gestion des erreurs ─────────────────────────────────────
:error
echo.
echo ============================================================
echo  BUILD ÉCHOUÉ — Consultez les messages d'erreur ci-dessus
echo ============================================================
pause
exit /b 1
