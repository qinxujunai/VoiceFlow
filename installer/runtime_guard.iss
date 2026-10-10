; Shared by the product installer and the isolated compiled safety fixture.
[Code]
type
  TExecutableFileId = record
    VolumeSerial: Int64;
    Id0, Id1, Id2, Id3: Cardinal;
  end;

function OpenExecutableMetadata(FileName: String; DesiredAccess, ShareMode: Cardinal;
  SecurityAttributes: THandle; CreationDisposition, Flags: Cardinal;
  TemplateFile: THandle): THandle;
  external 'CreateFileW@kernel32.dll stdcall';
function QueryExecutableFileId(FileHandle: THandle; InformationClass: Integer;
  var Identity: TExecutableFileId; BufferBytes: Cardinal): Boolean;
  external 'GetFileInformationByHandleEx@kernel32.dll stdcall';
function CloseExecutableMetadata(FileHandle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function ReadExecutableFileId(FileName: String; var Identity: TExecutableFileId;
  var ErrorCode: Cardinal): Boolean;
var
  FileHandle: THandle;
begin
  Result := False;
  ErrorCode := 0;
  // Read metadata only, follow directory aliases, and allow existing readers.
  FileHandle := OpenExecutableMetadata(FileName, 0, 7, 0, 3, 0, 0);
  if FileHandle = THandle(-1) then
  begin
    ErrorCode := DLLGetLastError;
    Exit;
  end;
  try
    // FILE_ID_INFO is a volume serial and 128-bit identity, including on ReFS.
    Result := QueryExecutableFileId(FileHandle, 18, Identity, 24);
    if not Result then ErrorCode := DLLGetLastError;
  finally
    CloseExecutableMetadata(FileHandle);
  end;
end;

function SameExecutableFileId(Left, Right: TExecutableFileId): Boolean;
begin
  Result := (Left.VolumeSerial = Right.VolumeSerial) and
    (Left.Id0 = Right.Id0) and (Left.Id1 = Right.Id1) and
    (Left.Id2 = Right.Id2) and (Left.Id3 = Right.Id3);
end;

function RuntimeSafetyError: String;
var
  Locator, Services, Processes, Process: Variant;
  Index: Integer;
  ExpectedPath, ProcessPath: String;
  ExpectedIdentity, ProcessIdentity: TExecutableFileId;
  MatchesExpected: Boolean;
  IdentityError: Cardinal;
begin
  Result := '';
  ExpectedPath := ExpandFileName(ExpandConstant('{app}\{#MyAppExeName}'));
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Services := Locator.ConnectServer('', 'root\CIMV2');
    Processes := Services.ExecQuery(
      'SELECT ExecutablePath FROM Win32_Process WHERE Name = ''{#MyAppExeName}''');
    for Index := 0 to Processes.Count - 1 do
    begin
      Process := Processes.ItemIndex(Index);
      if VarIsNull(Process.ExecutablePath) or VarIsEmpty(Process.ExecutablePath) then
      begin
        Result := '无法确认正在运行的 VoiceFlow 位置。请先从托盘退出 VoiceFlow，再重试。 / Cannot verify the running VoiceFlow location. Exit VoiceFlow from its tray, then retry.';
        Exit;
      end;
      ProcessPath := ExpandFileName(Process.ExecutablePath);
      MatchesExpected := CompareText(ProcessPath, ExpectedPath) = 0;
      if not MatchesExpected then
      begin
        if ReadExecutableFileId(ExpectedPath, ExpectedIdentity, IdentityError) then
        begin
          if not ReadExecutableFileId(ProcessPath, ProcessIdentity, IdentityError) then
          begin
            Result := '无法核对正在运行的 VoiceFlow 文件。请先从托盘退出 VoiceFlow，再重试。 / Cannot verify the running VoiceFlow file. Exit VoiceFlow from its tray, then retry.';
            Exit;
          end;
          MatchesExpected := SameExecutableFileId(ExpectedIdentity, ProcessIdentity);
        end
        else if (IdentityError <> 2) and (IdentityError <> 3) then
        begin
          // A denied alias is unknown, not proof that the target is absent.
          Result := '无法核对正在运行的 VoiceFlow 文件。请先从托盘退出 VoiceFlow，再重试。 / Cannot verify the running VoiceFlow file. Exit VoiceFlow from its tray, then retry.';
          Exit;
        end;
      end;
      if MatchesExpected then
      begin
        Result := '此位置的 VoiceFlow 正在运行。请先结束听写，从托盘退出，再重试。 / VoiceFlow at this location is running. Finish dictation and exit from its tray, then retry.';
        Exit;
      end;
    end;
  except
    Result := '无法检查 VoiceFlow 是否已退出，操作已停止。请检查 Windows 管理服务后重试。 / Cannot check whether VoiceFlow has exited. Check Windows Management Instrumentation and retry.';
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := RuntimeSafetyError;
end;

function InitializeUninstall: Boolean;
var
  SafetyError: String;
begin
  SafetyError := RuntimeSafetyError;
  Result := SafetyError = '';
  if not Result then
  begin
    Log(SafetyError);
    if not UninstallSilent then
      MsgBox(SafetyError, mbError, MB_OK);
  end;
end;
