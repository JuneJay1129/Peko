#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
echo "正在打包 Peko（macOS）..."
pip install -q -r requirements.txt
pip install -q pyinstaller Pillow
# 兼容较老 macOS，减少 NSImage 等系统资源在低版本找不到导致的崩溃
export MACOSX_DEPLOYMENT_TARGET=10.15
pyinstaller main.spec
echo ""
echo "打包完成。应用包: dist/Peko.app（双击即可运行）"
echo "首次运行前请在 Peko.app 同目录下创建 config，并放入 api.json 与 secrets.json（可从 config/*.example 复制后修改）。"
