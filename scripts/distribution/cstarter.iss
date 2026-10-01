; L'installeur de CStarter, que scripts/distribution.py compile par
;   ISCC /DVersion=<version> /DSource=<dossier figé> /O<dossier de sortie> cstarter.iss
; et /DSignedUninstaller=<dossier> quand le désinstalleur se signe, en deux passes.
; Pour l'utilisateur seul, sans droits d'administrateur, dans %LOCALAPPDATA%\Programs\CStarter.
; Une mise à jour le lance sans fenêtre, avec /RELAUNCH=1 et /PROJECT=<dossier> : il relance
; alors l'interface sur ce projet. La désinstallation n'ouvre qu'une fenêtre, dont une case retire
; aussi les bibliothèques et les réglages ; sans fenêtre, /COMPLET=1 fait de même.

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
AppPublisher=jedreety
AppCopyright=Copyright (c) 2026 jedreety
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
#ifdef SignedUninstaller
; Inno Setup écrit dans ce dossier le désinstalleur à signer, puis reprend sa signature.
SignedUninstaller=yes
SignedUninstallerDir={#SignedUninstaller}
#endif

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "path"; Description: "Ajouter cstarter au PATH"

[InstallDelete]
; Les fichiers d'une version précédente ne se mêlent pas à ceux de la nouvelle.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion

[UninstallDelete]
; L'installeur qu'une mise à jour a téléchargé. Le cache et les réglages restent, sauf
; désinstallation complète.
Type: filesandordirs; Name: "{localappdata}\CStarter\mises-a-jour"

[Icons]
Name: "{autoprograms}\CStarter"; Filename: "{app}\cstarterw.exe"

[Run]
Filename: "{app}\cstarterw.exe"; Description: "Lancer CStarter"; Flags: nowait postinstall skipifsilent
Filename: "{app}\cstarterw.exe"; Parameters: "{code:Project}"; Flags: nowait; Check: Relaunching

[Code]
const
  Environment = 'Environment';

var
  // La désinstallation complète : les bibliothèques et les réglages partent avec l'application.
  Complete: Boolean;

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

// CStarter tourne-t-il ? Ses exécutables, cstarter.exe et cstarterw.exe, dans la liste des tâches.
function Running: Boolean;
var
  Code: Integer;
begin
  Result := Exec(ExpandConstant('{cmd}'), '/C tasklist /NH /FI "IMAGENAME eq cstarter*" | find /I "cstarter"', '', SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0);
end;

// La fenêtre de désinstallation : la case qui retire aussi les bibliothèques et les réglages, puis
// Désinstaller ou Annuler.
function Confirmed: Boolean;
var
  Form: TSetupForm;
  Box: TNewCheckBox;
  Hint: TNewStaticText;
  Uninstall, Cancel: TNewButton;
  Width: Integer;
begin
  Form := CreateCustomForm(ScaleX(440), ScaleY(124), False, True);
  try
    Form.Caption := 'Désinstaller CStarter';

    Box := TNewCheckBox.Create(Form);
    Box.Parent := Form;
    Box.Left := ScaleX(16);
    Box.Top := ScaleY(16);
    Box.Width := Form.ClientWidth - ScaleX(32);
    Box.Height := ScaleY(20);
    Box.Caption := 'Supprimer aussi les bibliothèques installées et les réglages';

    // Un dossier par ligne, raccourci au milieu s'il est trop long ; la fenêtre suit sa hauteur.
    Hint := TNewStaticText.Create(Form);
    Hint.Parent := Form;
    Hint.Left := ScaleX(34);
    Hint.Top := Box.Top + Box.Height + ScaleY(2);
    Hint.Font.Color := clGrayText;
    Width := Form.ClientWidth - Hint.Left - ScaleX(16);  // Hint, à taille automatique, n'a pas encore la sienne
    Hint.Caption := MinimizePathName(ExpandConstant('{%USERPROFILE}\.cstarter'), Hint.Font, Width) + #13#10 +
      MinimizePathName(ExpandConstant('{%LOCALAPPDATA}\CStarter'), Hint.Font, Width) + #13#10 + 'Les projets restent intacts.';
    Form.ClientHeight := Hint.Top + Hint.Height + ScaleY(16 + 23 + 14);

    Uninstall := TNewButton.Create(Form);
    Uninstall.Parent := Form;
    Uninstall.Caption := 'Désinstaller';
    Uninstall.ModalResult := mrOk;
    Uninstall.Default := True;

    Cancel := TNewButton.Create(Form);
    Cancel.Parent := Form;
    Cancel.Caption := 'Annuler';
    Cancel.ModalResult := mrCancel;
    Cancel.Cancel := True;

    Uninstall.Width := Form.CalculateButtonWidth([Uninstall.Caption, Cancel.Caption]);
    Cancel.Width := Uninstall.Width;
    Uninstall.Height := ScaleY(23);
    Cancel.Height := ScaleY(23);
    Cancel.Left := Form.ClientWidth - ScaleX(16) - Cancel.Width;
    Uninstall.Left := Cancel.Left - ScaleX(6) - Uninstall.Width;
    Cancel.Top := Form.ClientHeight - ScaleY(14) - Cancel.Height;
    Uninstall.Top := Cancel.Top;

    Form.ActiveControl := Uninstall;
    Result := Form.ShowModal = mrOk;
    Complete := Box.Checked;
  finally
    Form.Free;
  end;
end;

// Une seule fenêtre, la nôtre : une fois confirmée, la désinstallation se relance sans fenêtre
// (/SILENT), donc sans la question ni le message de fin d'Inno Setup. Lancée sans fenêtre par un
// script, elle garde les bibliothèques et les réglages, sauf avec /COMPLET=1.
function InitializeUninstall: Boolean;
var
  Parameters: String;
  Code: Integer;
begin
  if UninstallSilent then
  begin
    Complete := ExpandConstant('{param:complet|0}') = '1';
    Result := True;
    exit;
  end;
  Result := False;
  if not Confirmed then
    exit;
  while Running do
    if MsgBox('CStarter est ouvert : fermez-le, puis recommencez.', mbInformation, MB_RETRYCANCEL) = IDCANCEL then
      exit;
  Parameters := '/SILENT';
  if Complete then
    Parameters := Parameters + ' /COMPLET=1';
  Exec(ExpandConstant('{uninstallexe}'), Parameters, '', SW_SHOW, ewNoWait, Code);
end;

// La désinstallation retire le dossier du PATH de l'utilisateur ; complète, elle retire aussi les
// bibliothèques du cache et les réglages, aux chemins que CStarter lit dans son environnement.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Path: String;
begin
  if CurUninstallStep <> usPostUninstall then
    exit;
  if RegQueryStringValue(HKCU, Environment, 'Path', Path) then
    if EntryAt(ExpandConstant('{app}'), Path) > 0 then
      RegWriteExpandStringValue(HKCU, Environment, 'Path', Without(ExpandConstant('{app}'), Path));
  if Complete then
  begin
    if GetEnv('LOCALAPPDATA') <> '' then
      DelTree(ExpandConstant('{%LOCALAPPDATA}\CStarter'), True, True, True);
    if GetEnv('USERPROFILE') <> '' then
      DelTree(ExpandConstant('{%USERPROFILE}\.cstarter'), True, True, True);
  end;
end;
