# 설계 리뷰 실행 기록

입력 v1은 `input-v1/`의 문서 4개와 Git `a3031fa`의 라이브러리·테스트·
설정이다. 문서 본문은 고정 snapshot으로 보존한다. 상대 링크는 원래
`.worknote/`와 저장소 기준으로 해석한다. 입력은 수정하지 않는다.

| snapshot | SHA-256 |
| --- | --- |
| `01-current-design.md` | `229F05B9C9D7722636F94493C532A84D0EFE40755E1819C94CD9A503DD8CA227` |
| `02-interface-design.md` | `F5D79E6C123F717BAA3A0A68951B9A6FB0BC4ADB7DBF90C8482243858525D486` |
| `03-implementation-proposal.md` | `7E7F9C488D4220A9D3B114FDA4B33EA0F3219118FBBFAC7044DAA910AD427938` |
| `sources.md` | `E4D2331AE7BF89CE8250677B6CEA0622379F42C04245A8F95C9D8A4FD4CB8788` |

리뷰팀은 아래 책임을 가진 독립 subagent 3명이다. 실제 외부 사람의 리뷰나
별도 전문가 자격을 뜻하지 않는다. 각 reviewer는 같은 v1 입력을 읽고
다른 reviewer의 결과를 보지 않은 채 자기 보고서만 작성한다.

| reviewer | 책임 | 출력 |
| --- | --- | --- |
| 사용성·이관 | 기존 사용자가 작업을 완료하는가, API 의미·호환성·문서 일치 | `usability.md` |
| SDK·리소스 통합 | 인증·transport·discovery·scope·SSA·최신 GVK의 구현 가능성 | `sdk-integration.md` |
| 검증·운영 | 오류·watch·deadline·RBAC·cleanup·release 근거와 완료 조건 | `validation-operations.md` |

중요도는 설계 선결, 구현 검증, 선택 개선으로 구분한다. 지적에는 finding ID,
입력 revision과 위치, 실패 조건, 이미 있는 보호 장치에 대한 반증 검토,
최소 수정과 판정 사례를 적는다. 숫자로 지적 개수를 채우지 않는다.

동시 실행 범위는 조정자 1명+reviewer 3명이며 1차 검토 한 번 후 채택 지적의
국소 재검토를 수행한다. 각 reviewer는 모델 설정을 상속한다. runtime의
구체적 모델/effort 값은 확인 불가이며 권장값을 실제값으로 기록하지 않는다.

조정자는 원본 코드·SDK·문서를 대조해 [판정 기록](decisions.md)에
채택·일부 채택·구현 검증 이관·반증 제외와 이유를 적고 최종 계획에 반영한다.
보고서의 동의 수를 정확성의 근거로 사용하지 않는다. 후속 재검토는 1차
독립 결과와 별도 기록한다.

## 최종 v2의 국소 재검토

| 고정 입력 | SHA-256 |
| --- | --- |
| `input-v2/04-final-implementation-plan.md` | `20ED861547D49369A85659435F3478233D2465AF0DACBAFA571F81CDB5359291` |
| `input-v2/decisions.md` | `898943E090D80434279579C75E76C0E740B94ABE60D1E11BC4E6A86C63D00201` |

| 후속 reviewer | 재검토 범위 | 보고서 |
| --- | --- | --- |
| 사용성·이관 | USR-01/02/03과 변경된 기본 사용 예 | [후속 결과](usability-followup.md) |
| SDK·리소스 통합 | SDK-01–05의 request/discovery/patch 보정 | [후속 결과](sdk-integration-followup.md) |
| 검증·운영 | OPS-01–03과 조정자 추가 event parsing 관측 | [후속 결과](validation-operations-followup.md) |

후속 검토는 채택 수정의 동작 규칙을 대조하는 범위다. 1차 보고서는
변경하지 않고 구현·클러스터 검증과 구분한다.

## v3의 추가 query 보정

| 고정 입력 | SHA-256 |
| --- | --- |
| `input-v3/04-final-implementation-plan.md` | `82CF430949B414EE348114E94F98CBB5948143FE8335FE76BDC365EF41DBA7C6` |
| `input-v3/decisions.md` | `961F4234297782D9876146CA1BC9EDA27550ABDD5141353AF533B715778B7FC7` |

v2 SDK 후속 지적 SDK-02-F1의 resourceVersionMatch query 전달 규칙만
추가했다. SDK reviewer의 v3 확인은 SDK 후속 보고서에 별도로 연결한다.
사용성·운영의 v2 판정은 그 수정 항목에 한정된 결과로 보존한다.
보고서의 의미는 유지하고 보존 파일의 개행만 UTF-8/LF 기준으로 맞춘다.
