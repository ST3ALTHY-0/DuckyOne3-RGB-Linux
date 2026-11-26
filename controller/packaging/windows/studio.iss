#define StudioName "Ducky RGB Studio"
#define StudioVersion "0.1.2"
#ifndef BundleDir
  #define BundleDir "..\..\dist\native\Ducky RGB Studio"
#endif
[Setup]
AppId=DuckyRGBStudio
AppName={#StudioName}
AppVersion={#StudioVersion}
DefaultDirName={localappdata}\Programs\Ducky RGB Studio
DefaultGroupName={#StudioName}
PrivilegesRequired=lowest
SetupIconFile=studio.ico
OutputBaseFilename=DuckyRGBStudio-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\Ducky RGB Studio.exe

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Ducky RGB Studio"; Filename: "{app}\Ducky RGB Studio.exe"
Name: "{autodesktop}\Ducky RGB Studio"; Filename: "{app}\Ducky RGB Studio.exe"; Tasks: desktopicon
