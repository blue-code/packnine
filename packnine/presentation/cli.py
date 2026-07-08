"""PackNine CLI 진입점.

서브커맨드 없이 실행하면 GUI를 띄우고, 서브커맨드가 있으면 해당 유스케이스
서비스(application 계층)를 호출한다. presentation 계층은 application 서비스만
호출하고 infrastructure 어댑터를 직접 import하지 않는다(계층 경계 유지).
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from packnine.application.compress_service import CompressService
from packnine.application.extract_service import ExtractService
from packnine.application.inspect_service import InspectService
from packnine.domain.exceptions import ExternalToolMissingError, UnsafeArchiveEntryError
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


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        # 디스플레이 없는 환경(CI 등)에서 CLI만 쓸 때 PySide6 임포트 비용/실패를
        # 피하기 위해 GUI 관련 import는 실제로 GUI를 띄울 때만 지연 수행한다.
        from packnine.presentation.gui.main_window import run_gui

        return run_gui()

    try:
        if args.command == "compress":
            return _cmd_compress(args)
        if args.command == "extract":
            return _cmd_extract(args)
        if args.command == "list":
            return _cmd_list(args)
    except UnsafeArchiveEntryError as exc:
        print(f"오류: 안전하지 않은 아카이브입니다 - {exc}", file=sys.stderr)
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
