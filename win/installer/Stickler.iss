; Stickler's installer for Windows 11 (SPEC.md, module `win-package`, scopes 3 and 4), made with
; Inno Setup 7.1.1 from the folder scripts/win_bundle.sh assembles:
;
;   ISCC.exe /DLayout=<folder> /DAppVersion=<n> /DOutDir=<folder> win\installer\Stickler.iss
;
; Per user without administrator rights, into %LOCALAPPDATA%\Programs\Stickler; a Start menu
; entry, a desktop icon and an entry in Settings > Apps. Its texts beyond Inno's own come from
; po/ through scripts/winstrings.py (Messages.iss).
#ifndef Layout
  #error Pass /DLayout=<the folder scripts/win_bundle.sh made>
#endif
#ifndef AppVersion
  #error Pass /DAppVersion=<the release number>
#endif
#ifndef OutDir
  #define OutDir "."
#endif

[Setup]
; not the spike's: the throwaway installer of win-spike had an id of its own
AppId={{1307FF50-F481-4FF5-90FB-892B9A297AC6}
AppName=Stickler
AppVersion={#AppVersion}
AppVerName=Stickler {#AppVersion}
AppPublisher=Stickler
AppPublisherURL=https://stickler.tshia.ng/
AppSupportURL=https://github.com/niklastshiang/stickler/issues
AppUpdatesURL=https://stickler.tshia.ng/#get
VersionInfoVersion={#AppVersion}.0.0.0
VersionInfoProductName=Stickler
; per user only: never offered for all users (no administrator rights, no UAC prompt)
PrivilegesRequired=lowest
DefaultDirName={autopf}\Stickler
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableWelcomePage=yes
; Windows 11 (build 22000 and later) on x64; Windows 10 and ARM64 stop with Stickler's message
MinVersion=10.0.22000
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
SetupArchitecture=x64
Compression=lzma2/max
SolidCompression=yes
OutputDir={#OutDir}
OutputBaseFilename=Stickler-{#AppVersion}-setup
SetupIconFile=..\Stickler\Stickler.ico
UninstallDisplayIcon={app}\Stickler.exe
UninstallDisplayName=Stickler
WizardStyle=modern dynamic
; the running app holds this mutex (win/Stickler/App.xaml.cs): Setup and the uninstaller ask
; to close it first
AppMutex=ng.tshia.Stickler
CloseApplications=yes
RestartApplications=no
; the language follows Windows' display language, without a question; the uninstaller keeps it
ShowLanguageDialog=no
LanguageDetectionMethod=uilanguage
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "german"; MessagesFile: "compiler:Languages\German.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

#include "Messages.iss"

[InstallDelete]
; an update replaces the whole core: no file of an older release's Python stays
Type: filesandordirs; Name: "{app}\core"

[Files]
Source: "{#Layout}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Stickler"; Filename: "{app}\Stickler.exe"
Name: "{autodesktop}\Stickler"; Filename: "{app}\Stickler.exe"

[Run]
Filename: "{app}\Stickler.exe"; Description: "{cm:LaunchProgram,Stickler}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; the program folder: Python writes __pycache__ there, which the uninstaller would not know
Type: filesandordirs; Name: "{app}"
; WebView2's data, the program's browser cache: the running app holds it, so the core's removal
; leaves it (SPEC.md, `win-package`, scope 6); then Stickler's folder if nothing is left in it
Type: filesandordirs; Name: "{localappdata}\Stickler\WebView2"
Type: dirifempty; Name: "{localappdata}\Stickler"

[Code]
var
  RemoveEverything: Boolean;

function SetEnvironmentVariable(Name, Value: String): Boolean;
  external 'SetEnvironmentVariableW@kernel32.dll stdcall';

{ The app's "Uninstall Stickler..." starts the uninstaller silently and then ends; a silent
  uninstall would stop at once while the app still holds its mutex, so it waits for the app
  first, at most 20 seconds. }
function InitializeUninstall(): Boolean;
var
  Waited: Integer;
begin
  Waited := 0;
  while UninstallSilent() and CheckForMutexes('ng.tshia.Stickler') and (Waited < 20000) do
  begin
    Sleep(250);
    Waited := Waited + 250;
  end;
  Result := True;
end;

{ Settings > Apps starts the uninstaller without switches. Inno asks its own question first
  (its text is Stickler's: "Uninstall Stickler? This removes Stickler, its models and the saved
  analyses..."); then comes the second one, No by default; then the installed core removes
  Stickler's folders as the app's "Uninstall Stickler..." does, before the program goes (its
  Python is part of it). A silent uninstall (/SILENT, /VERYSILENT: the app's own "Uninstall
  Stickler...", which has removed the data itself) asks nothing and removes only the program. }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Code: Integer;
  Arguments: String;
begin
  if UninstallSilent() then
    Exit;
  case CurUninstallStep of
    usAppMutexCheck:
      RemoveEverything := MsgBox(CustomMessage('RemoveSettings'), mbConfirmation,
        MB_YESNO or MB_DEFBUTTON2) = IDYES;
    usUninstall:
      begin
        SetEnvironmentVariable('STICKLER_PACKAGED', 'windows');
        Arguments := '-I -m stickler_app.uninstall';
        if RemoveEverything then
          Arguments := Arguments + ' --everything';
        Log('Removing Stickler''s data: python ' + Arguments);
        if not Exec(ExpandConstant('{app}\core\python\python.exe'), Arguments,
          ExpandConstant('{app}\core'), SW_HIDE, ewWaitUntilTerminated, Code) or (Code <> 0) then
        begin
          Log(Format('The core''s removal did not finish (exit code %d)', [Code]));
          { a line of its own must not begin with "[": Inno reads that as a section }
          MsgBox(FmtMessage(CustomMessage('DataNotRemoved'), [ExpandConstant('{localappdata}\Stickler')]),
            mbError, MB_OK);
        end;
      end;
  end;
end;
