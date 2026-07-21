[Document Path]
\conductor\tracks\track_20260721_macos_release\analysis.md

---
트랙ID: track_20260721_macos_release
문서경로: \conductor\tracks\track_20260721_macos_release\analysis.md
프로젝트명: PackNine
작업일시: 2026-07-21
작성자: Kent
문서유형: Analysis
세션목적: macOS 코어 릴리스 실현 방안 분석 (빌드 도구·배포 형태·기존 구조 영향도)
track_status: draft
parent_track: track_20260708_packnine_archiver
depends_on:
  - track_20260721_macos_release (plan.md)
impact_matrix:
  track_20260708_packnine_archiver: High
  track_20260714_bandizip_parity: Medium
---

## 1. 요구사항

plan.md 목표를 구현 관점으로 재정리한다.

1. macOS(Apple Silicon, `arm64`) 대상 PyInstaller `.app` 빌드 스펙 신규 작성
2. GitHub Actions `ci.yml`에 `macos-latest` 매트릭스 추가, pytest 그린 확인
3. RAR 해제 의존성(`unrar`/`bsdtar`)의 macOS 설치 경로(Homebrew) 문서화
4. `.app`을 GitHub Release에 배포 가능한 형태(zip)로 산출
5. Gatekeeper 미서명 경고 등 macOS 고유 리스크를 README/문서에 명시

## 2. 제약 사항

- **크로스 컴파일 불가**: PyInstaller는 빌드를 실행 중인 OS용 바이너리만 만든다. Windows
  머신에서 macOS `.app`을 만들 수 없으므로, 실제 빌드는 macOS 머신(로컬 Mac) 또는 GitHub
  Actions `macos-latest` 호스티드 러너에서 수행해야 한다.
- **아키텍처**: GitHub Actions `macos-latest`는 Apple Silicon(`arm64`) 전용이다. Intel
  Mac(`x86_64`) 대응은 `macos-13` 등 별도 매트릭스가 필요하며, 이번 트랙은 plan.md 범위대로
  `arm64`만 다룬다.
- **코드 서명/공증(Notarization) 비용**: 정식 서명에는 Apple Developer Program(유료 연간
  구독)이 필요하다 → 이번 트랙 Out of Scope, Gatekeeper 경고는 안내 문구로 우선 대응한다.
- **RAR 바이너리 재배포 금지**: Windows와 동일하게 `unrar`/`bsdtar`를 앱에 동봉하지 않고
  사용자가 시스템에 별도 설치(Homebrew)하도록 위임하는 기존 정책을 유지한다.
- **`winreg` 기반 모듈의 예외 발생**: `infrastructure/context_menu.py`의 `register()`/
  `unregister()`는 `_require_windows()`에서 `sys.platform != "win32"`일 때 `RuntimeError`를
  던진다(코드 42-44행 근처, `import winreg` 지연 임포트 방식과 쌍을 이루는 가드).

## 3. 기존 구조 분석

실제 코드를 조사해 macOS 이식 시 영향받는 지점을 확인했다.

