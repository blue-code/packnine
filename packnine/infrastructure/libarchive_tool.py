"""구형 ZipCrypto 암호 zip 해제를 bsdtar(libarchive)에 위임한다.

왜 필요한가: ZipCrypto(PKWARE 구형 암호)는 바이트마다 키가 갱신되는 구조라 순수
파이썬으로는 병렬화도 벡터화도 불가능하다. 실측 1.39MB/s로, 7GB짜리 아카이브 하나에
약 87분이 걸린다. 같은 파일을 bsdtar는 88.9MB/s로 푼다(64배). 7.29GB 기준 87분이
82초가 된다.

왜 bsdtar인가: Windows 11에 `C:\\Windows\\System32\\tar.exe`로 기본 포함돼 있어
사용자가 따로 설치할 것이 없다. RAR 해제에서 이미 unrar/bsdtar에 의존하고 있으므로
외부 도구 위임 자체는 이 프로젝트에 새로운 방식이 아니다.

적용 범위는 ZipCrypto뿐이다. AES(WinZip AES) zip은 pyzipper가 pycryptodome(C)로
처리해 209MB/s가 나오므로 위임할 이유가 없다. 일반 zip도 마찬가지다.

보안: 이 모듈은 목적지에 직접 쓰지 않는다. 호출자가 만든 staging 폴더에만 풀고,
검증을 통과한 엔트리만 호출자가 목적지로 옮긴다. Zip Slip·압축 폭탄·심볼릭 링크
검사는 기존대로 ArchiveSecurityPolicy가 담당하며 이 경로에서도 그대로 선행된다.

알아 둘 제약: libarchive는 비밀번호를 `--passphrase` 명령행 인자로만 받는다
(환경변수·파일·표준입력 모두 지원하지 않는다). 해제하는 동안 같은 사용자 권한의
다른 프로세스가 작업 목록에서 비밀번호를 읽을 수 있다. 로컬 단일 사용자 환경을
전제로 받아들인 트레이드오프이며, 이 때문에 적용 범위를 "이렇게 하지 않으면 사실상
쓸 수 없는" ZipCrypto로만 한정했다.
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import threading
import time
from typing import Callable

from packnine.domain.exceptions import CorruptedArchiveError, InvalidPasswordError

# 바이트 진행률을 올리는 주기. 너무 잦으면 GUI 이벤트 큐만 채우고, 너무 뜸하면
# 막대가 끊겨 보인다.
_POLL_INTERVAL = 0.15

# 비밀번호가 틀렸을 때 bsdtar가 내놓는 문구. 종료 코드만으로는 손상과 구분되지 않는다.
_WRONG_PASSWORD_MARKERS = ("incorrect passphrase", "wrong passphrase")

_cached_tool: pathlib.Path | None | str = "unknown"


def _looks_like_libarchive(executable: pathlib.Path) -> bool:
    """`tar`라는 이름은 GNU tar일 수도 있다. libarchive인지 직접 물어본다."""
    try:
        result = subprocess.run(  # noqa: S603
            [str(executable), "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    banner = (result.stdout + result.stderr).lower()
    return "bsdtar" in banner or "libarchive" in banner


def _candidates() -> list[pathlib.Path]:
    """`tar`라는 이름을 가진 실행 파일을 PATH 전체에서 모은다.

    shutil.which는 첫 번째 것만 돌려준다. 그런데 Git for Windows를 설치했다면
    PATH 앞쪽의 `tar`가 GNU tar라서, 뒤쪽에 있는 Windows 기본 bsdtar를 영영 못 찾는다
    (이 개발 PC가 정확히 그 상태였다). 그래서 후보를 전부 모아 하나씩 확인한다.
    Windows 기본 경로는 PATH와 무관하게 맨 앞에 둔다.
    """
    found: list[pathlib.Path] = []

    system_root = os.environ.get("SystemRoot")
    if system_root:
        builtin = pathlib.Path(system_root) / "System32" / "tar.exe"
        if builtin.is_file():
            found.append(builtin)

    for directory in os.environ.get("PATH", "").split(os.pathsep):
        if not directory:
            continue
        for name in ("bsdtar", "tar"):
            located = shutil.which(name, path=directory)
            if located is None:
                continue
            candidate = pathlib.Path(located)
            if candidate not in found:
                found.append(candidate)
    return found


def find_tool() -> pathlib.Path | None:
    """쓸 수 있는 bsdtar를 찾는다. 없으면 None(호출자는 기존 경로로 돌아간다)."""
    global _cached_tool
    if _cached_tool != "unknown":
        return _cached_tool  # type: ignore[return-value]

    found: pathlib.Path | None = None
    for candidate in _candidates():
        if _looks_like_libarchive(candidate):
            found = candidate
            break

    _cached_tool = found
    return found


def reset_tool_cache() -> None:
    """테스트에서 탐색 결과를 되돌리기 위한 훅."""
    global _cached_tool
    _cached_tool = "unknown"


def _scan_staging(staging: pathlib.Path) -> tuple[int, str | None]:
    """지금까지 쓴 바이트 수와 "현재 쓰고 있는 파일" 이름을 한 번에 구한다.

    이름을 bsdtar의 -v 출력에서 읽지 않는 이유: stderr가 파이프로 가면 블록 버퍼링
    되어 줄이 뭉쳐서 늦게 도착한다. 실제로 6MB짜리를 쓰는 내내 직전 파일 이름이
    표시됐다. 디스크에서 가장 최근에 손댄 파일을 보는 쪽이 늘 맞다.
    """
    total = 0
    newest_name: str | None = None
    newest_time = -1.0
    for item in staging.rglob("*"):
        try:
            if not item.is_file():
                continue
            stat = item.stat()
        except OSError:
            # 쓰는 중인 파일이 잠깐 사라질 수 있다. 진행률일 뿐이니 넘어간다.
            continue
        total += stat.st_size
        if stat.st_mtime >= newest_time:
            newest_time = stat.st_mtime
            newest_name = item.relative_to(staging).as_posix()
    return total, newest_name


def extract_zip(
    tool: pathlib.Path,
    archive: pathlib.Path,
    staging: pathlib.Path,
    password: str,
    *,
    total_bytes: int = 0,
    on_progress: Callable[[str, int, int], None] | None = None,
    members: list[str] | None = None,
) -> None:
    """archive를 staging 폴더에 푼다. 실패하면 도메인 예외를 던진다.

    members를 주면 그 엔트리들만 꺼낸다(드래그 아웃처럼 일부만 필요한 경우).
    staging은 반드시 호출자가 만든 빈 폴더여야 한다. 이 함수는 목적지를 모른다.
    """
    # --passphrase를 반드시 넘긴다. 빠뜨리면 bsdtar가 콘솔에서 입력을 받으려 하고,
    # 콘솔 없는 우클릭 실행에서는 그대로 멈춰 버린다.
    command = [
        str(tool),
        "--passphrase",
        password,
        "-x",
        "-f",
        str(archive),
        "-C",
        str(staging),
    ]
    if members:
        # 이름은 옵션이 아니라 피연산자로 간다. `--`로 끊어 `-`로 시작하는 이름이
        # 옵션으로 해석되지 않게 한다.
        command.append("--")
        command.extend(members)

    process = subprocess.Popen(  # noqa: S603
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        errors="replace",
    )

    messages: list[str] = []

    def _drain_stderr() -> None:
        # 파이프를 비워 주지 않으면 출력이 많을 때 자식이 막힌다. 오류 판별에도 쓴다.
        assert process.stderr is not None
        for line in process.stderr:
            messages.append(line.rstrip("\r\n"))

    reader = threading.Thread(target=_drain_stderr, daemon=True)
    reader.start()

    last_name = archive.name
    if on_progress is not None and total_bytes > 0:
        while process.poll() is None:
            written, name = _scan_staging(staging)
            last_name = name or last_name
            on_progress(last_name, min(written, total_bytes), total_bytes)
            time.sleep(_POLL_INTERVAL)

    return_code = process.wait()
    reader.join(timeout=5)

    if on_progress is not None and total_bytes > 0 and return_code == 0:
        on_progress(last_name, total_bytes, total_bytes)

    if return_code == 0:
        return

    detail = "\n".join(messages).strip()
    lowered = detail.lower()
    if any(marker in lowered for marker in _WRONG_PASSWORD_MARKERS):
        raise InvalidPasswordError(f"비밀번호가 틀렸거나 필요합니다: {archive.name}")
    raise CorruptedArchiveError(
        f"압축을 푸는 중 오류가 발생했습니다: {archive.name}\n{detail}".rstrip()
    )
