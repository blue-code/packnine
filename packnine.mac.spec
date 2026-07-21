# -*- mode: python ; coding: utf-8 -*-
# PackNine macOS 배포용 PyInstaller 빌드 스펙 (Apple Silicon / arm64).
# 실행: python -m PyInstaller packnine.mac.spec --noconfirm
#
# packnine.spec(Windows)과 Analysis/PYZ 단계는 동일하고, 마지막 패키징 단계만
# EXE 단일 파일 대신 BUNDLE()로 PackNine.app을 만든다는 점이 다르다.

import pathlib
import tomllib


def _read_version_from_pyproject() -> str:
    # CFBundleShortVersionString을 pyproject.toml [project].version과 이중 관리하지
    # 않기 위해 spec 파일에서 직접 읽어온다.
    pyproject_path = pathlib.Path(SPECPATH) / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    return data["project"]["version"]


a = Analysis(
    ['packnine/main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('packnine/presentation/gui/assets/icon.icns', 'packnine/presentation/gui/assets'),
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
    [],
    exclude_binaries=True,
    name='PackNine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='packnine/presentation/gui/assets/icon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='PackNine',
)

app = BUNDLE(
    coll,
    name='PackNine.app',
    icon='packnine/presentation/gui/assets/icon.icns',
    bundle_identifier='com.packnine.app',
    info_plist={
        'CFBundleShortVersionString': _read_version_from_pyproject(),
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '11.0',
    },
)
