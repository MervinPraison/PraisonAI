# PraisonAI Installer for Windows
# Usage: iwr -useb https://praison.ai/install.ps1 | iex
#
# Parameters:
#   -Version      Specific version to install (default: latest)
#   -Extras       Comma-separated extras (e.g., "ui,chat,code")
#   -NoVenv       Skip virtual environment creation
#   -Python       Path to Python executable
#   -DryRun       Print what would happen without making changes
#   -Help         Show help message

param(
    [string]$Version = "latest",
    [string]$Extras = "",
    [switch]$NoVenv,
    [string]$Python = "",
    [switch]$DryRun,
    [switch]$Help
)

# Environment variable overrides
if ($env:PRAISONAI_VERSION) { $Version = $env:PRAISONAI_VERSION }
if ($env:PRAISONAI_EXTRAS) { $Extras = $env:PRAISONAI_EXTRAS }
if ($env:PRAISONAI_SKIP_VENV -eq "1") { $NoVenv = $true }
if ($env:PRAISONAI_PYTHON) { $Python = $env:PRAISONAI_PYTHON }
if ($env:PRAISONAI_DRY_RUN -eq "1") { $DryRun = $true }

$MinPythonVersion = [version]"3.10"
$VenvDir = "$env:USERPROFILE\.praisonai\venv"

function Write-Banner {
    Write-Host ""
    Write-Host "╔═══════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║                                                           ║" -ForegroundColor Cyan
    Write-Host "║   PraisonAI - AI Agents Made Simple                       ║" -ForegroundColor Cyan
    Write-Host "║                                                           ║" -ForegroundColor Cyan
    Write-Host "║   Works everywhere. Installs everything. You're welcome.  ║" -ForegroundColor Cyan
    Write-Host "║                                                           ║" -ForegroundColor Cyan
    Write-Host "╚═══════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Info {
    param([string]$Message)
    Write-Host "==> " -ForegroundColor Blue -NoNewline
    Write-Host $Message
}

function Write-Success {
    param([string]$Message)
    Write-Host "✓ " -ForegroundColor Green -NoNewline
    Write-Host $Message
}

function Write-Warning {
    param([string]$Message)
    Write-Host "⚠ " -ForegroundColor Yellow -NoNewline
    Write-Host $Message
}

function Write-Error {
    param([string]$Message)
    Write-Host "✗ " -ForegroundColor Red -NoNewline
    Write-Host $Message
}

function Write-Step {
    param([string]$Message)
    Write-Host "→ " -ForegroundColor Cyan -NoNewline
    Write-Host $Message
}

function Show-Help {
    Write-Host "PraisonAI Installer for Windows"
    Write-Host ""
    Write-Host "Usage: iwr -useb https://praison.ai/install.ps1 | iex"
    Write-Host "       & ([scriptblock]::Create((iwr -useb https://praison.ai/install.ps1))) [OPTIONS]"
    Write-Host ""
    Write-Host "Options:"
    Write-Host "  -Version VERSION    Install specific version (default: latest)"
    Write-Host "  -Extras EXTRAS      Install with extras (e.g., ui,chat,code)"
    Write-Host "  -NoVenv             Skip virtual environment creation"
    Write-Host "  -Python PATH        Use specific Python executable"
    Write-Host "  -DryRun             Print what would happen without making changes"
    Write-Host "  -Help               Show this help message"
    Write-Host ""
    Write-Host "Environment variables:"
    Write-Host "  PRAISONAI_VERSION    Specific version to install"
    Write-Host "  PRAISONAI_EXTRAS     Comma-separated extras"
    Write-Host "  PRAISONAI_SKIP_VENV  Skip virtual environment (1 to enable)"
    Write-Host "  PRAISONAI_PYTHON     Path to Python executable"
    Write-Host "  PRAISONAI_DRY_RUN    Print what would happen (1 to enable)"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  # Basic install"
    Write-Host "  iwr -useb https://praison.ai/install.ps1 | iex"
    Write-Host ""
    Write-Host "  # Install with extras"
    Write-Host '  & ([scriptblock]::Create((iwr -useb https://praison.ai/install.ps1))) -Extras "ui,chat"'
    Write-Host ""
}

function Test-PythonVersion {
    param([string]$PythonPath)
    
    try {
        $versionOutput = & $PythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($versionOutput) {
            $version = [version]$versionOutput
            return $version -ge $MinPythonVersion
        }
    } catch {
        return $false
    }
    return $false
}

