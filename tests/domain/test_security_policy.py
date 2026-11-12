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

    def test_absolute_total_limit_is_opt_in(self):
        """절대 용량 상한은 기본으로 걸지 않는다.

        예전에는 10GiB 절대 상한이 기본값이었는데, 압증 없이 단지 담아 둔 동영상 모음처럼
        압축폭학폭탄과 무관한 아카이부까지 "안전하지 않음"으로 막아 버렸다. 압축폭학폭탄의
        본질은 절대 크기가 아니라 효상률이라 상한을 호출자가 필요할 때만 주도록 바꿨다.
        """
        policy = ArchiveSecurityPolicy()
        assert policy.max_total_uncompressed_size is None


class TestAlternateDataStreamRejection:
    """NTFS ADS(Alternate Data Stream) 삽입 방지 - 엔트리명에 ':'가 섞여 있으면
    "normal.txt:evil.exe" 같은 형태로 파일이 아닌 대체 스트림에 쓰여 탐지를 피해
    숨겨진 실행파일이 생성될 수 있다(RAR ADS 처리 관련 CVE-2025-8088류와 동일한 클래스)."""

    @pytest.mark.parametrize(
        "malicious_name",
        [
            "normal.txt:evil.exe",
            "sub/dir/report.docx:hidden.dll",
            "a:b:c",
        ],
    )
    def test_entry_name_with_colon_is_rejected(
        self, policy: ArchiveSecurityPolicy, destination_root: pathlib.Path, malicious_name: str
    ):
        entry = ArchiveEntry(name=malicious_name, size=10, compressed_size=5)
        with pytest.raises(UnsafeArchiveEntryError):
            policy.validate_entry(entry, destination_root)


class TestEntryCountLimit:
    """엔트리 개수 상한 - 압축비/전체용량은 정상이어도 파일 수가 지나치게 많으면
    처리 자체가 리소스 고갈(DoS)로 이어질 수 있어 별도로 방어한다."""

    def test_entry_count_within_limit_passes(self):
        policy = ArchiveSecurityPolicy(max_entry_count=3)
        entries = [ArchiveEntry(name=f"{i}.txt", size=1, compressed_size=1) for i in range(3)]
        manifest = ArchiveManifest(entries=entries, format_name="zip")
        policy.validate_manifest(manifest)  # 예외 없이 통과해야 함

    def test_entry_count_exceeds_limit_raises(self):
        policy = ArchiveSecurityPolicy(max_entry_count=3)
        entries = [ArchiveEntry(name=f"{i}.txt", size=1, compressed_size=1) for i in range(4)]
        manifest = ArchiveManifest(entries=entries, format_name="zip")
        with pytest.raises(UnsafeArchiveEntryError) as exc_info:
            policy.validate_manifest(manifest)
        assert exc_info.value.entry_name == "__manifest__"

    def test_default_entry_count_limit(self):
        policy = ArchiveSecurityPolicy()
        assert policy.max_entry_count == 100_000


class TestEntryNameLengthLimit:
    """비정상적으로 긴 엔트리 이름(경로) 방어 - 파일시스템/외부 도구 호출 시
    예기치 못한 동작을 유발할 수 있는 병적인(pathological) 입력을 사전 차단한다."""

    def test_normal_length_name_passes(
        self, policy: ArchiveSecurityPolicy, destination_root: pathlib.Path
    ):
        entry = ArchiveEntry(name="normal_file.txt", size=1, compressed_size=1)
        result = policy.validate_entry(entry, destination_root)
        assert isinstance(result, pathlib.Path)

    def test_excessively_long_name_rejected(
        self, policy: ArchiveSecurityPolicy, destination_root: pathlib.Path
    ):
        entry = ArchiveEntry(name="a" * 2000 + ".txt", size=1, compressed_size=1)
        with pytest.raises(UnsafeArchiveEntryError):
            policy.validate_entry(entry, destination_root)

    def test_default_entry_name_length_limit(self):
        policy = ArchiveSecurityPolicy()
        assert policy.max_entry_name_length == 1024


class TestUnsafeArchiveEntryErrorMessage:
    def test_message_includes_entry_name_and_reason(self):
        error = UnsafeArchiveEntryError(entry_name="evil.exe", reason="경로 탈출 시도")
        assert "evil.exe" in str(error)
        assert "경로 탈출 시도" in str(error)
        assert error.entry_name == "evil.exe"
        assert error.reason == "경로 탈출 시도"


