# -*- mode: python ; coding: utf-8 -*-
import os
import sys

# 打包图标：Windows 用 icon.ico（或 inco.ico），macOS 用 icon.icns，放在项目根目录；有则使用，无则用默认
if sys.platform == 'darwin' and os.path.isfile('icon.icns'):
    exe_icon = 'icon.icns'
elif os.path.isfile('icon.ico'):
    exe_icon = 'icon.ico'
elif os.path.isfile('inco.ico'):
    exe_icon = 'inco.ico'
else:
    exe_icon = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('pets', 'pets'),
        ('config', 'config'),  # 打包配置模板，供首次运行复制到 exe 同目录
    ],
    hiddenimports=[
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'openai',
        'keyboard',
        'requests',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Peko',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=exe_icon,
)
