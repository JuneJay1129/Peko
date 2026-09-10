#!/usr/bin/env bash
set -e

# 一键打 macOS 双架构包（Apple Silicon + Intel）
# 要求：Apple Silicon Mac + 已安装 Rosetta 2
# 用法：./packaging/build_mac_universal.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

if [ "$(uname -s)" != "Darwin" ]; then
    echo "❌ 此脚本只能在 macOS 上运行"
    exit 1
fi

if [ "$(uname -m)" != "arm64" ]; then
    echo "⚠️  当前不是 Apple Silicon Mac，只能打当前架构 ($(uname -m)) 的包"
    echo "   跳过双架构打包，直接打单架构..."
    ./packaging/build_mac.sh
    exit 0
fi

echo "========================================"
echo "  Peko macOS 双架构打包"
echo "  Apple Silicon (arm64) + Intel (x86_64)"
echo "========================================"
echo ""

# 检查 Rosetta 2
if ! arch -x86_64 /usr/bin/uname -m > /dev/null 2>&1; then
    echo "⚠️  检测到未安装 Rosetta 2，正在安装..."
    softwareupdate --install-rosetta --agree-to-license
fi

OUTPUT_DIR="dist"
mkdir -p "$OUTPUT_DIR"

# --- 第 1 步：打 Apple Silicon (arm64) 包 ---
echo ""
echo "📦 [1/2] 打包 Apple Silicon (arm64)..."
./packaging/build_mac.sh arm64

if [ ! -d "$OUTPUT_DIR/Peko-AppleSilicon.app" ]; then
    echo "❌ Apple Silicon 打包失败"
    exit 1
fi
echo "✅ Apple Silicon 打包完成"

# --- 第 2 步：打 Intel (x86_64) 包 ---
echo ""
echo "📦 [2/2] 打包 Intel (x86_64)..."
./packaging/build_mac.sh x86_64

if [ ! -d "$OUTPUT_DIR/Peko-Intel.app" ]; then
    echo "❌ Intel 打包失败"
    exit 1
fi
echo "✅ Intel 打包完成"

# --- 第 3 步：打 zip 压缩包，方便分发 ---
echo ""
echo "🗜  压缩成 zip..."
cd "$OUTPUT_DIR"

ditto -c -k --sequesterRsrc --keepParent Peko-AppleSilicon.app Peko-macOS-AppleSilicon.zip
ditto -c -k --sequesterRsrc --keepParent Peko-Intel.app Peko-macOS-Intel.zip

cd ..

echo ""
echo "========================================"
echo "  🎉 双架构打包完成！"
echo "========================================"
echo ""
echo "输出目录：$OUTPUT_DIR/"
echo ""
echo "  📦 Peko-macOS-AppleSilicon.zip  — M1/M2/M3/M4 系列芯片"
echo "  📦 Peko-macOS-Intel.zip          — Intel Core i5/i7/i9 芯片"
echo ""
echo "发给朋友前看清楚芯片类型哦~"
