"""tar_adapter.py 에 대한 TDD 테스트 (RED 단계에서 먼저 작성).

표준 tarfile 기반 어댑터가 .tar / .tar.gz / .tar.bz2 / .tar.xz 를 모두
round-trip 처리하는지, 그리고 ArchiveSecurityPolicy + tarfile 표준 data filter
이중 방어가 실제로 작동하는지를 검증한다.
"""
from __future__ import annotations

import pathlib
import tarfile

import pytest

from packnine.domain.exceptions import UnsafeArchiveEntryError
from packnine.infrastructure.tar_adapter import TarArchiveReader, TarArchiveWriter
from tests.infrastructure.conftest import assert_tree_equal, make_sample_source_tree


class TestTarRoundTrip:
    @pytest.mark.parametrize(
        "archive_name",
        ["out.tar", "out.tar.gz", "out.tgz", "out.tar.bz2", "out.tar.xz"],
    )
    def test_round_trip_for_all_supported_extensions(
        self, tmp_path: pathlib.Path, archive_name: str
    ):
        src = make_sample_source_tree(tmp_path)
        archive_path = tmp_path / archive_name

        writer = TarArchiveWriter(archive_path)
        writer.add_files([src])
        writer.close()

        reader = TarArchiveReader(archive_path)
        entries = reader.list_entries()
        assert len(entries) > 0
        names = {e.name for e in entries}
        assert "source/a.txt" in names
        assert "source/sub/c.txt" in names

        dest = tmp_path / f"extracted_{archive_name.replace('.', '_')}"
        reader.extract_all(dest)
        reader.close()

        assert_tree_equal(src, dest / "source")

    def test_extract_one_extracts_single_entry(self, tmp_path: pathlib.Path):
        src = make_sample_source_tree(tmp_path)
        archive_path = tmp_path / "one.tar.gz"

        writer = TarArchiveWriter(archive_path)
        writer.add_files([src])
        writer.close()

        reader = TarArchiveReader(archive_path)
        dest = tmp_path / "extracted_one"
        reader.extract_one("source/a.txt", dest)
        reader.close()

        assert (dest / "source" / "a.txt").read_text(encoding="utf-8") == "hello a"
        assert not (dest / "source" / "b.txt").exists()


class TestTarProgressCallback:
    def test_extract_all_calls_progress_callback(self, tmp_path: pathlib.Path):
        src = make_sample_source_tree(tmp_path)
        archive_path = tmp_path / "progress.tar.gz"

        writer = TarArchiveWriter(archive_path)
        writer.add_files([src])
        writer.close()

        calls: list[tuple[str, int, int]] = []

        def on_progress(name: str, done: int, total: int) -> None:
            calls.append((name, done, total))

        reader = TarArchiveReader(archive_path)
        reader.extract_all(tmp_path / "extracted_progress", on_progress=on_progress)
        reader.close()

        assert len(calls) > 0


class TestTarSecurityRegression:
    def test_extract_all_rejects_path_traversal_and_writes_nothing(self, tmp_path: pathlib.Path):
        # tarfile을 직접 사용해 '../evil.txt' 라는 악성 엔트리를 가진 tar를 만든다.
        malicious_path = tmp_path / "evil.tar"
        with tarfile.open(malicious_path, "w") as tf:
            info = tarfile.TarInfo(name="../evil.txt")
            data = b"evil content"
            info.size = len(data)
            import io

            tf.addfile(info, io.BytesIO(data))

        dest = tmp_path / "extract_here"
        reader = TarArchiveReader(malicious_path)
        with pytest.raises(UnsafeArchiveEntryError):
            reader.extract_all(dest)
        reader.close()

        assert not dest.exists()
        assert not (tmp_path / "evil.txt").exists()
