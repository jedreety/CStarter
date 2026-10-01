; L'installeur de CStarter, que scripts/distribution.py compile par
;   ISCC /DVersion=<version> /DSource=<dossier figé> /O<dossier de sortie> cstarter.iss
; Pour l'utilisateur seul, sans droits d'administrateur, dans %LOCALAPPDATA%\Programs\CStarter.
; Une mise à jour le lance sans fenêtre, avec /RELAUNCH=1 et /PROJECT=<dossier> : il relance
; alors l'interface sur ce projet.

#ifndef Version
  #error Version manquante : scripts/distribution.py la passe par /DVersion
#endif
#ifndef Source
  #error Source manquante : scripts/distribution.py la passe par /DSource
#endif

[Setup]
; Dérivé du nom : uuid5(NAMESPACE_DNS, "cstarter"). Ne change jamais, sinon Windows verrait un autre programme.
AppId={{28F715C6-5724-5F79-8EFE-0F6DA841B9FB}
AppName=CStarter
AppVersion={#Version}
AppVerName=CStarter {#Version}
DefaultDirName={userpf}\CStarter
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=CStarter-{#Version}-setup
SetupIconFile=cstarter.ico
UninstallDisplayIcon={app}\cstarterw.exe
UninstallDisplayName=CStarter
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
ChangesEnvironment=yes
CloseApplications=force
RestartApplications=no
ShowLanguageDialog=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "path"; Description: "Ajouter cstarter au PATH"

[InstallDelete]
; Les fichiers d'une version précédente ne se mêlent pas à ceux de la nouvelle.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\CStarter"; Filename: "{app}\cstarterw.exe"

[Run]
Filename: "{app}\cstarterw.exe"; Description: "Lancer CStarter"; Flags: nowait postinstall skipifsilent
Filename: "{app}\cstarterw.exe"; Parameters: "{code:Project}"; Flags: nowait; Check: Relaunching

[Code]
const
  Environment = 'Environment';

// Une mise à jour lancée par CStarter : l'interface se relance à la fin.
function Relaunching: Boolean;
begin
  Result := ExpandConstant('{param:relaunch|0}') = '1';
end;

// Le projet que l'interface rouvre, entre guillemets, ou rien.
function Project(Param: String): String;
begin
  Result := ExpandConstant('{param:project|}');
  if Result <> '' then
    Result := AddQuotes(Result);
end;

// La position de l'entrée Folder dans Path, 0 si elle n'y est pas.
function EntryAt(Folder, Path: String): Integer;
begin
  Result := Pos(';' + Uppercase(Folder) + ';', ';' + Uppercase(Path) + ';');
end;

// Path avec Folder à la fin, dans le style de sa fin : un PATH qui finit par ';' y finit encore.
function Appended(Folder, Path: String): String;
begin
  if Path = '' then
    Result := Folder
  else if Copy(Path, Length(Path), 1) = ';' then
    Result := Path + Folder + ';'
  else
    Result := Path + ';' + Folder;
end;

// Path sans l'entrée Folder ni l'un de ses séparateurs : Appended défait, le PATH d'avant revient.
function Without(Folder, Path: String): String;
var
  Index: Integer;
begin
  Result := Path;
  Index := EntryAt(Folder, Path);
  if Index = 0 then
    exit;
  if Index + Length(Folder) <= Length(Path) then
    Delete(Result, Index, Length(Folder) + 1)
  else if Index > 1 then
    Delete(Result, Index - 1, Length(Folder) + 1)
  else
    Result := '';
end;

// La tâche path ajoute le dossier au PATH de l'utilisateur, s'il n'y est pas déjà.
procedure CurStepChanged(CurStep: TSetupStep);
var
  Path: String;
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('path') then
  begin
    if not RegQueryStringValue(HKCU, Environment, 'Path', Path) then
      Path := '';
    if EntryAt(ExpandConstant('{app}'), Path) = 0 then
      RegWriteExpandStringValue(HKCU, Environment, 'Path', Appended(ExpandConstant('{app}'), Path));
  end;
end;

// La désinstallation retire le dossier du PATH de l'utilisateur. Le cache et les réglages restent.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Path: String;
begin
  if CurUninstallStep = usPostUninstall then
    if RegQueryStringValue(HKCU, Environment, 'Path', Path) then
      if EntryAt(ExpandConstant('{app}'), Path) > 0 then
        RegWriteExpandStringValue(HKCU, Environment, 'Path', Without(ExpandConstant('{app}'), Path));
end;
