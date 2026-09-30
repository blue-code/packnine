"""아카이브 내부 텍스트 파일 미리보기 헬퍼 테스트.

미리보기는 "선택할 때마다" 도는 경로라 큰 파일을 통째로 읽으면 안 되고, 인코딩이
무엇이든 앱이 멈추거나 예외로 죽어서는 안 된다.
"""
from __future__ import annotations

from packnine.presentation.gui.text_preview import (
    MAX_PREVIEW_BYTES,
    MAX_PREVIEW_LINES,
    is_text_name,
    read_text_preview,
)


def test_recognizes_common_text_extensions():
    for name in ("메모.txt", "README.md", "data.csv", "conf.json", "a/b/script.py", "log.LOG"):
        assert is_text_name(name), name


def test_rejects_binary_and_image_names():
    for name in ("photo.png", "movie.mp4", "app.exe", "archive.zip", "noext"):
        assert not is_text_name(name), name


def test_reads_utf8_text(tmp_path):
    path = tmp_path / "a.txt"
    path.write_text("안녕하세요\n두 번째 줄", encoding="utf-8")

    assert read_text_preview(path) == "안녕하세요\n두 번째 줄"


def test_reads_legacy_cp949_text(tmp_path):
    # 옛 프로그램이 만든 한글 텍스트도 깨지지 않고 보여야 한다.
    path = tmp_path / "old.txt"
    path.write_bytes("한글 내용".encode("cp949"))

    assert read_text_preview(path) == "한글 내용"


def test_truncates_long_files_by_line_count(tmp_path):
    path = tmp_path / "long.txt"
    path.write_text("\n".join(f"line {i}" for i in range(MAX_PREVIEW_LINES + 100)), encoding="utf-8")

    preview = read_text_preview(path)

    # 본문은 상한까지만 남고, 그 뒤에 생략 안내가 붙는다.
    body = preview.split("\n\n…")[0]
    assert len(body.splitlines()) == MAX_PREVIEW_LINES
    assert "line 0" in preview
    assert f"line {MAX_PREVIEW_LINES + 50}" not in preview
    assert "생략" in preview


def test_reads_only_head_of_huge_file(tmp_path):
    # 수백 MB 로그를 통째로 읽어 UI가 멈추는 일이 없어야 한다.
    path = tmp_path / "huge.txt"
    path.write_bytes(b"A" * (MAX_PREVIEW_BYTES * 3))

    preview = read_text_preview(path)

    assert len(preview) <= MAX_PREVIEW_BYTES + 200


def test_binary_content_does_not_raise(tmp_path):
    path = tmp_path / "weird.txt"
    path.write_bytes(bytes(range(256)) * 10)

    # 어떤 바이트가 들어와도 예외 없이 문자열을 돌려줘야 한다.
    assert isinstance(read_text_preview(path), str)


def test_missing_file_returns_none(tmp_path):
    assert read_text_preview(tmp_path / "없는파일.txt") is None
