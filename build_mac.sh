#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
echo "正在打包 Peko（macOS）..."
pip install -q -r requirements.txt
pip install -q pyinstaller Pillow
export MACOSX_DEPLOYMENT_TARGET=10.15
pyinstaller main.spec
echo ""
echo "打包完成。可执行文件: dist/Peko（单文件，请放到桌面等目录后运行）"
echo "运行方式：在终端执行 chmod +x dist/Peko && dist/Peko，或将 Peko 拖到终端回车。"
echo "首次运行前请在 Peko 同目录下创建 config，并放入 api.json 与 secrets.json。"