| 파일 | 현재 동작 | macOS 영향 |
|---|---|---|
| `packnine.spec` | Windows 전용 PyInstaller 스펙. `.ico` 아이콘, `EXE()`만 사용(단일 실행파일) | macOS는 `BUNDLE()`로 `.app` 패키징 필요 → 신규 스펙 파일로 분리(기존 파일 불변) |
| `installer.nsi` | NSIS 스크립트, HKCU 경로 설치 + 시작메뉴/바탕화면 바로가기 | macOS는 NSIS를 쓸 수 없음. 1단계는 `.app`을 zip으로만 배포(설치 프로그램 없음) |
| `.github/workflows/ci.yml` | `windows-latest` + `ubuntu-latest` 매트릭스로 pytest 실행 중(`ubuntu`는 `QT_QPA_PLATFORM=offscreen`) | `macos-latest` 추가 시 동일한 offscreen 플랫폼 플러그인 사용 가능성 높음(Qt6이 `cocoa`/`offscreen` 둘 다 지원) |
| `infrastructure/motw.py` | `sys.platform != "win32"`면 `read_zone_identifier`/`propagate_zone_identifier` 모두 즉시 `None`/`no-op` 반환 | **이미 안전**. 코드 수정 불필요, macOS에서 MoTW 기능만 조용히 비활성화됨 |
| `infrastructure/context_menu.py` | `register()`/`unregister()` 최상단에서 `_require_windows()` 호출 → macOS면 `RuntimeError` | 호출부가 이미 방어돼 있는지 확인 필요(아래 참고) |
| `presentation/gui/main_window.py:419-430` | `_on_file_association()`(메뉴 클릭 핸들러)에서 `ContextMenuService().register()`를 `try/except Exception`으로 감싸고 실패 시 `self._show_error(exc)` 호출 | **크래시 없음**. macOS에서 클릭하면 일반 오류 다이얼로그가 뜨는 정도(UX 개선 여지는 있으나 이번 트랙 범위 밖) |
| `presentation/cli.py` `register-context-menu` 서브커맨드 | `_cmd_register_context_menu()`가 `service.register()`/`unregister()` 호출 | GUI와 달리 예외를 잡지 않으면 CLI가 트레이스백과 함께 비정상 종료할 수 있음 → 3.1 항목으로 별도 확인 필요 |
| `domain/security_policy.py` | Zip Slip/심볼릭 링크/절대경로 거부 로직이 `pathlib` 기반 | Windows 전용 API 호출 없음, POSIX에서도 동작할 것으로 예상되나 **실측 검증 안 됨**(6장 리스크 참고) |

### 3.1 CLI `register-context-menu`의 예외 처리 확인 필요

GUI 경로는 예외를 잡아 오류 다이얼로그로 전환하지만, CLI 서브커맨드는 `service.register()`
호출을 감싸는 try/except가 코드상 확인되지 않았다. macOS에서 `packnine
register-context-menu`를 실행하면 `RuntimeError` 트레이스백이 그대로 노출될 수 있다.
크래시는 아니지만(정상적인 예외로 종료 코드 1 반환) 사용자 친화적이지 않으므로,
implementation.md 단계에서 "Windows 전용 기능입니다" 형태의 명확한 오류 메시지로
다듬을지 여부를 결정한다(기능 자체를 추가하지 않으므로 plan.md In Scope와 상충하지 않음).

## 4. 대안 비교

### 4.1 빌드 도구

| 후보 | 선택 | 이유 |
|---|---|---|
| **PyInstaller**(현행 유지) | 채택 | Windows와 동일 도구라 스펙 구조·트러블슈팅 지식을 재사용. `packnine.spec`이 이미 검증된 참고 구현으로 존재 |
| briefcase(BeeWare) | 기각 | macOS/iOS 앱스토어 배포에 특화되어 있어 이번 범위(GitHub Release 직접 배포)에는 과함. 별도 프로젝트 구조(`pyproject.toml` toga 설정 등) 요구 |
| py2app | 기각 | macOS 전용이라 Windows 빌드와 스펙을 공유할 수 없어 유지보수 이중화 발생 |

### 4.2 배포 형태

| 후보 | 선택 | 이유 |
|---|---|---|
| **zip(`.app`을 압축)** | 채택(1단계) | 추가 도구 불필요(`ditto`/표준 zip만으로 생성), GitHub Release 첨부 파일로 바로 사용 가능 |
| `.dmg` | 보류(후속) | `hdiutil`/`create-dmg` 등 배경 이미지·설치 UX 작업이 추가로 필요해 1단계 범위를 벗어남 |
| `.pkg`(installer) | 보류(후속) | 시스템 설치 경험까지 제공하려면 서명/공증이 사실상 필수라 이번 트랙 Out of Scope와 충돌 |

### 4.3 CI 빌드 환경

