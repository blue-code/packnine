"""ZipCrypto 해제를 bsdtar에 위임하는 경로 테스트.

왜 위임하는가: ZipCrypto는 바이트마다 키가 갱신되는 구조라 순수 파이썬으로는
1.39MB/s가 한계다(실측). 7GB 아카이브 하나에 약 87분이 걸린다. 같은 파일을
bsdtar(libarchive)는 88.9MB/s로 푼다.

여기서 지키려는 계약은 네 가지다.
1. ZipCrypto일 때만 위임한다. AES는 이미 pycryptodome(C)로 빠르다.
2. 도구가 없으면 조용히 기존 경로로 돌아간다(기능이 사라지면 안 된다).
3. 외부 도구를 쓰더라도 보안 검증은 그대로다 - staging을 거쳐 검증된 엔트리만 남는다.
4. 틀린 비밀번호는 도메인 예외(InvalidPasswordError)로 올라온다.
"""
from __future__ import annotations

import os
import pathlib

import pytest

from packnine.domain.exceptions import InvalidPasswordError
from packnine.infrastructure import libarchive_tool
from packnine.infrastructure.zip_adapter import ZipArchiveReader

from tests.infrastructure.conftest import write_zipcrypto_archive


@pytest.fixture(autouse=True)
def _clear_tool_cache():
    libarchive_tool.reset_tool_cache()
    yield
    libarchive_tool.reset_tool_cache()


def _bsdtar_or_skip() -> pathlib.Path:
    tool = libarchive_tool.find_tool()
    if tool is None:
        pytest.skip("이 환경에는 bsdtar(libarchive)가 없다")
    return tool


class TestDelegationDecision:
    def test_zipcrypto_archive_is_detected(self, tmp_path: pathlib.Path):
        archive = tmp_path / "legacy.zip"
        write_zipcrypto_archive(archive, [("a.txt", b"hello")], password=b"pw")

        reader = ZipArchiveReader(archive, password="pw")
        try:
            assert reader.uses_legacy_zipcrypto() is True
        finally:
            reader.close()

    def test_aes_archive_is_not_treated_as_legacy(self, tmp_path: pathlib.Path):
        import pyzipper

        archive = tmp_path / "aes.zip"
        with pyzipper.AESZipFile(
            archive, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
        ) as zf:
            zf.setpassword(b"pw")
            zf.writestr("a.txt", b"hello")

        reader = ZipArchiveReader(archive, password="pw")
        try:
            # AES는 pycryptodome(C)로 209MB/s가 나온다. 위임할 이유가 없다.
            assert reader.uses_legacy_zipcrypto() is False
        finally:
            reader.close()

    def test_plain_archive_is_not_treated_as_legacy(self, tmp_path: pathlib.Path):
        import zipfile

        archive = tmp_path / "plain.zip"
        with zipfile.ZipFile(archive, "w") as zf:
            zf.writestr("a.txt", b"hello")

        reader = ZipArchiveReader(archive)
        try:
            assert reader.uses_legacy_zipcrypto() is False
        finally:
            reader.close()


class TestFallback:
    def test_extracts_correctly_when_tool_is_missing(self, tmp_path: pathlib.Path, monkeypatch):
        """도구가 없는 환경에서도 결과는 같아야 한다(느릴 뿐)."""
        archive = tmp_path / "legacy.zip"
        write_zipcrypto_archive(
            archive, [("문서/기획안.txt", "한글 내용".encode("utf-8"))], password=b"pw"
        )
        monkeypatch.setattr(libarchive_tool, "find_tool", lambda: None)

        destination = tmp_path / "out"
        reader = ZipArchiveReader(archive, password="pw")
        try:
            reader.extract_all(destination)
        finally:
            reader.close()

        assert (destination / "문서" / "기획안.txt").read_bytes() == "한글 내용".encode("utf-8")


