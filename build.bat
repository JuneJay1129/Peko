@echo off
chcp 65001 >nul
echo 正在打包 Peko 为 exe ...
pip install pyinstaller -q
pyinstaller main.spec
if %ERRORLEVEL% equ 0 (
    echo.
    echo 打包完成。可执行文件: dist\Peko.exe
    echo 首次运行前请在 exe 同目录下创建 config 文件夹，并放入 api.json 与 secrets.json（可从 config\api.json.example 与 config\secrets.json.example 复制后修改）。
) else (
    echo 打包失败。
    exit /b 1
)
