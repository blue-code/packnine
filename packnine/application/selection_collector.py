"""탐색기 다중 선택으로 여러 번 실행된 프로세스를 하나로 모으는 유스케이스 헬퍼.

배경: 우클릭 verb의 명령줄은 "%1"(항목 하나)이다. %*는 실제 탐색기에서 경로가 비어
전달돼 명령이 조용히 실패하던 원인이라 되돌릴 수 없다(infrastructure/context_menu.py
docstring 참고). 그래서 파일 5개를 선택하고 메뉴를 누르면 탐색기가 프로세스를 5번
띄운다. "알아서 압축"처럼 즉시 처리하는 명령은 그래도 무해하지만, 옵션 창을 띄우는
"PackNine으로 압축하기..."는 다이얼로그가 5개 뜨는 꼴이라 쓸 수 없다.

해결: 먼저 뜬 프로세스가 파일 락으로 대표(leader)가 되어 짧은 수집 창(window) 동안
기다렸다가, 그 사이 다른 프로세스들이 남긴 경로를 모두 합쳐 자기 다이얼로그 하나에
채운다. 대표가 되지 못한 프로세스는 경로만 남기고 즉시 종료한다(None 반환).

트레이드오프: 매 실행마다 window_seconds만큼(기본 0.6초) 다이얼로그가 늦게 뜬다.
COM 셸 확장(IShellExtInit)이면 지연 없이 선택 전체를 한 번에 받을 수 있지만, 그건
네이티브 DLL 등록/비트수 대응이 필요해 "관리자 권한 없이 HKCU만 건드린다"는 현재
설치 방침과 맞지 않는다. 지연 0.6초를 받아들이는 쪽을 택했다.
"""
from __future__ import annotations

import os
import pathlib
import tempfile
import time
import uuid

# 대표 자리를 나타내는 락 파일 이름. O_EXCL로 만들어져 가장 먼저 성공한 하나만 대표가 된다.
_LOCK_NAME = "leader.lock"
# 각 프로세스가 자기 경로를 적어두는 파일의 확장자. 프로세스마다 별도 파일을 쓰므로
# 동시 append로 인한 줄 깨짐이 원천적으로 없다.
_ITEM_SUFFIX = ".paths"
# 다이얼로그가 뜨기까지 사용자가 체감하는 지연이므로 짧게 잡는다. 탐색기는 선택 항목별
# 프로세스를 거의 동시에(수십 ms 내) 띄우므로 이 정도면 충분히 다 모인다.
_DEFAULT_WINDOW_SECONDS = 0.6
# 강제 종료 등으로 남은 락을 영원히 존중하면 이후 모든 우클릭이 먹통이 된다.
_DEFAULT_STALE_AFTER_SECONDS = 30.0


def _default_session_dir() -> pathlib.Path:
    base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    return pathlib.Path(base) / "PackNine" / "pending-selection"


def _write_item_file(session_dir: pathlib.Path, paths: list[str]) -> None:
    """이번 프로세스가 받은 경로들을 고유한 이름의 파일로 남긴다.

    대표가 되기 전에 먼저 남겨야, 락 획득에 실패해 곧바로 종료하더라도 경로가
    대표에게 전달된다.
    """
    item_path = session_dir / f"{os.getpid()}-{uuid.uuid4().hex}{_ITEM_SUFFIX}"
    item_path.write_text("\n".join(paths), encoding="utf-8")


def _is_stale(lock_path: pathlib.Path, stale_after_seconds: float) -> bool:
    try:
        return (time.time() - lock_path.stat().st_mtime) > stale_after_seconds
    except OSError:
        # 방금 사라졌다면 stale로 취급해 재시도하게 둔다.
        return True


def _try_become_leader(lock_path: pathlib.Path, stale_after_seconds: float) -> bool:
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        if not _is_stale(lock_path, stale_after_seconds):
            return False
        try:
            lock_path.unlink()
        except OSError:
            return False
        # 오래된 락을 치웠으니 한 번만 더 시도한다(무한 재귀 방지를 위해 재시도 1회).
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except OSError:
            return False
    except OSError:
        return False
    os.close(fd)
    return True


def _drain(session_dir: pathlib.Path) -> list[str]:
    """수집 창 동안 쌓인 경로 파일을 모두 읽어 합치고 정리한다.

    생성 시각 순(같으면 이름 순)으로 안정 정렬해 결과를 매번 같은 규칙으로 만든다.
    다만 탐색기가 항목별 프로세스를 띄우는 순서 자체가 보장되지 않으므로, 최종 목록이
    사용자가 선택한 순서와 일치한다고 가정해서는 안 된다(다이얼로그에서 재정렬 가능).
    중복 경로는 순서를 유지한 채 하나로 접는다.
    """
    item_paths = sorted(
        session_dir.glob(f"*{_ITEM_SUFFIX}"),
        key=lambda p: (p.stat().st_mtime if p.exists() else 0.0, p.name),
    )

    collected: list[str] = []
    seen: set[str] = set()
    for item_path in item_paths:
        try:
            content = item_path.read_text(encoding="utf-8")
        except OSError:
            continue
        finally:
            try:
                item_path.unlink()
            except OSError:
                pass
        for line in content.splitlines():
            if line and line not in seen:
                seen.add(line)
                collected.append(line)
    return collected


def collect_selection(
    paths: list[str],
    *,
    window_seconds: float = _DEFAULT_WINDOW_SECONDS,
    session_dir: pathlib.Path | str | None = None,
    stale_after_seconds: float = _DEFAULT_STALE_AFTER_SECONDS,
) -> list[str] | None:
    """다중 선택으로 흩어져 실행된 경로들을 대표 프로세스 하나로 모은다.

    반환값:
    - list[str]: 이번 프로세스가 대표다. 모인 전체 경로(중복 제거)를 그대로 쓰면 된다.
    - None: 다른 프로세스가 대표다. 호출자는 아무것도 하지 말고 즉시 종료해야 한다.

    수집 디렉터리 준비가 실패하면(권한/디스크 문제) 기능을 막지 않도록 받은 경로를
    그대로 돌려준다 - 최악의 경우 다이얼로그가 여러 개 뜰 뿐, 압축은 계속 가능하다.
    """
    session = pathlib.Path(session_dir) if session_dir is not None else _default_session_dir()
    try:
        session.mkdir(parents=True, exist_ok=True)
        _write_item_file(session, paths)
    except OSError:
        return list(paths)

    lock_path = session / _LOCK_NAME
    if not _try_become_leader(lock_path, stale_after_seconds):
        return None

    try:
        time.sleep(window_seconds)
        collected = _drain(session)
    finally:
        # 락을 반드시 풀어야 다음 우클릭이 대표를 다시 뽑을 수 있다.
        try:
            lock_path.unlink()
        except OSError:
            pass

    return collected or list(paths)
