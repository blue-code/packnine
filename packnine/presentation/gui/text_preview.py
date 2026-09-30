"""아카이브 안의 텍스트 파일을 미리보기용으로 읽어오는 헬퍼.

이미지 미리보기(image_viewer)와 짝을 이루는 텍스트 쪽 구현이다. 목록에서 항목을 고를
때마다 호출되는 경로이므로 두 가지를 반드시 지킨다.

1) 앞부분만 읽는다 - 수백 MB짜리 로그를 통째로 읽으면 선택 한 번에 UI가 멈춘다.
2) 어떤 바이트가 들어와도 예외를 내지 않는다 - 확장자가 .txt라도 내용이 바이너리일 수
   있고, 미리보기 실패가 앱을 방해해서는 안 된다.

인코딩은 UTF-8 -> cp949 순으로 시도한다(zip_adapter의 파일명 복원과 같은 순서). 둘 다
실패하면 대체 문자를 써서라도 보여준다.
"""
from __future__ import annotations

import pathlib

# 읽어들일 최대 바이트. 미리보기 패널에 들어갈 분량이면 충분하다.
MAX_PREVIEW_BYTES = 64 * 1024
# 보여줄 최대 줄 수. 한 줄이 아주 긴 파일도 있으므로 바이트 상한과 함께 건다.
MAX_PREVIEW_LINES = 300

_TEXT_EXTENSIONS = frozenset(
    {
        ".txt", ".md", ".markdown", ".log", ".csv", ".tsv",
        ".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".properties",
        ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".htm", ".css", ".scss",
        ".c", ".h", ".cpp", ".hpp", ".cs", ".java", ".kt", ".go", ".rs", ".rb", ".php",
        ".sh", ".bat", ".cmd", ".ps1", ".sql", ".srt", ".vtt", ".gitignore", ".env",
    }
)


def is_text_name(name: str) -> bool:
    """이름만 보고 텍스트로 미리보기할 대상인지 판단한다."""
    suffix = pathlib.PurePosixPath(name).suffix.lower()
    return suffix in _TEXT_EXTENSIONS


def _decode(raw: bytes) -> str:
    """바이트를 문자열로 바꾸고 줄바꿈을 LF로 통일한다.

    아카이브 안의 텍스트는 CRLF(Windows)/CR(옛 Mac)이 섞여 있다. 그대로 두면 줄 수 계산이
    어긋나고 미리보기에 빈 줄이 끼어 보인다.
    """
    text = None
    for encoding in ("utf-8", "cp949"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        # 어느 쪽도 아니면 읽을 수 있는 만큼이라도 보여준다(깨진 글자는 대체 문자로).
        text = raw.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_text_preview(path: pathlib.Path) -> str | None:
    """path의 앞부분을 읽어 미리보기 문자열로 돌려준다. 읽을 수 없으면 None."""
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_PREVIEW_BYTES)
            truncated_by_size = len(f.read(1)) > 0
    except OSError:
        return None

    text = _decode(raw)

    lines = text.splitlines()
    truncated_by_lines = len(lines) > MAX_PREVIEW_LINES
    if truncated_by_lines:
        lines = lines[:MAX_PREVIEW_LINES]
        text = "\n".join(lines)

    if truncated_by_size and not truncated_by_lines:
        # 마지막 줄이 중간에서 잘렸을 수 있으므로 통째로 버린다.
        text = "\n".join(lines[:-1]) if len(lines) > 1 else text

    if truncated_by_size or truncated_by_lines:
        text += "\n\n… (이하 생략 — 전체 내용은 압축을 풀어 확인하세요)"
    return text
