"""최근 연 아카이브 목록을 사용자 프로필에 보관한다.

편의 기능이라 어떤 실패도 앱을 멈춰서는 안 된다 - 읽기/쓰기 오류는 모두 삼키고 빈 목록
또는 무동작으로 처리한다. 목록에 남은 파일이 그 사이 삭제·이동됐을 수 있으므로 읽을 때
존재 여부를 확인해 사라진 항목은 조용히 걸러낸다(메뉴에서 눌렀을 때 오류만 보는 상황 방지).
"""
from __future__ import annotations

import json
import os
import pathlib
import tempfile

# 메뉴에 한눈에 들어오는 길이. 이보다 길면 고르기가 오히려 번거롭다.
MAX_ENTRIES = 10


def _default_store_path() -> pathlib.Path:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return pathlib.Path(base) / "PackNine" / "recent.json"


def _resolve(store_path: pathlib.Path | str | None) -> pathlib.Path:
    return pathlib.Path(store_path) if store_path is not None else _default_store_path()


def _read_raw(store: pathlib.Path) -> list[str]:
    try:
        data = json.loads(store.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # 파일 없음/권한 없음/JSON 깨짐 - 모두 "기록 없음"으로 취급한다.
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, str)]


def load(*, store_path: pathlib.Path | str | None = None) -> list[pathlib.Path]:
    """최근 연 아카이브 경로를 최신순으로 돌려준다(사라진 파일은 제외)."""
    store = _resolve(store_path)
    result: list[pathlib.Path] = []
    for raw in _read_raw(store):
        path = pathlib.Path(raw)
        try:
            if path.is_file():
                result.append(path)
        except OSError:
            # 네트워크 드라이브가 끊긴 경우 등 - 목록에서 빼고 넘어간다.
            continue
    return result[:MAX_ENTRIES]


def remember(
    archive_path: pathlib.Path | str, *, store_path: pathlib.Path | str | None = None
) -> None:
    """방금 연 아카이브를 목록 맨 앞에 올린다(중복 제거, 상한 적용)."""
    store = _resolve(store_path)
    target = str(pathlib.Path(archive_path))

    entries = [raw for raw in _read_raw(store) if raw != target]
    entries.insert(0, target)
    entries = entries[:MAX_ENTRIES]

    try:
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        # 기록에 실패해도 사용자가 하던 작업을 방해하지 않는다.
        pass


def clear(*, store_path: pathlib.Path | str | None = None) -> None:
    store = _resolve(store_path)
    try:
        store.parent.mkdir(parents=True, exist_ok=True)
        store.write_text("[]", encoding="utf-8")
    except OSError:
        pass
