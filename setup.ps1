$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$RequirementsFile = Join-Path $Root "requirements.txt"
$RequirementMarker = Join-Path $VenvDir ".requirements.sha256"
$AppUrl = "http://127.0.0.1:8765"

Set-Location $Root

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Checked {
    param(
        [string]$Exe,
        [string[]]$Arguments,
        [string]$ErrorMessage
    )

    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw $ErrorMessage
    }
}

function Update-ProcessPath {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$userPath;$machinePath"
}

function Test-PythonCandidate {
    param(
        [string]$Exe,
        [string[]]$PythonArgs = @()
    )

    try {
        & $Exe @PythonArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Get-PythonCandidate {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        if (Test-PythonCandidate -Exe "py" -PythonArgs @("-3")) {
            return @{ Exe = "py"; Args = @("-3") }
        }
    }

    if (Get-Command python -ErrorAction SilentlyContinue) {
        if (Test-PythonCandidate -Exe "python") {
            return @{ Exe = "python"; Args = @() }
        }
    }

    if (Get-Command python3 -ErrorAction SilentlyContinue) {
        if (Test-PythonCandidate -Exe "python3") {
            return @{ Exe = "python3"; Args = @() }
        }
    }

    return $null
}

function Ensure-Python {
    $python = Get-PythonCandidate
    if ($python) {
        return $python
    }

    Write-Step "Python 3.10+ was not found. Trying winget install"
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Python is missing and winget is not available. Install Python 3.10+ manually: https://www.python.org/downloads/"
    }

    Invoke-Checked `
        -Exe "winget" `
        -Arguments @(
            "install",
            "--id", "Python.Python.3.12",
            "-e",
            "--source", "winget",
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--silent"
        ) `
        -ErrorMessage "winget could not install Python. Install Python 3.10+ manually and run start.bat again."

    Update-ProcessPath
    $python = Get-PythonCandidate
    if (-not $python) {
        throw "Python was installed but is not visible in this session. Close this window and run start.bat again."
    }

    return $python
}

function Ensure-Venv {
    param($Python)

    if (Test-Path $VenvPython) {
        return
    }

    Write-Step "Creating local Python environment: .venv"
    Invoke-Checked `
        -Exe $Python.Exe `
        -Arguments @($Python.Args + @("-m", "venv", $VenvDir)) `
        -ErrorMessage "Could not create .venv."
}

function Test-PythonPackages {
    if (-not (Test-Path $VenvPython)) {
        return $false
    }

    try {
        & $VenvPython -c "import fastapi, uvicorn, jinja2, multipart, googleapiclient, google_auth_oauthlib" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Ensure-PythonPackages {
    if (-not (Test-Path $RequirementsFile)) {
        throw "requirements.txt was not found."
    }

    $currentHash = (Get-FileHash -Path $RequirementsFile -Algorithm SHA256).Hash
    $savedHash = if (Test-Path $RequirementMarker) { Get-Content $RequirementMarker -Raw } else { "" }
    $needInstall = ($currentHash.Trim() -ne $savedHash.Trim()) -or (-not (Test-PythonPackages))

    if (-not $needInstall) {
        Write-Step "Python packages are already installed"
        return
    }

    Write-Step "Installing Python packages"
    Invoke-Checked `
        -Exe $VenvPython `
        -Arguments @("-m", "pip", "install", "--disable-pip-version-check", "--upgrade", "pip") `
        -ErrorMessage "Could not upgrade pip."
    Invoke-Checked `
        -Exe $VenvPython `
        -Arguments @("-m", "pip", "install", "--disable-pip-version-check", "-r", $RequirementsFile) `
        -ErrorMessage "Could not install packages from requirements.txt."

    Set-Content -Path $RequirementMarker -Value $currentHash -Encoding ASCII
}

function Find-Ffmpeg {
    $cmd = Get-Command ffmpeg.exe -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    $knownPaths = @(
        (Join-Path $Root "tools\ffmpeg\bin\ffmpeg.exe"),
        "C:\ffmpeg\bin\ffmpeg.exe",
        (Join-Path $env:ProgramFiles "ffmpeg\bin\ffmpeg.exe")
    )

    if ($programFilesX86) {
        $knownPaths += (Join-Path $programFilesX86 "ffmpeg\bin\ffmpeg.exe")
    }

    foreach ($path in $knownPaths) {
        if ($path -and (Test-Path $path)) {
            return $path
        }
    }

    $wingetPackages = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path $wingetPackages) {
        $match = Get-ChildItem -Path $wingetPackages -Filter "ffmpeg.exe" -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($match) {
            return $match.FullName
        }
    }

    return $null
}

function Ensure-Ffmpeg {
    $ffmpeg = Find-Ffmpeg
    if (-not $ffmpeg) {
        Write-Step "ffmpeg was not found. Trying winget install"
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw "ffmpeg is missing and winget is not available. Install ffmpeg manually and add it to PATH."
        }

        Invoke-Checked `
            -Exe "winget" `
            -Arguments @(
                "install",
                "--id", "Gyan.FFmpeg",
                "-e",
                "--source", "winget",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--silent"
            ) `
            -ErrorMessage "winget could not install ffmpeg. Install ffmpeg manually and add it to PATH."

        Update-ProcessPath
        $ffmpeg = Find-Ffmpeg
    }

    if (-not $ffmpeg) {
        throw "ffmpeg was installed but ffmpeg.exe was not found. Close this window and run start.bat again."
    }

    $ffmpegDir = Split-Path -Parent $ffmpeg
    if (($env:Path -split ";") -notcontains $ffmpegDir) {
        $env:Path = "$ffmpegDir;$env:Path"
    }

    $env:FFMPEG_BIN = $ffmpeg
    $ffprobe = Join-Path $ffmpegDir "ffprobe.exe"
    if (Test-Path $ffprobe) {
        $env:FFPROBE_BIN = $ffprobe
    }

    Write-Step "ffmpeg found: $ffmpeg"
}

function Test-AppAlreadyRunning {
    try {
        $response = Invoke-WebRequest -Uri "$AppUrl/api/status" -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

try {
    Write-Step "Checking system dependencies"
    $python = Ensure-Python
    Ensure-Venv -Python $python
    Ensure-PythonPackages
    Ensure-Ffmpeg

    if (Test-AppAlreadyRunning) {
        Write-Step "App is already running: $AppUrl"
        Start-Process $AppUrl
        return
    }

    Write-Step "Starting local app: $AppUrl"
    Start-Process $AppUrl
    & $VenvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8765
} catch {
    Write-Host ""
    Write-Host "Startup error:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
