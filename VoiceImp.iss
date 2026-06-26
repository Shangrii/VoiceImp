; VoiceImp installer (Inno Setup).
; Build:  "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" VoiceImp.iss

#define AppName "VoiceImp"
#define AppVersion "1.0.0"

[Setup]
AppId={{8F3A1C0E-4B7D-4E2A-9A1F-0A1B2C3D4E5F}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=VoiceImp
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=installer
OutputBaseFilename=VoiceImp_Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
DisableWelcomePage=no
SetupIconFile=voiceimp.ico
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\VoiceImp.exe

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\VoiceImp\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\VoiceImp"; Filename: "{app}\VoiceImp.exe"
Name: "{group}\Uninstall VoiceImp"; Filename: "{uninstallexe}"
Name: "{autodesktop}\VoiceImp"; Filename: "{app}\VoiceImp.exe"; Tasks: desktopicon

[Run]
Filename: "https://vb-audio.com/Cable/"; Description: "Download VB-CABLE (required virtual microphone)"; Flags: postinstall shellexec skipifsilent
Filename: "{app}\VoiceImp.exe"; Description: "Launch VoiceImp now"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    MsgBox('VoiceImp was installed successfully.' + #13 + #13 +
           'IMPORTANT: for your game or app to hear the voice you need to install ' +
           'VB-CABLE (a free virtual microphone):' + #13 +
           '  1. Download VB-CABLE (the page will open).' + #13 +
           '  2. Run it as administrator and install the driver.' + #13 +
           '  3. Reboot your PC.' + #13 + #13 +
           'Then, in your game set the microphone to "CABLE Output".',
           mbInformation, MB_OK);
end;