class TestValidateManifestCompressionBomb:
    """전체 팽창률 기준 압축폭탄 검사.

    엔트리 하나하나는 압축률 상한 안에 있어도 그런 엔트리를 수만 개 모으면 디스크를
    가득 채울 수 있다. 그래서 엔트리별 압축률과 별개로 합계 팽창률에도 상한을 둔다.
    """

    def test_stored_large_archive_passes(self):
        """압축하지 않고 담은 대용량 아카이브는 통과해야 한다.

        실제로 막혔던 사례다. 동영상 16개를 STORED로 담은 10.6GiB zip은 팽창률이 1.0이라
        압축폭탄일 수가 없다 - 출력이 이미 입력만큼 크기 때문이다.
        """
        entries = [
            ArchiveEntry(
                name=f"ep{index:02d}.mkv", size=700_000_000, compressed_size=700_000_000
            )
            for index in range(16)
        ]
        manifest = ArchiveManifest(entries=entries, format_name="zip")
        ArchiveSecurityPolicy().validate_manifest(manifest)  # 예외 없이 통과해야 함

    def test_total_ratio_over_limit_raises(self):
        """작은 아카이브가 거대하게 부풀면 거부한다."""
        policy = ArchiveSecurityPolicy(
            max_total_compression_ratio=10.0, min_total_uncompressed_size=1000
        )
        entries = [ArchiveEntry(name="bomb.bin", size=1_000_000, compressed_size=1000)]
        manifest = ArchiveManifest(entries=entries, format_name="zip")
        with pytest.raises(UnsafeArchiveEntryError) as exc_info:
            policy.validate_manifest(manifest)
        assert exc_info.value.entry_name == "__manifest__"
        assert "팽창률" in exc_info.value.reason

    def test_many_entries_each_within_entry_ratio_still_caught(self):
        """엔트리별 압축률은 통과하는데 합계가 과도한 경우를 잡는다."""
        policy = ArchiveSecurityPolicy(min_total_uncompressed_size=1000)
        # 엔트리별 압축률 50은 엔트리 상한(100) 안이지만, 100개가 모이면 전체 상한을 넘는다.
        entries = [
            ArchiveEntry(name=f"f{index}.txt", size=50_000, compressed_size=1000)
            for index in range(100)
        ]
        manifest = ArchiveManifest(entries=entries, format_name="zip")
        with pytest.raises(UnsafeArchiveEntryError):
            policy.validate_manifest(manifest)

    def test_small_archive_under_allowance_floor_passes(self):
        """작은 아카이브는 팽창률이 높아도 허용 하한까지는 통과시킨다.

        텍스트 로그를 묶은 gzip은 팽창률이 100을 넘기도 한다. 결과물이 몇백 MB면
        디스크를 위협하지 않으므로 비율만으로 막으면 과잉 차단이 된다.
        """
        policy = ArchiveSecurityPolicy(min_total_uncompressed_size=500_000_000)
        entries = [
            ArchiveEntry(name="logs.txt", size=400_000_000, compressed_size=1_000_000)
        ]
        manifest = ArchiveManifest(entries=entries, format_name="zip")
        policy.validate_manifest(manifest)  # 예외 없이 통과해야 함

    def test_empty_manifest_passes(self):
        manifest = ArchiveManifest(entries=[], format_name="zip")
        ArchiveSecurityPolicy().validate_manifest(manifest)

    def test_absolute_limit_still_applies_when_given(self):
        """호출자가 절대 상한을 주면 팽창률과 무관하게 그 상한이 걸린다."""
        policy = ArchiveSecurityPolicy(max_total_uncompressed_size=1000)
        entries = [ArchiveEntry(name="big.bin", size=2000, compressed_size=2000)]
        manifest = ArchiveManifest(entries=entries, format_name="zip")
        with pytest.raises(UnsafeArchiveEntryError):
            policy.validate_manifest(manifest)

    def test_default_total_ratio_limit(self):
        policy = ArchiveSecurityPolicy()
        assert policy.max_total_compression_ratio == 20.0

    def test_default_allowance_floor_is_ten_gib(self):
        """하한은 0.13.0까지 '절대 상한'이던 10GiB를 뒤집어 '바닥'으로 쓴다."""
        policy = ArchiveSecurityPolicy()
        assert policy.min_total_uncompressed_size == 10 * 1024 * 1024 * 1024

    def test_well_compressing_text_archive_is_not_blocked(self):
        """잘 줄어든 텍스트 묶음을 과잉 차단하지 않는다.

        50MB zip이 2GB로 풀리면 팽창률 40이다. 전체 상한(20)만 보면 걸리지만 이건
        악의가 아니라 로그/덤프가 잘 줄어든 결과이고, 2GB는 디스크를 위협하지 않는다.
        """
        entries = [
            ArchiveEntry(name="dump.sql", size=2_000_000_000, compressed_size=50_000_000)
        ]
        manifest = ArchiveManifest(entries=entries, format_name="zip")
        ArchiveSecurityPolicy().validate_manifest(manifest)  # 예외 없이 통과해야 함

    def test_real_bomb_above_floor_is_still_blocked(self):
        """하한을 올려도 진짜 압축폭탄은 계속 막힌다.

        10MB가 500GB로 부푸는 경우다. 하한(10GiB)을 훌쩍 넘고 팽창률도 5만이다.
        """
        entries = [
            ArchiveEntry(
                name="bomb.bin", size=500 * 1024**3, compressed_size=10 * 1024**2
            )
        ]
        manifest = ArchiveManifest(entries=entries, format_name="zip")
        with pytest.raises(UnsafeArchiveEntryError):
            ArchiveSecurityPolicy().validate_manifest(manifest)

    def test_large_archive_expanding_far_beyond_its_size_is_blocked(self):
        """아카이브가 커도 팽창률이 과하면 막는다(10GB → 500GB)."""
        entries = [
            ArchiveEntry(
                name="big.bin", size=500 * 1024**3, compressed_size=10 * 1024**3
            )
        ]
        manifest = ArchiveManifest(entries=entries, format_name="zip")
        with pytest.raises(UnsafeArchiveEntryError):
            ArchiveSecurityPolicy().validate_manifest(manifest)

    def test_total_ratio_limit_must_be_below_entry_ratio_limit_to_matter(self):
        """전체 팽창률은 엔트리별 팽창률의 가중평균이라는 전제를 못 박아 둔다.

        두 상한을 같게 두면 엔트리 검사를 통과한 아카이브는 전체 검사도 항상 통과해
        이 검사가 죽은 코드가 된다. 기본값이 그렇게 바뀌는 것을 막는다.
        """
        policy = ArchiveSecurityPolicy()
        assert policy.max_total_compression_ratio < policy.max_compression_ratio
