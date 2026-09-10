#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 用法：
#   ./packaging/build_mac.sh           # 用当前架构打包（默认）
#   ./packaging/build_mac.sh x86_64    # 强制打 Intel (x86_64) 包（需 Rosetta 2）
#   ./packaging/build_mac.sh arm64     # 强制打 Apple Silicon (arm64) 包
TARGET_ARCH="${1:-native}"

if [ "$TARGET_ARCH" = "x86_64" ] || [ "$TARGET_ARCH" = "arm64" ]; then
    if [ "$(uname -m)" = "$TARGET_ARCH" ]; then
        echo "当前已经是 $TARGET_ARCH 架构，直接打包"
    else
        echo "使用 Rosetta 2 切换到 $TARGET_ARCH 架构打包..."
        exec arch -"$TARGET_ARCH" /bin/bash "$0" "$TARGET_ARCH"_native
    fi
fi

echo "正在打包 Peko（macOS .app / 架构: $(uname -m)）..."
pip install -q -r requirements.txt
pip install -q pyinstaller Pillow
export MACOSX_DEPLOYMENT_TARGET=10.15
pyinstaller packaging/main.spec

# 打包完成后标记架构
ARCH_NAME="$(uname -m)"
if [ -d "dist/Peko.app" ]; then
    # 重命名带架构标识，方便区分
    cd dist
    if [ "$ARCH_NAME" = "x86_64" ]; then
        mv Peko.app Peko-Intel.app
        echo ""
        echo "✅ 打包完成（Intel x86_64）：dist/Peko-Intel.app"
    elif [ "$ARCH_NAME" = "arm64" ]; then
        mv Peko.app Peko-AppleSilicon.app
        echo ""
        echo "✅ 打包完成（Apple Silicon arm64）：dist/Peko-AppleSilicon.app"
    else
        echo ""
        echo "✅ 打包完成：dist/Peko.app"
    fi
    cd ..
fi

echo ""
echo "使用方式：将 Peko.app 拷贝到本地后，直接在 Finder 中双击运行。"
echo "若首次运行被 Gatekeeper 拦截，请在"系统设置 -> 隐私与安全性"中允许后再次打开。"
echo "首次运行后，会在 ~/Library/Application Support/Peko/config 自动创建配置。"
