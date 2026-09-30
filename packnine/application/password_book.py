"""여러 아카이브에 같은 비밀번호를 쓰는 경우를 위한 비밀번호 목록.

암호가 걸린 아카이브를 연달아 열 때 매번 같은 비밀번호를 타이핑하는 번거로움을 없앤다.
해제를 시도하기 전에 이 목록의 후보들을 조용히 먼저 넣어보고, 맞는 것이 없을 때만
사용자에게 입력을 요청한다.

보안상 두 가지를 전제로 설계했다.

1) 기본값은 '이번 실행 동안만' 기억이다. 디스크에 남기는 것은 호출자가 save()를 명시적으로
   불렀을 때만 일어난다.
2) 디스크에 남길 때도 평문으로 두지 않는다. 다만 이것은 **난독화이지 암호화가 아니다** -
   키가 프로그램 안에 있으므로 작정하고 들여다보는 공격자는 되돌릴 수 있다. 어깨너머로
   보거나 파일을 열어본 사람이 바로 읽지 못하게 하는 수준의 보호다. 그래서 기본은
   저장하지 않는 쪽이고, 저장은 사용자가 선택해야 한다.
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import tempfile
from typing import Callable

# 난독화용 고정 키. 암호학적 보호가 아님을 이름으로 분명히 한다(모듈 docstring 참고).
_OBFUSCATION_KEY = b"PackNine-password-book-v1"


def _obfuscate(raw: bytes) -> bytes:
    key = _OBFUSCATION_KEY
    return bytes(byte ^ key[index % len(key)] for index, byte in enumerate(raw))


class PasswordBook:
    """최근에 통했던 비밀번호를 기억하고, 새 아카이브에 차례로 시도한다."""

    # 너무 많으면 틀린 비밀번호를 반복 시도하느라 해제가 느려진다.
    MAX_ENTRIES = 20

    def __init__(self, store_path: pathlib.Path | str | None = None) -> None:
        self._passwords: list[str] = []
        self._store_path = pathlib.Path(store_path) if store_path is not None else None

    # ------------------------------------------------------------------
    # 메모리 상의 목록
    # ------------------------------------------------------------------
    def remember(self, password: str | None) -> None:
        """방금 통한 비밀번호를 목록 맨 앞에 올린다(중복 제거, 상한 적용)."""
        if not password:
            return
        if password in self._passwords:
            self._passwords.remove(password)
        self._passwords.insert(0, password)
        del self._passwords[self.MAX_ENTRIES :]

    def candidates(self) -> list[str]:
        """최근에 통한 순서대로 후보를 돌려준다."""
        return list(self._passwords)

    def try_each(self, attempt: Callable[[str], bool]) -> str | None:
        """후보를 차례로 넣어보고 성공한 비밀번호를 돌려준다. 없으면 None.

        attempt는 비밀번호 하나를 받아 성공 여부를 돌려주는 함수다. 성공하는 순간
        멈추므로 남은 후보는 시도하지 않는다.
        """
        for password in self._passwords:
            if attempt(password):
                return password
        return None

    def forget_all(self) -> None:
        self._passwords.clear()
        self.save()

    # ------------------------------------------------------------------
    # 디스크 보관 (선택)
    # ------------------------------------------------------------------
    def _resolve_store(self) -> pathlib.Path:
        if self._store_path is not None:
            return self._store_path
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        return pathlib.Path(base) / "PackNine" / "passwords.dat"

    def load(self) -> None:
        """저장해둔 목록을 읽어온다. 파일이 없거나 깨졌으면 조용히 빈 목록으로 둔다."""
        store = self._resolve_store()
        try:
            encoded = base64.b64decode(store.read_bytes())
            data = json.loads(_obfuscate(encoded).decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            return
        if not isinstance(data, list):
            return
        self._passwords = [item for item in data if isinstance(item, str) and item][
            : self.MAX_ENTRIES
        ]

    def save(self) -> None:
        """현재 목록을 디스크에 남긴다(호출자가 명시적으로 원할 때만 부른다)."""
        store = self._resolve_store()
        try:
            raw = json.dumps(self._passwords, ensure_ascii=False).encode("utf-8")
            store.parent.mkdir(parents=True, exist_ok=True)
            store.write_bytes(base64.b64encode(_obfuscate(raw)))
        except OSError:
            # 저장 실패가 사용자의 작업을 막아서는 안 된다.
            pass
