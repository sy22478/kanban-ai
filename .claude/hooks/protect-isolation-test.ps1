# PreToolUse hook for Edit, Write and NotebookEdit.
# Denies changes to the tenant isolation test once it exists. Creating it the first time is
# allowed, and the rest of backend/tests/ is untouched.
# Always exits 0: JSON on stdout is only parsed on exit 0. Silence means "no opinion, proceed".

$relative = 'backend\tests\test_tenant_isolation.py'

$root = $env:CLAUDE_PROJECT_DIR
if (-not $root) { $root = (Get-Location).Path }

try { $raw = [Console]::In.ReadToEnd() } catch { exit 0 }
if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }

try { $payload = $raw | ConvertFrom-Json } catch { exit 0 }

$toolInput = $payload.tool_input
if (-not $toolInput) { exit 0 }

$target = $toolInput.file_path
if (-not $target) { $target = $toolInput.notebook_path }
if (-not $target) { exit 0 }

function Resolve-Full {
    param([string]$Path)
    try {
        if (-not [System.IO.Path]::IsPathRooted($Path)) { $Path = Join-Path $root $Path }
        return [System.IO.Path]::GetFullPath($Path).TrimEnd('\').ToLowerInvariant()
    } catch { return '' }
}

$protectedPath = Join-Path $root $relative
$a = Resolve-Full $target
$b = Resolve-Full $protectedPath
if (-not $a -or -not $b -or $a -ne $b) { exit 0 }

# First creation is allowed. Only an existing file is protected.
if (-not (Test-Path -LiteralPath $protectedPath)) { exit 0 }

$reason = @"
Denied by the protect-isolation-test hook.

$relative is the boundary that proves user A cannot reach user B's data. Editing it is how a
failing isolation test quietly becomes a passing one, which is the specific failure CLAUDE.md
calls out: something that looks like it works because the failing path was never exercised.

If the test is wrong, or the API it calls has legitimately changed, say so and ask Sonu. Do not
route around this by writing the file through a shell command.
"@

$out = [ordered]@{
    hookSpecificOutput = [ordered]@{
        hookEventName            = 'PreToolUse'
        permissionDecision       = 'deny'
        permissionDecisionReason = $reason.Trim()
    }
}

$out | ConvertTo-Json -Depth 5 -Compress
exit 0
