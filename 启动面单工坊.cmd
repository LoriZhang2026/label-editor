@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "dist\LabelEditor\LabelEditor.exe" (
    start "" "dist\LabelEditor\LabelEditor.exe" %*
) else (
    if exist ".venv\Scripts\pythonw.exe" (
        start "" ".venv\Scripts\pythonw.exe" "main.py" %*
    ) else (
        echo 未找到程序，请先完成构建。
        pause
    )
)
