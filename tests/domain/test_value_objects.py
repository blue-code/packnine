"""value_objects.py 에 대한 테스트 (TDD RED 단계에서 먼저 작성)."""
import pytest

from packnine.domain.value_objects import CompressionLevel, PasswordPolicy


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
