; Instalador do RyzenTune (Inno Setup 6). Compile com:
;   ISCC.exe /DVersao=1.0.0 instalador\ryzentune.iss
#ifndef Versao
  #error Passe a versão: /DVersao=X.Y.Z
#endif
#ifndef Repo
  #define Repo "icekinggs/ryzentune"
#endif

[Setup]
AppId={{6B1D2C1E-6F0A-4B8B-9B7E-2F4C7A0E5D31}
AppName=RyzenTune
AppVersion={#Versao}
AppVerName=RyzenTune {#Versao}
AppPublisher=RyzenTune
AppPublisherURL=https://github.com/{#Repo}
AppSupportURL=https://github.com/{#Repo}/issues
AppUpdatesURL=https://github.com/{#Repo}/releases
VersionInfoVersion={#Versao}
DefaultDirName={autopf}\RyzenTune
DefaultGroupName=RyzenTune
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=RyzenTune-Setup-{#Versao}
SetupIconFile=..\recursos\ryzentune.ico
UninstallDisplayIcon={app}\RyzenTune.exe
InfoBeforeFile=aviso.txt
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "atalho"; Description: "Criar atalho na Área de Trabalho"; Flags: unchecked

[Files]
Source: "..\dist\RyzenTune\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; driver PawnIO (namazso, assinado). Só é instalado se ainda não existir; nunca é removido pelo
; desinstalador, porque outros programas (ZenTimings, LibreHardwareMonitor...) também o usam.
Source: "..\terceiros\baixado\PawnIO_setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall

[InstallDelete]
; remove arquivos de versões antigas que não existem mais
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\RyzenTune"; Filename: "{app}\RyzenTune.exe"
Name: "{autodesktop}\RyzenTune"; Filename: "{app}\RyzenTune.exe"; Tasks: atalho

[Run]
Filename: "{app}\RyzenTune.exe"; Parameters: "--instalar-tarefa"; Flags: runhidden waituntilterminated; StatusMsg: "Criando a tarefa de boot..."
Filename: "{app}\RyzenTune.exe"; Description: "Abrir o RyzenTune"; Flags: nowait postinstall skipifsilent
; atualização automática (modo silencioso): reabre o app no fim
Filename: "{app}\RyzenTune.exe"; Flags: nowait skipifnotsilent

[UninstallRun]
Filename: "{app}\RyzenTune.exe"; Parameters: "--remover-tarefa"; Flags: runhidden waituntilterminated; RunOnceId: "RemoverTarefa"

[Code]
var
  PrecisaReiniciar: Boolean;

function PawnIOInstalado(): Boolean;
var
  Local: String;
begin
  Result := RegQueryStringValue(HKLM64, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\PawnIO',
                                'InstallLocation', Local) and FileExists(AddBackslash(Local) + 'PawnIOLib.dll');
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Codigo: Integer;
begin
  if (CurStep = ssPostInstall) and not PawnIOInstalado() then
  begin
    WizardForm.StatusLabel.Caption := 'Instalando o driver de acesso ao hardware (PawnIO)...';
    if Exec(ExpandConstant('{tmp}\PawnIO_setup.exe'), '-install -silent', '', SW_HIDE, ewWaitUntilTerminated, Codigo) then
    begin
      if Codigo = 3010 then
        PrecisaReiniciar := True
      else if Codigo <> 0 then
        SuppressibleMsgBox('O driver PawnIO não foi instalado (código ' + IntToStr(Codigo) + '). ' +
          'Sem ele o RyzenTune não lê nem ajusta o hardware. Instale-o em https://pawnio.eu', mbError, MB_OK, IDOK);
    end;
  end;
end;

function NeedRestart(): Boolean;
begin
  Result := PrecisaReiniciar;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Dados: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    Dados := ExpandConstant('{localappdata}\RyzenTune');
    if DirExists(Dados) and not UninstallSilent then
      if MsgBox('Apagar também o histórico e os perfis salvos (' + Dados + ')?',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(Dados, True, True, True);
  end;
end;
