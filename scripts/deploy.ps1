<#
.SYNOPSIS
  Puts the Content Creation Agent on GitHub Actions, so it posts on schedule even when this PC is off.

.DESCRIPTION
  1. Checks .env and encrypts the Instagram token into state/ig_token.enc
  2. Creates a PUBLIC GitHub repository (Instagram downloads the media from it) and pushes the code
  3. Saves the API keys as encrypted GitHub Actions secrets
  4. Starts a first test run that creates a post WITHOUT publishing it

  Run from the project folder:
    powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1
#>
param([string]$RepoName = "sticker-content-agent", [switch]$SkipTestRun)

$ErrorActionPreference = "Continue"
Set-Location (Split-Path -Parent $PSScriptRoot)
$python = ".\.venv\Scripts\python.exe"

function Read-DotEnv {
    $values = @{}
    if (Test-Path ".env") {
        foreach ($line in Get-Content ".env" -Encoding UTF8) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') { $values[$Matches[1]] = $Matches[2].Trim().Trim('"') }
        }
    }
    return $values
}

function Stop-If-Failed([string]$message) {
    if ($LASTEXITCODE -ne 0) { Write-Host "ERROR: $message" -ForegroundColor Red; exit 1 }
}

gh auth status | Out-Null
Stop-If-Failed "Log in to GitHub first: gh auth login"
if (-not (Test-Path ".env")) { Write-Host "ERROR: copy .env.example to .env and fill it in first (README step 5)." -ForegroundColor Red; exit 1 }

$vars = Read-DotEnv
foreach ($name in @("ANTHROPIC_API_KEY", "HF_API_KEY_ID", "HF_API_KEY_SECRET", "IG_ACCESS_TOKEN")) {
    if (-not $vars[$name]) { Write-Host "ERROR: $name is empty in .env" -ForegroundColor Red; exit 1 }
}

$owner = (gh api user --jq .login).Trim()
$repo = "$owner/$RepoName"
Write-Host "Repository: https://github.com/$repo"

# Re-runs: start from the latest version on GitHub (the schedule commits post history and refreshed tokens).
if ((Test-Path ".git") -and (git remote)) {
    git pull --rebase --autostash origin main
    Stop-If-Failed "could not get the latest version from GitHub (resolve it, then run again)"
}

& $python run.py set-env MEDIA_REPO $repo
& $python run.py seal-token
Stop-If-Failed "could not encrypt the Instagram token"
$vars = Read-DotEnv

if (-not (Test-Path ".git")) { git init -b main | Out-Null }
if (-not (git config user.email)) {
    git config user.email "$owner@users.noreply.github.com"
    git config user.name $owner
}
git add -A
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) { git commit -m "Content Creation Agent" | Out-Null }

gh repo view $repo --json name | Out-Null
if ($LASTEXITCODE -ne 0) {
    gh repo create $repo --public --description "Automated Instagram content agent" --source . --remote origin --push
    Stop-If-Failed "could not create the repository"
} else {
    if (-not (git remote)) { git remote add origin "https://github.com/$repo.git" }
    git push -u origin main
    Stop-If-Failed "could not push to $repo"
}

foreach ($name in @("ANTHROPIC_API_KEY", "HF_API_KEY_ID", "HF_API_KEY_SECRET", "TOKEN_KEY")) {
    gh secret set $name --repo $repo --body $vars[$name] | Out-Null
    Stop-If-Failed "could not save the secret $name"
}
Write-Host "Secrets saved."

if (-not $SkipTestRun) {
    Write-Host "Starting a test run (creates a carousel without publishing it, about `$0.20)..."
    for ($i = 0; $i -lt 6; $i++) {
        gh workflow run autopost.yml --repo $repo -f format=carousel -f publish=false 2>$null
        if ($LASTEXITCODE -eq 0) { break }
        Start-Sleep -Seconds 10
    }
}
Write-Host ""
Write-Host "Done. Follow the run at https://github.com/$repo/actions" -ForegroundColor Green
Write-Host "From now on it posts automatically: a carousel every day at 19:00 and a reel on Tue/Thu/Sat at 13:00."
