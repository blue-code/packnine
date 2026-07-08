# -*- mode: python ; coding: utf-8 -*-
# PackNine Windows 배포용 PyInstaller 빌드 스펙.
# 실행: .venv\Scripts\python.exe -m PyInstaller packnine.spec --noconfirm

a = Analysis(
    ['packnine/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('packnine/presentation/gui/assets/icon.ico', 'packnine/presentation/gui/assets'),
        ('packnine/presentation/gui/assets/icon_256.png', 'packnine/presentation/gui/assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PackNine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='packnine/presentation/gui/assets/icon.ico',
)
