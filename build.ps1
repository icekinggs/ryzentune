# Gera o instalador do RyzenTune:  powershell -ExecutionPolicy Bypass -File build.ps1
# Passos: ambiente de build -> lint -> testes -> PyInstaller -> autoteste do .exe -> Inno Setup -> SHA-256
$ErrorActionPreference = 'Continue'
$raiz = $PSScriptRoot
Set-Location $raiz

function Rodar([string]$exe, [string[]]$argumentos, [string]$etapa) {
    Write-Host "==> $etapa" -ForegroundColor Cyan
    & $exe @argumentos
    if ($LASTEXITCODE -ne 0) { throw "Falhou: $etapa (código $LASTEXITCODE)" }
}

$texto = Get-Content -Raw -Encoding UTF8 ryzentune\versao.py
$versao = [regex]::Match($texto, '__version__\s*=\s*"(\d+\.\d+\.\d+)"').Groups[1].Value
$repo = [regex]::Match($texto, 'REPO\s*=\s*"([^"]+)"').Groups[1].Value
if (-not $versao) { throw "Versão não encontrada em ryzentune\versao.py" }
Write-Host "RyzenTune $versao ($repo)" -ForegroundColor Green

# ---- ambiente de build isolado
$venv = Join-Path $raiz '.venv-build'
$py = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $py)) { Rodar python @('-m', 'venv', $venv) 'Criar ambiente de build' }
Rodar $py @('-m', 'pip', 'install', '-q', '--disable-pip-version-check', '-r', 'requirements-build.txt') 'Instalar dependências'

# ---- qualidade
Rodar $py @('-m', 'ruff', 'check', 'ryzentune', 'tests', 'RyzenTune.py') 'Lint (ruff)'
Rodar $py @('-m', 'pytest', '-q') 'Testes'

# ---- recurso de versão do .exe
New-Item -ItemType Directory -Force build | Out-Null
$v4 = ($versao.Split('.') + '0') -join ', '
@"
VSVersionInfo(
  ffi=FixedFileInfo(filevers=($v4), prodvers=($v4)),
  kids=[StringFileInfo([StringTable('041604B0', [
    StringStruct('CompanyName', 'RyzenTune'),
    StringStruct('FileDescription', 'RyzenTune - assistente de overclock Ryzen AM4'),
    StringStruct('FileVersion', '$versao'),
    StringStruct('ProductName', 'RyzenTune'),
    StringStruct('ProductVersion', '$versao'),
    StringStruct('OriginalFilename', 'RyzenTune.exe')])]),
    VarFileInfo([VarStruct('Translation', [1046, 1200])])]
)
"@ | Set-Content -Encoding UTF8 build\versao.txt

# ---- PyInstaller (pasta, sem console)
Remove-Item -Recurse -Force dist -ErrorAction SilentlyContinue
Rodar $py @('-m', 'PyInstaller', 'RyzenTune.py', '--noconfirm', '--clean', '--onedir', '--windowed',
    '--name', 'RyzenTune', '--icon', "$raiz\recursos\ryzentune.ico",
    '--add-data', "$raiz\recursos;recursos", '--version-file', "$raiz\build\versao.txt",
    '--distpath', "$raiz\dist", '--workpath', "$raiz\build\pyi", '--specpath', "$raiz\build",
    '--log-level', 'WARN') 'PyInstaller'

# ---- autoteste do executável empacotado
Write-Host "==> Autoteste do .exe" -ForegroundColor Cyan
$tmp = Join-Path ([IO.Path]::GetTempPath()) ("ryzentune-autoteste-" + [guid]::NewGuid())
New-Item -ItemType Directory $tmp | Out-Null
$env:RYZENTUNE_DADOS = $tmp
$p = Start-Process "$raiz\dist\RyzenTune\RyzenTune.exe" -ArgumentList '--autoteste' -Wait -PassThru
Remove-Item Env:RYZENTUNE_DADOS
if ($p.ExitCode -ne 0) {
    Get-Content "$tmp\ryzentune.log" -ErrorAction SilentlyContinue
    throw "Autoteste do .exe falhou (código $($p.ExitCode))"
}
Remove-Item -Recurse -Force $tmp

# ---- instalador
$iscc = @("${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
          "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 não encontrado (winget install JRSoftware.InnoSetup)" }
Rodar $iscc @('/Q', "/DVersao=$versao", "/DRepo=$repo", 'instalador\ryzentune.iss') 'Inno Setup'

# ---- hash publicado junto (o atualizador confere antes de instalar)
$setup = "dist\RyzenTune-Setup-$versao.exe"
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
[IO.File]::WriteAllText("$raiz\$setup.sha256", "$hash  RyzenTune-Setup-$versao.exe`n")
Write-Host "Pronto: $setup" -ForegroundColor Green
Write-Host "SHA-256: $hash"
