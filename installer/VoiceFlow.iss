#define MyAppName "VoiceFlow"
#include "version.iss"
#define MyAppPublisher "qinxujunai / VoiceFlow contributors"
#define MyAppExeName "VoiceFlow.exe"
#ifndef APP_TEST_ID
#define MyAppId "{{A38E48E3-1D73-42EC-A5F7-7D16B29C55AF}"
#else
; Isolated acceptance installers must not replace the installed product's
; uninstall registration. Never set this override in a public build.
#define MyAppId "{{" + APP_TEST_ID + "}"
#endif
#ifndef APP_SOURCE_DIR
#define APP_SOURCE_DIR "..\dist\VoiceFlow"
#endif

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
VersionInfoVersion={#MyAppFileVersion}
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
LicenseFile=..\licenses\VoiceFlow-install-terms.txt
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=no
RestartApplications=no
Uninstallable=yes
; Older logs contain an image-wide process kill and recursive {app} deletion.
; Do not append those destructive instructions to the safe current uninstaller.
; Only the current installed inventory is removed; retired untracked files stay.
UninstallLogMode=overwrite

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
Source: "{#APP_SOURCE_DIR}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
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
#ifdef INCLUDE_PUNCTUATION
Source: "..\models\punctuation\model.int8.onnx"; DestDir: "{app}\models\punctuation"; Flags: ignoreversion
#endif

[Icons]
Name: "{group}\VoiceFlow"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\VoiceFlow"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 VoiceFlow"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent

; Inno's uninstall log owns installed files. Untracked files and legacy
; vocabulary must survive; the runtime migrates vocabulary before retiring it.
#include "runtime_guard.iss"
