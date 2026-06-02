$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$RequirementsFile = Join-Path $Root "requirements.txt"
$RequirementMarker = Join-Path $VenvDir ".requirements.sha256"
$AppUrl = "http://127.0.0.1:8765"
$ToolsDir = Join-Path $Root "tools"
$DownloadDir = Join-Path $ToolsDir "downloads"
$PythonInstallerUrl = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
$PythonInstallerFile = Join-Path $DownloadDir "python-3.12.10-amd64.exe"
$PythonInstallDir = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312"
$FfmpegZipUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
$FfmpegZipFile = Join-Path $DownloadDir "ffmpeg-release-essentials.zip"
$FfmpegExtractDir = Join-Path $ToolsDir "ffmpeg-extract"
$FfmpegLocalDir = Join-Path $ToolsDir "ffmpeg"

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

function Ensure-Directory {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Invoke-Download {
    param(
        [string]$Url,
        [string]$OutputPath,
        [string]$ErrorMessage
    )

    Ensure-Directory -Path (Split-Path -Parent $OutputPath)
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

    try {
        Invoke-WebRequest -Uri $Url -OutFile $OutputPath -UseBasicParsing
    } catch {
        throw "$ErrorMessage $($_.Exception.Message)"
    }

    if (-not (Test-Path $OutputPath)) {
        throw $ErrorMessage
    }
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

    $knownRoots = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python"),
        $env:ProgramFiles
    )

    foreach ($knownRoot in $knownRoots) {
        if (-not $knownRoot -or -not (Test-Path $knownRoot)) {
            continue
        }

        $matches = Get-ChildItem -Path $knownRoot -Directory -Filter "Python*" -ErrorAction SilentlyContinue |
            Sort-Object -Property Name -Descending

        foreach ($match in $matches) {
            $candidate = Join-Path $match.FullName "python.exe"
            if ((Test-Path $candidate) -and (Test-PythonCandidate -Exe $candidate)) {
                return @{ Exe = $candidate; Args = @() }
            }
        }
    }

    return $null
}

function Install-PythonFromOfficialInstaller {
    Write-Step "Trying direct Python download from python.org"
    Invoke-Download `
        -Url $PythonInstallerUrl `
        -OutputPath $PythonInstallerFile `
        -ErrorMessage "Could not download Python installer."

    Ensure-Directory -Path $PythonInstallDir
    $installerArgs = "/quiet InstallAllUsers=0 InstallLauncherAllUsers=0 Include_launcher=1 Include_pip=1 Include_test=0 PrependPath=1 TargetDir=`"$PythonInstallDir`""
    $process = Start-Process `
        -FilePath $PythonInstallerFile `
        -ArgumentList $installerArgs `
        -Wait `
        -PassThru

    if ($process.ExitCode -ne 0 -and $process.ExitCode -ne 3010) {
        throw "Python installer failed with exit code $($process.ExitCode). Install Python 3.10+ manually: https://www.python.org/downloads/"
    }

    Remove-Item -LiteralPath $PythonInstallerFile -Force -ErrorAction SilentlyContinue
}

function Ensure-Python {
    $python = Get-PythonCandidate
    if ($python) {
        return $python
    }

    $installed = $false

    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Step "Python 3.10+ was not found. Trying winget install"
        & winget @(
            "install",
            "--id", "Python.Python.3.12",
            "-e",
            "--source", "winget",
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--silent"
        )
        $installed = ($LASTEXITCODE -eq 0)
    }

    if (-not $installed -and (Get-Command choco -ErrorAction SilentlyContinue)) {
        Write-Step "Trying Chocolatey install for Python"
        Invoke-Checked `
            -Exe "choco" `
            -Arguments @("install", "python", "-y", "--no-progress") `
            -ErrorMessage "Chocolatey could not install Python. Install Python 3.10+ manually and run start.bat again."
        $installed = $true
    }

    if (-not $installed) {
        Install-PythonFromOfficialInstaller
        $installed = $true
    }

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

function Install-LocalFfmpeg {
    Write-Step "Trying direct ffmpeg download"
    Invoke-Download `
        -Url $FfmpegZipUrl `
        -OutputPath $FfmpegZipFile `
        -ErrorMessage "Could not download ffmpeg."

    if (Test-Path $FfmpegExtractDir) {
        Remove-Item -LiteralPath $FfmpegExtractDir -Recurse -Force
    }

    Expand-Archive -LiteralPath $FfmpegZipFile -DestinationPath $FfmpegExtractDir -Force
    $ffmpegExe = Get-ChildItem -Path $FfmpegExtractDir -Filter "ffmpeg.exe" -File -Recurse -ErrorAction SilentlyContinue |
        Select-Object -First 1

    if (-not $ffmpegExe) {
        throw "ffmpeg archive was downloaded but ffmpeg.exe was not found."
    }

    $sourceBinDir = Split-Path -Parent $ffmpegExe.FullName

    if (Test-Path $FfmpegLocalDir) {
        Remove-Item -LiteralPath $FfmpegLocalDir -Recurse -Force
    }

    Ensure-Directory -Path (Join-Path $FfmpegLocalDir "bin")
    Copy-Item -LiteralPath (Join-Path $sourceBinDir "ffmpeg.exe") -Destination (Join-Path $FfmpegLocalDir "bin\ffmpeg.exe") -Force

    $ffprobeSource = Join-Path $sourceBinDir "ffprobe.exe"
    if (Test-Path $ffprobeSource) {
        Copy-Item -LiteralPath $ffprobeSource -Destination (Join-Path $FfmpegLocalDir "bin\ffprobe.exe") -Force
    }

    if (Test-Path $FfmpegExtractDir) {
        Remove-Item -LiteralPath $FfmpegExtractDir -Recurse -Force
    }

    Remove-Item -LiteralPath $FfmpegZipFile -Force -ErrorAction SilentlyContinue
}

function Ensure-Ffmpeg {
    $ffmpeg = Find-Ffmpeg
    if (-not $ffmpeg) {
        $installed = $false

        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Write-Step "ffmpeg was not found. Trying winget install"
            & winget @(
                "install",
                "--id", "Gyan.FFmpeg",
                "-e",
                "--source", "winget",
                "--accept-package-agreements",
                "--accept-source-agreements",
                "--silent"
            )
            $installed = ($LASTEXITCODE -eq 0)
        }

        if (-not $installed -and (Get-Command choco -ErrorAction SilentlyContinue)) {
            Write-Step "Trying Chocolatey install for ffmpeg"
            Invoke-Checked `
                -Exe "choco" `
                -Arguments @("install", "ffmpeg", "-y", "--no-progress") `
                -ErrorMessage "Chocolatey could not install ffmpeg. Install ffmpeg manually and add it to PATH."
            $installed = $true
        }

        if (-not $installed) {
            Install-LocalFfmpeg
            $installed = $true
        }

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
