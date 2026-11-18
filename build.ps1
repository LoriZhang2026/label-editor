$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:PYINSTALLER_CONFIG_DIR = Join-Path $PSScriptRoot 'build/pyinstaller-cache'
$pythonPath = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create .venv and install requirements-dev.txt before building.'
}
& $pythonPath scripts/make_sample.py
if ($LASTEXITCODE -ne 0) { throw 'Sample generation failed.' }
& $pythonPath scripts/make_font_sample.py
if ($LASTEXITCODE -ne 0) { throw 'Font fixture generation failed.' }
& $pythonPath scripts/make_icon.py
if ($LASTEXITCODE -ne 0) { throw 'Icon generation failed.' }
$priorBuildSearchPath = $env:PATH
try {
    # Prevent unrelated tools (e.g. Poppler) from shadowing Windows' ICU DLL.
    $env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$PSScriptRoot\.venv\Scripts"
    & $pythonPath -m PyInstaller --noconfirm --clean --windowed --onedir --name 'LabelEditor' --icon assets/app.ico --add-data 'assets;assets' --collect-submodules fontTools.ttLib.tables --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets main.py
    if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
} finally {
    $env:PATH = $priorBuildSearchPath
}
& $pythonPath scripts/prepare_release.py
if ($LASTEXITCODE -ne 0) { throw 'Release preparation failed.' }
Write-Host 'Built: dist/LabelEditor/LabelEditor.exe'
