"""CLI 서브커맨드(compress/extract/list) end-to-end 스모크 테스트.

main()을 argv 리스트로 직접 호출해 서브프로세스 없이 빠르게 검증한다.
"""
from __future__ import annotations

import pathlib

from packnine.presentation.cli import main


def _make_source_tree(tmp_path: pathlib.Path) -> pathlib.Path:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "a.txt").write_text("hello a", encoding="utf-8")
    (src_dir / "b.txt").write_text("hello b " * 20, encoding="utf-8")
    return src_dir


def test_compress_then_list(tmp_path, capsys):
    src_dir = _make_source_tree(tmp_path)
    archive_path = tmp_path / "out.zip"

    exit_code = main(
        ["compress", str(src_dir / "a.txt"), str(src_dir / "b.txt"), "-o", str(archive_path)]
    )
    assert exit_code == 0
    assert archive_path.exists()
    compress_output = capsys.readouterr().out
    assert "압축 완료" in compress_output

    exit_code = main(["list", str(archive_path)])
    assert exit_code == 0
    list_output = capsys.readouterr().out
    assert "a.txt" in list_output
    assert "b.txt" in list_output


def test_compress_then_extract_round_trip(tmp_path, capsys):
    src_dir = _make_source_tree(tmp_path)
    archive_path = tmp_path / "out.zip"
    destination = tmp_path / "extracted"

    assert main(
        ["compress", str(src_dir / "a.txt"), str(src_dir / "b.txt"), "-o", str(archive_path)]
    ) == 0
    capsys.readouterr()

    exit_code = main(["extract", str(archive_path), "-d", str(destination)])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "압축 해제 완료" in output

    assert (destination / "a.txt").read_text(encoding="utf-8") == "hello a"
    assert (destination / "b.txt").read_text(encoding="utf-8") == "hello b " * 20


def test_extract_missing_archive_returns_exit_code_1_with_friendly_message(tmp_path, capsys):
    missing_archive = tmp_path / "does_not_exist.zip"
    destination = tmp_path / "out"

    exit_code = main(["extract", str(missing_archive), "-d", str(destination)])

    assert exit_code == 1
    captured = capsys.readouterr()
    # 스택트레이스가 아니라 사용자 친화적 메시지가 stderr로 나가야 한다.
    assert "Traceback" not in captured.err
    assert captured.err.strip() != ""


def test_compress_with_password(tmp_path, capsys):
    src_dir = _make_source_tree(tmp_path)
    archive_path = tmp_path / "secure.zip"

    exit_code = main(
        [
            "compress",
            str(src_dir / "a.txt"),
            "-o",
            str(archive_path),
            "--password",
            "s3cret!",
        ]
    )
    assert exit_code == 0
    assert archive_path.exists()

    exit_code = main(["list", str(archive_path), "--password", "s3cret!"])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "a.txt" in output
