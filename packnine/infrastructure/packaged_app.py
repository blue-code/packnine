"""MSIX(마이크로소프트 스토어) 패키지로 실행 중인지 판별한다.

왜 필요한가: MSIX 컨테이너 안에서는 HKCU\\Software\\Classes 쓰기가 패키지별 가상 레지스트리로
redirect되어 탐색기가 보지 못한다. 즉 `register-context-menu`가 오류 없이 끝나고도 메뉴는
생기지 않는다 - 사용자 입장에서 가장 나쁜 실패(조용한 실패)다. 패키지 모드에서는 런타임
등록을 시도하지 않고 명확히 거절하고, 파일 연결/아카이브 우클릭 메뉴는 패키지 매니페스트의
선언(windows.fileTypeAssociation)이 담당한다.

판별 방법: MSIX 앱은 항상 `%ProgramFiles%\\WindowsApps\\<패키지풀네임>\\` 아래에서 실행된다.
정식 API(GetCurrentPackageFullName)는 ctypes가 필요한데, 자체 바이너리 조작 금지 원칙에 따라
ctypes는 아키텍처 메타 테스트가 차단한다(SECURITY.md 6번). 경로 판별로 충분하다 - 이 경로는
Windows가 예약한 위치라 일반 설치본이 들어갈 수 없다.
"""
from __future__ import annotations

import pathlib
import sys

_PACKAGE_ROOT_DIR_NAME = "windowsapps"


def is_packaged(executable_path: str | pathlib.Path | None = None) -> bool:
    """MSIX 패키지로 설치되어 실행 중이면 True."""
    target = pathlib.Path(executable_path if executable_path is not None else sys.executable)
    # 경로 조각 단위로 비교한다. 문자열 포함 검사(in)로 하면 "MyWindowsAppsBackup" 같은
    # 이름에 걸려 정상 설치본을 패키지로 오인한다.
    return any(part.lower() == _PACKAGE_ROOT_DIR_NAME for part in target.parts)
