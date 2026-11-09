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
; Home app reaching the bridge). Windows' Private/Public setting is the trust list (ADR-0017,
; 1.1.1 addendum): on Private (and work-domain) networks, devices on the local subnet may reach
; Tandem; on Public networks Tandem is blocked, and the window offers to mark the network
; Private. With a rule for Tandem on every network type, Windows never asks "allow Python?".
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Tandem"""; Flags: runhidden waituntilterminated
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Tandem"" description=""Lets AirPlay speakers and TVs on your trusted (Private) networks reach Tandem"" dir=in action=allow program=""{app}\python\pythonw.exe"" enable=yes profile=private,domain remoteip=localsubnet"; StatusMsg: "Letting speakers on your network reach Tandem..."; Flags: runhidden waituntilterminated
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Tandem"" description=""Keeps Tandem closed on Public networks; mark a network Private in Windows to trust it"" dir=in action=block program=""{app}\python\pythonw.exe"" enable=yes profile=public"; Flags: runhidden waituntilterminated
; Compile Tandem's libraries once, here: under Program Files Python can't write its cache, so
; without this it would recompile them on every start (about a third slower to open).
Filename: "{app}\python\python.exe"; Parameters: "-m compileall -q -j 0 ""{app}\python\Lib\site-packages"""; StatusMsg: "Preparing Tandem..."; Flags: runhidden waituntilterminated
; The Privacy page's choices (docs/privacy-policy.md). Only "off" is written, as the user who
; started setup, so their own settings file gets it even though setup runs elevated.
Filename: "{app}\python\python.exe"; Parameters: "-m tandem privacy {code:PrivacyArgs}"; WorkingDir: "{app}"; Check: PrivacyChanged; Flags: runhidden waituntilterminated runasoriginaluser
; Opens as the signed-in user, not as administrator (setup itself runs elevated).
Filename: "{app}\python\pythonw.exe"; Parameters: "-m tandem.ui"; WorkingDir: "{app}"; Description: "Open Tandem"; Flags: postinstall nowait skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Tandem"""; Flags: runhidden; RunOnceId: "TandemFirewall"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\python"

[Code]
var
  PrivacyPage: TInputOptionWizardPage;
  PrivacyLink: TNewStaticText;

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
