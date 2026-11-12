#!/usr/bin/env bash
# 把 .app 打成可直接分发的 zip：里面是 Peko.app + 首次运行.command + 说明
#
# 必须用 ditto 而不是 zip / cp -R：
#   - .app 里有符号链接（framework 的 Versions/Current），普通压缩会压平它们
#   - 可执行位和扩展属性也得保留，否则解出来的 app 直接是坏的
#
# 用法：bash packaging/make_mac_zip.sh dist/Peko-Intel.app dist/Peko-macOS-Intel.zip
set -euo pipefail

APP_PATH="${1:?用法: make_mac_zip.sh 路径/Peko.app 输出.zip}"
OUT_ZIP="${2:?用法: make_mac_zip.sh 路径/Peko.app 输出.zip}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# 统一命名成 Peko.app：朋友解压出来看到的就是一个能双击的 Peko
ditto "$APP_PATH" "$WORK/Peko.app"

cp "$SCRIPT_DIR/首次运行.command" "$WORK/首次运行.command"
chmod +x "$WORK/首次运行.command"
cp "$SCRIPT_DIR/首次使用说明.txt" "$WORK/首次使用说明.txt"

# 不加 --keepParent：zip 解开就是上面这三个文件，解压即用，不用再解一层
ditto -c -k --sequesterRsrc "$WORK" "$OUT_ZIP"

echo "已生成: $OUT_ZIP"
ls -lh "$OUT_ZIP"
