# v1.0.0 구현 실행 기록

실행 기준은 [최종 구현계획](../04-final-implementation-plan.md)이다.
runtime 구현은 `398d360`, release README·metadata와 실행 기록은 `fcda918`에
고정했으며 v1.0.0 tag는 `fcda918`을 가리킨다.
검증 범위·원문·현재 배포 상태는 [validation.md](validation.md)에 기록한다.
v1.0.0 wheel·sdist의 PyPI 공개와 새 환경 설치·import·33개 회귀 검사까지
완료했다. tag를 검증한 Publish to PyPI의 16개 job이 모두 성공했다.

| 단계 | 반영한 책임 | 실제 검증 근거 |
| --- | --- | --- |
| P0 | legacy Manager·schema·quantity 보정 보존 | 기존 7개 회귀와 원본 파일 diff |
| P1 | 전용 Configuration·인증 factory·owned/borrowed 수명 | host/context 격리·global 불변·retry/pool·종료 사례 |
| P2 | 정확한 discovery·namespace·wire dict CRUD/SSA·pagination | 두 SDK wire 검사·CRD/RBAC/SSA·실제 builtin/new GVK |
| P3 | 순수 manifest·Secret data·SDK quantities | unit validation·Secret 실제 반복 SSA |
| P4 | strict watch·GET wait·UID/generation·deadline/취소 | Unicode/EOF/ERROR·real socket·finalizer와 live readiness |
| P5 | 사용·이관 가이드·지원 범위·package·release gate | Python/SDK matrix·3 server minor·wheel 설치·Actions |

독립 1차와 한정 후속 결과는 [리뷰 입력 기록](review/README.md)에 보존했다.
채택한 13개 지적과 설계 변경·환경 보정의 이유는
[decisions.md](decisions.md)에 연결했다. 초기 설계 문서의 미구현·미실행 표시는
당시 상태로 보존하며 현재 구현 완료 범위의 판정으로 사용하지 않는다.
