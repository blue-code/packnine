"""아키텍처 불변식(invariant)을 코드로 강제하는 메타 테스트.

SECURITY.md는 "PackNine은 자체 바이너리 파서를 구현하지 않는다"고 명시한다.
이 주장이 시간이 지나도 깨지지 않도록, 반디집 ARK 라이브러리류의 OOB 취약점을
유발할 수 있는 수동 바이트/오프셋 파싱 패턴이 소스에 유입되면 이 테스트가 실패한다.
"""
from __future__ import annotations

import pathlib
import re

import pytest

_PACKNINE_ROOT = pathlib.Path(__file__).resolve().parent.parent / "packnine"

# 수동 바이너리 파싱(오프셋 계산, struct 언패킹, ctypes 버퍼 접근)의 신호가 되는 패턴.
# 이런 코드가 필요해지면 반드시 그 이유를 문서화하고 리뷰를 거쳐야 한다.
_FORBIDDEN_PATTERNS = [
    re.compile(r"\bstruct\.(unpack|pack|calcsize)\b"),
    re.compile(r"\bctypes\b"),
    re.compile(r"\bmemoryview\b"),
]


def _all_source_files() -> list[pathlib.Path]:
    return sorted(_PACKNINE_ROOT.rglob("*.py"))


@pytest.mark.parametrize("path", _all_source_files(), ids=lambda p: str(p.relative_to(_PACKNINE_ROOT)))
def test_no_manual_binary_parsing_patterns(path: pathlib.Path) -> None:
    text = path.read_text(encoding="utf-8")
    for pattern in _FORBIDDEN_PATTERNS:
        assert not pattern.search(text), (
            f"{path}에서 수동 바이너리 파싱 패턴({pattern.pattern})이 발견되었습니다. "
            "PackNine은 압축 포맷을 직접 파싱하지 않고 zipfile/tarfile/py7zr/외부 unrar에 "
            "위임하는 것을 아키텍처 원칙으로 삼습니다(SECURITY.md 6번 항목 참고)."
        )
