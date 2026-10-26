param([ValidateSet("install","init","prepare","train","backend","frontend","test","demo","browser")][string]$Task="backend")
$ErrorActionPreference="Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
function Invoke-Checked {
    param([string]$Program,[string[]]$Arguments)
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}
$python=Join-Path (Get-Location) ".venv\Scripts\python.exe"
if ($Task -eq "install") {
    foreach ($program in @("py","node","npm.cmd","git")) {
        if (-not (Get-Command $program -ErrorAction SilentlyContinue)) { throw "Install prerequisite: $program. See README.md." }
    }
    if (-not (Test-Path $python)) { Invoke-Checked "py" @("-3.11","-m","venv",".venv") }
    Invoke-Checked $python @("-m","pip","install","pip==26.2.2","setuptools==83.0.0")
    Invoke-Checked $python @("-m","pip","install","-r","backend/requirements.txt")
    Invoke-Checked $python @("-m","pip","install","torch==2.7.0","--index-url","https://download.pytorch.org/whl/cpu")
    Invoke-Checked $python @("scripts/configure.py")
    Push-Location frontend
    try { Invoke-Checked "npm.cmd" @("ci") } finally { Pop-Location }
    Invoke-Checked $python @("scripts/init_db.py")
    exit
}
if (-not (Test-Path $python)) { throw "Python environment missing. Run .\scripts\spill.ps1 install first." }
switch ($Task) {
 "init" { Invoke-Checked $python @("scripts/configure.py"); Invoke-Checked $python @("scripts/init_db.py") }
 "prepare" {
    foreach ($name in @("click","flask","itsdangerous")) {
        $destination="ml/data/repos/$name"
        if (-not (Test-Path $destination)) { Invoke-Checked "git" @("clone","--depth","320","--single-branch","https://github.com/pallets/$name.git",$destination) }
    }
    Invoke-Checked $python @("-m","ml.prepare")
 }
 "train" { Invoke-Checked $python @("-m","ml.train") }
 "backend" { Invoke-Checked $python @("-m","uvicorn","backend.app.main:app","--host","127.0.0.1","--port","8000") }
 "frontend" { Push-Location frontend; try { Invoke-Checked "npm.cmd" @("run","dev") } finally { Pop-Location } }
 "test" {
    Invoke-Checked $python @("-m","pytest","tests","-q")
    Push-Location frontend
    try { Invoke-Checked "npm.cmd" @("test"); Invoke-Checked "npm.cmd" @("run","build") } finally { Pop-Location }
 }
 "demo" { Invoke-Checked $python @("-m","demo.demo_runner") }
 "browser" {
    Push-Location frontend
    try { Invoke-Checked "npx.cmd" @("playwright","install","chromium"); Invoke-Checked "npx.cmd" @("playwright","test") } finally { Pop-Location }
 }
}

