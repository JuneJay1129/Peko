#!/bin/bash
# 双击本文件即可启动 Peko。
#
# 为什么需要这一步：macOS 会给「从网上下载」的文件打上 com.apple.quarantine
# 标记，而 Peko 是 ad-hoc 签名（个人项目，没买 Apple 开发者证书，$99/年），
# 过不了系统的公证（notarization）检查。所以双击 Peko.app 会被判成
# 「已损坏，无法打开」，而且右键打开也绕不过去。
# 这个脚本只做一件事：清掉隔离标记再启动。清一次就够，以后直接双击 Peko.app。

cd "$(dirname "$0")" || exit 1

APP=""
for candidate in Peko.app Peko-Intel.app Peko-AppleSilicon.app; do
    if [ -d "$candidate" ]; then
        APP="$candidate"
        break
    fi
done
if [ -z "$APP" ]; then
    APP="$(/bin/ls -d ./*.app 2>/dev/null | head -n 1)"
fi

if [ -z "$APP" ]; then
    echo "没找到 Peko.app。"
    echo "请把本脚本和 Peko.app 放在同一个文件夹里，再双击本脚本。"
    read -r -p "按回车关闭窗口..." _
    exit 1
fi

echo "正在解除系统隔离标记: $APP"
/usr/bin/xattr -cr "$APP" || echo "清理失败，可手动执行: xattr -cr \"$APP\""

echo "正在启动 Peko ..."
/usr/bin/open "$APP"

echo ""
echo "如果 Peko 已经起来，这个窗口可以关掉；以后直接双击 Peko.app 就行。"
sleep 2
