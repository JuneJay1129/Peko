#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
echo "正在打包 Peko（macOS）..."
pip install -q -r requirements.txt
pip install -q pyinstaller
pyinstaller main.spec
echo ""
echo "打包完成。可执行文件: dist/Peko"
echo "首次运行前请在可执行文件同目录下创建 config，并放入 api.json 与 secrets.json（可从 config/*.example 复制后修改）。"
