# Lança uma versão nova:  powershell -ExecutionPolicy Bypass -File lancar.ps1 1.0.1
# 1) confere que está tudo commitado e que o CHANGELOG tem a seção da versão
# 2) atualiza ryzentune\versao.py, roda lint e testes
# 3) commit + tag vX.Y.Z + push  ->  o GitHub Actions gera o instalador e publica a release
param([Parameter(Mandatory = $true)][string]$Versao)
$ErrorActionPreference = 'Continue'
function Invoke-Git { & git.exe @args; if ($LASTEXITCODE) { throw "git $args falhou" } }
Set-Location $PSScriptRoot

if ($Versao -notmatch '^\d+\.\d+\.\d+$') { throw "Use o formato X.Y.Z (ex.: 1.0.1)" }
$arq = 'ryzentune\versao.py'
$texto = [IO.File]::ReadAllText((Resolve-Path $arq))
$atual = [regex]::Match($texto, '__version__\s*=\s*"(\d+\.\d+\.\d+)"').Groups[1].Value
if ([version]$Versao -le [version]$atual) { throw "A versão $Versao não é maior que a atual ($atual)" }

if (git status --porcelain) { throw "Há alterações não commitadas. Faça o commit antes de lançar." }
$ramo = git rev-parse --abbrev-ref HEAD
if ($ramo -ne 'main') { throw "Lance a partir do ramo main (você está em $ramo)" }
if (git tag --list "v$Versao") { throw "A tag v$Versao já existe" }

$log = [IO.File]::ReadAllText((Resolve-Path CHANGELOG.md))
if ($log -notmatch "(?m)^## \[$([regex]::Escape($Versao))\]") {
    throw "Adicione a seção '## [$Versao] - $(Get-Date -Format yyyy-MM-dd)' no CHANGELOG.md e faça o commit"
}

$novo = $texto -replace '__version__\s*=\s*"\d+\.\d+\.\d+"', "__version__ = `"$Versao`""
[IO.File]::WriteAllText((Resolve-Path $arq), $novo, (New-Object Text.UTF8Encoding $false))

$py = if (Test-Path .venv-build\Scripts\python.exe) { '.venv-build\Scripts\python.exe' } else { 'python' }
& $py -m ruff check ryzentune tests RyzenTune.py
if ($LASTEXITCODE) { git checkout -- $arq; throw "Lint falhou" }
& $py -m pytest -q
if ($LASTEXITCODE) { git checkout -- $arq; throw "Testes falharam" }

Invoke-Git add $arq
Invoke-Git commit -q -m "Versão $Versao"
Invoke-Git tag -a "v$Versao" -m "RyzenTune $Versao"
Invoke-Git push -q origin main
Invoke-Git push -q origin "v$Versao"
Write-Host "Tag v$Versao enviada. Acompanhe o build em: gh run watch  (ou na aba Actions do GitHub)" -ForegroundColor Green
