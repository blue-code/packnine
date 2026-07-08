"""security_policy.py 에 대한 테스트 (TDD RED 단계에서 먼저 작성).

압축/해제 프로그램의 보안 핵심 로직이므로 Zip Slip, 절대경로, 심볼릭 링크,
압축폭탄(zip bomb), 전체 용량 초과 케이스를 폭넓게 검증한다.
"""
from __future__ import annotations

import pathlib

import pytest

from packnine.domain.entities import ArchiveEntry, ArchiveManifest
from packnine.domain.exceptions import UnsafeArchiveEntryError
from packnine.domain.security_policy import ArchiveSecurityPolicy


@pytest.fixture
def policy() -> ArchiveSecurityPolicy:
    return ArchiveSecurityPolicy()


@pytest.fixture
def destination_root(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "extract_here"


class TestValidateEntryNormalCase:
    @pytest.mark.parametrize(
        "entry_name",
        [
            "a.txt",
            "sub/dir/file.txt",
            "sub\\dir\\file.txt",
            "폴더/파일.hwp",
            "just_a_name",
        ],
    )
    def test_normal_entry_passes_and_returns_path_under_destination_root(
        self, policy: ArchiveSecurityPolicy, destination_root: pathlib.Path, entry_name: str
    ):
        entry = ArchiveEntry(name=entry_name, size=100, compressed_size=50)
        result = policy.validate_entry(entry, destination_root)

        assert isinstance(result, pathlib.Path)
        assert result.is_absolute()
        resolved_root = destination_root.resolve()
        assert resolved_root in result.resolve().parents or result.resolve() == resolved_root


class TestZipSlip:
    @pytest.mark.parametrize(
        "malicious_name",
        [
            "../../evil.exe",
            "..\\..\\evil.exe",
            "../../../etc/passwd",
            "sub/../../evil.exe",
            "..",
            "a/b/../../../../evil.exe",
            "sub\\..\\..\\evil.exe",
        ],
    )
    def test_path_traversal_is_rejected(
        self, policy: ArchiveSecurityPolicy, destination_root: pathlib.Path, malicious_name: str
    ):
        entry = ArchiveEntry(name=malicious_name, size=10, compressed_size=5)
        with pytest.raises(UnsafeArchiveEntryError) as exc_info:
            policy.validate_entry(entry, destination_root)
        assert malicious_name == exc_info.value.entry_name


class TestAbsolutePathRejected:
    @pytest.mark.parametrize(
        "absolute_name",
        [
            "/etc/passwd",
            "C:\\Windows\\System32\\evil.dll",
            "C:/Windows/System32/evil.dll",
            "D:\\evil.exe",
            "/root/.ssh/id_rsa",
        ],
    )
    def test_absolute_path_or_drive_letter_is_rejected(
        self, policy: ArchiveSecurityPolicy, destination_root: pathlib.Path, absolute_name: str
    ):
        entry = ArchiveEntry(name=absolute_name, size=10, compressed_size=5)
        with pytest.raises(UnsafeArchiveEntryError):
            policy.validate_entry(entry, destination_root)


class TestSymlinkRejection:
    def test_symlink_rejected_by_default(
        self, policy: ArchiveSecurityPolicy, destination_root: pathlib.Path
    ):
        entry = ArchiveEntry(name="link", size=0, compressed_size=0, is_symlink=True)
        with pytest.raises(UnsafeArchiveEntryError):
            policy.validate_entry(entry, destination_root)

    def test_symlink_allowed_when_policy_permits(self, destination_root: pathlib.Path):
        permissive_policy = ArchiveSecurityPolicy(allow_symlinks=True)
        entry = ArchiveEntry(name="link", size=0, compressed_size=0, is_symlink=True)
        result = permissive_policy.validate_entry(entry, destination_root)
        assert isinstance(result, pathlib.Path)


class TestCompressionBombRejection:
    def test_excessive_compression_ratio_rejected(
        self, policy: ArchiveSecurityPolicy, destination_root: pathlib.Path
    ):
        # zip bomb 시뮬레이션: 100MB로 압축해제되는데 압축된 크기는 100바이트 뿐
        entry = ArchiveEntry(name="bomb.txt", size=100_000_000, compressed_size=100)
        with pytest.raises(UnsafeArchiveEntryError):
            policy.validate_entry(entry, destination_root)

    def test_ratio_within_limit_passes(
        self, policy: ArchiveSecurityPolicy, destination_root: pathlib.Path
    ):
        entry = ArchiveEntry(name="ok.txt", size=1000, compressed_size=50)  # 비율 20 < 기본 100
        result = policy.validate_entry(entry, destination_root)
        assert isinstance(result, pathlib.Path)

    def test_directory_entry_skips_ratio_check(
        self, policy: ArchiveSecurityPolicy, destination_root: pathlib.Path
    ):
        # 디렉터리는 size/compressed_size가 극단적이어도 압축폭탄 검사를 건너뛴다
        entry = ArchiveEntry(
            name="huge_dir/", size=100_000_000, compressed_size=1, is_dir=True
        )
        result = policy.validate_entry(entry, destination_root)
        assert isinstance(result, pathlib.Path)


class TestValidateManifest:
    def test_total_size_within_limit_passes(self):
        policy = ArchiveSecurityPolicy(max_total_uncompressed_size=1000)
        entries = [
            ArchiveEntry(name="a.txt", size=400, compressed_size=100),
            ArchiveEntry(name="b.txt", size=500, compressed_size=100),
        ]
        manifest = ArchiveManifest(entries=entries, format_name="zip")
        policy.validate_manifest(manifest)  # 예외 없이 통과해야 함

    def test_total_size_exceeds_limit_raises(self):
        policy = ArchiveSecurityPolicy(max_total_uncompressed_size=1000)
        entries = [
            ArchiveEntry(name="a.txt", size=800, compressed_size=100),
            ArchiveEntry(name="b.txt", size=800, compressed_size=100),
        ]
        manifest = ArchiveManifest(entries=entries, format_name="zip")
        with pytest.raises(UnsafeArchiveEntryError) as exc_info:
            policy.validate_manifest(manifest)
        assert exc_info.value.entry_name == "__manifest__"

    def test_default_manifest_limit_is_ten_gb(self):
        policy = ArchiveSecurityPolicy()
        assert policy.max_total_uncompressed_size == 10 * 1024 * 1024 * 1024


class TestUnsafeArchiveEntryErrorMessage:
    def test_message_includes_entry_name_and_reason(self):
        error = UnsafeArchiveEntryError(entry_name="evil.exe", reason="경로 탈출 시도")
        assert "evil.exe" in str(error)
        assert "경로 탈출 시도" in str(error)
        assert error.entry_name == "evil.exe"
        assert error.reason == "경로 탈출 시도"
