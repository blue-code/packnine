"""압축할 소스 경로를 (실제 파일, 아카이브 내부 이름) 쌍으로 평탄화한다.

zip/7z/tar 어댑터가 각자 디렉터리를 훑고 있었는데, 제외 패턴을 지원하려면 세 곳에
같은 규칙을 넣어야 해서 한 곳으로 모았다. 내부 이름 규칙은 기존 zip 어댑터의 동작을
그대로 따른다(`폴더명/상대경로`, 단일 파일은 파일명).

제외 패턴이 비어 있으면 어댑터는 이 헬퍼를 쓰지 않고 기존 경로를 그대로 탄다 -
라이브러리의 재귀 기능(py7zr.writeall, tarfile.add)이 빈 디렉터리 등을 더 충실히
담기 때문에, 필터가 필요 없는 일반적인 경우의 동작을 바꾸지 않기 위해서다.
"""
from __future__ import annotations

import pathlib

from packnine.domain.file_filter import ExcludeFilter


def collect_files(
    paths: list[pathlib.Path], exclude: ExcludeFilter | None = None
) -> list[tuple[pathlib.Path, str]]:
    """소스 경로들을 압축 대상 파일 목록으로 펼친다.

    반환값은 (디스크상의 파일 경로, 아카이브 안에 들어갈 이름) 쌍의 목록이다.
    제외 패턴은 아카이브 내부 이름을 기준으로 판단한다 - 사용자가 보는 구조와 같아야
    "node_modules 제외"가 직관대로 동작한다.
    """
    exclude = exclude or ExcludeFilter()
    collected: list[tuple[pathlib.Path, str]] = []

    for raw_path in paths:
        path = pathlib.Path(raw_path)
        if path.is_dir():
            for file_path in sorted(path.rglob("*")):
                if not file_path.is_file():
                    continue
                arcname = f"{path.name}/{file_path.relative_to(path).as_posix()}"
                if exclude.excludes(pathlib.PurePosixPath(arcname)):
                    continue
                collected.append((file_path, arcname))
        else:
            arcname = path.name
            if exclude.excludes(pathlib.PurePosixPath(arcname)):
                continue
            collected.append((path, arcname))

    return collected
