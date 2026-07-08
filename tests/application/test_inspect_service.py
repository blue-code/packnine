"""InspectService 테스트."""
from __future__ import annotations

import pathlib

from packnine.application.compress_service import CompressService
from packnine.application.inspect_service import InspectService
from packnine.domain.entities import ArchiveManifest
from tests.infrastructure.conftest import make_sample_source_tree


def test_list_contents_returns_expected_entries_without_writing_to_disk(
    tmp_path: pathlib.Path,
) -> None:
    src_dir = make_sample_source_tree(tmp_path)
    archive_path = tmp_path / "out.zip"
    compress_manifest = CompressService().compress([src_dir], archive_path)

    # archive_path 외의 tmp_path 내용물이 호출 전후로 변하지 않는지 비교하기 위한 스냅샷.
    before = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))

    manifest = InspectService().list_contents(archive_path)

    after = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*"))

    assert isinstance(manifest, ArchiveManifest)
    assert before == after
    assert {e.name for e in manifest.entries} == {e.name for e in compress_manifest.entries}
