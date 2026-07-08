"""image_viewer.is_image_name 단위 테스트."""
from __future__ import annotations

import pytest

from packnine.presentation.gui.image_viewer import is_image_name


@pytest.mark.parametrize(
    "name,expected",
    [
        ("photo.png", True),
        ("photo.PNG", True),
        ("sub/dir/photo.jpg", True),
        ("photo.jpeg", True),
        ("photo.bmp", True),
        ("photo.gif", True),
        ("notes.txt", False),
        ("archive.zip", False),
        ("photo.webp", False),  # Qt 빌드에 따라 지원 여부가 갈려 대상에서 제외
        ("no_extension", False),
    ],
)
def test_is_image_name(name: str, expected: bool) -> None:
    assert is_image_name(name) is expected