class TestDelegatedExtraction:
    def test_delegated_result_matches_the_python_path(self, tmp_path: pathlib.Path, monkeypatch):
        _bsdtar_or_skip()
        members = [
            ("문서/기획안.txt", "한글 내용 " .encode("utf-8") * 50),
            ("읽어보기.txt", b"readme\n"),
        ]
        archive = tmp_path / "legacy.zip"
        write_zipcrypto_archive(archive, members, password=b"pw")

        fast = tmp_path / "fast"
        reader = ZipArchiveReader(archive, password="pw")
        try:
            assert reader._should_delegate() is not None, "bsdtar가 있으면 위임해야 한다"
            reader.extract_all(fast)
        finally:
            reader.close()

        slow = tmp_path / "slow"
        monkeypatch.setattr(libarchive_tool, "find_tool", lambda: None)
        reader = ZipArchiveReader(archive, password="pw")
        try:
            reader.extract_all(slow)
        finally:
            reader.close()

        for name, payload in members:
            assert (fast / name).read_bytes() == payload
            assert (fast / name).read_bytes() == (slow / name).read_bytes()

    def test_progress_is_reported_in_bytes(self, tmp_path: pathlib.Path):
        _bsdtar_or_skip()
        # 잘 압축되는 데이터는 압축폭탄 가드에 걸린다. 동영상처럼 안 줄어드는
        # 데이터를 써야 실제 상황과 같아진다.
        payload = os.urandom(3 * 1024 * 1024)
        archive = tmp_path / "legacy.zip"
        write_zipcrypto_archive(archive, [("big.bin", payload)], password=b"pw")

        calls: list[tuple[str, int, int]] = []
        reader = ZipArchiveReader(archive, password="pw")
        try:
            reader.extract_all(tmp_path / "out", on_progress=lambda *a: calls.append(a))
        finally:
            reader.close()

        assert calls, "진행률 보고가 하나도 없다"
        assert calls[-1][1] == calls[-1][2] == len(payload)

    def test_wrong_password_raises_domain_error(self, tmp_path: pathlib.Path):
        _bsdtar_or_skip()
        archive = tmp_path / "legacy.zip"
        write_zipcrypto_archive(archive, [("a.txt", b"hello")], password=b"correct")

        reader = ZipArchiveReader(archive, password="wrong")
        try:
            with pytest.raises(InvalidPasswordError):
                reader.extract_all(tmp_path / "out")
        finally:
            reader.close()

    def test_path_escape_is_still_blocked(self, tmp_path: pathlib.Path):
        """외부 도구를 쓰더라도 Zip Slip은 막혀야 한다.

        bsdtar는 우리 보안 정책을 모른다. 그래서 목적지에 직접 쓰게 두지 않고
        staging을 거쳐 검증된 경로로만 옮긴다. 검증 단계에서 걸리면 외부 도구는
        아예 실행되지도 않는다.
        """
        from packnine.domain.exceptions import UnsafeArchiveEntryError

        archive = tmp_path / "evil.zip"
        write_zipcrypto_archive(archive, [("../탈출.txt", b"pwned")], password=b"pw")

        destination = tmp_path / "out"
        reader = ZipArchiveReader(archive, password="pw")
        try:
            with pytest.raises(UnsafeArchiveEntryError):
                reader.extract_all(destination)
        finally:
            reader.close()

        assert not (tmp_path / "탈출.txt").exists()


