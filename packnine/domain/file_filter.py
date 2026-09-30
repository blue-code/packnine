"""압축 대상에서 제외할 파일/폴더를 판단하는 도메인 규칙.

".git, node_modules, *.tmp 빼고 압축" 같은 요구를 처리한다. 외부 의존성이 없는 순수
규칙이라 도메인 계층에 둔다.

매칭 규칙은 사용자가 직관적으로 기대하는 쪽으로 정했다.

- 경로 구분자가 없는 패턴(`*.tmp`, `node_modules`)은 **경로의 각 조각**과 비교한다.
  그래서 어느 깊이에 있든 걸린다(`app/node_modules/pkg/index.js` 제외).
- 경로 구분자가 있는 패턴(`build/*`)은 **상대 경로 전체**와 비교한다.
- 대소문자를 구분하지 않는다(Windows 파일 시스템 관례).

빈 문자열은 패턴으로 받아들이지 않는다. 받아들이면 모든 경로가 걸려 빈 아카이브가
만들어지는데, 이는 사용자가 상상할 수 있는 최악의 실패다.
"""
from __future__ import annotations

import dataclasses
import fnmatch
import pathlib
import re

# 쉼표와 줄바꿈 둘 다 구분자로 받는다(옵션 창에서 한 줄로 쓰든 여러 줄로 쓰든 동작).
_SEPARATORS = re.compile(r"[,\n\r]+")


@dataclasses.dataclass(frozen=True)
class ExcludeFilter:
    """압축에서 제외할 패턴 모음."""

    patterns: tuple[str, ...] = ()

    @classmethod
    def from_text(cls, text: str | None) -> "ExcludeFilter":
        if not text:
            return cls()
        parts = (part.strip() for part in _SEPARATORS.split(text))
        return cls(tuple(part for part in parts if part))

    @property
    def is_empty(self) -> bool:
        return not self.patterns

    def excludes(self, relative_path: pathlib.PurePath) -> bool:
        """상대 경로가 제외 대상이면 True."""
        if self.is_empty:
            return False

        posix = relative_path.as_posix().lower()
        parts = [part.lower() for part in relative_path.parts]

        for pattern in self.patterns:
            lowered = pattern.lower()
            if "/" in lowered or "\\" in lowered:
                # 경로형 패턴: 상대 경로 전체와 비교한다.
                normalized = lowered.replace("\\", "/")
                if fnmatch.fnmatch(posix, normalized):
                    return True
                # "build/*"는 build 아래 더 깊은 항목도 제외해야 자연스럽다.
                if fnmatch.fnmatch(posix, normalized.rstrip("*").rstrip("/") + "/*"):
                    return True
            else:
                # 이름형 패턴: 경로의 어느 조각이든 걸리면 제외(폴더면 그 하위 전체가 빠진다).
                if any(fnmatch.fnmatch(part, lowered) for part in parts):
                    return True
        return False
