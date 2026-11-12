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
APP_NAME=""
ZIP_NAME=""
if [ -d "dist/Peko.app" ]; then
    # 重命名带架构标识，方便区分
    cd dist
    if [ "$ARCH_NAME" = "x86_64" ]; then
        mv Peko.app Peko-Intel.app
        APP_NAME="Peko-Intel.app"
        ZIP_NAME="Peko-macOS-Intel.zip"
        echo ""
        echo "✅ 打包完成（Intel x86_64）：dist/Peko-Intel.app"
    elif [ "$ARCH_NAME" = "arm64" ]; then
        mv Peko.app Peko-AppleSilicon.app
        APP_NAME="Peko-AppleSilicon.app"
        ZIP_NAME="Peko-macOS-AppleSilicon.zip"
        echo ""
        echo "✅ 打包完成（Apple Silicon arm64）：dist/Peko-AppleSilicon.app"
    else
        echo ""
        echo "✅ 打包完成：dist/Peko.app"
    fi
    cd ..
fi

# BUNDLE 整包重签 + 校验：PyInstaller 只签了内部二进制，整包不签的话
# 下载端会报「已损坏，无法打开」，这跟「未验证开发者」是两回事
if [ -n "$APP_NAME" ]; then
    echo ""
    echo "🔏 签名并校验 dist/$APP_NAME ..."
    codesign --force --deep --sign - "dist/$APP_NAME"
    codesign --verify --deep --strict --verbose=2 "dist/$APP_NAME"
    # ad-hoc + 未公证，spctl 一定 rejected，这里只留档
    spctl -a -vv "dist/$APP_NAME" || true

    echo ""
    echo "🗜  打包成可直接分发的 zip ..."
    bash "$SCRIPT_DIR/make_mac_zip.sh" "dist/$APP_NAME" "dist/$ZIP_NAME"
fi

echo ""
echo "分发方式：把 dist/$ZIP_NAME 直接发给朋友。"
echo "解压后里面有 Peko.app 和「首次运行.command」，让他先双击那个脚本。"
echo "脚本会清掉 macOS 下载隔离标记再启动——ad-hoc 签名的包过不了公证，"
echo "双击 .app 会被判「已损坏」，先跑一次脚本就不会了。"
echo "首次运行后，会在 ~/Library/Application Support/Peko/config 自动创建配置。"
