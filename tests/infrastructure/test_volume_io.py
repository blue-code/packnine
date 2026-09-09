"""volume_io.py 테스트 - 볼륨 이름 규칙과 단일 볼륨 정리 규칙을 검증한다."""
from __future__ import annotations

import os
import pathlib

import pytest

from packnine.domain.value_objects import VolumeSize
from packnine.infrastructure import volume_io


def test_first_volume_detection_is_case_insensitive():
    assert volume_io.is_first_volume(pathlib.Path("a.7z.001"))
    assert volume_io.is_first_volume(pathlib.Path("A.ZIP.001"))
    assert not volume_io.is_first_volume(pathlib.Path("a.7z.002"))
    assert not volume_io.is_first_volume(pathlib.Path("a.7z"))


def test_strip_volume_suffix_only_removes_three_digit_suffix():
    assert volume_io.strip_volume_suffix(pathlib.Path("x/a.zip.001")) == pathlib.Path("x/a.zip")
    assert volume_io.strip_volume_suffix(pathlib.Path("a.zip")) == pathlib.Path("a.zip")
    # 버전 번호 같은 4자리는 볼륨 접미사가 아니다.
    assert volume_io.strip_volume_suffix(pathlib.Path("a.zip.0001")) == pathlib.Path("a.zip.0001")


def test_write_produces_three_digit_volumes_and_reads_back(tmp_path: pathlib.Path):
    base = tmp_path / "out.bin"
    payload = os.urandom(250_000)

    with volume_io.open_volume_target(base, VolumeSize(bytes=100_000)) as target:
        target.write(payload)

    volumes = volume_io.list_volumes(base)
    assert [v.name for v in volumes] == ["out.bin.001", "out.bin.002", "out.bin.003"]
    assert not base.exists()

    with volume_io.open_volume_source(volumes[0]) as source:
        assert source.read() == payload


def test_finalize_renames_single_volume_to_plain_archive(tmp_path: pathlib.Path):
    base = tmp_path / "small.bin"
    with volume_io.open_volume_target(base, VolumeSize.from_megabytes(1)) as target:
        target.write(b"tiny")

    output_path, count = volume_io.finalize_volumes(base)

    assert count == 1
    assert output_path == base
    assert base.read_bytes() == b"tiny"
    assert volume_io.list_volumes(base) == []


def test_finalize_keeps_multiple_volumes_and_returns_first(tmp_path: pathlib.Path):
    base = tmp_path / "big.bin"
    with volume_io.open_volume_target(base, VolumeSize(bytes=10)) as target:
        target.write(b"0123456789abcdef")

    output_path, count = volume_io.finalize_volumes(base)

    assert count == 2
    assert output_path == base.with_name("big.bin.001")


def test_open_target_removes_stale_volumes_from_previous_run(tmp_path: pathlib.Path):
    base = tmp_path / "out.bin"
    stale = base.with_name("out.bin.007")
    stale.write_bytes(b"old")

    with volume_io.open_volume_target(base, VolumeSize.from_megabytes(1)) as target:
        target.write(b"new")

    assert not stale.exists()


def test_finalize_without_volumes_raises(tmp_path: pathlib.Path):
    with pytest.raises(FileNotFoundError):
        volume_io.finalize_volumes(tmp_path / "nothing.bin")
