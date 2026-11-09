# -*- mode: python ; coding: utf-8 -*-
import os
import sys

# 打包时资源路径：以项目根目录为基准，保证本地与 CI 下都能正确包含 pets/config
_spec_dir = os.path.dirname(os.path.abspath(SPEC))
_project_root = os.path.dirname(_spec_dir)

# 打包图标：macOS 只认 .icns（PyInstaller 在 darwin 上不接受 .ico，缺省用默认图标）；
# Windows 用 icon.ico（或 inco.ico）。统一放在项目根目录。
if sys.platform == 'darwin':
    exe_icon = os.path.join(_project_root, 'icon.icns') if os.path.isfile(os.path.join(_project_root, 'icon.icns')) else None
elif os.path.isfile(os.path.join(_project_root, 'icon.ico')):
    exe_icon = os.path.join(_project_root, 'icon.ico')
elif os.path.isfile(os.path.join(_project_root, 'inco.ico')):
    exe_icon = os.path.join(_project_root, 'inco.ico')
else:
    exe_icon = None

_datas = [
    (os.path.join(_project_root, 'pets'), 'pets'),
    (os.path.join(_project_root, 'config'), 'config'),
    (os.path.join(_project_root, 'peko', 'ui', 'plans'), 'peko/ui/plans'),
]
if exe_icon:
    _datas.append((exe_icon, '.'))

# 跨平台 hiddenimports；keyboard 仅 Windows 支持（macOS 未安装时避免 PyInstaller 告警）
_hidden = [
    'PyQt5.QtCore',
    'PyQt5.QtGui',
    'PyQt5.QtWidgets',
    'PyQt5.QtWebEngineWidgets',
    'PyQt5.QtWebEngineCore',
    'PyQt5.QtWebChannel',
    'openai',
    'pynput',
    'pynput.keyboard',
    'pynput._util',
    'requests',
]
_excludes = []
if sys.platform == 'win32':
    _hidden.append('keyboard')
else:
    # keyboard 库只有 Windows 实现，代码里那两处 import 也都包在
    # sys.platform == "win32" 里；但 PyInstaller 只看静态 import，在 mac
    # 构建机上会一路告警（还可能把缺包的坑留到运行时），这里显式排除。
    _excludes.append('keyboard')

if sys.platform == 'darwin':
    # pynput 在 mac 上靠 CGEventTap 收键，真正干活的是 _darwin 子模块，
    # 底下依赖 pyobjc 的几个 framework 包。PyInstaller 的 hook 只兜住一部分，
    # 漏一个的后果就是「键盘模式开不了」，甚至第一次点开关就崩。
    _hidden += [
        'pynput.keyboard._darwin',
        'pynput.mouse._darwin',
        'pynput._util.darwin',
        'objc',
        'HIServices',
        'Quartz',
        'AppKit',
        'Foundation',
        'CoreFoundation',
        'Carbon',
    ]

a = Analysis(
    [os.path.join(_project_root, 'main.py')],
    pathex=[_project_root],
    binaries=[],
    datas=_datas,
    hiddenimports=_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

if sys.platform == 'darwin':
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='Peko',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        # UPX 压 Mach-O 是 macOS 上的经典崩溃源（还会破坏签名），
        # 体积换稳定不值当，mac 一律不压
        upx=False,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        # ad-hoc 签名：Apple Silicon 上未签名的 arm64 二进制会被内核直接拒绝
        codesign_identity='-',
        entitlements_file=None,
        icon=exe_icon,
    )
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name='Peko',
    )
    app = BUNDLE(
        coll,
        name='Peko.app',
        icon=exe_icon,
    )
else:
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
