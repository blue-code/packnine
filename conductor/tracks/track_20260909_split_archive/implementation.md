[Document Path]
\conductor\tracks\track_20260909_split_archive\implementation.md

---
트랙ID: track_20260909_split_archive
문서경로: \conductor\tracks\track_20260909_split_archive\implementation.md
프로젝트명: PackNine
작업일시: 2026-09-09
작성자: Kent
문서유형: Implementation
세션목적: 분할 압축 구현 설계
track_status: draft
parent_track: track_20260714_bandizip_parity
depends_on:
  - track_20260909_split_archive (analysis.md)
impact_matrix:
  track_20260708_packnine_archiver: Medium
  track_20260714_bandizip_parity: Medium
---

## 1. 구현 전략

계층 순서대로 TDD로 진행한다. 도메인 값객체 → 어댑터 왕복 → 레지스트리 확장자 해석 →
서비스 → 다이얼로그/CLI → 우클릭 메뉴 순이며, 각 단계에서 실패하는 테스트를 먼저 둔다.

## 2. 아키텍처

```
CompressDialog ──get_result()──▶ (sources, dest, password, level, volume_size)
      │                                          │
      ▼                                          ▼
cli._cmd_compress_dialog / MainWindow ──▶ CompressService.compress(volume_size=)
                                                 │
                                                 ▼
                        format_registry.get_writer(path, volume_size=)
                                                 │
                     ┌───────────────────────────┴───────────────────────────┐
                     ▼                                                       ▼
        ZipArchiveWriter(volume_size)                        SevenZipArchiveWriter(volume_size)
        volume_io.open_volume_target(path, size)             (동일)
        close(): 볼륨 1개면 ".001" 제거
```

읽기: `format_registry._resolve_extension`이 `.zip.001`/`.7z.001`을 인식하고 reader에
`is_volume=True`를 넘긴다. reader는 volume_io로 볼륨 묶음을 하나의 파일 객체처럼 연다.

## 3. 컴포넌트 설계

- `domain/value_objects.py`
  - `VolumeSize(bytes)` frozen dataclass. `from_megabytes()` 팩터리, 1MB 미만 거부.
  - `SPLIT_PRESETS`: `SplitPreset(label, megabytes, note)` 목록. 메일 한도는 도메인 지식이므로 여기 둔다.
- `infrastructure/volume_io.py`
  - `open_volume_target(path, volume_size)` / `open_volume_source(path)` / `finalize_volumes(path)`.
    multivolumefile 호출을 한 곳에 모아 zip/7z 어댑터가 같은 규칙을 쓴다.
- `infrastructure/zip_adapter.py`, `sevenzip_adapter.py`
  - writer: `volume_size` 인자. 있으면 volume_io로 연 파일 객체를 라이브러리에 넘긴다.
    close 후 `output_path`에 실제 첫 파일 경로를 기록한다.
  - reader: `is_volume` 인자. 있으면 volume_io로 연 파일 객체를 넘기고 close 시 함께 닫는다.
- `infrastructure/format_registry.py`
  - `.zip.001`/`.7z.001`을 각각 zip/7z로 해석.
  - `get_writer(..., volume_size=None)`: zip/7z 외 포맷에 volume_size가 오면 `UnsupportedFormatError`.
- `application/compress_service.py`
  - `compress(..., volume_size=None)`. writer.close() 뒤 `writer.output_path`로 reader를 연다.
  - `ArchiveManifest`에 `archive_path`, `volume_count` 메타를 채운다.
- `presentation/gui/compress_dialog.py`
  - "분할" 콤보(분할 안 함 + 프리셋 + 사용자 지정) + MB `QSpinBox`. 프리셋 선택 시 스핀박스 채움.
  - tar 계열 포맷이면 두 위젯 비활성화. zip 선택 + 분할이면 안내 라벨 표시.
  - `get_result()` 5-튜플.
- `presentation/cli.py`
  - `compress --volume-size <MB>`. compress-dialog는 5-튜플 소비.
- `infrastructure/context_menu.py`, `presentation/gui/main_window.py`
  - `_ARCHIVE_EXTENSIONS`에 `.001` 추가.

## 4. 데이터 흐름

1. 사용자가 프리셋 "네이버 메일 일반첨부(10MB)" 선택 → 스핀박스 10.
2. get_result가 `VolumeSize.from_megabytes(10)` → bytes 10,485,760.
3. CompressService → get_writer(dest, volume_size) → writer가 `dest.001`, `dest.002` … 작성.
4. close 시 볼륨 1개면 `dest.001` → `dest`로 rename. `output_path`에 최종 첫 파일 경로 기록.
5. reader가 output_path를 열어 manifest 생성. archive_path/volume_count 채움.

## 5. 예외 처리

- tar 계열 + volume_size → `UnsupportedFormatError` (다이얼로그에서는 애초에 선택 불가).
- 1MB 미만 → `ValueError` (스핀박스 최소값이 1이라 GUI에서는 불가, CLI에서만 가능).
- `.002`가 없는 상태에서 `.001`을 열면 multivolumefile이 EOF를 내고 zipfile/py7zr이 손상 예외를
  던진다. 기존 `CorruptedArchiveError` 매핑을 그대로 탄다.

## 6. 테스트 전략

- `tests/domain/test_value_objects.py`: VolumeSize 변환·하한, 프리셋 값.
- `tests/infrastructure/test_zip_adapter.py`, `test_sevenzip_adapter.py`: 분할 왕복, 단일 볼륨 rename.
- `tests/infrastructure/test_format_registry.py`: `.001` 해석, tar+분할 거부.
- `tests/application/test_compress_service.py`: volume_size 전달, manifest 메타.
- `tests/presentation/test_compress_dialog.py`: 프리셋→스핀박스, tar 비활성화, get_result.
- `tests/presentation/test_cli.py`: `--volume-size`, compress-dialog 5-튜플.
- `tests/infrastructure/test_context_menu.py`: 가짜 확장자 기반이라 변경 없음(목록 상수만 확인).

## 7. 개선 포인트

- zip 스팬(`.z01`) 지원은 외부 도구 위임 방식이 정해지면 별도 트랙으로.
- 볼륨 누락 진단(몇 번이 없는지) 메시지.
