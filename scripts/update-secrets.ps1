<#
.SYNOPSIS
  Sends changed keys from .env to GitHub. Run it after you replace a key or the Instagram token.

.DESCRIPTION
  1. Gets the latest version from GitHub (the schedule saves post history and refreshed tokens there)
  2. Re-encrypts the Instagram token into state/ig_token.enc if .env has a new IG_ACCESS_TOKEN, and pushes it
  3. Overwrites the GitHub Actions secrets with the values in .env

  GitHub secrets can be replaced but never read back, so .env (and a copy in your password manager) is your record.

  Run from the project folder:
    powershell -ExecutionPolicy Bypass -File scripts\update-secrets.ps1
#>
$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)
$python = ".\.venv\Scripts\python.exe"

function Read-DotEnv {
    $values = @{}
    foreach ($line in Get-Content ".env" -Encoding UTF8) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { $values[$Matches[1]] = $Matches[2].Trim().Trim('"') }
    }
    return $values
}

function Stop-If-Failed([string]$message) {
    if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: $message" -ForegroundColor Red; exit 1 }
}

if (-not (Test-Path ".env")) { Write-Host "ERROR: .env not found." -ForegroundColor Red; exit 1 }
$vars = Read-DotEnv
$repo = $vars["MEDIA_REPO"]
if (-not $repo) { Write-Host "ERROR: MEDIA_REPO is empty in .env (run scripts\deploy.ps1 first)." -ForegroundColor Red; exit 1 }

git pull --rebase --autostash origin main
Stop-If-Failed "could not get the latest version from GitHub"

& $python run.py seal-token
Stop-If-Failed "could not encrypt the Instagram token"
git add state/ig_token.enc
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    git commit -m "chore: update Instagram token" | Out-Null
    git push origin main
    Stop-If-Failed "could not push the new Instagram token"
    Write-Host "New Instagram token pushed."
}

$vars = Read-DotEnv
foreach ($name in @("ANTHROPIC_API_KEY", "HF_API_KEY_ID", "HF_API_KEY_SECRET", "TOKEN_KEY")) {
    if (-not $vars[$name]) { Write-Host "Skipped $name (empty in .env)" -ForegroundColor Yellow; continue }
    gh secret set $name --repo $repo --body $vars[$name] | Out-Null
    Stop-If-Failed "could not save the secret $name"
    Write-Host "Updated secret $name"
}
Write-Host "Done. Secrets: https://github.com/$repo/settings/secrets/actions" -ForegroundColor Green
