@echo off
setlocal ENABLEDELAYEDEXPANSION
chcp 65001 >nul

echo ================================
echo  Peko 打包為 Windows 可執行文件
echo ================================
echo.

REM 檢查是否在項目根目錄（是否存在 main.spec）
if not exist "main.spec" (
    echo [錯誤] 當前目錄未找到 main.spec，請在 Peko 項目根目錄運行本腳本。
    echo 當前目錄: %cd%
    goto :end_error
)

REM 顯示 Python 版本
python --version 2>nul
if errorlevel 1 (
    echo [錯誤] 未找到 python，請先安裝 Python 並配置到 PATH。
    goto :end_error
)

echo.
echo 正在安裝/檢查依賴: PyInstaller...
python -m pip install --upgrade pip >nul
if errorlevel 1 (
    echo [警告] pip 升級失敗，將繼續使用當前版本。
)

python -m pip install pyinstaller -q
if errorlevel 1 (
    echo [錯誤] 安裝 PyInstaller 失敗，請檢查網絡或 pip 配置。
    goto :end_error
)

echo.
echo 開始使用 main.spec 打包 Peko ...
pyinstaller main.spec

if errorlevel 1 (
    echo.
    echo [錯誤] 打包失敗，請查看上方 PyInstaller 日誌。
    goto :end_error
)

echo.
echo 打包完成。
if exist "dist\Peko.exe" (
    echo 可執行文件: dist\Peko.exe
) else (
    echo 未在 dist\ 下找到 Peko.exe，請檢查打包輸出。
)

echo.
echo 提示：
echo - 首次運行 exe 前，請在 exe 同目錄下準備 config\api.json 和 config\secrets.json
echo - 可從 config\api.json.example 和 config\secrets.json.example 複製後修改

goto :end_ok

:end_error
echo.
echo ========= 打包結束（失敗） =========
exit /b 1

:end_ok
echo.
echo ========= 打包結束（成功） =========
endlocal
exit /b 0
