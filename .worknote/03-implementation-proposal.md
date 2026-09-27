# 구현안 v1

이 문서는 코드 작성 전에 리뷰하는 구현안이다. 최종 순서는
[최종 구현계획](04-final-implementation-plan.md)을 따른다.
입출력·실패 규칙은 [인터페이스 설계](02-interface-design.md)가 관리 원본이다.

## 코드 배치

기존 파일을 먼저 보존하고 실제 책임에 맞는 파일만 추가한다.

| 대상 | 변경 책임 |
| --- | --- |
| `kubernetes_client/__init__.py` | `KubernetesClient` 추가 export, 기존 export 보존 |
| `kubernetes_client/client.py` | 명시 factory, ApiClient 소유권, discovery cache, close |
| `kubernetes_client/resources.py` | GVK/scope, 공통 CRUD·SSA, pagination, dict 직렬화 |
| `kubernetes_client/watch.py` | 유한 stream·response 종료, wait의 deadline·UID 검사 |
| `kubernetes_client/manifests.py` | Namespace·Secret·ServiceAccount 최소 manifest와 quantities |
| `kubernetes_client/errors.py` | 발견 실패, 모호성, 입력, closed, wait 실패 구분 |
| `kubernetes_client/base.py`, `schema.py` | 이번 기본 구현에서는 legacy semantics 보존 |
| `tests/test_*.py` | 기능별 unittest; transport/discovery 실패 회귀 검증 |
| `tests/integration/` | opt-in 실클러스터 리소스·RBAC·SSA·watch 검증 |
| `docs/`와 README | 새 기본 사용법, migration과 지원 범위 |
| `pyproject.toml`, CI | 검증된 SDK 범위·dev extras·test matrix와 release 조건 |

위 파일은 책임 구분안이며 클래스마다 파일을 추가하지 않는다.
추가 Protocol, generic model hierarchy, model generator는 만들지 않는다.
helper manifest는 dict를 반환하고 SDK의 모델 전체를 Pydantic으로 복제하지 않는다.

## P0 — 기존 동작 고정과 SDK 경계 확인

현재 7개 테스트는 유지한다. 생성자별 configuration 전달, 반환값을 버리는
ServiceAccount, create 이름의 Secret upsert, labels 입력 변경 등 이관에
영향을 주는 동작을 mocking 기반 characterization test로 기록한다.
기존 결함을 새 API의 정상 동작 규칙으로 복사하지 않는다.

DynamicClient의 get/create/patch/replace/delete/SSA, discovery error,
`ApiClient.sanitize_for_serialization`, `Watch.stream`과 cleanup을 설치한
SDK 36.0.3 및 별도 37 beta 환경에서 확인한다. `ResourceInstance`와 모델의
`.to_dict()`가 같다고 가정하지 않는다. 구현 재개 시 PyPI와 release 정보를
다시 조회한다.

완료 조건: legacy 출력·반환·오류 기준표와 새 API 공개 signature 목록,
SDK 소스에서 확인한 transport 옵션 표가 리뷰 가능해야 한다.

## P1 — 인증 격리와 연결 수명

factory마다 `Configuration`을 만들고 SDK loader에
`client_configuration`을 전달한다. 생성한 `ApiClient`로 모든 dynamic과
generated 호출을 연결한다. lazy discovery는 쓰는 시점에만 활성화한다.
직접 SDK 호출만 하는 client 생성에도 discovery 권한을 요구하지 않는다.

검증은 두 개 client의 host/token/context 격리, 전역 설정 불변,
dict/file/in-cluster loader 인자, configuration copy, borrowed connection
보존, close 반복, closed client 요청 거부, 생성 실패 cleanup을 포함한다.
캐시 파일은 client별 임시 경로이며 종료 후 제거한다. 일부 생성에 실패해도
만들어진 owned connection을 누수하지 않는다.

완료 조건: fake transport로 서로 다른 인증 client가 다른 host/header를
사용하고, close가 소유권에 맞게 동작함을 확인한다.

## P2 — 공통 리소스 관리와 최신 GVK

GVK를 discovery로 찾고 verb·scope를 확인한다. lookup miss refresh는 한 번만
한다. 이 단계에서 read/list/create/patch/replace/apply/delete와 페이지
iteration을 구현한다. namespace 판단과 body 복사는 단일 경로에서 수행한다.

