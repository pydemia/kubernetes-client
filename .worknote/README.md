# Kubernetes high-level interface 설계 기록

기준일: 2026-09-27. 분석 대상: `a3031fa`, 패키지 0.9.0.
요청 범위는 설계와 구현계획 작성이다. 라이브러리 코드는 변경하지 않는다.

| 문서 | 용도 |
| --- | --- |
| [현재 설계](01-current-design.md) | 구현·테스트에서 확인한 기존 사용방식과 제약 |
| [표준 인터페이스 설계](02-interface-design.md) | SDK 기반 리소스 관리 규칙과 사용 예 |
| [구현안](03-implementation-proposal.md) | 파일별 변경, 단계별 검증과 이관 방안 |
| [최종 구현계획](04-final-implementation-plan.md) | 리뷰 판정을 반영한 실행 순서와 완료 조건 |
| [공식 근거와 실행 기록](sources.md) | 최신 버전, SDK 소스, skill, 실제 검증 범위 |
| [리뷰 기록](review/README.md) | 고정 입력, 독립 리뷰, 교차 판정과 재검토 |

`02`와 `03`은 독립 리뷰에 제출한 제안 v1이다. 수정 판단은 `04`에
반영한다. 리뷰 입력은 `review/input-v1/`에 보존한다. 최종 실행 기준은
`04`이며 원래 제안이나 reviewer의 개별 제안을 자동으로 확정하지 않는다.
