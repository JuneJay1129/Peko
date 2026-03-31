# -*- mode: python ; coding: utf-8 -*-
import os
import sys

# 打包时资源路径：以项目根目录为基准，保证本地与 CI 下都能正确包含 pets/config
_spec_dir = os.path.dirname(os.path.abspath(SPEC))
_project_root = os.path.dirname(_spec_dir)

# 打包图标：Windows 用 icon.ico（或 inco.ico），macOS 用 icon.icns，统一放在项目根目录
if sys.platform == 'darwin' and os.path.isfile(os.path.join(_project_root, 'icon.icns')):
    exe_icon = os.path.join(_project_root, 'icon.icns')
elif os.path.isfile(os.path.join(_project_root, 'icon.ico')):
    exe_icon = os.path.join(_project_root, 'icon.ico')
elif os.path.isfile(os.path.join(_project_root, 'inco.ico')):
    exe_icon = os.path.join(_project_root, 'inco.ico')
else:
    exe_icon = None

_datas = [
    (os.path.join(_project_root, 'pets'), 'pets'),
    (os.path.join(_project_root, 'config'), 'config'),
]
if exe_icon:
    _datas.append((exe_icon, '.'))

a = Analysis(
    [os.path.join(_project_root, 'main.py')],
    pathex=[_project_root],
    binaries=[],
    datas=_datas,
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
    coll = COLLECT(
        exe,
        a.binaries,
        a.datas,
        strip=False,
        upx=True,
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
