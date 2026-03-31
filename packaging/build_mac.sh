#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "正在打包 Peko（macOS .app）..."
pip install -q -r requirements.txt
pip install -q pyinstaller Pillow
export MACOSX_DEPLOYMENT_TARGET=10.15
pyinstaller packaging/main.spec

echo ""
echo "打包完成。应用包：dist/Peko.app"
echo "使用方式：将 Peko.app 解压/拷贝到本地可写目录后，直接在 Finder 中双击运行。"
echo "若首次运行被 Gatekeeper 拦截，请在“系统设置 -> 隐私与安全性”中允许后再次打开。"
echo "首次运行后，会在 Peko.app 同级目录自动创建 config，并写入 api.json / secrets.json 模板。"
