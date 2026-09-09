"""분할 압축(볼륨) 파일 입출력 헬퍼.

zip/7z 어댑터가 각자 multivolumefile을 호출하면 이름 규칙(자릿수, 단일 볼륨 처리)이
어긋나기 쉬우므로 이 모듈 한 곳에 모은다. multivolumefile은 py7zr의 의존성이라
추가 설치 없이 쓸 수 있고, 볼륨 경계를 넘나드는 seek/tell을 스스로 처리하기 때문에
zipfile/py7zr 모두 일반 파일 객체처럼 넘길 수 있다.

이름 규칙은 7-Zip/반디집과 같은 `이름.7z.001`, `이름.7z.002` … (3자리)이다.
multivolumefile 기본값은 4자리(.0001)라 반드시 ext_digits=3을 지정한다.
zip 볼륨은 WinZip 스팬(.z01)이 아니라 7-Zip 방식의 단순 바이트 분할(.zip.001)이다.
스팬 방식은 zip 헤더의 디스크 번호를 직접 써야 해서 "자체 바이너리 파서 금지"
원칙(SECURITY.md)과 충돌하므로 채택하지 않았다.
"""
from __future__ import annotations

import pathlib
import re

import multivolumefile

from packnine.domain.value_objects import VolumeSize

_EXT_DIGITS = 3
_VOLUME_SUFFIX_RE = re.compile(r"\.\d{3}$")
FIRST_VOLUME_SUFFIX = ".001"


def is_first_volume(path: pathlib.Path) -> bool:
    """`이름.zip.001`처럼 첫 번째 볼륨 파일인지 판단한다(.002 이후는 직접 열지 않는다)."""
    return pathlib.Path(path).name.lower().endswith(FIRST_VOLUME_SUFFIX)


def strip_volume_suffix(path: pathlib.Path) -> pathlib.Path:
    """`이름.zip.001` → `이름.zip`. 볼륨 접미사가 없으면 그대로 돌려준다."""
    path = pathlib.Path(path)
    if _VOLUME_SUFFIX_RE.search(path.name):
        return path.with_name(path.name[: -(_EXT_DIGITS + 1)])
    return path


def list_volumes(base_path: pathlib.Path) -> list[pathlib.Path]:
    """base_path(`이름.zip`)에 딸린 볼륨 파일들을 번호순으로 돌려준다."""
    base_path = pathlib.Path(base_path)
    pattern = base_path.name + "." + "[0-9]" * _EXT_DIGITS
    return sorted(base_path.parent.glob(pattern))


def open_volume_target(base_path: pathlib.Path, volume_size: VolumeSize):
    """쓰기용 볼륨 묶음을 연다. 라이브러리에 파일 객체로 넘기면 된다.

    같은 이름의 이전 볼륨이 남아 있으면 먼저 지운다. 이전 실행이 5개를 만들었는데 이번에
    3개만 만들면 .004/.005가 낡은 채로 남아 해제 시 손상된 것처럼 보이기 때문이다.
    사용자가 출력 경로를 직접 고른 상황이라 단일 아카이브를 덮어쓰는 것과 같은 의미다.
    """
    base_path = pathlib.Path(base_path)
    for stale in list_volumes(base_path):
        stale.unlink()
    return multivolumefile.MultiVolume(
        base_path, mode="wb", volume=volume_size.bytes, ext_digits=_EXT_DIGITS
    )


def open_volume_source(first_volume_path: pathlib.Path):
    """읽기용 볼륨 묶음을 연다. `.001` 경로를 받아 나머지 볼륨은 이름 규칙으로 찾는다."""
    base_path = strip_volume_suffix(pathlib.Path(first_volume_path))
    return multivolumefile.MultiVolume(base_path, mode="rb", ext_digits=_EXT_DIGITS)


def finalize_volumes(base_path: pathlib.Path) -> tuple[pathlib.Path, int]:
    """쓰기가 끝난 뒤 최종 첫 파일 경로와 볼륨 수를 확정한다.

    볼륨이 하나뿐이면 `.001`을 떼어 일반 아카이브로 이름을 바꾼다. 메일 첨부 용도에서
    받는 쪽이 `이름.7z.001` 하나만 받으면 열지 못하는 경우가 흔해, 결과가 한 조각이면
    분할하지 않은 것과 같은 파일을 주는 편이 낫다(7-Zip은 이 경우에도 .001을 붙인다).
    """
    base_path = pathlib.Path(base_path)
    volumes = list_volumes(base_path)
    if not volumes:
        raise FileNotFoundError(f"생성된 볼륨 파일이 없습니다: {base_path}")
    if len(volumes) == 1:
        volumes[0].replace(base_path)
        return base_path, 1
    return volumes[0], len(volumes)
