[CmdletBinding()]
param(
    [string]$Repository = 'csn1985-ship-it/ugas',
    [string]$Base = 'main',
    [string]$Branch = '',
    [string]$GhPath = '',
    [switch]$ConfigureRuleset,
    [switch]$Wait,
    [int]$TimeoutSeconds = 1800,
    [string]$OutputPath = ''
)

$ErrorActionPreference = 'Stop'

function Write-Result([hashtable]$Value) {
    $json = $Value | ConvertTo-Json -Depth 12
    if ($OutputPath) { $json | Set-Content -LiteralPath $OutputPath -Encoding UTF8 }
    $json
}

function Resolve-Gh() {
    if ($GhPath -and (Test-Path -LiteralPath $GhPath)) { return (Resolve-Path -LiteralPath $GhPath).Path }
    $command = Get-Command gh -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    $roots = @(
        (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'),
        (Join-Path $env:ProgramFiles 'GitHub CLI')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    foreach ($root in $roots) {
        $candidate = Get-ChildItem -LiteralPath $root -Filter gh.exe -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($candidate) { return $candidate.FullName }
    }
    return $null
}

function Invoke-GhJson([string[]]$Arguments) {
    $raw = (& $script:ResolvedGh @Arguments 2>&1 | Out-String).Trim()
    $code = $LASTEXITCODE
    $value = $null
    if ($raw) { try { $value = $raw | ConvertFrom-Json -Depth 50 } catch {} }
    return @{ code = $code; raw = $raw; value = $value }
}

function New-RulesetPayload() {
    return @{
        name = 'UGAS main PR protection v0.12.4'
        target = 'branch'
        enforcement = 'active'
        conditions = @{ ref_name = @{ include = @('refs/heads/main'); exclude = @() } }
        rules = @(
            @{ type = 'pull_request'; parameters = @{ dismiss_stale_reviews_on_push = $true; require_code_owner_review = $false; required_approving_review_count = 0; require_last_push_approval = $false; required_review_thread_resolution = $true } },
            @{ type = 'required_status_checks'; parameters = @{ required_status_checks = @(
                @{ context = 'UGAS CI / unit-and-validation'; integration_id = -1 },
                @{ context = 'UGAS CI / docker-smoke'; integration_id = -1 },
                @{ context = 'UGAS Review / evidence'; integration_id = -1 }
            ); strict_required_status_checks_policy = $true } },
            @{ type = 'deletion' },
            @{ type = 'non_fast_forward' }
        )
    }
}

$script:ResolvedGh = Resolve-Gh
if (-not $script:ResolvedGh) {
    Write-Result @{ schema_version = '0.12.4'; status = 'GITHUB_AUTH_REQUIRED'; reason = 'gh_cli_not_found'; credential_values_recorded = $false }
    exit 2
}

$branchValue = if ($Branch) { $Branch } else { ((git branch --show-current 2>$null) | Out-String).Trim() }
$headSha = ((git rev-parse HEAD 2>$null) | Out-String).Trim()
$remote = ((git remote get-url origin 2>$null) | Out-String).Trim()
$failures = @()
if (-not $branchValue -or $branchValue -eq $Base) { $failures += 'implementation_branch_required' }
if ($headSha -notmatch '^[0-9a-f]{40}$') { $failures += 'head_sha_unresolved' }
if ($remote -notmatch 'github\.com[:/]csn1985-ship-it/ugas(?:\.git)?$') { $failures += 'origin_repository_mismatch' }

$auth = Invoke-GhJson @('auth', 'status', '--hostname', 'github.com')
if ($auth.code -ne 0) {
    Write-Result @{ schema_version = '0.12.4'; status = 'GITHUB_AUTH_REQUIRED'; repository = $Repository; branch = $branchValue; head_sha = $headSha; credential_values_recorded = $false; reason = 'gh_auth_status_failed'; remediation = 'Authenticate gh with repository pull-request write and administration permissions.' }
    exit 2
}
if ($failures.Count -gt 0) {
    Write-Result @{ schema_version = '0.12.4'; status = 'FAIL'; repository = $Repository; branch = $branchValue; head_sha = $headSha; failures = $failures; credential_values_recorded = $false }
    exit 1
}

$prs = Invoke-GhJson @('pr', 'list', '--repo', $Repository, '--state', 'open', '--base', $Base, '--head', $branchValue, '--json', 'number,url,state,headRefOid,baseRefName')
if ($prs.code -ne 0) {
    Write-Result @{ schema_version = '0.12.4'; status = 'GITHUB_PR_CREATE_GAP'; repository = $Repository; branch = $branchValue; head_sha = $headSha; reason = 'gh_pr_list_failed'; detail = $prs.raw; credential_values_recorded = $false }
    exit 3
}
$pr = if ($prs.value -and $prs.value.Count -gt 0) { $prs.value[0] } else { $null }
$created = $false
if (-not $pr) {
    $body = @'
## UGAS v0.12.4 GitHub CI and governance recovery

This corrective PR starts from the current main merge commit, fixes the historical snapshot/no-git validation defects, and proves the real PR-triggered CI and review evidence workflows. It records PR #1 as an immutable governance incident and keeps production blocked.

The executor leaves this PR open. No merge is authorized before explicit Sol approval bound to this exact PR number and head SHA.
'@
    $createdResult = Invoke-GhJson @('pr', 'create', '--repo', $Repository, '--base', $Base, '--head', $branchValue, '--title', 'v0.12.4 GitHub CI and governance recovery', '--body', $body)
    if ($createdResult.code -ne 0) {
        Write-Result @{ schema_version = '0.12.4'; status = 'GITHUB_PR_CREATE_GAP'; repository = $Repository; branch = $branchValue; head_sha = $headSha; reason = 'gh_pr_create_failed'; detail = $createdResult.raw; credential_values_recorded = $false }
        exit 3
    }
    $prUrl = [regex]::Match($createdResult.raw, 'https://github\.com/[^\s]+/pull/\d+').Value
    $prNumber = [int]([regex]::Match($prUrl, '/pull/(\d+)$').Groups[1].Value)
    $pr = @{ number = $prNumber; url = $prUrl; state = 'OPEN'; headRefOid = $headSha; baseRefName = $Base }
    $created = $true
}
$prNumber = [int]$pr.number
$prView = Invoke-GhJson @('pr', 'view', $prNumber, '--repo', $Repository, '--json', 'number,url,state,headRefOid,baseRefOid,baseRefName,headRefName')
if ($prView.code -eq 0 -and $prView.value) { $pr = $prView.value }
if ([string]$pr.headRefOid -ne $headSha) {
    Write-Result @{ schema_version = '0.12.4'; status = 'FAIL'; repository = $Repository; pr_number = $prNumber; pr_url = $pr.url; branch = $branchValue; head_sha = $headSha; github_head_sha = $pr.headRefOid; failures = @('pr_head_sha_mismatch'); credential_values_recorded = $false }
    exit 1
}

$ruleset = @{ status = 'READBACK_REQUIRED'; protected = $false; rulesets = @(); capability_gap = $null; credential_values_recorded = $false }
$readRules = Invoke-GhJson @('api', "repos/$Repository/rulesets")
if ($readRules.code -eq 0) {
    $rulesets = @($readRules.value)
    $effective = $rulesets | Where-Object { $_.name -eq 'UGAS main PR protection v0.12.4' } | Select-Object -First 1
    if (-not $effective -and $ConfigureRuleset) {
        $payload = (New-RulesetPayload | ConvertTo-Json -Depth 12 -Compress)
        $createdRule = $payload | & $script:ResolvedGh api --method POST "repos/$Repository/rulesets" --input - 2>&1 | Out-String
        if ($LASTEXITCODE -eq 0) { try { $effective = $createdRule | ConvertFrom-Json -Depth 50 } catch {} }
        else { $ruleset.capability_gap = 'RULESET_CAPABILITY_GAP'; $ruleset.error = $createdRule.Trim() }
    }
    $ruleset.rulesets = if ($effective) { @($effective) } else { @($rulesets) }
    $ruleset.protected = [bool]$effective
    $ruleset.status = if ($effective) { 'CONFIGURED_READ_BACK' } else { 'NOT_CONFIGURED' }
} else {
    $ruleset.status = 'RULESET_CAPABILITY_GAP'; $ruleset.capability_gap = 'RULESET_CAPABILITY_GAP'; $ruleset.error = $readRules.raw
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$checks = @()
do {
    $checkResult = Invoke-GhJson @('pr', 'checks', $prNumber, '--repo', $Repository, '--json', 'name,state,workflow,bucket,link')
    if ($checkResult.code -eq 0 -and $checkResult.value) { $checks = @($checkResult.value) }
    $required = @('UGAS CI / unit-and-validation', 'UGAS CI / docker-smoke', 'UGAS Review / evidence')
    $missing = @($required | Where-Object { $_ -notin @($checks | ForEach-Object { $_.name }) })
    $red = @($checks | Where-Object { $_.name -in $required -and $_.state -notin @('SUCCESS', 'COMPLETED') -and $_.bucket -notin @('pass') })
    $allGreen = $missing.Count -eq 0 -and $red.Count -eq 0 -and @($checks | Where-Object { $_.name -in $required }).Count -eq $required.Count -and @($checks | Where-Object { $_.name -in $required -and $_.state -eq 'SUCCESS' }).Count -eq $required.Count
    if (-not $Wait -or $allGreen -or (Get-Date) -ge $deadline) { break }
    Start-Sleep -Seconds 10
} while ($true)

$runs = Invoke-GhJson @('run', 'list', '--repo', $Repository, '--branch', $branchValue, '--limit', '20', '--json', 'databaseId,workflowName,status,conclusion,headSha,url,createdAt,updatedAt')
$artifacts = Invoke-GhJson @('api', "repos/$Repository/actions/artifacts?per_page=100")
$required = @('UGAS CI / unit-and-validation', 'UGAS CI / docker-smoke', 'UGAS Review / evidence')
$missing = @($required | Where-Object { $_ -notin @($checks | ForEach-Object { $_.name }) })
$failed = @($checks | Where-Object { $_.name -in $required -and $_.state -ne 'SUCCESS' })
$status = if ($missing.Count -gt 0) { 'CHECKS_PENDING_OR_MISSING' } elseif ($failed.Count -gt 0) { 'CHECKS_FAILED' } elseif (@($checks | Where-Object { $_.name -in $required -and $_.state -eq 'SUCCESS' }).Count -eq $required.Count) { 'READY_FOR_EXTERNAL_REVIEW' } else { 'CHECKS_PENDING_OR_MISSING' }

Write-Result @{
    schema_version = '0.12.4'
    status = $status
    repository = $Repository
    branch = $branchValue
    head_sha = $headSha
    pr_number = $prNumber
    pr_url = $pr.url
    pr_state = $pr.state
    created = $created
    checks = $checks
    required_checks = $required
    failed_or_pending_checks = $failed
    ruleset = $ruleset
    workflow_runs = if ($runs.value) { @($runs.value | Where-Object { $_.headSha -eq $headSha }) } else { @() }
    artifacts = if ($artifacts.value.artifacts) { @($artifacts.value.artifacts | Where-Object { $_.workflow_run.head_sha -eq $headSha }) } else { @() }
    credential_values_recorded = $false
    merge_performed = $false
}
if ($status -ne 'READY_FOR_EXTERNAL_REVIEW') { exit 4 }
