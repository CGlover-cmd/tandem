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
; Home app reaching the bridge), so let devices on the local network reach Tandem. The rule
; covers every network type, because Windows often marks home Wi-Fi as Public and then asks
; "allow Python?" on first run; it only admits the local subnet, so nothing past the router can
; reach Tandem (ADR-0017, 1.1.1 addendum; the maintainer's choice).
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Tandem"""; Flags: runhidden waituntilterminated
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""Tandem"" description=""Lets AirPlay speakers and TVs on your local network reach Tandem"" dir=in action=allow program=""{app}\python\pythonw.exe"" enable=yes profile=any remoteip=localsubnet"; StatusMsg: "Letting speakers on your network reach Tandem..."; Flags: runhidden waituntilterminated
; Opens as the signed-in user, not as administrator (setup itself runs elevated).
Filename: "{app}\python\pythonw.exe"; Parameters: "-m tandem.ui"; WorkingDir: "{app}"; Description: "Open Tandem"; Flags: postinstall nowait skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""Tandem"""; Flags: runhidden; RunOnceId: "TandemFirewall"

[UninstallDelete]
Type: filesandordirs; Name: "{app}\python"

[Code]
function NeedsWebView2(): Boolean;
var
  Version: String;
begin
  Result := not (
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) or
    RegQueryStringValue(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version)
  ) or (Version = '') or (Version = '0.0.0.0');
end;
