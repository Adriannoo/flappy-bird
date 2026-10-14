#define RootDir AddBackslash(SourcePath) + ".."
#ifndef AppIdentifier
  #define AppIdentifier "FlappyBird-46D6C03B-089F-4A7E-BC03-46CF87B9C6ED"
#endif
#ifndef SetupName
  #define SetupName "FlappyBird-Setup"
#endif

[Setup]
AppId={#AppIdentifier}
AppName=Flappy Bird
AppVersion=1.0.0
DefaultDirName={localappdata}\Programs\FlappyBird
DefaultGroupName=Flappy Bird
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#RootDir}\releases
OutputBaseFilename={#SetupName}
SetupIconFile={#RootDir}\build\flappy.ico
UninstallDisplayIcon={app}\FlappyBird.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; Flags: unchecked

[Files]
Source: "{#RootDir}\dist\FlappyBird.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Flappy Bird"; Filename: "{app}\FlappyBird.exe"
Name: "{userdesktop}\Flappy Bird"; Filename: "{app}\FlappyBird.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FlappyBird.exe"; Description: "Abrir Flappy Bird"; Flags: nowait postinstall skipifsilent
