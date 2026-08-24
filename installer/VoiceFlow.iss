#define MyAppName "VoiceFlow"
#define MyAppVersion "0.3.1"
#define MyAppBuildId "260812.1"
#define MyAppPublisher "qinxujunai / VoiceFlow contributors"
#define MyAppExeName "VoiceFlow.exe"

[Setup]
AppId={{A38E48E3-1D73-42EC-A5F7-7D16B29C55AF}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
VersionInfoVersion=0.3.1.4
VersionInfoTextVersion={#MyAppVersion}+{#MyAppBuildId}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\VoiceFlow
DefaultGroupName=VoiceFlow
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=VoiceFlow-{#MyAppVersion}-Windows-x64
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
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式"

[Files]
Source: "..\dist\VoiceFlow\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; The offline default model is only included in an internal build after its
; distribution license review is recorded. CI sets INCLUDE_SENSEVOICE for that build.
#ifdef INCLUDE_SENSEVOICE
Source: "..\models\sensevoice\model.int8.onnx"; DestDir: "{app}\models\sensevoice"; Flags: ignoreversion
Source: "..\models\sensevoice\tokens.txt"; DestDir: "{app}\models\sensevoice"; Flags: ignoreversion
#endif
#ifdef INCLUDE_STREAMING_PREVIEW
Source: "..\models\streaming-preview\encoder-epoch-99-avg-1.int8.onnx"; DestDir: "{app}\models\streaming-preview"; Flags: ignoreversion
Source: "..\models\streaming-preview\decoder-epoch-99-avg-1.onnx"; DestDir: "{app}\models\streaming-preview"; Flags: ignoreversion
Source: "..\models\streaming-preview\joiner-epoch-99-avg-1.int8.onnx"; DestDir: "{app}\models\streaming-preview"; Flags: ignoreversion
Source: "..\models\streaming-preview\tokens.txt"; DestDir: "{app}\models\streaming-preview"; Flags: ignoreversion
#endif

[Icons]
Name: "{group}\VoiceFlow"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\VoiceFlow"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 VoiceFlow"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

[InstallDelete]
Type: files; Name: "{app}\knowledge-base\ai-terms.txt"
Type: files; Name: "{app}\knowledge-base\company-terms.txt"
Type: files; Name: "{app}\knowledge-base\user-custom.txt"
#ifndef INCLUDE_STREAMING_PREVIEW
; Public builds omit experimental preview weights. Remove a copy left by an
; earlier internal build so the quiet-capsule fallback is deterministic.
Type: filesandordirs; Name: "{app}\models\streaming-preview"
#endif

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c taskkill /IM VoiceFlow.exe /F"; Flags: runhidden; RunOnceId: "StopVoiceFlow"

[UninstallDelete]
; User-owned config, history, vocabulary, logs, and downloaded models live
; under {localappdata}\VoiceFlow and are intentionally retained.
Type: filesandordirs; Name: "{app}"
