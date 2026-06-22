param(
    [ValidateSet('summary', 'verify', 'auto')]
    [string]$Mode,
    [string]$Site,
    [string]$PdfPath
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$appExe = Join-Path $scriptDir 'synerion_attendance.exe'
$distExe = Join-Path $scriptDir 'dist\synerion_attendance.exe'
$pythonExe = Join-Path $scriptDir '.venv\Scripts\python.exe'
$attendPy = Join-Path $scriptDir 'attend.py'
$selectPdfScript = Join-Path $scriptDir 'select_pdf.ps1'
$siteConfigPath = Join-Path $scriptDir 'synerion_site.txt'

function Normalize-SitePrefix([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }

    $normalized = $Value.Trim().ToLowerInvariant()
    if ($normalized -eq 'klomelbek') {
        $normalized = 'trex'
    }

    $normalized = $normalized -replace '^https?://', ''
    $normalized = ($normalized -split '/', 2)[0]
    if ($normalized.EndsWith('.synerioncloud.com')) {
        $normalized = $normalized.Substring(0, $normalized.Length - '.synerioncloud.com'.Length)
    }
    $normalized = $normalized.Trim('.')

    if ($normalized -notmatch '^[a-z0-9-]+$') {
        return $null
    }

    return $normalized
}

function Get-PersistedSite {
    if (Test-Path -LiteralPath $siteConfigPath) {
        $value = Get-Content -LiteralPath $siteConfigPath -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return Normalize-SitePrefix $value
        }
    }
    return $null
}

function Set-PersistedSite([string]$Site) {
    $normalized = Normalize-SitePrefix $Site
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        throw 'Invalid site prefix'
    }
    Set-Content -LiteralPath $siteConfigPath -Value $normalized -Encoding UTF8
}

if (-not (Test-Path $appExe) -and -not (Test-Path $distExe) -and -not (Test-Path $pythonExe)) {
    Write-Host '[ERROR] Release EXE and development environment were not found.'
    Write-Host 'End user: run the files from the release folder.'
    Write-Host 'Developer: run setup.bat first.'
    exit 1
}

$site = if ([string]::IsNullOrWhiteSpace($Site)) { Get-PersistedSite } else { $Site.Trim().ToLowerInvariant() }
if ([string]::IsNullOrWhiteSpace($site)) {
    $site = 'prologic'
}
$site = Normalize-SitePrefix $site
if ([string]::IsNullOrWhiteSpace($site)) {
    Write-Host "[ERROR] Invalid site. Use only the part before .synerioncloud.com, for example: prologic"
    exit 1
}
Set-PersistedSite $site

if ($Mode -in @('summary', 'auto')) {
    if ([string]::IsNullOrWhiteSpace($PdfPath)) {
        $pdfPath = & $selectPdfScript
    } else {
        $pdfPath = $PdfPath
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
}
Write-Host "Site selected: $site"
Write-Host ''

$modeFlag = switch ($Mode) {
    'summary' { '--summary-only' }
    'verify' { '--verify' }
    'auto' { '--auto' }
}

$cliTokens = @($modeFlag, '--site', $site)
if (-not [string]::IsNullOrWhiteSpace($pdfPath)) {
    $cliTokens += @('--pdf', $pdfPath)
}

if (Test-Path $appExe) {
    & $appExe @cliTokens
    exit $LASTEXITCODE
}

if (Test-Path $distExe) {
    & $distExe @cliTokens
    exit $LASTEXITCODE
}

& $pythonExe $attendPy @cliTokens
exit $LASTEXITCODE