SSA는 exists 후 create/patch로 구현하지 않고 단일 apply PATCH다.
patch의 기본 content type은 SDK default strategic merge를 그대로 쓰지 않고
`application/merge-patch+json`으로 지정한다. SDK request keyword는
`field_manager`, `force_conflicts`, `dry_run`, `field_validation`,
`_request_timeout`으로 명시적으로 매핑한다.

resource discovery miss와 단일 객체 404를 분리하고 unsupported verb를
쓰기 전에 거부한다. 확인한 discovery로도 실제 허가 여부는 알 수 없으므로
서버 403을 그대로 전달한다. 성공 dict를 임의 정형 schema로 축소하지 않는다.

| 회귀 조건 | 기대 결과 |
| --- | --- |
| Namespace에 explicit namespace | 로컬 입력 오류, HTTP write 없음 |
| namespaced bind와 body namespace 충돌 | 오류, 사용자 body 불변 |
| CRD plural이 kind lowercase와 다름 | 발견한 plural URL 사용 |
| beta만 있는 GVK와 stable lookup | unsupported, beta 자동 선택 없음 |
| 403/timeout discovery | False·빈 목록 아님 |
| get 객체 404, exists 객체 404 | 각각 예외, False |
| create 409, apply field conflict 409 | 예외; 자동 patch/force/retry 없음 |
| omitted/null/빈 dict/list patch | 원래 wire payload 차이 유지 |
| SDK V1 model 입력 | snake_case 없이 wire aliases 사용 |
| 미등록 새 field dict | round trip 보존, 서버 검증 사용 |
| continue token pagination | selector 유지, metadata RV를 변경하지 않음 |
| delete accepted+finalizer | requested; 삭제 완료라고 보고하지 않음 |
| replace에 RV 없음 또는 충돌 | 각각 입력 오류 또는 SDK 409 |

실클러스터 기본 사례는 Namespace·Pod·Deployment·Service·ConfigMap·Secret·
ServiceAccount·Job·CronJob·HPA·Ingress·EndpointSlice·NetworkPolicy·
Role/RoleBinding·ClusterRole/ClusterRoleBinding·PVC·StorageClass·Lease다.
모든 리소스에 bespoke wrapper를 작성하지 않고 동일 공통 경로를 쓴다.
리소스별 server prerequisites와 삭제 정리는 fixture에 명시한다.

최신성 사례는 1.37 cluster의 새 리소스/필드를 dict로 관리하는 것과 설치한
test CRD의 irregular plural·scope·status 유무다. ResourceClaim·
ResourceClaimTemplate·ResourceSlice는 discovery와 dry-run을 우선 사용한다.
외부 driver가 없는 상태에서 할당 완료를 성공 기준으로 삼지 않는다.
CRD structural schema, version served=false, 권한 제한, 추가 후 cache refresh도
검증한다. alpha/beta·feature-gated resource는 발견되는 환경에서만 opt-in한다.

완료 조건: builtin과 CRD가 같은 규칙을 사용하고, 정상·권한 실패·conflict·
schema 실패가 원래 status와 구분되어 검증되어야 한다.

## P3 — 기존 편의 기능의 표준화

최소 manifest helper를 추가한다. helper 이름에는 create/prepare를 쓰지 않고
create 또는 apply 선택은 호출자에게 둔다. Namespace 업무 labels는 명시
입력으로 받는다. credential 검증은 helper에서 수행하고 기존 메서드는 유지한다.
새 quantities는 문자열과 임의 resource key를 보존하며 request > limit을
오류로 다룬다. None/empty와 GPU alias의 이관 사례를 migration 문서에 적는다.

완료 조건: helper가 사용자 dict를 바꾸거나 credential을 출력하지 않고,
동일 manifest가 create와 apply 양쪽에서 사용할 수 있어야 한다. Secret SSA는
stringData를 data로 변환한 body로 반복 적용과 충돌 검증을 통과한다.

## P4 — watch와 workload 대기

유한 watch timeout과 request timeout을 전달해 SDK 자동 retry를 제어한다.
context manager를 벗어나면 stream·HTTP response를 닫는다. typed/dict event와
BOOKMARK·ERROR를 구분한다. watch API에는 SDK와 다른 resourceVersion
보장을 암묵적으로 추가하지 않는다.

