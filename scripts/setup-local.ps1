<#
.SYNOPSIS
  Prepares this project on a Windows computer: Python environment, packages, and a .env file to fill in.

  Run from the project folder:
    powershell -ExecutionPolicy Bypass -File scripts\setup-local.ps1
#>
$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)

$missing = @()
foreach ($tool in @(
        @{ name = "python"; winget = "Python.Python.3.12" },
        @{ name = "ffmpeg"; winget = "Gyan.FFmpeg" },
        @{ name = "git"; winget = "Git.Git" },
        @{ name = "gh"; winget = "GitHub.cli" })) {
    if (-not (Get-Command $tool.name -ErrorAction SilentlyContinue)) { $missing += $tool }
}
if ($missing.Count -gt 0) {
    Write-Host "Install these first, then open a new terminal and run this script again:" -ForegroundColor Yellow
    foreach ($tool in $missing) { Write-Host "  winget install $($tool.winget)" }
    exit 1
}

# Windows limits paths to 260 characters unless long paths are enabled, and some packages have very long file names.
$longPaths = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -ErrorAction SilentlyContinue).LongPathsEnabled
$here = (Get-Location).Path
if ($longPaths -ne 1 -and $here.Length -gt 100) {
    Write-Host "This folder's path is too long for Windows ($($here.Length) characters): package installation would fail." -ForegroundColor Yellow
    Write-Host "Move the project to a shorter folder (for example C:\sticker-agent), or enable long paths as administrator:"
    Write-Host '  New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force'
    exit 1
}

if (-not (Test-Path ".venv")) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --quiet --upgrade pip
.\.venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: package install failed." -ForegroundColor Red; exit 1 }
Write-Host "Python packages installed."

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env: fill in your keys (docs/SETUP.md, step 5)."
}

gh auth status *> $null
if ($LASTEXITCODE -ne 0) { Write-Host "Next: log in to GitHub with  gh auth login" -ForegroundColor Yellow }

Write-Host "Ready. Check everything with:  .\.venv\Scripts\python.exe run.py check" -ForegroundColor Green
