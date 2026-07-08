"""motw.py 테스트 - Zone.Identifier(MoTW) 전파.

NTFS 전용 기능이므로 Windows가 아니면 대부분 스킵한다(Windows CI 매트릭스에서 검증됨).
"""
from __future__ import annotations

import pathlib
import sys

import pytest

from packnine.infrastructure import motw

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="Zone.Identifier ADS는 Windows/NTFS 전용 기능입니다"
)


@pytest.fixture
def downloaded_archive(tmp_path: pathlib.Path) -> pathlib.Path:
    """웹에서 받은 것처럼 Zone.Identifier ADS가 붙은 더미 아카이브 파일을 만든다."""
    archive = tmp_path / "downloaded.zip"
    archive.write_bytes(b"dummy archive bytes")
    zone_data = b"[ZoneTransfer]\r\nZoneId=3\r\n"
    with open(f"{archive}:Zone.Identifier", "wb") as f:
        f.write(zone_data)
    return archive


def test_read_zone_identifier_returns_none_when_not_downloaded(tmp_path: pathlib.Path):
    plain_archive = tmp_path / "local_only.zip"
    plain_archive.write_bytes(b"dummy")
    assert motw.read_zone_identifier(plain_archive) is None


def test_read_zone_identifier_returns_content_when_present(downloaded_archive: pathlib.Path):
    content = motw.read_zone_identifier(downloaded_archive)
    assert content is not None
    assert b"ZoneId=3" in content


def test_propagate_copies_zone_identifier_to_every_extracted_file(
    downloaded_archive: pathlib.Path, tmp_path: pathlib.Path
):
    extracted_root = tmp_path / "extracted"
    (extracted_root / "sub").mkdir(parents=True)
    (extracted_root / "a.txt").write_bytes(b"a")
    (extracted_root / "sub" / "b.exe").write_bytes(b"b")

    motw.propagate_zone_identifier(downloaded_archive, extracted_root)

    for extracted_file in (extracted_root / "a.txt", extracted_root / "sub" / "b.exe"):
        with open(f"{extracted_file}:Zone.Identifier", "rb") as f:
            assert b"ZoneId=3" in f.read()


def test_propagate_does_nothing_when_source_has_no_zone_identifier(tmp_path: pathlib.Path):
    plain_archive = tmp_path / "local_only.zip"
    plain_archive.write_bytes(b"dummy")
    extracted_root = tmp_path / "extracted2"
    extracted_root.mkdir()
    target = extracted_root / "a.txt"
    target.write_bytes(b"a")

    motw.propagate_zone_identifier(plain_archive, extracted_root)

    # 원본에 Zone.Identifier가 없었으므로 전파할 것도 없어 조용히 아무 일도 일어나지 않는다.
    with pytest.raises(OSError):
        open(f"{target}:Zone.Identifier", "rb")
