; Tandem's Windows installer (Inno Setup 6), ADR-0017.
; Built in CI: iscc /DAppVersion=1.0.0 /DBundleDir=..\build\Tandem packaging\tandem.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef BundleDir
  #define BundleDir "..\build\Tandem"
#endif

[Setup]
AppId={{6E7C2B1A-4D1F-4C8E-9B57-2A6F0D3E9C41}
AppName=Tandem
AppVersion={#AppVersion}
AppPublisher=Tandem contributors
AppPublisherURL=https://github.com/CGlover-cmd/tandem
AppSupportURL=https://github.com/CGlover-cmd/tandem/issues
AppUpdatesURL=https://github.com/CGlover-cmd/tandem/releases
DefaultDirName={autopf}\Tandem
DefaultGroupName=Tandem
DisableProgramGroupPage=yes
LicenseFile={#BundleDir}\LICENSE.txt
OutputDir=..\dist
OutputBaseFilename=Tandem-{#AppVersion}-setup
SetupIconFile={#BundleDir}\Tandem.ico
UninstallDisplayIcon={app}\Tandem.ico
UninstallDisplayName=Tandem
VersionInfoVersion={#AppVersion}
VersionInfoProductName=Tandem
VersionInfoDescription=Tandem Setup
VersionInfoCompany=Tandem contributors
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Windows 10 22H2 (build 19045) or later.
MinVersion=10.0.19045
; The firewall rule needs administrator rights.
PrivilegesRequired=admin
; Setup closes a running Tandem itself (CloseTandem in [Code]): Windows' Restart Manager can't,
; because closing Tandem's window only hides it to the tray. This stays on as a backstop.
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "Add a desktop shortcut"; Flags: unchecked
Name: "startup"; Description: "Start Tandem when I sign in to Windows"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#BundleDir}\..\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: NeedsWebView2

[Icons]
Name: "{group}\Tandem"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m tandem.ui"; WorkingDir: "{app}"; IconFilename: "{app}\Tandem.ico"
Name: "{group}\Uninstall Tandem"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Tandem"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m tandem.ui"; WorkingDir: "{app}"; IconFilename: "{app}\Tandem.ico"; Tasks: desktopicon
Name: "{autostartup}\Tandem"; Filename: "{app}\python\pythonw.exe"; Parameters: "-m tandem.ui"; WorkingDir: "{app}"; IconFilename: "{app}\Tandem.ico"; Tasks: startup

[Run]
; WebView2 (Tandem's window) ships with Windows 11 and with Edge on Windows 10; install it if missing.
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft Edge WebView2..."; Check: NeedsWebView2; Flags: waituntilterminated
; Speakers and the TV connect back to Tandem (AirPlay timing, the TV fetching a sent file, the
; Home app reaching the bridge, a speaker's own buttons). One rule on every network type,
; Public included, so speakers work on any network with nothing to change in Windows, and
; Windows never asks "allow Python?". It lets in devices on the PC's own local subnet only:
; nothing from beyond the router, and only Tandem's program (ADR-0017, ADR-0023).
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Tandem"""; Flags: runhidden waituntilterminated
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Tandem"" description=""Lets AirPlay speakers and TVs on your local network reach Tandem"" dir=in action=allow program=""{app}\python\pythonw.exe"" enable=yes profile=any remoteip=localsubnet"; StatusMsg: "Letting speakers on your network reach Tandem..."; Flags: runhidden waituntilterminated
; Compile Tandem's libraries once, here: under Program Files Python can't write its cache, so
; without this it would recompile them on every start (about a third slower to open).
Filename: "{app}\python\python.exe"; Parameters: "-m compileall -q -j 0 ""{app}\python\Lib\site-packages"""; StatusMsg: "Preparing Tandem..."; Flags: runhidden waituntilterminated
; The Privacy page's choices (docs/privacy-policy.md). Only "off" is written, as the user who
; started setup, so their own settings file gets it even though setup runs elevated.
Filename: "{app}\python\python.exe"; Parameters: "-m tandem privacy {code:PrivacyArgs}"; WorkingDir: "{app}"; Check: PrivacyChanged; Flags: runhidden waituntilterminated runasoriginaluser
; Opens as the signed-in user, not as administrator (setup itself runs elevated). If setup
; closed Tandem to update it, Tandem opens again by itself, silent installs included.
Filename: "{app}\python\pythonw.exe"; Parameters: "-m tandem.ui"; WorkingDir: "{app}"; Check: ShouldReopenTandem; Flags: nowait runasoriginaluser
Filename: "{app}\python\pythonw.exe"; Parameters: "-m tandem.ui"; WorkingDir: "{app}"; Description: "Open Tandem"; Check: ShouldOfferToOpenTandem; Flags: postinstall nowait skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Tandem"""; Flags: runhidden; RunOnceId: "TandemFirewall"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\python"

[Code]
const
  { The names tandem.ui.platform uses (QUIT_EVENT, SINGLE_INSTANCE); a test keeps them equal. }
  QuitEventName = 'Local\TandemQuit';
  InstanceMutexName = 'Local\TandemApp';
  SYNCHRONIZE = $00100000;
  EVENT_MODIFY_STATE = $0002;
  ERROR_ACCESS_DENIED = 5;
  { The exit code a stopped copy gets (the installer test checks for it). }
  StoppedExitCode = 1;

var
  PrivacyPage: TInputOptionWizardPage;
  PrivacyLink: TNewStaticText;
  ReopenTandem: Boolean;

function OpenEvent(DesiredAccess: DWORD; InheritHandle: BOOL; Name: String): THandle;
  external 'OpenEventW@kernel32.dll stdcall';
function OpenMutex(DesiredAccess: DWORD; InheritHandle: BOOL; Name: String): THandle;
  external 'OpenMutexW@kernel32.dll stdcall';
function SetEvent(Event: THandle): BOOL;
  external 'SetEvent@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): BOOL;
  external 'CloseHandle@kernel32.dll stdcall';

{ True while a named object exists in this Windows session (one we can't open still exists). }
function NamedObjectExists(Name: String; IsEvent: Boolean): Boolean;
var
  Handle: THandle;
begin
  if IsEvent then
    Handle := OpenEvent(SYNCHRONIZE, False, Name)
  else
    Handle := OpenMutex(SYNCHRONIZE, False, Name);
  Result := Handle <> 0;
  if Result then
    CloseHandle(Handle)
  else
    Result := DLLGetLastError() = ERROR_ACCESS_DENIED;
end;

{ Counts Tandem's own Python processes, the ones run from this install's folder (Python started
  from anywhere else is never touched), and stops them when Stop is true. }
function TandemProcesses(Stop: Boolean): Integer;
var
  Locator, Service, Found, Process: Variant;
  Folder, Path: String;
  I: Integer;
begin
  Result := 0;
  Folder := AddBackslash(ExpandConstant('{app}'));
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root\CIMV2');
    Found := Service.ExecQuery('SELECT ProcessId, ExecutablePath FROM Win32_Process ' +
      'WHERE Name = ''python.exe'' OR Name = ''pythonw.exe''');
    for I := 0 to Found.Count - 1 do
    begin
      Process := Found.ItemIndex(I);
      if VarIsNull(Process.ExecutablePath) then
        continue;
      Path := Process.ExecutablePath;
      if CompareText(Copy(Path, 1, Length(Folder)), Folder) <> 0 then
        continue;
      Result := Result + 1;
      if Stop then
      begin
        Log('Stopping a Tandem process that did not quit');
        Process.Terminate(StoppedExitCode);
      end;
    end;
  except
    Log('Could not list Tandem''s processes: ' + GetExceptionMessage);
  end;
end;

{ Closes every running Tandem before its files are replaced or removed. Its window, tray icon
  and engine all live in one Python process; WebView2's helper processes end with it. }
procedure CloseTandem();
var
  Event: THandle;
  I: Integer;
begin
  { 1.2.1 and later listen for this event and quit cleanly (tandem.ui.platform.on_quit_request).
    The event lasts until the last copy listening has exited. }
  Event := OpenEvent(EVENT_MODIFY_STATE, False, QuitEventName);
  if Event <> 0 then
  begin
    Log('Asking Tandem to quit');
    SetEvent(Event);
    CloseHandle(Event);
    for I := 1 to 60 do { up to 15 seconds }
    begin
      if not NamedObjectExists(QuitEventName, True) then
        break;
      Sleep(250);
    end;
  end;
  { Older copies can't be asked, and one that didn't quit in time is stopped. }
  if TandemProcesses(True) > 0 then
    for I := 1 to 20 do { its files are free once it's gone }
    begin
      Sleep(250);
      if TandemProcesses(False) = 0 then
        break;
    end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  WasOpen: Boolean;
begin
  WasOpen := NamedObjectExists(InstanceMutexName, False);
  CloseTandem();
  { Open it again afterwards, unless a copy setup leaves alone (an older one run from somewhere
    else, such as a developer's checkout) still holds the one-window lock: a new one would exit. }
  ReopenTandem := WasOpen and not NamedObjectExists(InstanceMutexName, False);
  Result := '';
end;

function ShouldReopenTandem(): Boolean;
begin
  Result := ReopenTandem;
end;

function ShouldOfferToOpenTandem(): Boolean;
begin
  Result := not ReopenTandem;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    CloseTandem();
end;

procedure PrivacyLinkClick(Sender: TObject);
var
  ErrorCode: Integer;
begin
  ShellExec('open', 'https://github.com/CGlover-cmd/tandem/blob/main/docs/privacy-policy.md', '', '', SW_SHOWNORMAL, ewNoWait, ErrorCode);
end;

{ Shows Tandem's two optional internet lookups and lets the user turn them off (SignPath
  Foundation's terms ask for this). Silent installs skip the page; /NoAppIcons=1 and
  /NoUpdateCheck=1 start the boxes unticked, which the installer test uses. }
procedure InitializeWizard();
begin
  PrivacyPage := CreateInputOptionPage(wpLicense, 'Privacy',
    'Tandem makes two small requests on the internet',
    'Tandem sends nothing about you or your PC to anyone, and has no accounts or telemetry. ' +
    'The icons lookup tells Apple which apps are on your Apple TV. The update check asks GitHub ' +
    'for the list of Tandem releases. Both see this PC''s internet address. You can change ' +
    'either one later in Tandem''s Settings.',
    False, False);
  PrivacyPage.Add('Look up App Store icons for my Apple TV''s apps');
  PrivacyPage.Add('Check GitHub for a newer version of Tandem');
  PrivacyPage.Values[0] := ExpandConstant('{param:NoAppIcons|0}') <> '1';
  PrivacyPage.Values[1] := ExpandConstant('{param:NoUpdateCheck|0}') <> '1';

  PrivacyLink := TNewStaticText.Create(PrivacyPage);
  PrivacyLink.Parent := PrivacyPage.Surface;
  PrivacyLink.Caption := 'Read the full privacy policy';
  PrivacyLink.Cursor := crHand;
  PrivacyLink.Font.Style := [fsUnderline];
  PrivacyLink.Font.Color := clBlue;
  PrivacyLink.OnClick := @PrivacyLinkClick;
  PrivacyPage.CheckListBox.Height := ScaleY(48);
  PrivacyLink.Left := 0;
  PrivacyLink.Top := PrivacyPage.CheckListBox.Top + PrivacyPage.CheckListBox.Height + ScaleY(12);
end;

function PrivacyChanged(): Boolean;
begin
  Result := not (PrivacyPage.Values[0] and PrivacyPage.Values[1]);
end;

function PrivacyArgs(Param: String): String;
begin
  Result := '';
  if not PrivacyPage.Values[0] then Result := '--app-icons off';
  if not PrivacyPage.Values[1] then Result := Trim(Result + ' --update-check off');
end;

function NeedsWebView2(): Boolean;
var
  Version: String;
begin
  Result := not (
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version)
  ) or (Version = '') or (Version = '0.0.0.0');
end;
