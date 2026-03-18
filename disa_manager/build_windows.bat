@echo off
REM ============================================================
REM  CNPS Disa Manager — Script de compilation Windows
REM  Usage : double-cliquer build_windows.bat (ou lancer dans cmd)
REM ============================================================

echo [1/3] Installation des dependances...
pip install -r requirements.txt

echo.
echo [2/3] Compilation en cours (PyInstaller)...
pyinstaller disa_manager.spec --noconfirm --clean

echo.
echo [3/3] Copie des fichiers de deploiement...

REM Copier disa.conf dans le dossier de sortie
REM (vide par defaut = base locale ; a remplir pour reseau partage)
copy /Y disa.conf dist\DisaManager\disa.conf

REM Creer le dossier data/ a cote de l'exe avec la base initiale
if not exist dist\DisaManager\data mkdir dist\DisaManager\data
copy /Y data\disa.db dist\DisaManager\data\disa.db

echo.
echo ============================================================
echo  Build termine !
echo  Dossier de sortie : dist\DisaManager\
echo.
echo  Pour deployer sur un poste :
echo    1. Copier tout le dossier dist\DisaManager\ sur le poste
echo    2. Lancer DisaManager.exe
echo.
echo  Pour le mode multi-postes (base partagee reseau) :
echo    1. Copier disa.db dans un dossier reseau partage
echo    2. Sur chaque poste, editer disa.conf et renseigner DB_PATH
echo       Ex: DB_PATH=\\SERVEUR\Partages\CNPS\disa.db
echo ============================================================
pause
