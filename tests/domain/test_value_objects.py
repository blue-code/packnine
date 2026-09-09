"""value_objects.py 에 대한 테스트 (TDD RED 단계에서 먼저 작성)."""
import pytest

from packnine.domain.value_objects import (
    SPLIT_PRESETS,
    CompressionLevel,
    PasswordPolicy,
    VolumeSize,
)


class TestCompressionLevel:
    def test_store_is_zero(self):
        assert CompressionLevel.STORE == 0

    def test_fastest_is_one(self):
        assert CompressionLevel.FASTEST == 1

    def test_normal_is_five(self):
        assert CompressionLevel.NORMAL == 5

    def test_maximum_is_nine(self):
        assert CompressionLevel.MAXIMUM == 9

    def test_is_int_enum_comparable(self):
        assert CompressionLevel.MAXIMUM > CompressionLevel.STORE


class TestPasswordPolicy:
    def test_default_is_not_encrypted(self):
        policy = PasswordPolicy()
        assert policy.is_encrypted is False

    def test_none_password_is_not_encrypted(self):
        policy = PasswordPolicy(password=None)
        assert policy.is_encrypted is False

    def test_empty_password_is_not_encrypted(self):
        policy = PasswordPolicy(password="")
        assert policy.is_encrypted is False

    def test_non_empty_password_is_encrypted(self):
        policy = PasswordPolicy(password="secret")
        assert policy.is_encrypted is True

    def test_default_use_aes256_is_true(self):
        policy = PasswordPolicy(password="secret")
        assert policy.use_aes256 is True

    def test_is_frozen(self):
        policy = PasswordPolicy(password="secret")
        with pytest.raises(Exception):
            policy.password = "changed"


class TestVolumeSize:
    def test_from_megabytes_uses_binary_megabyte(self):
        # 메일 서비스 한도는 MiB 기준으로 잡혀 있어 1024 기반이 안전하다.
        assert VolumeSize.from_megabytes(10).bytes == 10 * 1024 * 1024

    def test_megabytes_property_round_trips(self):
        assert VolumeSize.from_megabytes(25).megabytes == 25

    @pytest.mark.parametrize("bad", [0, -1])
    def test_non_positive_bytes_rejected(self, bad):
        with pytest.raises(ValueError):
            VolumeSize(bytes=bad)

    def test_from_megabytes_rejects_less_than_one(self):
        with pytest.raises(ValueError):
            VolumeSize.from_megabytes(0)

    def test_is_frozen(self):
        size = VolumeSize.from_megabytes(1)
        with pytest.raises(Exception):
            size.bytes = 5


class TestSplitPresets:
    def _by_label(self, keyword: str):
        matches = [p for p in SPLIT_PRESETS if keyword in p.label]
        assert len(matches) == 1, f"'{keyword}' 프리셋이 정확히 하나여야 한다: {matches}"
        return matches[0]

    def test_naver_regular_attachment_is_10mb(self):
        assert self._by_label("네이버 메일 일반첨부").megabytes == 10

    def test_naver_large_attachment_is_2gb(self):
        assert self._by_label("네이버 메일 대용량첨부").megabytes == 2048

    def test_daum_regular_attachment_is_25mb(self):
        assert self._by_label("다음 메일 일반첨부").megabytes == 25

    def test_daum_large_attachment_stays_under_fat32_limit(self):
        # 4096MB는 FAT32 파일 한도를 1바이트 넘겨 USB 복사가 실패하므로 4095MB로 잡는다.
        assert self._by_label("다음 메일 대용량첨부").megabytes == 4095

    def test_gmail_attachment_is_25mb(self):
        assert self._by_label("Gmail").megabytes == 25

    def test_every_preset_has_note_and_positive_size(self):
        for preset in SPLIT_PRESETS:
            assert preset.megabytes >= 1
            assert preset.note
            assert preset.volume_size.megabytes == preset.megabytes
