# -*- mode: python ; coding: utf-8 -*-
import os
import sys

# 打包时资源路径：以 spec 所在目录为基准，保证 CI（如 GitHub Actions）下也能正确包含 pets/config
_spec_dir = os.path.dirname(os.path.abspath(SPEC))

# 打包图标：Windows 用 icon.ico（或 inco.ico），macOS 用 icon.icns，放在项目根目录；有则使用，无则用默认
if sys.platform == 'darwin' and os.path.isfile(os.path.join(_spec_dir, 'icon.icns')):
    exe_icon = os.path.join(_spec_dir, 'icon.icns')
elif os.path.isfile(os.path.join(_spec_dir, 'icon.ico')):
    exe_icon = os.path.join(_spec_dir, 'icon.ico')
elif os.path.isfile(os.path.join(_spec_dir, 'inco.ico')):
    exe_icon = os.path.join(_spec_dir, 'inco.ico')
else:
    exe_icon = None

_datas = [
    (os.path.join(_spec_dir, 'pets'), 'pets'),
    (os.path.join(_spec_dir, 'config'), 'config'),  # 打包配置模板，供首次运行复制到 exe 同目录
]
# 托盘图标运行时需与 exe 一致，将同一图标文件打进包内根目录（与 get_app_exe_icon_path 查找一致）
if exe_icon:
    _datas.append((exe_icon, '.'))

a = Analysis(
    ['main.py'],
    pathex=[],
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
    # macOS：单文件可执行程序（与 Windows 一致），避免 BUNDLE 重组目录后找不到 _internal/Python
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
else:
    # Windows：单文件 exe
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
