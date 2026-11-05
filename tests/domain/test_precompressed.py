"""이미 압축된 형식 판별 테스트.

이 판단이 틀리면 둘 중 하나가 된다. 압축되는 파일을 저장으로 넘겨 크기를 손해보거나,
안 줄어드는 파일에 deflate를 돌려 시간을 버린다. 경계가 되는 형식들을 못 박아 둔다.
"""
from __future__ import annotations

import pytest

from packnine.domain.precompressed import is_precompressed


@pytest.mark.parametrize(
    "name",
    [
        "영화.mkv",
        "clip.MP4",
        "노래.flac",
        "사진.JPG",
        "그림.png",
        "묶음.zip",
        "묶음.7z",
        "문서.docx",
        "앱.apk",
        "폴더/안쪽/영상.webm",
        r"윈도우\경로\영상.avi",
    ],
)
def test_already_compressed_formats(name: str) -> None:
    assert is_precompressed(name) is True


@pytest.mark.parametrize(
    "name",
    [
        "메모.txt",
        "데이터.csv",
        "코드.py",
        "로그.log",
        # 비압축이라 잘 줄어든다. 저장으로 넘기면 손해다.
        "소리.wav",
        "그림.bmp",
        # 내부 스트림 압축 여부가 제각각이라 10~20% 줄기도 한다.
        "문서.pdf",
        # 담긴 내용에 따라 다르다.
        "디스크.iso",
        # 보통 잘 줄어든다.
        "프로그램.exe",
        "확장자없음",
    ],
)
def test_formats_that_still_benefit_from_compression(name: str) -> None:
    assert is_precompressed(name) is False