class TestToolDiscovery:
    def test_gnu_tar_is_rejected(self, monkeypatch, tmp_path: pathlib.Path):
        """`tar`라는 이름이라고 다 libarchive가 아니다. GNU tar는 거른다."""
        gnu_tar = tmp_path / "tar"
        gnu_tar.write_text("", encoding="utf-8")
        monkeypatch.setattr(libarchive_tool, "_candidates", lambda: [gnu_tar])
        monkeypatch.setattr(libarchive_tool, "_looks_like_libarchive", lambda path: False)

        assert libarchive_tool.find_tool() is None

    def test_first_libarchive_candidate_wins(self, monkeypatch, tmp_path: pathlib.Path):
        """GNU tar가 PATH 앞쪽에 있어도 뒤쪽의 bsdtar를 찾아내야 한다.

        Git for Windows를 깔면 PATH 앞쪽 `tar`가 GNU tar다. shutil.which는 첫
        번째만 돌려주므로, 거기서 멈추면 Windows 기본 bsdtar를 영영 못 쓴다
        (이 개발 PC가 정확히 그 상태였다).
        """
        gnu_tar = tmp_path / "gnu" / "tar"
        bsd_tar = tmp_path / "win" / "tar.exe"
        for item in (gnu_tar, bsd_tar):
            item.parent.mkdir(parents=True, exist_ok=True)
            item.write_text("", encoding="utf-8")

        monkeypatch.setattr(libarchive_tool, "_candidates", lambda: [gnu_tar, bsd_tar])
        monkeypatch.setattr(
            libarchive_tool, "_looks_like_libarchive", lambda path: path == bsd_tar
        )

        assert libarchive_tool.find_tool() == bsd_tar

    def test_discovery_result_is_cached(self, monkeypatch, tmp_path: pathlib.Path):
        fake = tmp_path / "bsdtar"
        fake.write_text("", encoding="utf-8")
        lookups: list[int] = []

        def _candidates():
            lookups.append(1)
            return [fake]

        monkeypatch.setattr(libarchive_tool, "_candidates", _candidates)
        monkeypatch.setattr(libarchive_tool, "_looks_like_libarchive", lambda path: True)

        first = libarchive_tool.find_tool()
        second = libarchive_tool.find_tool()

        assert first == second == fake
        # 우클릭할 때마다 PATH를 훑고 --version을 실행하면 그 자체가 비용이다.
        assert len(lookups) == 1

    def test_windows_builtin_is_checked_first(self):
        """Windows 11 기본 tar.exe가 후보 맨 앞에 와야 한다(PATH 순서와 무관하게)."""
        candidates = libarchive_tool._candidates()
        if not candidates:
            pytest.skip("후보가 하나도 없는 환경")
        assert candidates[0].name.lower() == "tar.exe"
        assert "system32" in str(candidates[0]).lower()


class TestLegacyFilenames:
    """깨진 한글 파일명 복원과 위임이 충돌하지 않아야 한다."""

    def test_legacy_named_archive_is_not_delegated(self, tmp_path: pathlib.Path):
        """UTF-8 플래그 없는 cp949 이름이 섞이면 위임하지 않는다.

        우리는 cp437 왕복으로 원본 바이트를 되살려 복원하지만, libarchive는 시스템
        코드 페이지로 해석한다. 한국어 Windows에서는 우연히 같은 이름이 나오지만
        다른 로캘에서는 어긋나고, 그러면 staging에서 그 파일을 찾지 못해 조용히
        빠진다. 속도보다 파일명 복원이 우선이다.
        """
        _bsdtar_or_skip()
        archive = tmp_path / "legacy_name.zip"
        write_zipcrypto_archive(
            archive, [("한글문서.txt", "내용".encode("utf-8"))],
            password=b"pw", legacy_encoding="cp949",
        )

        reader = ZipArchiveReader(archive, password="pw")
        try:
            assert reader.list_entries()[0].name == "한글문서.txt"
            assert reader._should_delegate() is None, "레거시 이름은 위임하지 않는다"
            reader.extract_all(tmp_path / "out")
        finally:
            reader.close()

        assert (tmp_path / "out" / "한글문서.txt").read_bytes() == "내용".encode("utf-8")

    def test_utf8_named_archive_is_delegated(self, tmp_path: pathlib.Path):
        """반대로 UTF-8 플래그가 제대로 붙은 한글 이름은 위임해도 안전하다."""
        _bsdtar_or_skip()
        archive = tmp_path / "utf8_name.zip"
        write_zipcrypto_archive(
            archive, [("한글문서.txt", "내용".encode("utf-8"))], password=b"pw"
        )

        reader = ZipArchiveReader(archive, password="pw")
        try:
            assert reader._should_delegate() is not None
            reader.extract_all(tmp_path / "out")
        finally:
            reader.close()

        assert (tmp_path / "out" / "한글문서.txt").read_bytes() == "내용".encode("utf-8")


