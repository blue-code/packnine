"""MSIX 패키지 실행 여부 판별 테스트.

스토어(MSIX)로 설치되면 레지스트리 쓰기가 패키지별로 가상화되어 탐색기에 보이지 않는다.
그래서 우클릭 메뉴/파일 연결은 런타임 등록이 아니라 매니페스트 선언으로 처리해야 하고,
런타임 등록 명령은 "성공한 척"하는 대신 명확히 거절해야 한다.
"""
from __future__ import annotations

import sys

import pytest

from packnine.infrastructure import packaged_app

# 판별은 경로 조각을 비교하는데, 비-Windows에서는 pathlib이 PosixPath라 역슬래시를 구분자로
# 보지 않는다("C:\\...\\WindowsApps\\..." 전체가 조각 하나가 된다). MSIX 자체가 Windows
# 전용이고 다른 OS에서는 항상 False면 충분하므로, 레지스트리 테스트와 같은 방식으로
# Windows에서만 돌린다.
pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="MSIX 패키지 판별은 Windows 전용 기능입니다"
)


def test_detects_windowsapps_install_path_as_packaged():
    path = r"C:\Program Files\WindowsApps\3067F945.PackNine_0.9.0.0_x64__m98x1dt5xbckc\PackNine.exe"

    assert packaged_app.is_packaged(path) is True


def test_detects_packaged_regardless_of_letter_case():
    path = r"c:\program files\windowsapps\3067F945.PackNine_0.9.0.0_x64__abc\PackNine.exe"

    assert packaged_app.is_packaged(path) is True


def test_normal_install_is_not_packaged():
    path = r"C:\Users\someone\AppData\Local\Programs\PackNine\PackNine.exe"

    assert packaged_app.is_packaged(path) is False


def test_folder_merely_named_like_windowsapps_is_not_packaged():
    # "MyWindowsAppsBackup" 같은 이름에 걸려 오탐하면 정상 설치본의 우클릭 등록이 막힌다.
    path = r"D:\backup\MyWindowsAppsBackup\PackNine.exe"

    assert packaged_app.is_packaged(path) is False


def test_uses_current_executable_when_path_omitted():
    # 인자를 생략하면 현재 실행 파일을 본다. 테스트 실행 환경은 패키지가 아니다.
    assert packaged_app.is_packaged() is False
