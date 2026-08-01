# SessionStart hook. Re-asserts the security constraints on every session start, including
# source "compact", which is the only documented way to get context back after compaction.
# Must always exit 0 and print JSON on stdout: Claude Code only parses JSON on exit 0.

$root = $env:CLAUDE_PROJECT_DIR
if (-not $root) { $root = (Get-Location).Path }

function Get-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$GitArgs)
    try {
        $out = & git -C $root @GitArgs
        if ($LASTEXITCODE -ne 0) { return '' }
        return (@($out) -join "`n").Trim()
    } catch { return '' }
}

$branch = Get-Git rev-parse --abbrev-ref HEAD
$head = Get-Git log -1 '--format=%h %s'
$status = Get-Git status --short

if (-not $branch) { $branch = 'unknown' }
if (-not $head) { $head = 'unknown' }
if ([string]::IsNullOrWhiteSpace($status)) { $tree = 'clean' } else { $tree = "dirty" }

# The security section, lifted verbatim so this cannot drift from the spec.
$security = ''
$claudeMd = Join-Path $root 'CLAUDE.md'
if (Test-Path -LiteralPath $claudeMd) {
    $lines = @(Get-Content -LiteralPath $claudeMd)
    $start = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match '^##\s+Security') { $start = $i; break }
    }
    if ($start -ge 0) {
        $end = $lines.Count
        for ($j = $start + 1; $j -lt $lines.Count; $j++) {
            if ($lines[$j] -match '^##\s') { $end = $j; break }
        }
        $security = (($lines[$start..($end - 1)]) -join "`n").Trim()
    }
}
if (-not $security) {
    $security = 'CLAUDE.md could not be read at session start. Treat every auth, tenancy and secrets decision as non-negotiable, and ask before deviating.'
}

$dirtyBlock = ''
if ($tree -eq 'dirty') { $dirtyBlock = "`n" + $status }

$context = @"
Re-asserted at session start, including after compaction. These are constraints, not suggestions.

Live repository state, read just now rather than remembered:
- branch: $branch
- HEAD: $head
- working tree: $tree$dirtyBlock

Verbatim from CLAUDE.md:

$security

Structural guardrails now in force. Do not rely on prose alone to stop you:
- Real .env files are deny-listed for Read and Edit in .claude/settings.json. .env.example stays
  readable on purpose. Denies also cover cat, head, tail and sed in a shell, but not a script that
  opens the file itself.
- backend/tests/test_tenant_isolation.py is write-protected by a PreToolUse hook once it exists.
  Weakening that test so it passes is the exact failure being prevented. If it genuinely needs to
  change, ask Sonu.
- A build phase starts only when Sonu says so. run-phase, save-session and capture-skill are
  invoke-only and will not self-trigger.
"@

if ($context.Length -gt 9500) { $context = $context.Substring(0, 9500) + "`n[truncated at 9500 characters]" }

$payload = [ordered]@{
    hookSpecificOutput = [ordered]@{
        hookEventName     = 'SessionStart'
        additionalContext = $context
    }
}

$payload | ConvertTo-Json -Depth 5 -Compress
exit 0
