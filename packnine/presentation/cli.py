"""PackNine CLI 진입점.

서브커맨드 없이 실행하면 GUI를 띄우고, 서브커맨드가 있으면 해당 유스케이스
서비스(application 계층)를 호출한다. presentation 계층은 application 서비스만
호출하고 infrastructure 어댑터를 직접 import하지 않는다(계층 경계 유지).
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from packnine.application import smart_naming
from packnine.application.compress_service import CompressService
from packnine.application.context_menu_service import ContextMenuService
from packnine.application.extract_service import ExtractService
from packnine.application.inspect_service import InspectService
from packnine.domain.exceptions import (
    CorruptedArchiveError,
    ExternalToolMissingError,
    InvalidPasswordError,
    UnsafeArchiveEntryError,
)
from packnine.domain.value_objects import CompressionLevel


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="packnine", description="PackNine - 압축/해제 데스크톱 프로그램"
    )
    subparsers = parser.add_subparsers(dest="command")

    compress_parser = subparsers.add_parser("compress", help="파일/폴더를 압축한다")
    compress_parser.add_argument("sources", nargs="+", help="압축할 파일/폴더 경로들")
    compress_parser.add_argument("-o", "--output", required=True, help="출력 아카이브 경로")
    compress_parser.add_argument("--password", default=None, help="암호화 비밀번호")
    compress_parser.add_argument(
        "--level",
        type=int,
        default=int(CompressionLevel.NORMAL),
        choices=range(0, 10),
        metavar="0-9",
        help="압축 강도 (0=저장, 9=최대)",
    )

    extract_parser = subparsers.add_parser("extract", help="아카이브를 해제한다")
    extract_parser.add_argument("archive", help="해제할 아카이브 경로")
    extract_parser.add_argument("-d", "--destination", required=True, help="해제 대상 폴더")
    extract_parser.add_argument("--password", default=None, help="암호화 비밀번호")

    list_parser = subparsers.add_parser("list", help="아카이브 내용을 목록으로 출력한다")
    list_parser.add_argument("archive", help="조회할 아카이브 경로")
    list_parser.add_argument("--password", default=None, help="암호화 비밀번호")

    # 반디집 "알아서 압축"/"알아서 압축풀기"에 대응하는 원클릭 서브커맨드.
    # 목적지 경로를 사용자가 지정하지 않고 smart_naming이 자동으로 정한다.
    smart_compress_parser = subparsers.add_parser(
        "smart-compress", help="목적지를 자동으로 정해 바로 압축한다(알아서 압축)"
    )
    smart_compress_parser.add_argument("sources", nargs="+", help="압축할 파일/폴더 경로들")
    smart_compress_parser.add_argument("--password", default=None, help="암호화 비밀번호")
    smart_compress_parser.add_argument(
        "--level",
        type=int,
        default=int(CompressionLevel.NORMAL),
        choices=range(0, 10),
        metavar="0-9",
        help="압축 강도 (0=저장, 9=최대)",
    )
    smart_compress_parser.add_argument(
        "--dest-dir",
        default=None,
        help="자동 계산된 파일명을 이 디렉터리 아래에 둔다(없으면 원본과 같은 위치)",
    )
    smart_compress_parser.add_argument(
        "--each",
        action="store_true",
        help="선택한 항목들을 하나로 묶지 않고 항목별로 각각 압축한다(각각 압축하기)",
    )

    smart_extract_parser = subparsers.add_parser(
        "smart-extract", help="아카이브 내용에 맞춰 해제 위치를 자동으로 정한다(알아서 압축풀기)"
    )
    smart_extract_parser.add_argument("archives", nargs="+", help="해제할 아카이브 경로들")
    smart_extract_parser.add_argument("--password", default=None, help="암호화 비밀번호")
    smart_extract_parser.add_argument(
        "--dest-dir",
        default=None,
        help="해제 기준 폴더(base_destination). 없으면 각 아카이브와 같은 폴더를 사용",
    )

    context_menu_parser = subparsers.add_parser(
        "register-context-menu", help="탐색기 우클릭 메뉴/파일 연결을 등록·해제한다(설치 프로그램이 호출)"
    )
    context_menu_parser.add_argument(
        "--unregister", action="store_true", help="등록된 메뉴/파일 연결을 제거한다"
    )

    # 파일 연결(더블클릭) 시 탐색기가 실행하는 명령. GUI를 띄우고 그 아카이브를 바로 연다.
    open_parser = subparsers.add_parser(
        "open", help="아카이브를 GUI로 열어 내용을 보여준다(더블클릭 파일 연결용)"
    )
    open_parser.add_argument("archive", help="열 아카이브 경로")

    return parser


def _compression_level_from_int(value: int) -> CompressionLevel:
    # CompressionLevel은 STORE/FASTEST/NORMAL/MAXIMUM 몇 개 값만 있는 IntEnum이라
    # 임의 정수(0-9)를 그대로 만들 수 없으므로 구간별로 가장 가까운 값에 매핑한다.
    if value <= CompressionLevel.STORE:
        return CompressionLevel.STORE
    if value <= CompressionLevel.FASTEST:
        return CompressionLevel.FASTEST
    if value <= CompressionLevel.NORMAL:
        return CompressionLevel.NORMAL
    return CompressionLevel.MAXIMUM


def _cmd_compress(args: argparse.Namespace) -> int:
    service = CompressService()
    sources = [pathlib.Path(p) for p in args.sources]
    destination = pathlib.Path(args.output)
    manifest = service.compress(
        sources,
        destination,
        password=args.password,
        compression_level=_compression_level_from_int(args.level),
    )
    print(f"압축 완료: {len(manifest.entries)}개 항목, 출력 경로: {destination}")
    return 0


def _cmd_extract(args: argparse.Namespace) -> int:
    service = ExtractService()
    archive_path = pathlib.Path(args.archive)
    destination = pathlib.Path(args.destination)
    manifest = service.extract(archive_path, destination, password=args.password)
    print(f"압축 해제 완료: {len(manifest.entries)}개 항목, 대상 경로: {destination}")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    service = InspectService()
    manifest = service.list_contents(pathlib.Path(args.archive), password=args.password)

    name_width = max((len(e.name) for e in manifest.entries), default=4)
    name_width = max(name_width, 4)
    header = f"{'이름':<{name_width}}  {'크기':>12}  {'압축크기':>12}"
    print(header)
    print("-" * len(header))
    for entry in manifest.entries:
        print(f"{entry.name:<{name_width}}  {entry.size:>12}  {entry.compressed_size:>12}")
    print("-" * len(header))
    print(f"총 {len(manifest.entries)}개 항목")
    return 0


def _has_console() -> bool:
    """터미널에 연결되어 있는지 안전하게 확인한다.

    PyInstaller로 windowed(console=False) 빌드된 exe를 탐색기 우클릭 메뉴처럼
    부모 콘솔 없이 실행하면 sys.stdout 자체가 None이 되어 .isatty() 호출이
    AttributeError를 던진다 - 콘솔이 없는데도 예외가 잡히지 않고 조용히 죽어
    "아무 반응이 없는" 것처럼 보이는 버그였다. 여기서 모든 예외를 콘솔 없음으로 취급한다.
    """
    try:
        return bool(sys.stdout) and sys.stdout.isatty()
    except (AttributeError, ValueError, OSError):
        return False


def _smart_compress_each(args: argparse.Namespace) -> int:
    """선택 항목들을 항목별로 각각 압축한다(반디집 "각각 압축하기" 대응).

    하나가 실패해도 나머지는 계속 진행하고, 실패가 하나라도 있으면 1을 반환한다.
    """
    service = CompressService()
    level = _compression_level_from_int(args.level)
    dest_dir = pathlib.Path(args.dest_dir) if args.dest_dir else None
    use_gui_progress = not _has_console()

    if use_gui_progress:
        from packnine.presentation.gui import quick_progress

    had_failure = False
    for source_str in args.sources:
        source = pathlib.Path(source_str)
        auto_name = smart_naming.resolve_smart_compress_destination([source]).name
        destination = (dest_dir / auto_name) if dest_dir else source.parent / auto_name

        def operation(on_progress, _source=source, _destination=destination):
            return service.compress(
                [_source],
                _destination,
                password=args.password,
                compression_level=level,
                on_progress=on_progress,
            )

        if use_gui_progress:
            if not quick_progress.run_with_progress(f"압축 중: {source.name}", operation):
                had_failure = True
            continue

        try:
            manifest = operation(None)
        except (FileNotFoundError, OSError) as exc:
            print(f"실패: {source} - {exc}")
            had_failure = True
        else:
            print(f"성공: {destination} ({len(manifest.entries)}개 항목)")

    return 1 if had_failure else 0


def _cmd_smart_compress(args: argparse.Namespace) -> int:
    if args.each:
        return _smart_compress_each(args)

    service = CompressService()
    sources = [pathlib.Path(p) for p in args.sources]
    level = _compression_level_from_int(args.level)

    if args.dest_dir:
        # 고급 옵션: 자동 계산된 "파일명"만 재사용하고, 그 파일을 둘 디렉터리는
        # 사용자가 지정한 곳으로 바꾼다(원본 위치 기준 계산은 smart_naming에 맡긴다).
        dest_dir = pathlib.Path(args.dest_dir)
        destination = dest_dir / smart_naming.resolve_smart_compress_destination(sources).name

        def operation(on_progress):
            return service.compress(
                sources,
                destination,
                password=args.password,
                compression_level=level,
                on_progress=on_progress,
            )
    else:
        # 목적지 미리보기(출력 메시지용)는 실제 압축이 일어나기 전에 계산해야
        # smart_compress() 내부에서 다시 계산하는 값과 일치한다(파일이 아직 없으므로
        # 두 번 계산해도 동일한 경로가 나온다).
        destination = smart_naming.resolve_smart_compress_destination(sources)

        def operation(on_progress):
            return service.smart_compress(
                sources,
                password=args.password,
                compression_level=level,
                on_progress=on_progress,
            )

    # 콘솔이 연결되어 있으면(터미널에서 직접 실행) 텍스트로만 결과를 알리고,
    # 콘솔이 없으면(탐색기 우클릭 -> windowed exe) 작은 진행률 창 + 에러 다이얼로그로 대신한다.
    if _has_console():
        manifest = operation(None)
        print(f"압축 완료: {len(manifest.entries)}개 항목, 출력 경로: {destination}")
        return 0

    from packnine.presentation.gui import quick_progress

    ok = quick_progress.run_with_progress("압축 중...", operation)
    return 0 if ok else 1


def _cmd_smart_extract(args: argparse.Namespace) -> int:
    service = ExtractService()
    dest_dir = pathlib.Path(args.dest_dir) if args.dest_dir else None
    use_gui_progress = not _has_console()

    if use_gui_progress:
        from packnine.presentation.gui import quick_progress

    had_failure = False
    for archive_str in args.archives:
        archive_path = pathlib.Path(archive_str)
        # --dest-dir이 없으면 각 아카이브와 같은 폴더를 base_destination으로 사용한다.
        base_destination = dest_dir if dest_dir is not None else archive_path.parent

        def operation(on_progress, _archive_path=archive_path, _base=base_destination):
            return service.smart_extract(
                _archive_path, _base, password=args.password, on_progress=on_progress
            )

        if use_gui_progress:
            # 여러 아카이브를 순차 처리하되, 하나가 실패해도(에러 다이얼로그만 뜨고)
            # 나머지는 계속 진행한다. 암호 아카이브면 비밀번호 입력을 받아 재시도한다.
            def operation_with_password(
                on_progress, password, _archive_path=archive_path, _base=base_destination
            ):
                return service.smart_extract(
                    _archive_path, _base, password=password, on_progress=on_progress
                )

            ok = quick_progress.run_extract_with_password_retry(
                f"압축 해제 중: {archive_path.name}",
                operation_with_password,
                archive_name=archive_path.name,
                initial_password=args.password,
            )
            if not ok:
                had_failure = True
            continue

        try:
            manifest = operation(None)
        except UnsafeArchiveEntryError as exc:
            print(f"실패: {archive_path} - 안전하지 않은 아카이브입니다 ({exc})")
            had_failure = True
        except InvalidPasswordError as exc:
            print(f"실패: {archive_path} - 비밀번호를 확인하세요 ({exc})")
            had_failure = True
        except CorruptedArchiveError as exc:
            print(f"실패: {archive_path} - 손상된 아카이브입니다 ({exc})")
            had_failure = True
        except ExternalToolMissingError as exc:
            print(f"실패: {archive_path} - 필요한 외부 도구가 없습니다 ({exc})")
            had_failure = True
        except (FileNotFoundError, OSError) as exc:
            print(f"실패: {archive_path} - {exc}")
            had_failure = True
        else:
            print(f"성공: {archive_path} ({len(manifest.entries)}개 항목)")

    return 1 if had_failure else 0


def _cmd_register_context_menu(args: argparse.Namespace) -> int:
    service = ContextMenuService()
    if args.unregister:
        service.unregister()
        print("PackNine 우클릭 메뉴를 제거했습니다.")
    else:
        service.register()
        print("PackNine 우클릭 메뉴를 등록했습니다.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        # 디스플레이 없는 환경(CI 등)에서 CLI만 쓸 때 PySide6 임포트 비용/실패를
        # 피하기 위해 GUI 관련 import는 실제로 GUI를 띄울 때만 지연 수행한다.
        from packnine.presentation.gui.main_window import run_gui

        return run_gui()

    if args.command == "open":
        # 파일 연결(더블클릭)로 실행되는 경로 - GUI를 띄우고 그 아카이브를 바로 연다.
        # 아카이브 관련 예외는 MainWindow가 자체적으로 메시지 박스로 처리하므로
        # 여기서 별도로 try/except할 필요가 없다.
        from packnine.presentation.gui.main_window import run_gui

        return run_gui(initial_archive=pathlib.Path(args.archive))

    try:
        if args.command == "compress":
            return _cmd_compress(args)
        if args.command == "extract":
            return _cmd_extract(args)
        if args.command == "list":
            return _cmd_list(args)
        if args.command == "smart-compress":
            return _cmd_smart_compress(args)
        if args.command == "smart-extract":
            return _cmd_smart_extract(args)
        if args.command == "register-context-menu":
            return _cmd_register_context_menu(args)
    except RuntimeError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    except UnsafeArchiveEntryError as exc:
        print(f"오류: 안전하지 않은 아카이브입니다 - {exc}", file=sys.stderr)
        return 1
    except InvalidPasswordError as exc:
        print(f"오류: 비밀번호를 확인하세요 - {exc}", file=sys.stderr)
        return 1
    except CorruptedArchiveError as exc:
        print(f"오류: 손상된 아카이브입니다 - {exc}", file=sys.stderr)
        return 1
    except ExternalToolMissingError as exc:
        print(f"오류: 필요한 외부 도구가 없습니다 - {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, OSError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
