# 리뷰 비교 판정과 최종 반영

기준: 고정 `input-v1/` 네 문서, Git `a3031fa`.
조정자는 reviewer 3명의 1차 보고서를 읽고 원문·설치 SDK 소스를 대조했다.
SDK transport probe는 두 SDK에서 직접 재실행했다. 운영 reviewer의 local
fault-server 실행은 보고서의 실행 근거이며 조정자가 동일 서버를 재실행한
결과로 표시하지 않는다. 판정은 동의한 reviewer 수로 정하지 않았다.

| 원 지적 | 판정 | 근거와 최종 변경 | 실행 단계 |
| --- | --- | --- | --- |
| USR-01 write와 wait 대상 연결 | 채택 | 최초 GET 이후 UID 검사만으로 write→GET 경합을 막지 못함. expected_uid/target_generation 명시, name-only 보장 범위와 generation 변경 오류 고정 | P0 signature, P4 |
| USR-02 namespace 연결 | 채택 | body namespace는 후속 name-only 조회의 namespace를 바꾸지 않음. 기본 예제의 같은 explicit resource bind 사용 | P0/P2, migration |
| USR-03 Secret SSA 출력 | 채택, 구현 검증 이관 | 순수 helper가 data만 출력하도록 책임 확정. raw Secret apply의 stringData는 거부하고 같은 body create/apply 반복·conflict 검증 | P3 |
| SDK-01 discovery 실패 분류 | 채택 | 503→미발견 재현 확인. discovery raw decode/shape·status 보정, 진짜 empty와 통신/형식 실패 분리 | P0/P1/P2 |
| SDK-02 fieldValidation 전달 | 채택 | keyword는 wire에서 빠짐. fresh query_params에 정확한 fieldValidation 추가 | P0/P2 |
| SDK-03 empty JSON Patch | 채택, 구현 검증 이관 | []가 {}·strategic로 변하는 것을 재현. discovered path의 직접 DynamicClient.request로 배열 보존 | P0/P2 |
| SDK-04 discovery timeout | 채택 | SDK discovery의 timeout 인자 부재. request 경계 default 적용, wait deadline은 resolve 이후 시작한다고 명시 | P1/P4 |
| SDK-05 strategic 판별 | 채택 | APIResource에 CRD/strategic 지원 표지가 없음. merge/json으로 제한, strategic는 SDK 직접 호출 | P0/P2 |
| OPS-01 deadline/취소 범위 | 일부 채택 | 엄격한 wall-clock SLA 요구는 사용자 요청에 없음. 동기 SDK의 협조적 deadline으로 고정, GET polling 대기·cancel_event·남은 예산·응답 후 deadline 검사, generic watch 분리 | P0/P1/P4 |
| OPS-02 write retry | 채택 | wrapper call 1회와 HTTP 1회는 다름. owned retries=0, borrowed의 실제 no-retry 조건 검증/거부; 연결은 임의 변경하지 않음 | P0/P1 |
| OPS-03 delete 대상 UID | 채택 | delete→wait 첫 GET 사이 이름 재사용은 최초 UID 고정만으로 해결 불가. wait_deleted expected_uid 필수, replacement는 별도 오류 | P0/P2/P4 |

USR-01과 OPS-03은 동일한 원인(write 대상과 후속 name-only 조회의 identity
연결 누락)을 공유한다. 준비 완료와 삭제 완료의 결과는 달라 각각의 메서드
입출력 규칙을 남겼다. SDK-04와 OPS-01의 discovery timeout도 겹치며 하나의
request 경계에서 보정한다. OPS-02는 이와 다른 transport replay 문제다.

deadline의 두 선택지는 절대 중단용 별도 실행 주체와 동기 SDK 범위의 협조적
종료였다. 이번 목적에 강제 wall-clock 중단 요구가 없어 후자를 채택했다.
polling은 종료·취소 조건이 있는 준비 상태 조회이며 자동 resource reconcile나
watch reconnect가 아니다. generic watch의 410은 그대로 caller에게 전달한다.
Pod의 Ready와 Deployment generation rollout도 같은 보장으로 합치지 않았다.

## 조정자의 추가 관측

