"""Windows 탐색기 우클릭 컨텍스트 메뉴 등록/해제 스크립트.

관리자 권한이 필요 없도록 HKEY_CURRENT_USER 아래에만 키를 만든다(HKLM은 건드리지 않음).
- 범용 메뉴: 모든 파일 우클릭 시 "PackNine으로 압축하기" (Software\\Classes\\*\\shell)
- 아카이브 전용 메뉴: .zip/.7z/.rar 우클릭 시 "PackNine으로 열기" (해당 확장자 키의 shell)

실행: .venv\\Scripts\\python.exe scripts\\register_context_menu.py [--unregister]
"""
from __future__ import annotations

import argparse
import pathlib
import shutil
import sys

# winreg는 Windows 전용 표준 라이브러리 모듈이라, 다른 OS에서 import하면
# ModuleNotFoundError로 알아보기 힘든 메시지가 나온다 - 여기서 먼저 명확하게 막는다.
if sys.platform != "win32":
    raise RuntimeError("이 스크립트는 Windows 전용입니다 (winreg 모듈이 필요합니다)")

import winreg  # noqa: E402 - 위 플랫폼 체크 이후에만 import해야 함

_MENU_KEY_NAME = "PackNine"
_ARCHIVE_EXTENSIONS = (".zip", ".7z", ".rar")


def _resolve_packnine_command() -> str:
    """설치된 packnine 실행 파일 경로를 찾는다.

    PATH에 packnine(.exe)이 없으면 현재 파이썬과 같은 venv의 Scripts 폴더를 확인하고,
    그마저도 없으면 최후 수단으로 `python -m packnine.main`을 사용한다.
    """
    exe_path = shutil.which("packnine")
    if exe_path:
        return f'"{exe_path}"'

    candidate = pathlib.Path(sys.executable).parent / "packnine.exe"
    if candidate.exists():
        return f'"{candidate}"'

    return f'"{sys.executable}" -m packnine.main'


def _create_menu_key(parent_key_path: str, command: str, label: str) -> None:
    key_path = f"{parent_key_path}\\shell\\{_MENU_KEY_NAME}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, label)

    command_key_path = f"{key_path}\\command"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, command_key_path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, command)


def _delete_menu_key(parent_key_path: str) -> None:
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
    try:
        packnine_cmd = _resolve_packnine_command()

        _create_menu_key(
            r"Software\Classes\*",
            f'{packnine_cmd} compress "%1" -o "%1.zip"',
            "PackNine으로 압축하기",
        )

        for ext in _ARCHIVE_EXTENSIONS:
            _create_menu_key(
                rf"Software\Classes\{ext}",
                f'{packnine_cmd} extract "%1" -d "%1_extracted"',
                "PackNine으로 열기",
            )
    except OSError as exc:
        raise RuntimeError(
            "레지스트리 등록에 실패했습니다. 권한 문제이거나 동일한 키를 다른 프로그램이 "
            f"점유하고 있을 수 있습니다. (원인: {exc})"
        ) from exc


def unregister() -> None:
    """register()로 등록한 키를 모두 제거한다."""
    try:
        _delete_menu_key(r"Software\Classes\*")
        for ext in _ARCHIVE_EXTENSIONS:
            _delete_menu_key(rf"Software\Classes\{ext}")
    except OSError as exc:
        raise RuntimeError(f"레지스트리 해제(삭제)에 실패했습니다. (원인: {exc})") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="PackNine 탐색기 우클릭 메뉴 등록/해제")
    parser.add_argument("--unregister", action="store_true", help="등록된 메뉴를 제거한다")
    args = parser.parse_args()

    try:
        if args.unregister:
            unregister()
            print("PackNine 우클릭 메뉴를 제거했습니다.")
        else:
            register()
            print("PackNine 우클릭 메뉴를 등록했습니다.")
    except RuntimeError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
