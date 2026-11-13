param([switch]$SkipTests)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if ($env:OS -ne 'Windows_NT') { throw 'This build must run on Windows.' }

function Invoke-Python {
    param([string[]]$PythonArgs)
    & $script:PythonPath @PythonArgs
    if ($LASTEXITCODE -ne 0) { throw "Python command failed ($LASTEXITCODE)." }
}

function Invoke-SelfTest {
    param([string]$Executable, [string]$Report)
    $process = Start-Process -FilePath $Executable -ArgumentList @('--self-test', '--report', "`"$Report`"") -PassThru
    if (-not $process.WaitForExit(120000)) {
        Stop-Process -Id $process.Id -ErrorAction SilentlyContinue
        throw "Packaged startup check timed out: $Executable"
    }
    if ($process.ExitCode -ne 0 -or -not (Test-Path $Report)) {
        throw "Packaged startup check failed: $Executable"
    }
    $result = Get-Content $Report -Raw | ConvertFrom-Json
    if (-not $result.ok) { throw $result.error }
}

function Find-InnoCompiler {
    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }
    foreach ($base in @(${env:ProgramFiles(x86)}, $env:ProgramFiles)) {
        if (-not $base) { continue }
        foreach ($version in @('Inno Setup 6', 'Inno Setup 7')) {
            $candidate = Join-Path $base "$version\ISCC.exe"
            if (Test-Path $candidate) { return $candidate }
        }
    }
    throw 'Inno Setup 6 or 7 is required. Install it from https://jrsoftware.org/isinfo.php.'
}

if (-not (Test-Path '.venv-win/Scripts/python.exe')) {
    py -3.12 -m venv .venv-win
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 x64 with the Python launcher first.' }
}
$script:PythonPath = (Resolve-Path '.venv-win/Scripts/python.exe').Path
Invoke-Python -PythonArgs @('-m', 'pip', 'install', '-r', 'packaging/requirements-build.txt')
if (-not $SkipTests) {
    $env:QT_QPA_PLATFORM = 'offscreen'
    try { Invoke-Python -PythonArgs @('-m', 'unittest', 'discover', '-s', 'tests', '-q') }
    finally { Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue }
}
Invoke-Python -PythonArgs @('-m', 'PyInstaller', '--clean', '--noconfirm', 'packaging/DeskPaw.spec')
$exe = (Resolve-Path 'dist/DeskPaw.exe').Path
$report = Join-Path (Get-Location) 'dist/windows-self-test.json'
Invoke-SelfTest -Executable $exe -Report $report
Get-FileHash $exe -Algorithm SHA256 | Format-List
Compress-Archive -Path $exe, 'docs/WINDOWS.md' -DestinationPath 'dist/DeskPaw-Windows-x64.zip' -Force

$iscc = Find-InnoCompiler
& $iscc 'packaging/DeskPaw.iss'
if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed ($LASTEXITCODE)." }
$setup = (Resolve-Path 'dist/DeskPaw-Setup-x64.exe').Path
Get-FileHash $setup -Algorithm SHA256 | Format-List

$installDir = Join-Path $env:TEMP ("DeskPaw-install-smoke-" + [guid]::NewGuid().ToString('N'))
$install = Start-Process -FilePath $setup -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/NOICONS', "/DIR=`"$installDir`"") -Wait -PassThru
if ($install.ExitCode -ne 0) { throw "Installer smoke check failed ($($install.ExitCode))." }
$installedExe = Join-Path $installDir 'DeskPaw.exe'
if (-not (Test-Path $installedExe)) { throw 'Installer did not place DeskPaw.exe in the target directory.' }
$installedReport = Join-Path (Get-Location) 'dist/windows-installer-self-test.json'
Invoke-SelfTest -Executable $installedExe -Report $installedReport
$uninstaller = Get-ChildItem -Path $installDir -Filter 'unins*.exe' -File | Select-Object -First 1
if (-not $uninstaller) { throw 'Installer did not create an uninstaller.' }
$uninstall = Start-Process -FilePath $uninstaller.FullName -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART') -Wait -PassThru
if ($uninstall.ExitCode -ne 0 -or (Test-Path $installedExe)) { throw 'Uninstaller smoke check failed.' }
Write-Host 'Ready: dist/DeskPaw-Setup-x64.exe, dist/DeskPaw.exe, and dist/DeskPaw-Windows-x64.zip'
