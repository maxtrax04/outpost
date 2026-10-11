<#
.SYNOPSIS
    One-time setup of labels, milestones, and issues for the Outpost repository.

.DESCRIPTION
    Reads issues.json (next to this script) and creates everything with the
    GitHub CLI. Safe to run again: labels are updated, and milestones and
    issues that already exist (matched by title) are skipped.

.PARAMETER DryRun
    Show what would be created without changing anything.

.EXAMPLE
    .\scripts\github-setup\setup.ps1 -DryRun
    .\scripts\github-setup\setup.ps1
#>
[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

function Assert-Ok([string]$what) {
    if ($LASTEXITCODE -ne 0) { throw "Failed: $what" }
}

# --- Preflight ---------------------------------------------------------------
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "The GitHub CLI (gh) is not installed. Install it with: winget install --id GitHub.cli"
}

gh auth status 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "You are not signed in to GitHub. Run: gh auth login"
}

$repoRoot = (git rev-parse --show-toplevel).Trim()
Set-Location $repoRoot

$repo = (gh repo view --json nameWithOwner --jq ".nameWithOwner").Trim()
Assert-Ok "find the repository"
Write-Host "Repository: $repo" -ForegroundColor Cyan
if ($DryRun) { Write-Host "DRY RUN: nothing will be created." -ForegroundColor Yellow }

$dataPath = Join-Path $PSScriptRoot "issues.json"
$data = Get-Content -Raw -Encoding UTF8 -Path $dataPath | ConvertFrom-Json

# --- Labels ------------------------------------------------------------------
Write-Host "`nLabels" -ForegroundColor Cyan
foreach ($label in $data.labels) {
    Write-Host "  $($label.name)"
    if (-not $DryRun) {
        gh label create $label.name --color $label.color --description $label.description --force | Out-Null
        Assert-Ok "create label $($label.name)"
    }
}

# --- Milestones --------------------------------------------------------------
Write-Host "`nMilestones" -ForegroundColor Cyan
$existingMilestones = @(gh api "repos/$repo/milestones?state=all&per_page=100" --jq ".[].title")
Assert-Ok "list milestones"

foreach ($milestone in $data.milestones) {
    if ($existingMilestones -contains $milestone.title) {
        Write-Host "  exists:  $($milestone.title)"
        continue
    }
    Write-Host "  create:  $($milestone.title)"
    if (-not $DryRun) {
        gh api "repos/$repo/milestones" -f "title=$($milestone.title)" -f "description=$($milestone.description)" | Out-Null
        Assert-Ok "create milestone $($milestone.title)"
    }
}

# --- Issues ------------------------------------------------------------------
Write-Host "`nIssues" -ForegroundColor Cyan
$existingIssues = @(gh issue list --state all --limit 1000 --json title --jq ".[].title")
Assert-Ok "list issues"

$created = 0
$skipped = 0

foreach ($issue in $data.issues) {
    if ($existingIssues -contains $issue.title) {
        Write-Host "  exists:  $($issue.title)"
        $skipped++
        continue
    }

    $milestoneText = "no milestone"
    if ($issue.milestone) { $milestoneText = $issue.milestone }
    Write-Host "  create:  $($issue.title)  [$milestoneText]"

    if ($DryRun) {
        $created++
        continue
    }

    # Write the body to a temp file so markdown and quotes survive intact
    $bodyFile = Join-Path ([System.IO.Path]::GetTempPath()) ("outpost-issue-" + [guid]::NewGuid().ToString() + ".md")
    [System.IO.File]::WriteAllText($bodyFile, $issue.body, (New-Object System.Text.UTF8Encoding($false)))

    $ghArgs = @("issue", "create", "--title", $issue.title, "--body-file", $bodyFile)
    foreach ($labelName in $issue.labels) {
        $ghArgs += @("--label", $labelName)
    }
    if ($issue.milestone) {
        $ghArgs += @("--milestone", $issue.milestone)
    }

    try {
        gh @ghArgs | Out-Null
        Assert-Ok "create issue '$($issue.title)'"
        $created++
    }
    finally {
        Remove-Item -Path $bodyFile -Force -ErrorAction SilentlyContinue
    }

    # Stay under GitHub's limits for creating many issues quickly
    Start-Sleep -Seconds 2
}

Write-Host "`nDone. Created: $created, already existed: $skipped." -ForegroundColor Green
Write-Host "Milestones: https://github.com/$repo/milestones"
