param(
    [ValidateSet('summary', 'verify', 'auto')]
    [string]$Mode,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$RemainingArgs
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appExe = Join-Path $scriptDir 'synerion_attendance.exe'
$distExe = Join-Path $scriptDir 'dist\synerion_attendance.exe'
$pythonExe = Join-Path $scriptDir '.venv\Scripts\python.exe'
$attendPy = Join-Path $scriptDir 'attend.py'
$selectPdfScript = Join-Path $scriptDir 'select_pdf.ps1'

if (-not (Test-Path $appExe) -and -not (Test-Path $distExe) -and -not (Test-Path $pythonExe)) {
    Write-Host '[ERROR] Release EXE and development environment were not found.'
    Write-Host 'End user: run the files from the release folder.'
    Write-Host 'Developer: run setup.bat first.'
    exit 1
}

$pdfPath = $null
if ($RemainingArgs.Count -gt 0) {
    $pdfPath = $RemainingArgs[0]
}

if ([string]::IsNullOrWhiteSpace($pdfPath)) {
    $pdfPath = & $selectPdfScript
}

if ([string]::IsNullOrWhiteSpace($pdfPath)) {
    Write-Host '[INFO] No PDF file was selected.'
    exit 1
}

if (-not (Test-Path -LiteralPath $pdfPath)) {
    Write-Host '[ERROR] PDF file not found:'
    Write-Host $pdfPath
    exit 1
}

Write-Host 'PDF selected successfully.'
Write-Host ''

$modeFlag = switch ($Mode) {
    'summary' { '--summary-only' }
    'verify' { '--verify' }
    'auto' { '--auto' }
}

$args = @($modeFlag, '--pdf', $pdfPath)

if (Test-Path $appExe) {
    & $appExe @args
    exit $LASTEXITCODE
}

if (Test-Path $distExe) {
    & $distExe @args
    exit $LASTEXITCODE
}

& $pythonExe $attendPy @args
exit $LASTEXITCODE