"""Windows MoTW(Mark of the Web) 전파 - NTFS Zone.Identifier 대체 스트림 복사.

웹 브라우저로 압축파일을 내려받으면 Windows는 그 파일 자체에 "인터넷에서 받음" 표시
(Zone.Identifier라는 NTFS 대체 데이터 스트림)를 남긴다. 이 표시가 있어야 탐색기에서 실행
파일을 열 때 SmartScreen이 뜨고, Office 문서를 열 때 보호된 보기가 작동한다.

압축 프로그램이 해제된 개별 파일에 이 표시를 옮겨 주지 않으면, 다운로드한 압축파일 안의
악성코드가 압축 해제만으로 "인터넷에서 받지 않은 파일"처럼 위장되어 이런 방어 기제를
그대로 우회해 버린다(여러 상용 압축 프로그램에서 실제로 반복 보고된 취약점 클래스).
그래서 압축 해제가 끝나면 원본 아카이브의 Zone.Identifier를 해제된 모든 파일에 복사한다.
"""
from __future__ import annotations

import pathlib
import sys

_ZONE_IDENTIFIER_STREAM = "Zone.Identifier"


def read_zone_identifier(source_path: pathlib.Path) -> bytes | None:
    """source_path(아카이브 파일 자체)의 Zone.Identifier ADS 내용을 읽는다.

    Windows/NTFS가 아니거나, 웹에서 받은 파일이 아니라 ADS가 아예 없으면 None을 반환한다.
    pathlib이 아니라 내장 open()에 콜론이 포함된 문자열 경로를 그대로 넘겨야
    "path:Zone.Identifier" 형태가 대체 스트림으로 올바르게 열린다(pathlib은 이런 경로를
    다른 방식으로 파싱해버릴 수 있다).
    """
    if sys.platform != "win32":
        return None
    try:
        with open(f"{source_path}:{_ZONE_IDENTIFIER_STREAM}", "rb") as f:
            return f.read()
    except OSError:
        return None


def propagate_zone_identifier(
    source_archive: pathlib.Path,
    extracted_root: pathlib.Path,
    extracted_names: list[str],
) -> None:
    """source_archive의 Zone.Identifier를 이번에 해제된 파일들에만 복사한다.

    extracted_names는 아카이브 내부 경로(posix 구분자 '/') 목록이며, 이 목록에 있는
    파일만 대상으로 한다. 과거에는 extracted_root를 통째로 rglob해서, 다운로드 폴더처럼
    기존 파일이 많은 곳에 풀면 원래 있던 파일까지 전부 ADS를 써 수정 날짜가 바뀌고
    인터넷 출처로 잘못 표시되는 심각한 버그가 있었다 - 반드시 해제된 파일만 건드린다.

    FAT32처럼 ADS를 지원하지 않는 파일시스템이거나 권한 문제가 있으면 파일 단위로 조용히
    건너뛴다 - MoTW 전파 실패가 압축 해제 자체를 실패시켜서는 안 되기 때문이다.
    """
    if sys.platform != "win32":
        return

    zone_data = read_zone_identifier(source_archive)
    if zone_data is None:
        return

    root = pathlib.Path(extracted_root)
    for name in extracted_names:
        # 아카이브 내부 경로('a/b.txt')를 목적지 기준 실제 경로로 변환한다.
        file_path = root.joinpath(*pathlib.PurePosixPath(name).parts)
        if not file_path.is_file():
            continue
        try:
            with open(f"{file_path}:{_ZONE_IDENTIFIER_STREAM}", "wb") as f:
                f.write(zone_data)
        except OSError:
            continue
