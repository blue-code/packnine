[Document Path]
\conductor\tracks\track_20260909_split_archive\plan.md

---
트랙ID: track_20260909_split_archive
문서경로: \conductor\tracks\track_20260909_split_archive\plan.md
프로젝트명: PackNine
작업일시: 2026-09-09
작성자: Kent
문서유형: Plan
세션목적: 우클릭 "PackNine으로 압축하기..." 옵션 창에 분할 압축(볼륨)과 메일 첨부 용량 프리셋 추가
track_status: approved
parent_track: track_20260714_bandizip_parity
depends_on:
  - track_20260708_packnine_archiver
  - track_20260714_bandizip_parity
impact_matrix:
  track_20260708_packnine_archiver: Medium
  track_20260714_bandizip_parity: Medium
  track_20260721_macos_release: Low
---

## 1. 기획 배경

반디집 패리티 트랙(`track_20260714_bandizip_parity`)은 "분할 압축(볼륨) 생성/해제"를
zipfile 미지원을 이유로 후속 후보(Out)로 남겼다. v0.7.0에서 우클릭 "PackNine으로
압축하기..." 옵션 창이 생기면서 분할 크기를 입력받을 자연스러운 자리가 마련되었고,
사용자가 "메일 첨부 한도에 맞춰 나눠 보내는" 용도를 직접 요청했다.

사전 조사 결과 py7zr의 의존성으로 이미 설치되는 `multivolumefile` 0.2.3이 7z와 zip
양쪽의 볼륨 쓰기·읽기를 처리할 수 있어, 추가 의존성 없이 구현 가능함을 확인했다.

## 2. 문제 정의

- 옵션 창에 분할 크기를 지정할 수단이 없다. 큰 결과물을 메일로 보내려면 다른 도구가 필요하다.
- 메일 서비스마다 첨부 한도가 다르고 자주 바뀐다. 사용자가 숫자를 외워 입력해야 한다.
- 생성만 지원하면 PackNine이 만든 `.001` 파일을 PackNine 자신이 열지 못한다.
  CompressService가 압축 직후 결과를 다시 열어 목록을 만드는 구조라 생성 기능도 완결되지 않는다.

## 3. 목표

1. 옵션 창에서 분할 크기(MB)를 지정하면 `이름.7z.001`, `이름.7z.002` … 형태의 볼륨이 만들어진다.
2. 네이버·다음 메일의 일반첨부/대용량첨부, Gmail 첨부 한도를 프리셋으로 제공한다.
3. 첫 볼륨(`.001`)을 열기·해제·알아서 풀기·우클릭 메뉴에서 일반 아카이브처럼 다룰 수 있다.
4. CLI `compress`에도 동일 옵션을 제공해 스크립트에서 쓸 수 있게 한다.

## 4. 범위 (In / Out)

**In**
- 도메인: 볼륨 크기 값객체와 프리셋 목록
- 인프라: zip/7z writer 볼륨 쓰기, `.zip.001`/`.7z.001` reader, format_registry 확장자 해석
- 애플리케이션: CompressService `volume_size` 인자, 단일 볼륨 시 `.001` 미부착 규칙
- 표현: 옵션 창 분할 콤보 + MB 입력, CLI `--volume-size`, 우클릭 메뉴 `.001` 등록,
  GUI/드롭 아카이브 판별에 `.001` 포함
- 문서: README 기능 설명·CLI 예시 갱신

**Out (후속 후보)**
- WinZip 스팬 방식(`.z01`, `.z02`, `.zip`) 생성·해제. zip 헤더의 디스크 번호를 직접 써야 해서
  "자체 바이너리 파서 금지" 원칙(SECURITY.md)과 충돌한다.
- tar 계열 분할. 단일 스트림이라 기술적으로 가능하지만 수요가 없어 옵션을 비활성화한다.
- 볼륨 일부가 빠졌을 때의 상세 진단 메시지(어느 번호가 없는지). 이번에는 손상 오류로 통일한다.

## 5. 사용자 시나리오

- 200MB 폴더를 우클릭 → "PackNine으로 압축하기..." → 분할에서 "네이버 메일 일반첨부(10MB)"를
  고르고 확인 → `폴더.7z.001` … `폴더.7z.020`이 생긴다. 볼륨을 메일에 한 통씩 첨부해 보낸다.
- 받은 사람이 `.001`을 더블클릭하면 PackNine이 열리고 목록이 보인다. "알아서 풀기"로 원본이 복원된다.
- 5MB 파일에 10MB 분할을 지정하면 볼륨이 하나뿐이므로 `.001` 없이 `파일.7z`로 저장된다.
- `packnine compress big/ -o big.7z --volume-size 25` 로 스크립트에서 분할한다.

## 6. 성공 기준

- [x] zip/7z 분할 쓰기 → 읽기 → 원본과 동일(왕복) 테스트 통과
- [x] 결과가 볼륨 크기 이하일 때 `.001` 없이 단일 파일 생성
- [x] `.001` 첫 볼륨으로 list/extract/smart-extract/GUI 열기 동작 (빌드된 exe로 스모크 확인)
- [x] 옵션 창 프리셋 선택 시 MB 입력란이 채워지고 get_result에 바이트 값이 실림
- [x] tar 계열 포맷 선택 시 분할 옵션 비활성화
- [x] 전체 테스트 스위트 그린(325 passed), README 갱신, v0.8.0 릴리스 게시(Windows/macOS 3종 첨부)

## 7. 리스크 및 가정

- **가정**: 메일 한도는 2026-09 기준 조사값이다(네이버 일반 10MB/대용량 2GB, 다음 일반 25MB/
  대용량 4GB, Gmail 25MB). 프리셋은 MB 입력란을 채우는 단축키일 뿐이라 값이 바뀌어도 사용자가
  직접 수정할 수 있다.
- **리스크**: `.zip.001`은 Windows 탐색기 기본 압축 풀기로 열 수 없다. 반디집·7-Zip·알집은 연다.
  옵션 창의 안내 문구로 7z를 권장한다.
- **리스크**: 다음·Gmail 한도는 "합계" 기준이라 한 메일에 볼륨 여러 개를 붙이면 초과한다.
  프리셋 툴팁에 "볼륨 하나당 메일 한 통" 안내를 넣는다.
- **리스크**: 다음 대용량 4GB를 4096MB로 잡으면 FAT32 파일 한도를 1바이트 넘는다. 4095MB로 잡는다.
- **리스크**: 단일 볼륨 판정은 압축이 끝난 뒤에만 가능하다. close 시점에 볼륨 수를 보고
  이름을 확정하는 방식으로 처리한다.

## Approval Gate 체크리스트

```yaml
approval_checklist:
  - [x] plan.md 작성 완료
  - [x] analysis.md 작성 완료
  - [x] implementation.md 방향 확정
  - [x] 주요 리스크 문서화
  - [x] 상위 track 정합성 확인 (bandizip_parity가 Out으로 남긴 항목을 그대로 이어받음)
  - [x] 영향도 매트릭스 작성
```
