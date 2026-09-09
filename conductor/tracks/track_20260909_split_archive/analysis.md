[Document Path]
\conductor\tracks\track_20260909_split_archive\analysis.md

---
트랙ID: track_20260909_split_archive
문서경로: \conductor\tracks\track_20260909_split_archive\analysis.md
프로젝트명: PackNine
작업일시: 2026-09-09
작성자: Kent
문서유형: Analysis
세션목적: 분할 압축 구현 방식 비교와 선택
track_status: draft
parent_track: track_20260714_bandizip_parity
depends_on:
  - track_20260909_split_archive (plan.md)
impact_matrix:
  track_20260708_packnine_archiver: Medium
  track_20260714_bandizip_parity: Medium
---

## 1. 요구사항

- 옵션 창에서 MB 단위 분할 크기와 메일 프리셋(네이버/다음 일반·대용량, Gmail)을 고른다.
- 생성된 분할 파일을 PackNine에서 열고 풀 수 있다.
- 추가 런타임 의존성을 만들지 않는다.

## 2. 제약 사항

- SECURITY.md 6항: 자체 바이너리 파서를 구현하지 않는다(`tests/test_architecture_constraints.py`가 강제).
- RAR 쓰기 미지원 정책은 그대로 유지한다.
- 도메인 계층은 외부 라이브러리를 import하지 않는다.

## 3. 기존 구조 분석

| 지점 | 현재 | 분할에 필요한 변경 |
|---|---|---|
| `CompressDialog.get_result` | 4-튜플 반환, 소비 지점 3곳(cli, main_window 2곳) | 5번째 값 추가. 세 곳 동시 수정 |
| `CompressService.compress` | writer로 쓰고 reader로 다시 열어 manifest 생성 | `volume_size` 전달, 실제 생성 경로로 reader 열기 |
| `format_registry._resolve_extension` | 접미사 일치로 포맷 판정 | `.zip.001`/`.7z.001`을 zip/7z로 해석, 볼륨 여부를 어댑터에 전달 |
| `ZipArchiveWriter` | 경로를 `zipfile.ZipFile`에 직접 전달 | 파일 객체(multivolume)를 전달, close 후 이름 확정 |
| `SevenZipArchiveWriter` | 경로를 `py7zr.SevenZipFile`에 직접 전달 | 동일 |
| `context_menu._ARCHIVE_EXTENSIONS` | `.zip` 등 8종 | `.001` 추가 |
| `main_window._ARCHIVE_EXTENSIONS` | 레지스트리와 별도 정의 | `.001` 추가 |

## 4. 대안 비교

| 대안 | 장점 | 단점 |
|---|---|---|
| A. multivolumefile로 바이트 분할(`.001`) | 추가 의존성 없음, 7z 표준 방식과 동일, zip/7z 코드 경로 통일 | zip은 WinZip 스팬(`.z01`)과 다른 방식. 탐색기 기본 풀기 불가 |
| B. zip 스팬(`.z01`) 직접 구현 | 반디집 zip 분할과 동일 | 중앙 디렉터리 디스크 번호를 직접 써야 함. 바이너리 파서 금지 원칙 위반 |
| C. 7z만 분할 지원 | 구현 최소 | zip 사용자에게 선택지 없음 |
| D. 외부 7z.exe 호출 | 완전 호환 | 바이너리 동봉 필요, 라이선스·배포 부담 |

## 5. 선택 이유

**A를 선택한다.** 실험으로 zip·7z 모두 쓰기와 읽기 복원을 확인했고 의존성이 늘지 않는다.
zip 분할의 호환 한계는 옵션 창 안내 문구와 README로 알린다. 확장자 자릿수는 `ext_digits=3`으로
맞춰 7-Zip·반디집이 만든 파일과 같은 이름 규칙을 따른다.

단일 볼륨 처리: multivolumefile은 결과가 작아도 `.001`을 붙인다. 메일 첨부 용도에서는 받는 쪽이
`.7z.001` 하나만 받으면 열지 못하는 최악의 경험이 되므로, close 시점에 볼륨이 하나면 `.001`을
떼어 단일 아카이브로 이름을 바꾼다.

## 6. 기술적 리스크

- multivolumefile은 볼륨 경계에서 seek/tell을 자체 관리한다. zipfile은 중앙 디렉터리를 쓰기 위해
  tell을 자주 호출하는데 실험에서 정상 동작했다. 회귀 방지를 위해 왕복 테스트를 둔다.
- py7zr reader에 파일 객체를 넘기면 `close()`가 그 객체를 닫지 않으므로 어댑터가 직접 닫아야 한다.
- 볼륨 크기 하한: 너무 작은 값(수 KB)이면 볼륨 수가 폭증한다. UI 최소값을 1MB로 둔다.
