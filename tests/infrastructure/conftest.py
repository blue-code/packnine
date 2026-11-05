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


# ----------------------------------------------------------------------
# ZipCrypto(구형 PKWARE 암호) 아카이브 생성
#
# 표준 zipfile은 ZipCrypto를 "읽기"만 하고 쓰지 못하며, pyzipper는 AES만 쓴다.
# 그래서 위임 경로를 테스트하려면 픽스처를 직접 만들 수밖에 없다.
# struct를 쓰는 것은 테스트 전용이라 괜찮다 - 아키텍처 제약(수동 바이너리 파싱 금지)은
# packnine/ 아래 제품 코드에만 적용된다.
# ----------------------------------------------------------------------
import binascii
import os
import struct
import zlib


def _crc_table() -> list[int]:
    table = []
    for index in range(256):
        value = index
        for _ in range(8):
            value = (value >> 1) ^ (0xEDB88320 if value & 1 else 0)
        table.append(value)
    return table


_CRC_TABLE = _crc_table()


class _ZipCryptoEncrypter:
    """PKWARE 구형 암호. 바이트마다 평문으로 키를 갱신하는 자기동기 스트림 암호다."""

    def __init__(self, password: bytes) -> None:
        self._key0, self._key1, self._key2 = 305419896, 591751049, 878082192
        for byte in password:
            self._update(byte)

    def _update(self, char: int) -> None:
        self._key0 = (self._key0 >> 8) ^ _CRC_TABLE[(self._key0 ^ char) & 0xFF]
        self._key1 = (self._key1 + (self._key0 & 0xFF)) & 0xFFFFFFFF
        self._key1 = (self._key1 * 134775813 + 1) & 0xFFFFFFFF
        self._key2 = (self._key2 >> 8) ^ _CRC_TABLE[(self._key2 ^ (self._key1 >> 24)) & 0xFF]

    def _keystream_byte(self) -> int:
        temp = self._key2 | 2
        return ((temp * (temp ^ 1)) >> 8) & 0xFF

    def encrypt(self, data: bytes) -> bytes:
        out = bytearray()
        for plain in data:
            out.append(plain ^ self._keystream_byte())
            self._update(plain)
        return bytes(out)


def write_zipcrypto_archive(
    path: pathlib.Path,
    members: list[tuple[str, bytes]],
    password: bytes,
) -> pathlib.Path:
    """ZipCrypto로 암호화된 zip을 만든다(테스트 픽스처 전용)."""
    _ENCRYPTED_AND_UTF8 = 0x1 | 0x800
    central: list[tuple[bytes, int, int, int, int]] = []
    with path.open("wb") as out:
        for name, data in members:
            offset = out.tell()
            crc = binascii.crc32(data) & 0xFFFFFFFF
            compressor = zlib.compressobj(6, zlib.DEFLATED, -15)
            body = compressor.compress(data) + compressor.flush()
            # 12바이트 암호 헤더의 마지막 바이트는 CRC 최상위 바이트여야 한다.
            header = bytes(bytearray(os.urandom(11)) + bytes([(crc >> 24) & 0xFF]))
            blob = _ZipCryptoEncrypter(password).encrypt(header + body)

            raw_name = name.encode("utf-8")
            out.write(
                struct.pack(
                    "<IHHHHHIIIHH", 0x04034B50, 20, _ENCRYPTED_AND_UTF8, 8,
                    0, 0, crc, len(blob), len(data), len(raw_name), 0,
                )
            )
            out.write(raw_name)
            out.write(blob)
            central.append((raw_name, crc, len(blob), len(data), offset))

        directory_start = out.tell()
        for raw_name, crc, compressed, size, offset in central:
            out.write(
                struct.pack(
                    "<IHHHHHHIIIHHHHHII", 0x02014B50, 20, 20, _ENCRYPTED_AND_UTF8, 8,
                    0, 0, crc, compressed, size, len(raw_name), 0, 0, 0, 0, 0, offset,
                )
            )
            out.write(raw_name)
        directory_size = out.tell() - directory_start
        out.write(
            struct.pack(
                "<IHHHHIIH", 0x06054B50, 0, 0, len(central), len(central),
                directory_size, directory_start, 0,
            )
        )
    return path
