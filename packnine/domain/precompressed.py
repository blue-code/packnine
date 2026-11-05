"""이미 압축된 파일 형식 판별.

왜 필요한가: x265 동영상 같은 파일은 deflate를 돌려도 줄지 않는다. 실측으로
419MB 영상에 deflate를 돌리면 29.2MB/s로 3분 30초(6GB 기준)를 써서 1.6%를 아낀다.
같은 파일을 그냥 저장하면 디스크 속도(546MB/s)로 12초에 끝나고 크기는 1.6% 커질
뿐이다. 17배를 버리고 1.6%를 얻는 거래라 할 이유가 없다.

반디집과 7-Zip도 같은 판단을 한다(반디집은 "이미 압축된 파일은 압축하지 않음"이
기본값이다). 결과물은 어느 쪽이든 똑같이 호환되는 일반 zip이다.

목록 기준: 포맷 자체가 엔트로피 부호화를 포함해 deflate가 손댈 여지가 없는 것만
넣는다. 애매한 것은 넣지 않는다.
- WAV와 BMP는 비압축이라 잘 줄어든다 → 제외
- PDF는 내부 스트림 압축 여부가 제각각이라 10~20% 줄기도 한다 → 제외
- ISO는 담긴 내용에 따라 다르다 → 제외
- EXE는 보통 잘 줄어든다 → 제외
"""
from __future__ import annotations

import pathlib

# 소문자 확장자(점 포함). 추가할 때는 "deflate가 정말 할 일이 없는가"를 기준으로 본다.
_PRECOMPRESSED_EXTENSIONS: frozenset[str] = frozenset(
    {
        # 동영상
        ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v",
        ".mpg", ".mpeg", ".ts", ".m2ts", ".mts", ".rmvb", ".3gp", ".divx",
        # 음악
        ".mp3", ".aac", ".m4a", ".ogg", ".opus", ".flac", ".wma", ".ape", ".alac",
        # 이미지
        ".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".heif", ".avif", ".jxl",
        # 압축 파일(이중 압축은 의미가 없다)
        ".zip", ".7z", ".rar", ".gz", ".bz2", ".xz", ".zst", ".lz4", ".lzma",
        ".cab", ".alz", ".egg", ".tgz", ".tbz2", ".txz", ".arj", ".lzh",
        # 내부가 zip인 컨테이너
        ".jar", ".war", ".apk", ".ipa", ".whl", ".epub", ".crx",
        ".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp",
    }
)


def is_precompressed(name: str | pathlib.PurePath) -> bool:
    """이름의 확장자가 "이미 압축된 형식"이면 True.

    아카이브 안에 들어갈 이름을 그대로 넘겨도 된다(경로 구분자가 섞여 있어도 된다).
    """
    suffix = pathlib.PurePosixPath(str(name).replace("\\", "/")).suffix
    return suffix.lower() in _PRECOMPRESSED_EXTENSIONS