function Find-Python {
    # Check user-specified Python first
    if ($Python -and (Test-Path $Python)) {
        if (Test-PythonVersion $Python) {
            return $Python
        }
    }
    
    # Try common Python commands
    $pythonCommands = @("python", "python3", "py -3.12", "py -3.11", "py -3.10", "py")
    
    foreach ($cmd in $pythonCommands) {
        try {
            $cmdParts = $cmd -split " "
            $exe = $cmdParts[0]
            $args = if ($cmdParts.Length -gt 1) { $cmdParts[1..($cmdParts.Length-1)] } else { @() }
            
            if (Get-Command $exe -ErrorAction SilentlyContinue) {
                $fullCmd = if ($args) { "$exe $($args -join ' ')" } else { $exe }
                if (Test-PythonVersion $fullCmd) {
                    return $fullCmd
                }
            }
        } catch {
            continue
        }
    }
    
    return $null
}

function Install-Python {
    Write-Info "Python $MinPythonVersion+ not found. Installing..."
    
    # Try winget first
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Step "Installing Python via winget..."
        if ($DryRun) {
            Write-Info "[DRY RUN] Would run: winget install Python.Python.3.12"
        } else {
            winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements
        }
        return
    }
    
    # Try Chocolatey
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        Write-Step "Installing Python via Chocolatey..."
        if ($DryRun) {
            Write-Info "[DRY RUN] Would run: choco install python -y"
        } else {
            choco install python -y
        }
        return
    }
    
    # Try Scoop
    if (Get-Command scoop -ErrorAction SilentlyContinue) {
        Write-Step "Installing Python via Scoop..."
        if ($DryRun) {
            Write-Info "[DRY RUN] Would run: scoop install python"
        } else {
            scoop install python
        }
        return
    }
    
    Write-Error "Could not find a package manager (winget, choco, or scoop)."
    Write-Host "Please install Python $MinPythonVersion+ manually from: https://www.python.org/downloads/"
    exit 1
}

function Ensure-Python {
    Write-Info "Checking Python installation..."
    
    $pythonCmd = Find-Python
    
    if ($pythonCmd) {
        $version = & $pythonCmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
        Write-Success "Python $version found: $pythonCmd"
        return $pythonCmd
    }
    
    Install-Python
    
    # Refresh PATH
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    
    $pythonCmd = Find-Python
    if ($pythonCmd) {
        Write-Success "Python installed successfully"
        return $pythonCmd
    }
    
    Write-Error "Failed to install Python. Please install Python $MinPythonVersion+ manually."
    exit 1
}

function Ensure-Pip {
    param([string]$PythonCmd)
    
    Write-Info "Checking pip..."
    
    try {
        & $PythonCmd -m pip --version 2>$null | Out-Null
        Write-Success "pip is available"
        return
    } catch {}
    
    Write-Step "Installing pip..."
    
    if ($DryRun) {
        Write-Info "[DRY RUN] Would install pip"
        return
    }
    
    # Try ensurepip
    try {
        & $PythonCmd -m ensurepip --upgrade 2>$null
        Write-Success "pip installed via ensurepip"
        return
    } catch {}
    
    # Fall back to get-pip.py
    $getPipUrl = "https://bootstrap.pypa.io/get-pip.py"
    $getPipPath = "$env:TEMP\get-pip.py"
    Invoke-WebRequest -Uri $getPipUrl -OutFile $getPipPath
    & $PythonCmd $getPipPath
    Remove-Item $getPipPath -ErrorAction SilentlyContinue
    Write-Success "pip installed via get-pip.py"
}

function Create-Venv {
    param([string]$PythonCmd)
    
    if ($NoVenv) {
        Write-Info "Skipping virtual environment (NoVenv specified)"
        return $null
    }
    
    Write-Info "Creating virtual environment..."
    
    if ($DryRun) {
        Write-Info "[DRY RUN] Would create venv at: $VenvDir"
        return $VenvDir
    }
    
    $parentDir = Split-Path $VenvDir -Parent
    if (-not (Test-Path $parentDir)) {
        New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }
    
    if (Test-Path $VenvDir) {
        Write-Step "Virtual environment already exists at $VenvDir"
    } else {
        & $PythonCmd -m venv $VenvDir
        Write-Success "Virtual environment created at $VenvDir"
    }
    
    return $VenvDir
}

