"""Windows 탐색기 우클릭 컨텍스트 메뉴 등록/해제 + 파일 연결(더블클릭).

관리자 권한이 필요 없도록 HKEY_CURRENT_USER 아래에만 키를 만든다(HKLM은 건드리지 않음).
반디집의 "알아서 압축"/"알아서 압축풀기"처럼 다이얼로그 없이 바로 실행되도록
smart-compress/smart-extract CLI 서브커맨드를 연결한다(목적지 경로는 CLI가 스스로 계산).

- 범용 메뉴: 모든 파일 우클릭 시 "PackNine으로 압축하기" (Software\\Classes\\*\\shell)
- 폴더 메뉴: 폴더 우클릭 시 "압축하기" + "각각 압축하기" (Directory\\shell).
  '*'는 파일에만 적용되어 폴더에는 별도 등록이 필요하고, "각각 압축하기"는 파일 1개
  선택 시에도 떠서 혼란스럽다는 피드백에 따라 폴더 전용으로 두었다(정적 레지스트리
  verb는 선택 개수를 조건으로 표시/숨김할 수 없다 - 그러려면 COM 셸 확장이 필요).
- 아카이브 전용 메뉴: .zip/.7z/.rar 등 우클릭 시 "PackNine으로 압축풀기"/"열기"
  (SystemFileAssociations\\확장자\\shell). 확장자 키(.zip 등)의 shell에 넣으면
  그 확장자에 ProgID(기본 프로그램)가 연결된 순간 탐색기가 무시한다 - 실제로 .zip
  기본 앱이 탐색기(CompressedFolder UserChoice)인 환경에서 압축풀기 메뉴가 아예
  안 보이는 문제가 있었다. SystemFileAssociations의 verb는 기본 프로그램과 무관하게
  항상 병합 표시된다(반디집과 같은 방식).
- 압축/해제 메뉴는 서로 다른 verb 키 이름(PackNineCompress/PackNineExtract)을 쓴다.
  같은 이름을 쓰면 탐색기가 양쪽에 등록된 동일 이름의 verb를 병합하면서 하나만
  표시해 버리는 문제가 있었다 - 실제로 이 버그가 발견되어 이름을 분리해 고쳤다.
- 두 메뉴 모두 MultiSelectModel=Player를 등록해, 여러 항목을 선택해도 명령이 한 번만
  실행되고 %*로 선택된 모든 경로를 한꺼번에 전달받는다.
- 파일 연결: PackNine.Archive라는 ProgID를 만들어 아카이브 확장자의 더블클릭 기본 동작을
  "GUI로 열어 내용 보기"(open 서브커맨드)로 등록한다. 이미 다른 프로그램이 그 확장자의
  기본 프로그램으로 지정돼 있었다면 그 값을 백업해두었다가 unregister() 시 그대로
  복원한다(파일 연결을 영구적으로 빼앗지 않기 위함).

설치 프로그램(installer.nsi)이 설치/제거 시 `PackNine.exe register-context-menu`와
`--unregister`를 호출해 이 모듈의 register()/unregister()를 실행한다.
"""
from __future__ import annotations

import pathlib
import shutil
import sys

_COMPRESS_VERB = "PackNineCompress"
_COMPRESS_EACH_VERB = "PackNineCompressEach"
_EXTRACT_VERB = "PackNineExtract"
_OPEN_VERB = "PackNineOpen"
# .gz/.bz2/.xz는 tar.gz 같은 복합 확장자든 순수 단일 파일 압축이든
# format_registry가 양쪽 모두 처리하므로(단일 파일 해제 지원 추가) 대상에 포함한다.
_ARCHIVE_EXTENSIONS = (".zip", ".7z", ".rar", ".tar", ".tgz", ".gz", ".bz2", ".xz")
_PROG_ID = "PackNine.Archive"
_ASSOC_BACKUP_KEY = r"Software\PackNine\PreviousFileAssociations"


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


