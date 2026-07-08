# 기여 가이드 (Contributing)

PackNine에 관심을 가져주셔서 감사합니다. 이 프로젝트는 **SDD → TDD → 구현** 순서를 원칙으로
개발합니다. 기여하실 때도 아래 순서를 따라주세요.

## 기여 순서

1. **SDD(Spec-Driven Development)**: 새 기능/변경 사항을 구현하기 전에 관련 도메인 값객체,
   인터페이스(Protocol/ABC), 또는 서비스 시그니처 등 스펙을 먼저 정의하거나 문서화합니다.
2. **TDD(Test-Driven Development)**: 스펙을 기준으로 실패하는 테스트를 `tests/`에 먼저
   작성합니다. 그 다음 테스트를 통과시키는 최소 구현을 추가하고, 이후 리팩터링합니다.
3. **구현**: DDD 계층 경계(`domain` → `application` → `infrastructure` / `presentation`)를
   지켜 구현합니다. 각 계층의 책임을 넘어서는 의존성을 추가하지 마세요(예: `domain`이
   외부 라이브러리에 직접 의존하지 않도록 유지).

## PR 제출 전 체크리스트

- [ ] 변경 사항에 대응하는 테스트를 작성했는가 (TDD 순서를 지켰는가)
- [ ] `pytest` 전체 테스트가 통과하는가

```powershell
pytest
```

- [ ] 보안 관련 변경(아카이브 파싱, 경로 처리 등)이라면 Zip Slip/압축 폭탄/심볼릭 링크
  방어 테스트가 함께 포함되었는가
- [ ] `packnine/domain`, `packnine/application`, `packnine/infrastructure`,
  `packnine/presentation` 각 계층의 책임 경계를 넘지 않았는가

## 커밋 메시지 규칙

커밋 메시지는 **한글로, 무엇을 바꿨는지 나열하기보다 왜 바꿨는지(의도와 맥락)를 중심으로**
작성해주세요.

예시:

```
fix : Zip Slip 우회 가능한 상대경로 정규화 누락 수정
feat : TAR.XZ 압축 옵션 추가
refactor : ExtractService의 사전 검증 로직을 SecurityPolicy로 이관
docs : RAR 해제 사전 요구사항(unrar/bsdtar) 안내 보강
```

## 이슈/버그 제보

일반 버그나 기능 제안은 GitHub Issue로 등록해주세요. 단, **보안 취약점**은 공개 Issue가 아닌
[SECURITY.md](./SECURITY.md)에 안내된 대로 GitHub Security Advisory를 통해 비공개로
제보해주세요.