function Install-PraisonAI {
    param(
        [string]$PythonCmd,
        [string]$VenvPath
    )
    
    Write-Info "Installing PraisonAI..."
    
    $pipCmd = "$PythonCmd -m pip"
    
    # Use venv pip if available
    if ($VenvPath -and (Test-Path "$VenvPath\Scripts\pip.exe")) {
        $pipCmd = "$VenvPath\Scripts\pip.exe"
    }
    
    # Build install package name
    $installPkg = "praisonaiagents"
    if ($Version -ne "latest") {
        $installPkg = "praisonaiagents==$Version"
    }
    
    # Add extras if specified
    if ($Extras) {
        $installPkg = "praisonaiagents[$Extras]"
        if ($Version -ne "latest") {
            $installPkg = "praisonaiagents[$Extras]==$Version"
        }
    }
    
    if ($DryRun) {
        Write-Info "[DRY RUN] Would run: $pipCmd install --upgrade $installPkg"
        return
    }
    
    # Upgrade pip first
    Invoke-Expression "$pipCmd install --upgrade pip"
    
    # Install PraisonAI
    Invoke-Expression "$pipCmd install --upgrade $installPkg"
    
    # Also install wrapper if extras include ui/chat/code
    if ($Extras -match "ui|chat|code") {
        $wrapperPkg = "praisonai[$Extras]"
        if ($Version -ne "latest") {
            $wrapperPkg = "praisonai[$Extras]==$Version"
        }
        Invoke-Expression "$pipCmd install --upgrade $wrapperPkg"
    }
    
    Write-Success "PraisonAI installed successfully!"
}

function Setup-Path {
    param([string]$VenvPath)
    
    if ($NoVenv -or -not $VenvPath) {
        return
    }
    
    Write-Info "Setting up PATH..."
    
    $binDir = "$VenvPath\Scripts"
    
    if ($DryRun) {
        Write-Info "[DRY RUN] Would add to PATH: $binDir"
        return
    }
    
    # Check if already in PATH
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($currentPath -notlike "*$binDir*") {
        $newPath = "$binDir;$currentPath"
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Success "Added PraisonAI to user PATH"
    } else {
        Write-Step "PATH already configured"
    }
    
    # Update current session
    $env:Path = "$binDir;$env:Path"
}

function Test-Installation {
    param([string]$VenvPath)
    
    Write-Info "Verifying installation..."
    
    if ($DryRun) {
        Write-Info "[DRY RUN] Would verify installation"
        return
    }
    
    $pythonCmd = "python"
    if ($VenvPath -and (Test-Path "$VenvPath\Scripts\python.exe")) {
        $pythonCmd = "$VenvPath\Scripts\python.exe"
    }
    
    try {
        $version = & $pythonCmd -c "import praisonaiagents; print(f'Version: {praisonaiagents.__version__}')" 2>$null
        if ($version) {
            Write-Success "PraisonAI agents package verified: $version"
        }
    } catch {
        Write-Error "Failed to import praisonaiagents"
        exit 1
    }
    
    # Check CLI
    if (Get-Command praisonai -ErrorAction SilentlyContinue) {
        $cliVersion = & praisonai --version 2>$null | Select-Object -First 1
        Write-Success "CLI available: praisonai $cliVersion"
    }
}

function Show-NextSteps {
    param([string]$VenvPath)
    
    Write-Host ""
    Write-Host "Installation complete!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor White
    Write-Host ""
    
    if ($VenvPath -and -not $NoVenv) {
        Write-Host "  1. Activate the virtual environment:"
        Write-Host "     $VenvPath\Scripts\Activate.ps1" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "  2. Or restart your terminal to use PraisonAI globally"
        Write-Host ""
    }
    
    Write-Host "  Quick start:"
    Write-Host '     python -c "from praisonaiagents import Agent; Agent(name=''test'').start(''Hello!'')"' -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Documentation:"
    Write-Host "     https://docs.praison.ai" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Set your API key:"
    Write-Host '     $env:OPENAI_API_KEY = "your_key"' -ForegroundColor Cyan
    Write-Host ""
}

# Main
function Main {
    if ($Help) {
        Show-Help
        return
    }
    
    Write-Banner
    
    Write-Info "Detected OS: Windows"
    
    if ($DryRun) {
        Write-Warning "Running in DRY RUN mode - no changes will be made"
    }
    
    # Ensure Python
    $pythonCmd = Ensure-Python
    
    # Ensure pip
    Ensure-Pip $pythonCmd
    
    # Create virtual environment
    $venvPath = Create-Venv $pythonCmd
    
    # Install PraisonAI
    Install-PraisonAI $pythonCmd $venvPath
    
    # Setup PATH
    Setup-Path $venvPath
    
    # Verify installation
    Test-Installation $venvPath
    
    # Show next steps
    Show-NextSteps $venvPath
}

Main