| 후보 | 선택 | 이유 |
|---|---|---|
| **GitHub Actions `macos-latest`** | 채택 | 호스티드 러너라 재현 가능하고 로컬 Mac 없이도 회귀 검증 가능. 기존 `ci.yml` 매트릭스 패턴을 그대로 확장 |
| 로컬 Mac 수동 빌드만 | 기각 | 1회성 검증에는 필요(수동 스모크 테스트)하지만 CI 자동화 없이는 회귀를 상시 잡을 수 없음 |

## 5. 선택 이유

- **PyInstaller 유지**가 가장 리스크가 낮다: 이미 `packnine.spec`으로 Windows 빌드가
  검증되어 있고, macOS 스펙(`packnine.mac.spec` 가칭)도 동일한 `Analysis`/`PYZ` 단계를
  공유하며 마지막 패키징 단계(`EXE` → `BUNDLE`)만 달라진다.
- **Apple Silicon(`arm64`) 우선**은 GitHub Actions `macos-latest`의 기본 아키텍처이자
  현재 판매되는 Mac 대부분의 아키텍처이므로 커버리지 대비 구현 비용이 가장 낮다.
- **zip 우선 배포**는 "코어 기능이 실제로 macOS에서 동작하는가"를 가장 빠르게 검증하고
  공개하는 경로이며, `.dmg`/코드 서명 같은 UX·신뢰성 개선은 별도 트랙으로 미뤄도 사용자
  가치 제공에는 지장이 없다(Windows도 포터블 exe를 함께 배포하는 것과 동일한 패턴).

## 6. 기술적 리스크 및 대응

| 리스크 | 대응 |
|---|---|
| Gatekeeper "확인되지 않은 개발자" 차단 | README에 "시스템 설정 > 개인정보 보호 및 보안"에서 실행 허용하는 안내 추가(정식 서명은 후속 트랙) |
| `unrar`/`bsdtar` 미설치 시 RAR 해제 실패 | 기존 에러 메시지 경로 재사용 확인 + README에 `brew install unrar` 또는 `brew install libarchive` 안내 추가 |
| CLI `register-context-menu`가 macOS에서 트레이스백 노출(3.1 참고) | implementation.md 단계에서 예외 메시지를 "Windows 전용 기능입니다" 수준으로 다듬을지 결정 |
| `domain/security_policy.py`의 심볼릭 링크/절대경로 판정이 POSIX에서 미검증 | macOS CI 테스트 통과 여부로 1차 검증, 실패 시 이번 트랙에서 최소 수정(로직 확장이 아닌 버그 수정 성격이면 In Scope로 포함) |
| PySide6 macOS 헤드리스 CI 테스트에서 Qt 플랫폼 플러그인 오류 가능성 | Ubuntu와 동일하게 `QT_QPA_PLATFORM=offscreen` 우선 적용, 실패 시 `cocoa` 플랫폼 대체 조사 |
| GitHub Release 첨부물이 zip이라 "설치된 앱" 느낌이 약함(더블클릭 실행 안내 필요) | README에 "다운로드 후 압축 해제 → PackNine.app 더블클릭" 절차 명시 |

## 7. 결론

코어 로직(도메인/애플리케이션/포맷 어댑터/GUI/CLI)은 수정 없이 재사용하고, 다음 3가지
신규 산출물만으로 1단계 macOS 릴리스가 가능하다고 판단한다.

1. macOS 전용 PyInstaller 스펙(`packnine.mac.spec`) — `.icns` 아이콘, `BUNDLE()` 패키징
2. `ci.yml`에 `macos-latest` 매트릭스 추가
3. README macOS 섹션(설치·실행·RAR 의존성·Gatekeeper 안내)

Windows 전용 모듈(`motw.py`, `context_menu.py`)은 이번 트랙에서 기능을 추가하지 않으며,
`motw.py`는 이미 완전히 안전하고 `context_menu.py`는 GUI 경로가 이미 안전함을 확인했다.
CLI 경로의 트레이스백 노출만 implementation.md에서 최소 수정 여부를 결정한다.
