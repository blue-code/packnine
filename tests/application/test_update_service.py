"""UpdateService(아카이브 편집) 테스트 - TDD RED 단계에서 먼저 작성.

반디집처럼 이미 만든 아카이브에 파일을 추가하거나 엔트리를 삭제할 수 있어야 한다.
포맷별 append/delete 지원 편차를 없애기 위해 재작성 방식을 쓰므로, 편집 후에도
나머지 내용과 비밀번호가 그대로 유지되는지가 핵심 검증 대상이다.
"""
from __future__ import annotations

import pathlib

import pytest

from packnine.application.compress_service import CompressService
from packnine.application.extract_service import ExtractService
from packnine.application.update_service import UpdateService
from packnine.domain.exceptions import InvalidPasswordError


def _make_zip(tmp_path: pathlib.Path, password: str | None = None) -> pathlib.Path:
    src = tmp_path / "base"
    (src / "docs").mkdir(parents=True)
    (src / "keep.txt").write_text("keep me", encoding="utf-8")
    (src / "docs" / "inner.txt").write_text("inner", encoding="utf-8")
    archive_path = tmp_path / "target.zip"
    CompressService().compress([src / "keep.txt", src / "docs"], archive_path, password=password)
    return archive_path


class TestAddFiles:
    def test_add_file_appears_in_manifest_and_extraction(self, tmp_path: pathlib.Path):
        archive_path = _make_zip(tmp_path)
        new_file = tmp_path / "added.txt"
        new_file.write_text("new content", encoding="utf-8")

        manifest = UpdateService().add_files(archive_path, [new_file])

        names = {e.name for e in manifest.entries}
        assert "added.txt" in names
        assert "keep.txt" in names  # 기존 내용 유지

        dest = tmp_path / "out"
        ExtractService().extract(archive_path, dest)
        assert (dest / "added.txt").read_text(encoding="utf-8") == "new content"
        assert (dest / "keep.txt").read_text(encoding="utf-8") == "keep me"

    def test_add_preserves_password(self, tmp_path: pathlib.Path):
        archive_path = _make_zip(tmp_path, password="pw123")
        new_file = tmp_path / "added.txt"
        new_file.write_text("secret add", encoding="utf-8")

        UpdateService().add_files(archive_path, [new_file], password="pw123")

        # 편집 후에도 암호가 유지되어야 한다: 무암호 해제는 실패, 올바른 암호는 성공.
        with pytest.raises(InvalidPasswordError):
            ExtractService().extract(archive_path, tmp_path / "nopw")
        dest = tmp_path / "out_pw"
        ExtractService().extract(archive_path, dest, password="pw123")
        assert (dest / "added.txt").read_text(encoding="utf-8") == "secret add"

    def test_add_missing_source_leaves_archive_unchanged(self, tmp_path: pathlib.Path):
        archive_path = _make_zip(tmp_path)
        before = archive_path.read_bytes()

        with pytest.raises(FileNotFoundError):
            UpdateService().add_files(archive_path, [tmp_path / "does_not_exist.txt"])

        assert archive_path.read_bytes() == before  # 원자성: 실패 시 원본 무손상


class TestRemoveEntries:
    def test_remove_file_entry(self, tmp_path: pathlib.Path):
        archive_path = _make_zip(tmp_path)

        manifest = UpdateService().remove_entries(archive_path, ["keep.txt"])

        names = {e.name for e in manifest.entries}
        assert "keep.txt" not in names
        assert any(n.startswith("docs") for n in names)  # 다른 엔트리는 유지

    def test_remove_directory_entry_removes_children(self, tmp_path: pathlib.Path):
        archive_path = _make_zip(tmp_path)

        manifest = UpdateService().remove_entries(archive_path, ["docs"])

        names = {e.name for e in manifest.entries}
        assert not any(n.startswith("docs") for n in names)
        assert "keep.txt" in names

    def test_remove_unknown_entry_raises_keyerror(self, tmp_path: pathlib.Path):
        archive_path = _make_zip(tmp_path)
        before = archive_path.read_bytes()

        with pytest.raises(KeyError):
            UpdateService().remove_entries(archive_path, ["ghost.txt"])

        assert archive_path.read_bytes() == before
