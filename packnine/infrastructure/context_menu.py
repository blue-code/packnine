"""Windows 탐색기 우클릭 컨텍스트 메뉴 등록/해제.

관리자 권한이 필요 없도록 HKEY_CURRENT_USER 아래에만 키를 만든다(HKLM은 건드리지 않음).
반디집의 "알아서 압축"/"알아서 압축풀기"처럼 다이얼로그 없이 바로 실행되도록
smart-compress/smart-extract CLI 서브커맨드를 연결한다(목적지 경로는 CLI가 스스로 계산).
- 범용 메뉴: 모든 파일 우클릭 시 "PackNine으로 압축하기" (Software\\Classes\\*\\shell)
- 아카이브 전용 메뉴: .zip/.7z/.rar 우클릭 시 "PackNine으로 열기" (해당 확장자 키의 shell)
- 두 메뉴 모두 MultiSelectModel=Player를 등록해, 여러 항목을 선택해도 명령이 한 번만
  실행되고 %*로 선택된 모든 경로를 한꺼번에 전달받는다.

설치 프로그램(installer.nsi)이 설치/제거 시 `PackNine.exe register-context-menu`와
`--unregister`를 호출해 이 모듈의 register()/unregister()를 실행한다.
"""
from __future__ import annotations

import pathlib
import shutil
import sys

_MENU_KEY_NAME = "PackNine"
_ARCHIVE_EXTENSIONS = (".zip", ".7z", ".rar")


def _require_windows() -> None:
    if sys.platform != "win32":
        raise RuntimeError("이 기능은 Windows 전용입니다 (winreg 모듈이 필요합니다)")


def _resolve_packnine_command() -> str:
    """현재 실행 중인 packnine 실행 파일 경로를 찾는다.

    PyInstaller로 빌드된 exe로 실행 중이면 그 exe 자신을 가리키고, 그렇지 않으면(개발
    환경) PATH의 packnine 커맨드나 venv의 Scripts 폴더를 확인한 뒤, 그마저 없으면
    최후 수단으로 `python -m packnine.main`을 사용한다.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'

    exe_path = shutil.which("packnine")
    if exe_path:
        return f'"{exe_path}"'

    candidate = pathlib.Path(sys.executable).parent / "packnine.exe"
    if candidate.exists():
        return f'"{candidate}"'

    return f'"{sys.executable}" -m packnine.main'


def _create_menu_key(
    parent_key_path: str, command: str, label: str, multi_select: bool = False
) -> None:
    import winreg

    key_path = f"{parent_key_path}\\shell\\{_MENU_KEY_NAME}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, label)
        if multi_select:
            # 이 값이 없으면 탐색기가 다중 선택 시 명령을 파일마다 개별 실행해
            # 별도 zip이 여러 개 생긴다. "Player"로 지정해야 %*에 선택된 모든
            # 경로가 한 번에 전달되어 하나의 명령으로 처리된다.
            winreg.SetValueEx(key, "MultiSelectModel", 0, winreg.REG_SZ, "Player")

    command_key_path = f"{key_path}\\command"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, command_key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)


def _delete_menu_key(parent_key_path: str) -> None:
    import winreg

    key_path = f"{parent_key_path}\\shell\\{_MENU_KEY_NAME}"
    # command 하위 키부터 지워야 부모 키(shell\PackNine)를 지울 수 있다(자식이 남아있으면 실패).
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"{key_path}\\command")
    except FileNotFoundError:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
    except FileNotFoundError:
        pass


def register() -> None:
    """탐색기 우클릭 메뉴 두 종류(범용 압축 / 아카이브 열기)를 등록한다."""
    _require_windows()

    try:
        packnine_cmd = _resolve_packnine_command()

        # smart-compress/smart-extract는 목적지 경로를 다이얼로그 없이 스스로 계산하므로
        # 명령에 "%1.zip" 같은 고정 목적지를 넘길 필요가 없다 - 그냥 선택된 경로들(%*)만 넘긴다.
        _create_menu_key(
            r"Software\Classes\*",
            f"{packnine_cmd} smart-compress %*",
            "PackNine으로 압축하기",
            multi_select=True,
        )

        for ext in _ARCHIVE_EXTENSIONS:
            _create_menu_key(
                rf"Software\Classes\{ext}",
                f"{packnine_cmd} smart-extract %*",
                "PackNine으로 열기",
                multi_select=True,
            )
    except OSError as exc:
        raise RuntimeError(
            "레지스트리 등록에 실패했습니다. 권한 문제이거나 동일한 키를 다른 프로그램이 "
            f"점유하고 있을 수 있습니다. (원인: {exc})"
        ) from exc


def unregister() -> None:
    """register()로 등록한 키를 모두 제거한다."""
    _require_windows()

    try:
        _delete_menu_key(r"Software\Classes\*")
        for ext in _ARCHIVE_EXTENSIONS:
            _delete_menu_key(rf"Software\Classes\{ext}")
    except OSError as exc:
        raise RuntimeError(f"레지스트리 해제(삭제)에 실패했습니다. (원인: {exc})") from exc
