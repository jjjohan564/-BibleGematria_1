<#
.SYNOPSIS
    Sets BIBLE_DB_NAME (and optionally other BIBLE_DB_* vars) for the current PowerShell session.

.DESCRIPTION
    Use this to quickly target a specific database (the real "stepbible" DB or a test one)
    without editing files.
    IMPORTANT: Changes made with $env:FOO only last for this PowerShell window / process.
    Close this window or open a new one and the setting disappears.

    To make the setting survive new PowerShell windows, use the -Persist switch
    (writes to your user environment variables in the registry).

.EXAMPLE
    .\scripts\set-bible-db.ps1
    # Sets BIBLE_DB_NAME=stepbible (the real DB) for this session only

.EXAMPLE
    .\scripts\set-bible-db.ps1 -Name stepbible
    # Point at the real production-like database for this session

.EXAMPLE
    .\scripts\set-bible-db.ps1 -Name stepbibletest -Persist
    # Set a test DB permanently for your user account (new shells will inherit it).
    # You will still need to open a fresh PowerShell window after running with -Persist.
#>
param(
    [string]$Name = "stepbible",
    [switch]$Persist
)

$env:BIBLE_DB_NAME = $Name

Write-Host ""
Write-Host "BIBLE_DB_NAME set to '$env:BIBLE_DB_NAME' " -ForegroundColor Green -NoNewline
Write-Host "(for this PowerShell session only)." -ForegroundColor Yellow

if ($Persist) {
    [Environment]::SetEnvironmentVariable("BIBLE_DB_NAME", $Name, "User")
    Write-Host ""
    Write-Host "Also wrote it to your USER environment variables (persistent)." -ForegroundColor Green
    Write-Host ">>> CLOSE this PowerShell window and open a NEW one for Python processes to see the change. <<<" -ForegroundColor Magenta
    Write-Host ""
    Write-Host "To verify in a new shell:  " -NoNewline; Write-Host '$env:BIBLE_DB_NAME' -ForegroundColor Cyan
    Write-Host "To remove later:           " -NoNewline; Write-Host '[Environment]::SetEnvironmentVariable("BIBLE_DB_NAME", $null, "User")' -ForegroundColor Cyan
} else {
    Write-Host ""
    Write-Host "This change does NOT survive closing this window or opening new terminals." -ForegroundColor DarkYellow
    Write-Host ""
    Write-Host "To make it permanent for new shells, re-run with -Persist:" -ForegroundColor Cyan
    Write-Host "    .\scripts\set-bible-db.ps1 -Name $Name -Persist" -ForegroundColor White
    Write-Host ""
    Write-Host "Or set it by hand (session only):" -ForegroundColor DarkGray
    Write-Host "    `$env:BIBLE_DB_NAME = `"$Name`"" -ForegroundColor White
    Write-Host ""
    Write-Host "Or set it persistently by hand:" -ForegroundColor DarkGray
    Write-Host "    [Environment]::SetEnvironmentVariable(`"BIBLE_DB_NAME`", `"$Name`", `"User`")" -ForegroundColor White
}

Write-Host ""
Write-Host "Now run your import/maintenance script in THIS SAME window, e.g.:" -ForegroundColor DarkGray
Write-Host "    python scripts/import/import_bible.py" -ForegroundColor White
Write-Host ""
