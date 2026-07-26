#define MyAppName "VoiceFlow"
#define MyAppVersion "0.2.0-beta.1"
#define MyAppPublisher "qinxujunai / VoiceFlow contributors"
#define MyAppExeName "VoiceFlow.exe"

[Setup]
AppId={{A38E48E3-1D73-42EC-A5F7-7D16B29C55AF}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\VoiceFlow
DefaultGroupName=VoiceFlow
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=VoiceFlow-Setup-{#MyAppVersion}-x64
SetupIconFile=..\assets\voiceflow.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
LicenseFile=..\LICENSE
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
Uninstallable=yes

#ifdef SIGNTOOL
SignTool={#SIGNTOOL}
SignedUninstaller=yes
#endif

[Languages]
#if FileExists(CompilerPath + "Languages\ChineseSimplified.isl")
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
#endif
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式"; Flags: unchecked

[Files]
Source: "..\dist\VoiceFlow\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; The offline default model is only included in an internal build after its
; distribution license review is recorded. CI sets INCLUDE_SENSEVOICE for that build.
#ifdef INCLUDE_SENSEVOICE
Source: "..\models\sensevoice\model.int8.onnx"; DestDir: "{app}\models\sensevoice"; Flags: ignoreversion
Source: "..\models\sensevoice\tokens.txt"; DestDir: "{app}\models\sensevoice"; Flags: ignoreversion
#endif

[Icons]
Name: "{group}\VoiceFlow"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\VoiceFlow"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 VoiceFlow"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c taskkill /IM VoiceFlow.exe /F"; Flags: runhidden; RunOnceId: "StopVoiceFlow"

[UninstallDelete]
; User-owned config, history, vocabulary, logs, and downloaded models live
; under {localappdata}\VoiceFlow and are intentionally retained.
Type: filesandordirs; Name: "{app}"
