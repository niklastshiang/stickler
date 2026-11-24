; Stickler spike installer (SPEC.md, module `win-spike`, task 169). Throwaway: lives on the
; branch claude/win-spike only. Built by .github/workflows/win-spike.yml:
;   ISCC.exe /DLayout=<folder> /DAppVersion=<n> /DOutDir=<folder> win\spike\Stickler-Spike.iss
#ifndef Layout
  #error Pass /DLayout=<the folder to install>
#endif
#ifndef AppVersion
  #define AppVersion "0"
#endif
#ifndef OutDir
  #define OutDir "."
#endif

[Setup]
AppId={{54BBD3E4-8455-4D60-9CE6-7498C3FF2077}
AppName=Stickler (spike)
AppVersion={#AppVersion}
AppPublisher=Stickler
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\Stickler
DisableProgramGroupPage=yes
DisableDirPage=auto
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2
SolidCompression=yes
OutputDir={#OutDir}
OutputBaseFilename=Stickler-spike-setup
UninstallDisplayName=Stickler (spike)
WizardStyle=modern

[Files]
Source: "{#Layout}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Stickler (spike)"; Filename: "{app}\Stickler-Spike.cmd"; WorkingDir: "{app}"

; The program folder only: Python writes __pycache__ below it at run time, which the uninstaller
; would not know. The data (%LOCALAPPDATA%\Stickler) is not named here and stays.
[UninstallDelete]
Type: filesandordirs; Name: "{app}"
