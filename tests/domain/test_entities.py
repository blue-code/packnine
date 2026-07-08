"""entities.py 에 대한 테스트 (TDD RED 단계에서 먼저 작성)."""
import pytest

from packnine.domain.entities import ArchiveEntry, ArchiveManifest


class TestArchiveEntry:
    def test_compression_ratio_normal_case(self):
        entry = ArchiveEntry(name="a.txt", size=1000, compressed_size=100)
        assert entry.compression_ratio == 10

    def test_compression_ratio_zero_compressed_size_no_zero_division(self):
        entry = ArchiveEntry(name="a.txt", size=1000, compressed_size=0)
        # compressed_size=0 이어도 ZeroDivisionError가 나지 않고 size / max(compressed_size, 1) 로 계산
        assert entry.compression_ratio == 1000

    def test_compression_ratio_zero_size_and_zero_compressed(self):
        entry = ArchiveEntry(name="empty.txt", size=0, compressed_size=0)
        assert entry.compression_ratio == 0

    def test_defaults(self):
        entry = ArchiveEntry(name="a.txt", size=10, compressed_size=5)
        assert entry.is_dir is False
        assert entry.is_symlink is False
        assert entry.modified_at is None


class TestArchiveManifest:
    def test_total_uncompressed_size(self):
        entries = [
            ArchiveEntry(name="a.txt", size=100, compressed_size=10),
            ArchiveEntry(name="b.txt", size=200, compressed_size=20),
        ]
        manifest = ArchiveManifest(entries=entries, format_name="zip")
        assert manifest.total_uncompressed_size == 300

    def test_total_compressed_size(self):
        entries = [
            ArchiveEntry(name="a.txt", size=100, compressed_size=10),
            ArchiveEntry(name="b.txt", size=200, compressed_size=20),
        ]
        manifest = ArchiveManifest(entries=entries, format_name="zip")
        assert manifest.total_compressed_size == 30

    def test_empty_manifest_totals_are_zero(self):
        manifest = ArchiveManifest(entries=[], format_name="zip")
        assert manifest.total_uncompressed_size == 0
        assert manifest.total_compressed_size == 0

    def test_format_name_stored(self):
        manifest = ArchiveManifest(entries=[], format_name="7z")
        assert manifest.format_name == "7z"
