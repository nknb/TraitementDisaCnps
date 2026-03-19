; ============================================================
; Inno Setup 6 — Installeur Windows — CNPS Traitement DiSA
; Générer le setup : ISCC.exe installer.iss
; ============================================================

#define AppName      "Traitement DiSA CNPS"
#define AppVersion   "1.0.0"
#define AppPublisher "CNPS — Agence de Gagnoa"
#define AppExeName   "DisaManager.exe"
#define AppId        "{{E4B2A3C1-7F5D-4E8A-B9C2-1D3F6E7A8B9C}"
#define SourceDir    "dist\DisaManager"

[Setup]
; ── Identification ──────────────────────────────────────────
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://www.cnps.ci
AppSupportURL=https://www.cnps.ci
AppUpdatesURL=https://www.cnps.ci

; ── Répertoire d'installation ──────────────────────────────
; {localappdata} = C:\Users\<user>\AppData\Local
; → Pas besoin de droits administrateur pour installer
DefaultDirName={localappdata}\CNPS\DisaManager
DefaultGroupName={#AppName}
DisableDirPage=no
DirExistsWarning=no

; ── Droits ─────────────────────────────────────────────────
; "lowest" = installation sans élévation UAC (chaque utilisateur installe dans son profil)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; ── Apparence ───────────────────────────────────────────────
; Icône du setup.exe lui-même
SetupIconFile=src\ui\images\cnps_logo.ico
; Image de bienvenue (164×314 px recommandé — optionnelle)
; WizardImageFile=src\ui\images\installer_banner.bmp
; Image petite icône (55×58 px — optionnelle)
; WizardSmallImageFile=src\ui\images\installer_icon_small.bmp

; Compression LZMA2 maximale
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; ── Sortie ──────────────────────────────────────────────────
OutputDir=dist\installer
OutputBaseFilename=TraitementDisaCNPS_Setup_v{#AppVersion}

; ── Options Windows ─────────────────────────────────────────
; Exécutable 64 bits uniquement (Windows 10/11)
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0

; ── Désinstallation ─────────────────────────────────────────
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
CreateUninstallRegKey=yes

; Langue française
ShowLanguageDialog=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Messages]
; ── Messages personnalisés ──
french.WelcomeLabel1=Bienvenue dans l'assistant d'installation de%n{#AppName}
french.WelcomeLabel2=Cette application permet la gestion du traitement des%nDéclarations Individuelles des Salaires Annuels (DiSA)%nauprès de la CNPS — Agence de Gagnoa.%n%nCliquez sur Suivant pour continuer.
french.FinishedLabel=L'installation de {#AppName} est terminée.%n%nCliquez sur Terminer pour quitter l'assistant.

[Tasks]
; Raccourci bureau (proposé par défaut)
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; ── Fichiers de l'application ───────────────────────────────
; Copie tout le contenu de dist\DisaManager\ dans le répertoire cible
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; ── Fichier de configuration réseau ─────────────────────────
; disa.conf est copié seulement si absent (ne jamais écraser la config existante)
Source: "disa.conf"; DestDir: "{app}"; Flags: onlyifdoesntexist

; ── Dossier data/ (base de données locale) ──────────────────
; Le dossier est créé ; la base disa.db sera générée au premier lancement
; Si une base source existe dans le projet, elle est copiée une seule fois
; Source: "data\disa.db"; DestDir: "{app}\data"; Flags: onlyifdoesntexist; Check: FileExists(ExpandConstant('{src}\data\disa.db'))

[Dirs]
; Crée le dossier data/ dès l'installation (init_db le remplit au premier lancement)
Name: "{app}\data"
; Crée le dossier logs/
Name: "{app}\logs"

[Icons]
; ── Menu Démarrer ────────────────────────────────────────────
Name: "{group}\{#AppName}";    Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"
Name: "{group}\Désinstaller";  Filename: "{uninstallexe}"

; ── Bureau (si la tâche est cochée) ─────────────────────────
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
; Lancer l'application à la fin de l'installation (optionnel)
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Supprimer les logs à la désinstallation (la base disa.db est conservée)
Type: filesandordirs; Name: "{app}\logs"

[Code]
// ── Vérification : l'application n'est pas déjà en cours d'exécution ──
function IsAppRunning(): Boolean;
var
  ResultCode: Integer;
begin
  Result := False;
  if FindWindowByWindowName('Traitement DiSA — CNPS') <> 0 then
    Result := True;
end;

function InitializeSetup(): Boolean;
begin
  Result := True;
  if IsAppRunning() then
  begin
    MsgBox(
      'L''application "Traitement DiSA CNPS" est actuellement en cours d''exécution.' + #13#10 +
      'Veuillez la fermer avant de lancer l''installation.',
      mbError, MB_OK
    );
    Result := False;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
  if IsAppRunning() then
  begin
    MsgBox(
      'L''application "Traitement DiSA CNPS" est actuellement en cours d''exécution.' + #13#10 +
      'Veuillez la fermer avant de lancer la désinstallation.',
      mbError, MB_OK
    );
    Result := False;
  end;
end;
