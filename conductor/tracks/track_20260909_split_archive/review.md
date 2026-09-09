[Document Path]
\conductor\tracks\track_20260909_split_archive\review.md

---
트랙ID: track_20260909_split_archive
문서경로: \conductor\tracks\track_20260909_split_archive\review.md
프로젝트명: PackNine
작업일시: 2026-09-09
작성자: Kent
문서유형: Review
세션목적: 분할 압축 구현 결과 정리
track_status: draft
parent_track: track_20260714_bandizip_parity
depends_on:
  - track_20260909_split_archive (implementation.md)
impact_matrix:
  track_20260708_packnine_archiver: Medium
  track_20260714_bandizip_parity: Medium
---

## 1. 구현 결과 요약

| 계층 | 변경 | 테스트 |
|---|---|---|
| domain | `VolumeSize`, `SplitPreset`, `SPLIT_PRESETS`(네이버 일반/대용량, 다음 일반/대용량, Gmail). `ArchiveManifest`에 `archive_path`/`volume_count` 메타 | `test_value_objects.py` 12개 |
| infrastructure | 신규 `volume_io.py`(multivolumefile 래핑, 3자리 볼륨, 단일 볼륨 rename). zip/7z writer `volume_size`, reader `.001` 자동 감지. `format_registry` `.zip.001`/`.7z.001` 해석, tar 분할 거부, `.001` 출력 경로 거부 | `test_volume_io.py` 7개, 어댑터 왕복 7개, 레지스트리 8개 |
| application | `CompressService.compress(volume_size=)`, 실제 첫 볼륨 경로로 manifest 생성. `smart_naming` 분할 파일 폴더명에서 볼륨 번호 제거 | 서비스 6개, 네이밍 1개 |
| presentation | 옵션 창 "분할 압축" 콤보 + MB 스핀박스 + 안내 라벨, `get_result` 5-튜플. CLI `compress --volume-size`, `UnsupportedFormatError` 안내. 메인 창 완료 메시지에 볼륨 수 표시, `.001` 아카이브 판별. 우클릭 메뉴 `.001` 등록 | 다이얼로그 5개, CLI 5개, 메인 창 1개 |

전체 스위트 325 passed, 1 skipped (변경 전 270 passed).

## 2. 설계 대비 차이

- implementation.md는 reader에 `is_volume` 인자를 명시하기로 했으나, 어댑터가 경로 이름(`.001`)을
  보고 스스로 판단하도록 바꿨다. `get_reader` 시그니처가 그대로라 ExtractService/InspectService/
  GUI 열기 경로를 하나도 고치지 않아도 됐다.
- CLI 볼륨 크기 검증 실패를 처음엔 `SystemExit`로 처리했다가 종료 코드 1 + stderr로 바꿨다.
  `main()`이 콘솔 없는 실행에서 `SystemExit`를 모달 메시지 박스로 바꾸기 때문에 테스트가
  멈췄고, 실제 우클릭 실행에서도 같은 일이 벌어질 수 있었다.

## 3. 잘된 점

- 추가 의존성 없이 구현됐다. `multivolumefile`은 py7zr이 이미 끌고 온다.
- zip/7z 어댑터가 `volume_io` 한 곳을 공유해 이름 규칙이 어긋날 여지가 없다.
- 단일 볼륨이면 `.001`을 떼는 규칙 덕에 "분할 켜 놓고 작은 파일 압축"이 무해하다.

## 4. 아쉬운 점

- zip 분할이 WinZip 스팬(`.z01`)이 아니라 사용자가 반디집 결과와 다르다고 느낄 수 있다.
  옵션 창 안내와 README로 알렸다.
- 이 PC에 7-Zip/반디집이 없어 외부 도구와의 실호환은 자동 테스트로 검증하지 못했다.
  `.7z.001`은 7z 표준 볼륨 형식 그대로이고 `.zip.001`은 7-Zip이 만드는 것과 같은 단순 바이트
  분할이라 형식상 문제는 없지만, 실제 열기 확인은 사용자 환경에서 필요하다.

## 5. 기술 부채 후보

- `main_window._ARCHIVE_EXTENSIONS`, `context_menu._ARCHIVE_EXTENSIONS`, `format_registry`
  세 곳의 확장자 목록이 따로 관리된다. 이번에 `.001`을 세 곳에 넣었다. 한 곳으로 모으는 리팩터링 후보.
- `smart_naming._archive_base_name`과 `volume_io.strip_volume_suffix`가 같은 정규식을 각자 가진다
  (계층 경계 때문). 도메인에 순수 헬퍼를 두면 합칠 수 있다.

## 6. 후속 작업

- 볼륨 누락 시 "몇 번 볼륨이 없습니다" 진단 메시지.
- 메일 한도 프리셋 값 정기 점검(조사 기준 2026-09).
