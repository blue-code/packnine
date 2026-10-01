# -*- mode: python ; coding: utf-8 -*-
# PackNine 스토어(MSIX) 배포용 PyInstaller 빌드 스펙 - 폴더(onedir) 모드.
#
# 왜 단일 파일(packnine.spec)과 따로 두는가: 단일 파일 모드는 실행할 때마다 54MB를
# 임시 폴더에 풀어내느라 기동에만 2.1~2.5초가 걸린다. 우클릭 "알아서 풀기"처럼 짧은
# 작업에서는 이 시간이 전체 체감 속도를 지배한다. 폴더 모드는 푸는 과정이 없어 즉시
# 뜨고, MSIX는 어차피 패키지 안에 파일을 펼쳐 담으므로 폴더 모드가 자연스럽다.
#
# 단일 파일 모드는 GitHub 포터블 배포(파일 하나로 받고 싶은 경우)용으로 남겨 둔다.
#
# 실행: .venv\Scripts\python.exe -m PyInstaller packnine.onedir.spec --noconfirm

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
    icon='packnine/presentation/gui/assets/icon.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='PackNine',
)
