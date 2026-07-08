"""반디집 "알아서 압축"/"알아서 압축풀기" 스타일의 목적지 자동 결정 로직.

순수 함수만 담는다 - 파일시스템에 실제로 쓰지는 않지만(이름 충돌 확인을 위한
`Path.exists()` 조회는 예외적으로 허용), 도메인 엔티티 외의 외부 의존성은 없다.
그래야 유닛 테스트가 파일 I/O 없이도 빠르게 돌아간다.
"""
from __future__ import annotations

import pathlib

from packnine.domain.entities import ArchiveManifest


def _resolve_unique_file_path(path: pathlib.Path) -> pathlib.Path:
    """path가 이미 존재하면 stem 뒤에 _2, _3 ... 을 붙여 존재하지 않는 경로를 찾는다."""
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    counter = 2
    while True:
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _resolve_unique_dir_path(path: pathlib.Path) -> pathlib.Path:
    """path(폴더)가 이미 존재하면 이름 뒤에 _2, _3 ... 을 붙여 존재하지 않는 경로를 찾는다.

    폴더 이름에는 압축 파일과 달리 별도로 떼어낼 확장자가 없으므로
    전체 이름 뒤에 그대로 접미사를 붙인다.
    """
    if not path.exists():
        return path

    name = path.name
    counter = 2
    while True:
        candidate = path.with_name(f"{name}_{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


def resolve_smart_compress_destination(
    source_paths: list[pathlib.Path], *, extension: str = ".zip"
) -> pathlib.Path:
    """원클릭 압축("알아서 압축") 시 결과 아카이브 경로를 자동으로 정한다.

    - 폴더 하나만 선택: 그 폴더와 같은 위치에 폴더명.zip
    - 파일 하나만 선택: 그 파일과 같은 위치에 파일명(확장자 제외).zip
    - 여러 개 선택: 공통 부모 폴더 이름으로 묶는다(같은 폴더에서 다중 선택한 경우를 가정).
    - 계산된 이름이 이미 존재하면 기존 파일을 덮어쓰지 않도록 _2, _3 ... 을 붙인다.
    """
    paths = [pathlib.Path(p) for p in source_paths]

    if len(paths) == 1:
        only = paths[0]
        if only.is_dir():
            destination = only.parent / f"{only.name}{extension}"
        else:
            destination = only.parent / f"{only.stem}{extension}"
    else:
        # 같은 탐색기 폴더에서 다중 선택한 경우가 일반적이므로, 첫 항목의 부모를
        # 공통 부모로 간주한다(모든 항목의 부모가 동일함을 별도로 보장하지 않는다).
        common_parent = paths[0].parent
        destination = common_parent / f"{common_parent.name}{extension}"

    return _resolve_unique_file_path(destination)


def resolve_smart_extract_destination(
    manifest: ArchiveManifest,
    archive_path: pathlib.Path,
    base_destination: pathlib.Path,
) -> pathlib.Path:
    """원클릭 압축해제("알아서 압축풀기") 시 실제 해제 대상 폴더를 자동으로 정한다.

    - 빈 아카이브: base_destination 그대로 사용.
    - 아카이브 내부 최상위 항목이 정확히 하나뿐(폴더 하나 또는 파일 하나로 이미 정리된
      아카이브): 그 항목 자체가 자연스러운 컨테이너 역할을 하므로 추가 폴더로 감싸지 않고
      base_destination을 그대로 사용한다.
    - 최상위 항목이 여러 개(느슨한 파일들이 흩어져 있음): 압축을 풀 때 지저분해지지
      않도록 base_destination / 아카이브명 하위 폴더를 만들어 그 안에 푼다.
    """
    archive_path = pathlib.Path(archive_path)
    base_destination = pathlib.Path(base_destination)

    if not manifest.entries:
        return base_destination

    top_level_names = {entry.name.split("/", 1)[0] for entry in manifest.entries}

    if len(top_level_names) <= 1:
        return base_destination

    candidate = base_destination / archive_path.stem
    return _resolve_unique_dir_path(candidate)
