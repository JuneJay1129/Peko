@echo off
setlocal ENABLEDELAYEDEXPANSION
chcp 65001 >nul

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"

echo ================================
echo  Peko Build ^(Windows^)
echo ================================
echo.

if not exist "packaging\main.spec" (
    echo [ERROR] packaging\main.spec was not found.
    echo Current directory: %cd%
    goto :end_error
)

python --version 2>nul
if errorlevel 1 (
    echo [ERROR] python was not found in PATH.
    goto :end_error
)

echo.
echo Installing/checking PyInstaller...
python -m pip install --upgrade pip >nul
if errorlevel 1 (
    echo [WARN] pip upgrade failed, continuing with the current version.
)

python -m pip install pyinstaller -q
if errorlevel 1 (
    echo [ERROR] Failed to install PyInstaller.
    goto :end_error
)

echo.
echo Building Peko with packaging\main.spec ...
pyinstaller packaging\main.spec

if errorlevel 1 (
    echo.
    echo [ERROR] Build failed. Check the PyInstaller log above.
    goto :end_error
)

echo.
echo Build completed.
if exist "dist\Peko.exe" (
    echo Output: dist\Peko.exe
) else (
    echo [WARN] dist\Peko.exe was not found. Check the build output.
)

echo.
echo Notes:
echo - On first run, the app will create config\api.json and config\secrets.json next to the exe.
echo - You can fill them using config\api.json.example and config\secrets.json.example.

goto :end_ok

:end_error
echo.
echo ========= Build Finished ^(Failed^) =========
exit /b 1

:end_ok
echo.
echo ========= Build Finished ^(Success^) =========
endlocal
exit /b 0