아래는 독립 1차 reviewer가 먼저 발견한 결과와 구분한다.

| ID | 관측/판정 | 후속 기준 |
| --- | --- | --- |
| COORD-01 | SDK36 close는 HTTP pool clear까지 하지 않고 37은 rest close를 호출함. 초안이 이미 검증 대상으로 남긴 항목을 최종 종료 순서로 구체화 | P1 owned/borrowed close regression |
| COORD-02 | SDK Watch.unmarshal_event는 malformed JSON을 무시할 수 있음. strict event parser와 형식 오류 종료 검증으로 이관 | P4 raw event/BOOKMARK/ERROR/cleanup |
| COORD-03 | DRA 기존 리소스만으로 1.37 최신성 증거가 부족함. 새 stable certificates GVK를 36 generic 경로의 필수 integration으로 지정 | P2/P5 실제 served 신규 GVK·field round trip |
| COORD-04 | continuation은 server snapshot token이며 이후 페이지에 새 RV를 적용하면 안 됨. 첫 페이지 RV 옵션과 후속 token 요청 분리 | P2 일관된 metadata RV·410·token 반복 검사 |
| COORD-05 | discovery refresh 후 기존 handle이 descriptor를 계속 쓰면 삭제/재등록을 놓침. 다음 operation resolve와 진행 중 wait의 descriptor 고정을 구분 | P2 refresh 후 handle·scope/verb, P4 실행 중 target 고정 |

COORD-02는 운영 reviewer에게 독립 리뷰 도중 추가 메시지로 전달되었다.
곧바로 독립 finding에 넣지 말고 조정자 추가 관측으로 구분하도록 정정했으며
운영 reviewer는 1차 지적에 포함하지 않았다고 기록했다. 이 항목의 후속 검토를
독립 최초 발견으로 세지 않는다.

## 반증으로 제외하거나 범위에 넣지 않은 사항

dict 기반 dynamic 관리가 SDK에 모델이 없는 모든 resource를 무조건 지원한다는
해석은 제외한다. served API·scope·verb·RBAC·schema·feature gate를 확인한
경로만 지원한다. SDK 모델 부재 자체는 관리 불가의 근거가 아니지만 실제
server round trip은 구현 후 검증해야 한다.

legacy create_opaque_secret upsert와 새 create-only의 차이는 regression이
아니다. old API 보존과 migration에 명시한 새 API 의미다. 기존 labels 정책,
수량 상향과 None 반환을 새 규칙으로 복사하지 않는다. external consumer가
확인되지 않아 old API 제거 시점을 정하지 않았다.

CRD readiness 추정, async/controller, collection delete, 일괄 rollback,
subresource 통합은 사용자 목표에 필요한 기본 scope가 아니므로 제외한다.
2xx delete를 실제 소멸로 취급한다는 의심, 410 이후 무손실 자동 재개를
약속한다는 의심은 초안의 수락/소멸 구분과 자동 relist 제외로 반증되었다.

## 요구사항 대비 판정

| 사용자 요구 | 결과 상태 |
| --- | --- |
| 현재 library 설계 기록 | 구현·테스트·설정 기준으로 01에 작성 |
| 사용방식 표준화 | 공통 ResourceOperations 규칙과 helper/write/wait 책임 확정 |
| 최신 official SDK 기반 | stable/preview 분리, 원본 SDK 의존, 버전별 보정·갱신 조건 명시 |
| 최신 Kubernetes resource 관리 설계 | generic discovered GVK·dict와 최신 실제 GVK integration 기준 작성 |
| review팀 검토 | 동일 v1 입력의 독립 agent 3명 보고서와 반증 기록 보존 |
| 최종 구현계획 | 04의 P0–P5·완료 조건·검증 lane으로 반영 |
| 구현·실클러스터 검증 | 이번 요청의 산출물 범위 밖; 미구현/미실행으로 유지 |

설계에 대한 검토 판단은 코드 테스트 성공이나 외부 전문가 승인과 다르다.
세 reviewer의 국소 재검토는 최종 v2의 변경 규칙만 대상으로 수행하고
별도 followup 보고서에 남긴다. 실제 코드·클러스터의 미검증을 해결로 표시하지 않는다.
