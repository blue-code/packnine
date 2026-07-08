"""tests/infrastructure 공통 픽스처 및 헬퍼.

각 포맷 어댑터 테스트가 동일한 방식으로 샘플 파일 트리를 만들고
round-trip 결과(압축 -> 해제 -> 원본과 동일한지)를 검증할 수 있도록
공통 유틸리티를 제공한다.
"""
from __future__ import annotations

import pathlib


def make_sample_source_tree(tmp_path: pathlib.Path, name: str = "source") -> pathlib.Path:
    """하위 폴더를 포함한 샘플 파일 트리를 생성하고 루트 디렉터리를 반환한다."""
    src_dir = tmp_path / name
    src_dir.mkdir()
    (src_dir / "a.txt").write_text("hello a", encoding="utf-8")
    # 압축률 검사(압축폭탄 방어)에 걸리지 않도록 적당히 반복되는 텍스트를 사용한다.
    (src_dir / "b.txt").write_text("hello b " * 50, encoding="utf-8")
    sub_dir = src_dir / "sub"
    sub_dir.mkdir()
    (sub_dir / "c.txt").write_text("hello c in sub directory", encoding="utf-8")
    return src_dir


def assert_tree_equal(original_root: pathlib.Path, extracted_root: pathlib.Path) -> None:
    """extracted_root 하위 구조/내용이 original_root와 동일한지 검증한다."""
    original_files = sorted(
        p.relative_to(original_root) for p in original_root.rglob("*") if p.is_file()
    )
    extracted_files = sorted(
        p.relative_to(extracted_root) for p in extracted_root.rglob("*") if p.is_file()
    )
    assert original_files == extracted_files, (original_files, extracted_files)
    for rel in original_files:
        assert (original_root / rel).read_bytes() == (extracted_root / rel).read_bytes()
