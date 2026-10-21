param([switch]$Push)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

# Refresh this year and last year; the QC caches retain older accepted hours.
$fromYear = (Get-Date).Year - 1
python sync_clidata.py --station RIGASLU --from-year $fromYear
if ($LASTEXITCODE -ne 0) { throw 'HTDRY sync failed; existing site remains intact.' }
python sync_precipitation.py --from-year $fromYear
if ($LASTEXITCODE -ne 0) { throw 'HPRAB sync failed; existing site remains intact.' }
python -m unittest discover -p 'test_*.py'
if ($LASTEXITCODE -ne 0) { throw 'Tests failed; site was not rebuilt.' }
python build_static_site.py
if ($LASTEXITCODE -ne 0) { throw 'Static build failed.' }

if ($Push) {
    git add -- site
    git diff --cached --quiet
    if ($LASTEXITCODE -eq 1) {
        git commit -m 'Refresh Rigas LU weather snapshot'
        if ($LASTEXITCODE -ne 0) { throw 'Commit failed.' }
        git push origin main
        if ($LASTEXITCODE -ne 0) { throw 'Push failed.' }
    }
}
