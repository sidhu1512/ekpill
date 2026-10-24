; Inno Setup script for EkPill.
;
; Compile with:   ISCC.exe installer.iss        (or python build_packaged.py)
;
; Per-user install (PrivilegesRequired=lowest): no admin prompt, and the app
; lands in %LocalAppData%\Programs where a shell utility belongs.

#define MyAppName "EkPill"
#define MyAppVersion "1.3"
#define MyAppPublisher "EkPill"
#define MyAppExeName "EkPill.exe"

[Setup]
AppId={{D4A3E92B-351E-49A4-B937-5C8E8F5A291A}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableWelcomePage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=EkPillSetup
SetupIconFile=build\ekpill.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern dark
WizardSizePercent=100
WizardKeepAspectRatio=no
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
SetupLogging=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[InstallDelete]
; The app folder belongs to EkPill. Clearing it prevents a half-replaced
; runtime from an older version surviving an upgrade.
Type: filesandordirs; Name: "{app}"

[Files]
; The whole one-folder build: the exe plus its _internal runtime (Qt, QML,
; assets and the pywinrt native modules).
Source: "dist\EkPill\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"

[UninstallDelete]
; Uninstall leaves nothing behind: the program folder, the per-user settings
; and caches, both shortcuts, and the Start-menu group.
Type: filesandordirs; Name: "{app}"
Type: filesandordirs; Name: "{localappdata}\EkPill"
Type: filesandordirs; Name: "{userappdata}\EkPill"
Type: files; Name: "{autodesktop}\{#MyAppName}.lnk"
Type: files; Name: "{userstartup}\{#MyAppName}.lnk"
Type: filesandordirs; Name: "{group}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Start EkPill"; Flags: nowait skipifsilent

[Code]
// Resize wizard form to a sleek, compact modern dialog
procedure InitializeWizard();
begin
  WizardForm.Constraints.MinHeight := 0;
  WizardForm.Constraints.MinWidth := 0;
  WizardForm.Constraints.MaxHeight := 0;
  WizardForm.Constraints.MaxWidth := 0;
  WizardForm.ClientWidth := ScaleX(380);
  WizardForm.ClientHeight := ScaleY(165);
  WizardForm.Position := poScreenCenter;
  WizardForm.Bevel.Visible := False;
  WizardForm.BackButton.Visible := False;
  WizardForm.OuterNotebook.ClientWidth := ScaleX(380);
  WizardForm.OuterNotebook.ClientHeight := ScaleY(165);
  WizardForm.InnerNotebook.ClientWidth := ScaleX(380);
  WizardForm.InnerNotebook.ClientHeight := ScaleY(165);
  WizardForm.NextButton.Top := WizardForm.ClientHeight - WizardForm.NextButton.Height - ScaleY(10);
  WizardForm.CancelButton.Top := WizardForm.ClientHeight - WizardForm.CancelButton.Height - ScaleY(10);
  WizardForm.CancelButton.Left := WizardForm.ClientWidth - WizardForm.CancelButton.Width - ScaleX(14);
  WizardForm.StatusLabel.Left := ScaleX(16);
  WizardForm.StatusLabel.Top := ScaleY(28);
  WizardForm.StatusLabel.Width := ScaleX(348);
  WizardForm.FileNameLabel.Visible := False;
  WizardForm.ProgressGauge.Left := ScaleX(16);
  WizardForm.ProgressGauge.Top := ScaleY(56);
  WizardForm.ProgressGauge.Width := ScaleX(348);
  WizardForm.ProgressGauge.Height := ScaleY(16);
end;

// Auto-advance through any intermediate page so setup runs in 0 extra clicks
procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID <> wpInstalling) and (CurPageID <> wpFinished) then
    PostMessage(WizardForm.NextButton.Handle, $00F5, 0, 0);  // BM_CLICK
end;

// A capsule you never close: it sits in the tray with no window of its own.
procedure StopEkPill();
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#MyAppExeName}', '',
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function InitializeUninstall(): Boolean;
begin
  StopEkPill();
  Result := True;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  StopEkPill();
  Result := '';
end;

// Shred every leftover file, setting directory, and shortcut completely on uninstall
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DelTree(ExpandConstant('{localappdata}\EkPill'), True, True, True);
    DelTree(ExpandConstant('{userappdata}\EkPill'), True, True, True);
    DelTree(ExpandConstant('{app}'), True, True, True);
    DeleteFile(ExpandConstant('{autodesktop}\{#MyAppName}.lnk'));
    DeleteFile(ExpandConstant('{userstartup}\{#MyAppName}.lnk'));
    DelTree(ExpandConstant('{group}'), True, True, True);
  end;
end;
