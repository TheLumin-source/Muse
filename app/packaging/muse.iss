; Inno Setup script for Muse
; Wraps the PyInstaller one-folder build (dist\Muse) into a single Setup.exe.
; Compile:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" muse.iss
; (build.ps1 runs PyInstaller then this, if ISCC is installed.)

#define MyAppName "Muse"
; Version comes from muse/__init__.py via build.ps1 (/DMyAppVersion=...).
; The literal below is only a fallback for compiling the .iss by hand.
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppPublisher "Martin De Lange"
#define MyAppURL "https://martinworks.org"
#define MyAppExeName "Muse.exe"
; Relative to this script, so the repo compiles on any machine.
#define MyAppDir AddBackslash(ExtractFilePath(ExtractFileDir(SourcePath)))
#define MyBuildDir MyAppDir + "dist\Muse"

[Setup]
AppId={{B6E4B0F2-9C3D-4A7E-9E21-7A5C1D3F8B44}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppCopyright=Copyright (C) 2026 Martin De Lange (MartinWorks). All rights reserved.
LicenseFile={#SourcePath}EULA.txt
; Templated like AppVersion above. Hardcoded, this silently disagreed with
; the installer the moment the version moved.
VersionInfoVersion={#MyAppVersion}.0
VersionInfoCompany=Martin De Lange (MartinWorks)
VersionInfoProductName={#MyAppName}
VersionInfoDescription={#MyAppName} Setup
VersionInfoCopyright=Copyright (C) 2026 Martin De Lange
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Per-user install: no admin/UAC prompt, friendlier to distribute.
PrivilegesRequired=lowest
OutputDir={#MyAppDir}..\out
OutputBaseFilename=Muse Setup
SetupIconFile={#MyAppDir}muse.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "{#MyBuildDir}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#MyBuildDir}\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#SourcePath}EULA.txt"; DestDir: "{app}"; DestName: "License.txt"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Muse"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"; Flags: uninsdeletekey

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Code]
function PriorInstallDir(): String;
var s: String;
begin
  Result := '';
  if RegQueryStringValue(HKCU, 'Software\Muse', 'InstallDir', s) then
    Result := s;
end;

// If Muse is already installed, offer to repair/reinstall or uninstall.
function InitializeSetup(): Boolean;
var dir, unins: String; res: Integer;
begin
  Result := True;
  dir := PriorInstallDir();
  if (dir <> '') and DirExists(dir) and (not WizardSilent()) then begin
    unins := AddBackslash(dir) + 'unins000.exe';
    res := MsgBox('Muse is already installed on this computer.' #13#10 #13#10
      + 'YES  -  repair / reinstall it (recommended after an update)' #13#10
      + 'NO   -  uninstall it' #13#10
      + 'CANCEL  -  do nothing',
      mbConfirmation, MB_YESNOCANCEL);
    if res = IDNO then begin
      if FileExists(unins) then
        Exec(unins, '/SILENT', '', SW_SHOW, ewWaitUntilTerminated, res);
      Result := False;
    end else if res = IDCANCEL then
      Result := False;
  end;
end;
