$ErrorActionPreference = 'Stop'
$taskName = 'AnalogForecastingSnapshot'
$publisher = Join-Path $PSScriptRoot 'publish_snapshot.ps1'
if (!(Test-Path -LiteralPath $publisher)) { throw 'Publisher script missing.' }

# Uses this Windows account's local CLIDATA access and Git Credential Manager.
# No password or Oracle DSN is written to Task Scheduler or GitHub.
$runner = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$publisher`" -Push"
schtasks.exe /Create /TN $taskName /TR $runner /SC HOURLY /MO 3 /ST 06:00 /F
if ($LASTEXITCODE -ne 0) { throw 'Could not register the local update task.' }
schtasks.exe /Query /TN $taskName /FO LIST