wait는 monotonic deadline, UID, 최초 generation, resourceVersion을 추적한다.
ready, 삭제, terminal failure, timeout, 410, 403, 취소를 별도 경로로 다룬다.
Pod/Deployment 외에는 명시 predicate 없는 readiness를 제공하지 않는다.
namespace/name이 같은 대체 객체는 원래 작업의 성공으로 세지 않는다.

검증은 fake clock과 제어된 event iterable을 사용하고 arbitrary sleep으로
동기화를 맞추지 않는다. replica=0, observedGeneration 지연, progress deadline,
Pod Ready=Unknown, watch 중 삭제·재생성, 이벤트 없는 read timeout,
iterator 조기 종료, caller 예외 발생 시 cleanup을 포함한다.

완료 조건: deadline 종료가 실제 wall-clock/network 범위를 포함하고
연결이 정리되어야 한다. 실클러스터에서 watch 연결 중단과 finalizer 대기도
검증하되 unit 성공을 이 조건의 대체 근거로 쓰지 않는다.

## P5 — 사용법 이관과 배포 검증

README의 기본 예제를 새 API로 전환하고 `docs/migration.md`에 legacy/new
메서드의 반환·예외·create/upsert·기본 namespace 차이를 기록한다.
legacy 동작은 유지하며 제거 시점을 이번 계획에서 임의 지정하지 않는다.
새 interface가 기존 `.client`를 다른 타입으로 바꾸지 않게 한다.

runtime에는 SDK와 Pydantic만 남기는 의존성 정리는 package validation과
분리해서 검토한다. test/type/build 도구는 dev extras로 옮긴다. formatter 도구는
기존 설정이 없어 이번 기능을 위해 임의 선택하지 않는다. type check는 새
public API의 입력·출력과 unsupported SDK type 범위를 확인한다.

unit matrix는 Python 3.10–3.14, SDK 안정 baseline과 최신 안정 SDK다.
사전 릴리스 lane은 별도 허용하며 설치 명령에 정확한 beta 버전을 지정한다.
현재 `<38` 범위가 두 SDK의 모든 기능 호환을 증명하지 않는다. 구현 이후
실행 결과로 범위를 결정한다. integration matrix는 supported 서버 minor 중
최신 1.37과 1.36을 우선하고 1.35를 공통 stable API 검증에 추가한다.
feature gate·CRD 설치·RBAC 계정·cluster image version을 실행 기록에 남긴다.

release 전에 wheel/sdist build, `twine check --strict`, 깨끗한 환경 wheel
설치와 공개 import를 확인한다. code 변경 없이 이번 문서만으로 배포하지 않는다.

완료 조건: 실행한 SDK/Python/server 조합과 미검증 조합이 지원표에 명시되고,
legacy regression·새 API unit·필수 integration·package validation이 통과해야 한다.

## 단계별 모델·effort 권장

아래는 skill의 작업 난도 권장이며 실제 설정이나 성능 측정 결과가 아니다.
현재 실행 모델/effort는 확인할 수 없다. 사용자 설정을 임의 변경하지 않는다.

| 단계 | 기획 | 설계 | 구현 | 검증 |
| --- | --- | --- | --- | --- |
| P0 기존 동작/SDK 경계 | Astra/high | Astra/high | Sol/medium | Sol/high |
| P1 인증/수명 | 해당 없음 | Astra/high | Sol/high | Astra/high |
| P2 공통 resource | 해당 없음 | Astra/high | Sol/high | Sol/high |
| P3 manifest/quantities | 해당 없음 | Sol/medium | Sol/medium | Sol/high |
| P4 watch/wait | 해당 없음 | Astra/high | Astra/high | Astra/high |
| P5 migration/release | Sol/medium | 해당 없음 | Sol/medium | Sol/high |

Astra는 `gpt-6-astra`, Sol은 구현·검증 권장의 `gpt-5.6-sol`을 뜻한다.
P2 namespace와 SSA 의미 교차 검증, P5 지원 범위 최종 판정은 Astra/high를
권장한다. 이는 모델 선택을 위한 subagent routing 지시가 아니다.