def _resolve_icon_reference() -> str:
    """DefaultIcon에 쓸 "경로,인덱스" 형태의 문자열을 만든다.

    frozen exe는 자기 자신에 아이콘이 내장돼 있으므로 그 exe를 가리키고, 개발 환경에서는
    패키지에 포함된 .ico 파일을 직접 가리킨다(둘 다 없으면 python.exe로 대체).
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}",0'

    icon_path = pathlib.Path(__file__).resolve().parent.parent / "presentation" / "gui" / "assets" / "icon.ico"
    if icon_path.exists():
        return f'"{icon_path}",0'

    return f'"{sys.executable}",0'


def _create_menu_key(
    parent_key_path: str, verb: str, command: str, label: str, multi_select: bool = False
) -> None:
    import winreg

    key_path = f"{parent_key_path}\\shell\\{verb}"
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


def _delete_menu_key(parent_key_path: str, verb: str) -> None:
    import winreg

    key_path = f"{parent_key_path}\\shell\\{verb}"
    # command 하위 키부터 지워야 부모 verb 키를 지울 수 있다(자식이 남아있으면 실패).
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"{key_path}\\command")
    except FileNotFoundError:
        pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
    except FileNotFoundError:
        pass


def _register_prog_id(open_command: str, icon_reference: str) -> None:
    import winreg

    prog_key = rf"Software\Classes\{_PROG_ID}"
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, prog_key) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, "PackNine 압축 파일")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{prog_key}\DefaultIcon") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, icon_reference)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{prog_key}\shell\open\command") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, open_command)


def _unregister_prog_id() -> None:
    import winreg

    prog_key = rf"Software\Classes\{_PROG_ID}"
    for sub in (
        rf"{prog_key}\shell\open\command",
        rf"{prog_key}\shell\open",
        rf"{prog_key}\shell",
        rf"{prog_key}\DefaultIcon",
        prog_key,
    ):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
        except FileNotFoundError:
            pass


def _read_current_default(ext: str) -> str | None:
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}") as key:
            value, _ = winreg.QueryValueEx(key, "")
            return value or None
    except FileNotFoundError:
        return None


def _backup_and_set_default(ext: str) -> None:
    """ext의 현재 기본 연결 프로그램을 백업해두고 PackNine을 기본값으로 설정한다."""
    import winreg

    previous = _read_current_default(ext)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _ASSOC_BACKUP_KEY) as key:
        # 이미 우리가 등록해서 기본값이 우리 자신이면(재등록 케이스) 백업을 덮어쓰지
        # 않아야 그 이전의 진짜 원래 프로그램 정보를 잃지 않는다.
        if previous != _PROG_ID:
            winreg.SetValueEx(key, ext, 0, winreg.REG_SZ, previous or "")

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}") as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, _PROG_ID)


def _restore_default(ext: str) -> None:
    """_backup_and_set_default()로 바꾸기 전의 기본 연결 프로그램을 복원한다."""
    import winreg

    previous: str | None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ASSOC_BACKUP_KEY) as key:
            previous, _ = winreg.QueryValueEx(key, ext)
    except (FileNotFoundError, OSError):
        previous = None

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{ext}") as key:
            if previous:
                winreg.SetValueEx(key, "", 0, winreg.REG_SZ, previous)
            else:
                # 원래 기본값이 없었으면(비어 있었으면) 우리가 설정한 값만 지운다.
                try:
                    winreg.DeleteValue(key, "")
                except FileNotFoundError:
                    pass
    except OSError:
        pass

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _ASSOC_BACKUP_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.DeleteValue(key, ext)
    except (FileNotFoundError, OSError):
        pass


def register() -> None:
    """탐색기 우클릭 메뉴(압축/압축풀기)와 아카이브 확장자 파일 연결을 등록한다."""
    _require_windows()

    try:
        packnine_cmd = _resolve_packnine_command()

        # smart-compress/smart-extract는 목적지 경로를 다이얼로그 없이 스스로 계산하므로
        # 명령에 "%1.zip" 같은 고정 목적지를 넘길 필요가 없다 - 그냥 선택된 경로들(%*)만 넘긴다.
        _create_menu_key(
            r"Software\Classes\*",
            _COMPRESS_VERB,
            f"{packnine_cmd} smart-compress %*",
            "PackNine으로 압축하기",
            multi_select=True,
        )
        # 폴더 우클릭: '*'는 파일에만 적용되므로 Directory에 별도 등록한다.
        _create_menu_key(
            r"Software\Classes\Directory",
            _COMPRESS_VERB,
            f"{packnine_cmd} smart-compress %*",
            "PackNine으로 압축하기",
            multi_select=True,
        )
        # "각각 압축하기"(항목별 zip)는 폴더 전용 - 파일 1개 선택 시에도 떠서
        # 혼란스럽다는 피드백에 따라 파일('*')에는 등록하지 않는다.
        _create_menu_key(
            r"Software\Classes\Directory",
            _COMPRESS_EACH_VERB,
            f"{packnine_cmd} smart-compress --each %*",
            "PackNine으로 각각 압축하기",
            multi_select=True,
        )

        for ext in _ARCHIVE_EXTENSIONS:
            # SystemFileAssociations: 기본 프로그램(UserChoice/ProgID)이 무엇이든
            # 항상 병합 표시되는 유일한 per-user 위치다(모듈 docstring 참고).
            _create_menu_key(
                rf"Software\Classes\SystemFileAssociations\{ext}",
                _EXTRACT_VERB,
                f"{packnine_cmd} smart-extract %*",
                "PackNine으로 압축풀기",
                multi_select=True,
            )
            # 더블클릭 기본 동작(파일 연결)과 별개로, 우클릭에서도 명시적으로
            # "열기"를 제공한다(기본 프로그램이 다른 압축 프로그램인 경우 대비).
            _create_menu_key(
                rf"Software\Classes\SystemFileAssociations\{ext}",
                _OPEN_VERB,
                f'{packnine_cmd} open "%1"',
                "PackNine으로 열기",
            )

        # 파일 연결: 더블클릭하면 GUI로 열어 내용을 보여준다(압축풀기와는 별개의 동작).
        _register_prog_id(
            open_command=f'{packnine_cmd} open "%1"',
            icon_reference=_resolve_icon_reference(),
        )
        for ext in _ARCHIVE_EXTENSIONS:
            _backup_and_set_default(ext)
    except OSError as exc:
        raise RuntimeError(
            "레지스트리 등록에 실패했습니다. 권한 문제이거나 동일한 키를 다른 프로그램이 "
            f"점유하고 있을 수 있습니다. (원인: {exc})"
        ) from exc


def unregister() -> None:
    """register()로 등록한 모든 것(메뉴, ProgID, 파일 연결)을 원상 복구한다."""
    _require_windows()

    try:
        _delete_menu_key(r"Software\Classes\*", _COMPRESS_VERB)
        _delete_menu_key(r"Software\Classes\Directory", _COMPRESS_VERB)
        _delete_menu_key(r"Software\Classes\Directory", _COMPRESS_EACH_VERB)
        # 과거 버전(v0.4.0 이하)이 등록했던 위치도 함께 정리한다(업그레이드 잔여물 방지).
        _delete_menu_key(r"Software\Classes\*", _COMPRESS_EACH_VERB)
        for ext in _ARCHIVE_EXTENSIONS:
            _delete_menu_key(rf"Software\Classes\SystemFileAssociations\{ext}", _EXTRACT_VERB)
            _delete_menu_key(rf"Software\Classes\SystemFileAssociations\{ext}", _OPEN_VERB)
            # 과거 버전이 확장자 키에 직접 등록했던 verb 정리
            _delete_menu_key(rf"Software\Classes\{ext}", _EXTRACT_VERB)
            _delete_menu_key(rf"Software\Classes\{ext}", _OPEN_VERB)
            _restore_default(ext)
        _unregister_prog_id()
    except OSError as exc:
        raise RuntimeError(f"레지스트리 해제(삭제)에 실패했습니다. (원인: {exc})") from exc
