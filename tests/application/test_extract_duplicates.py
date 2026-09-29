"""해제 시 중복 파일 처리(덮어쓰기/건너뛰기/이름 바꾸기) 테스트.

반디집의 "같은 이름의 파일이 있을 때" 동작에 대응한다. 기본값은 기존 동작인
덮어쓰기라서, 정책을 주지 않은 호출은 지금까지와 똑같이 움직여야 한다(회귀 금지).
"""
from __future__ import annotations

import pathlib

from packnine.application.compress_service import CompressService
from packnine.application.extract_service import ExtractService
from packnine.application.inspect_service import InspectService
from packnine.domain.value_objects import DuplicatePolicy


def _make_archive(tmp_path: pathlib.Path) -> pathlib.Path:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("아카이브 내용 A", encoding="utf-8")
    (src / "b.txt").write_text("아카이브 내용 B", encoding="utf-8")
    archive = tmp_path / "out.zip"
    CompressService().compress([src / "a.txt", src / "b.txt"], archive)
    return archive


def test_default_policy_overwrites_like_before(tmp_path):
    archive = _make_archive(tmp_path)
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("기존 내용", encoding="utf-8")

    ExtractService().extract(archive, dest)

    assert (dest / "a.txt").read_text(encoding="utf-8") == "아카이브 내용 A"


def test_skip_policy_keeps_existing_file(tmp_path):
    archive = _make_archive(tmp_path)
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("기존 내용", encoding="utf-8")

    ExtractService().extract(archive, dest, duplicate_policy=DuplicatePolicy.SKIP)

    # 충돌한 a.txt는 그대로 두고, 충돌하지 않은 b.txt는 정상적으로 풀려야 한다.
    assert (dest / "a.txt").read_text(encoding="utf-8") == "기존 내용"
    assert (dest / "b.txt").read_text(encoding="utf-8") == "아카이브 내용 B"


def test_rename_policy_keeps_both(tmp_path):
    archive = _make_archive(tmp_path)
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("기존 내용", encoding="utf-8")

    ExtractService().extract(archive, dest, duplicate_policy=DuplicatePolicy.RENAME)

    assert (dest / "a.txt").read_text(encoding="utf-8") == "기존 내용"
    assert (dest / "a_2.txt").read_text(encoding="utf-8") == "아카이브 내용 A"
    assert (dest / "b.txt").read_text(encoding="utf-8") == "아카이브 내용 B"


def test_no_conflict_extracts_normally_under_every_policy(tmp_path):
    archive = _make_archive(tmp_path)

    for index, policy in enumerate(DuplicatePolicy):
        dest = tmp_path / f"dest{index}"
        manifest = ExtractService().extract(archive, dest, duplicate_policy=policy)

        assert (dest / "a.txt").read_text(encoding="utf-8") == "아카이브 내용 A"
        assert (dest / "b.txt").read_text(encoding="utf-8") == "아카이브 내용 B"
        assert len(manifest.entries) == 2


def test_find_conflicts_lists_existing_targets_only(tmp_path):
    archive = _make_archive(tmp_path)
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "a.txt").write_text("기존 내용", encoding="utf-8")

    service = ExtractService()
    manifest = InspectService().list_contents(archive)

    assert service.find_conflicts(manifest, dest) == ["a.txt"]
    assert service.find_conflicts(manifest, tmp_path / "없는폴더") == []


def test_skip_policy_does_not_touch_unrelated_existing_files(tmp_path):
    # 목적지에 원래 있던 무관한 파일은 어떤 정책에서도 건드리면 안 된다.
    archive = _make_archive(tmp_path)
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "무관한파일.txt").write_text("남아 있어야 한다", encoding="utf-8")

    ExtractService().extract(archive, dest, duplicate_policy=DuplicatePolicy.SKIP)

    assert (dest / "무관한파일.txt").read_text(encoding="utf-8") == "남아 있어야 한다"


def test_rename_policy_preserves_nested_structure(tmp_path):
    src = tmp_path / "src"
    (src / "sub").mkdir(parents=True)
    (src / "sub" / "deep.txt").write_text("깊은 내용", encoding="utf-8")
    archive = tmp_path / "nested.zip"
    CompressService().compress([src], archive)

    dest = tmp_path / "dest"
    (dest / "src" / "sub").mkdir(parents=True)
    (dest / "src" / "sub" / "deep.txt").write_text("기존 깊은 내용", encoding="utf-8")

    ExtractService().extract(archive, dest, duplicate_policy=DuplicatePolicy.RENAME)

    assert (dest / "src" / "sub" / "deep.txt").read_text(encoding="utf-8") == "기존 깊은 내용"
    assert (dest / "src" / "sub" / "deep_2.txt").read_text(encoding="utf-8") == "깊은 내용"