class TestMissingOutputIsLoud:
    def test_missing_staging_file_raises_instead_of_silently_skipping(
        self, tmp_path: pathlib.Path, monkeypatch
    ):
        """외부 도구가 파일을 안 내놓으면 조용히 넘어가지 않는다.

        조용히 건너뛰면 사용자는 다 풀린 줄 알고 넘어간다. 데이터가 없어진 것을
        모르는 쪽이 느린 쪽보다 훨씬 나쁘다.
        """
        from packnine.domain.exceptions import CorruptedArchiveError

        _bsdtar_or_skip()
        archive = tmp_path / "legacy.zip"
        write_zipcrypto_archive(archive, [("a.txt", b"hello")], password=b"pw")

        # 도구가 아무것도 쓰지 않은 상황을 흉내 낸다.
        monkeypatch.setattr(libarchive_tool, "extract_zip", lambda *a, **k: None)

        reader = ZipArchiveReader(archive, password="pw")
        try:
            with pytest.raises(CorruptedArchiveError, match="찾지 못했습니다"):
                reader.extract_all(tmp_path / "out")
        finally:
            reader.close()


class TestBatchedEntryExtraction:
    def test_extract_many_pulls_only_the_requested_entries(self, tmp_path: pathlib.Path):
        _bsdtar_or_skip()
        members = [
            ("문서/기획안.txt", b"plan"),
            ("문서/회의록.txt", b"minutes"),
            ("사진/현장.bin", os.urandom(512 * 1024)),
        ]
        archive = tmp_path / "legacy.zip"
        write_zipcrypto_archive(archive, members, password=b"pw")

        destination = tmp_path / "out"
        reader = ZipArchiveReader(archive, password="pw")
        try:
            reader.extract_many(["문서/회의록.txt", "사진/현장.bin"], destination)
        finally:
            reader.close()

        assert (destination / "문서" / "회의록.txt").read_bytes() == b"minutes"
        assert (destination / "사진" / "현장.bin").read_bytes() == members[2][1]
        # 요청하지 않은 것은 나오지 않는다.
        assert not (destination / "문서" / "기획안.txt").exists()

    def test_extract_many_matches_one_by_one_result(self, tmp_path: pathlib.Path, monkeypatch):
        _bsdtar_or_skip()
        members = [("a.txt", b"aaa"), ("b.txt", b"bbb")]
        archive = tmp_path / "legacy.zip"
        write_zipcrypto_archive(archive, members, password=b"pw")

        fast = tmp_path / "fast"
        reader = ZipArchiveReader(archive, password="pw")
        try:
            reader.extract_many(["a.txt", "b.txt"], fast)
        finally:
            reader.close()

        slow = tmp_path / "slow"
        monkeypatch.setattr(libarchive_tool, "find_tool", lambda: None)
        reader = ZipArchiveReader(archive, password="pw")
        try:
            reader.extract_many(["a.txt", "b.txt"], slow)
        finally:
            reader.close()

        for name, payload in members:
            assert (fast / name).read_bytes() == payload == (slow / name).read_bytes()

    def test_unknown_entry_still_raises_key_error(self, tmp_path: pathlib.Path):
        archive = tmp_path / "legacy.zip"
        write_zipcrypto_archive(archive, [("a.txt", b"hello")], password=b"pw")

        reader = ZipArchiveReader(archive, password="pw")
        try:
            with pytest.raises(KeyError):
                reader.extract_many(["없는파일.txt"], tmp_path / "out")
        finally:
            reader.close()
