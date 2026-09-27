# 최종 구현계획

기준일: 2026-09-27. 기준 코드: `a3031fab6a1608b01d13a856186369db24fbc973`.
이 문서는 구현할 설계의 실행 기준이다. 라이브러리 구현 완료를 뜻하지 않는다.
초안과 다른 결정은 이 문서를 우선하며 원문과 판정은
[리뷰 기록](review/README.md)에 보존한다.

## 선택한 기본 설계

공식 SDK를 runtime dependency와 API/model 원본으로 유지하고
`KubernetesClient` → `ResourceOperations` → 공식 `DynamicClient` →
인스턴스 `ApiClient` → API server 경로를 기본으로 구현한다.
SDK generated API/model은 복제하지 않는다. 기본 응답은 wire key의 dict다.
typed model과 subresource가 필요하면 같은 `ApiClient`로 공식 API를 직접 쓴다.

기존 `KubernetesManager`의 import·signature·반환·예외·수량 보정은 유지한다.
새 문서와 새 기능은 `KubernetesClient` 기준으로 통일한다. 기존 `prepare_*`를
SSA로 내부 치환하지 않고 migration에서 create-only, patch, apply, wait의
차이를 설명한다. legacy 제거는 외부 소비자를 확인한 별도 breaking release의
결정이다. 이번 변경을 SDK fork나 범용 controller framework로 확대하지 않는다.

| 대안 | 채택 여부와 현재 요구에 대한 이유 |
| --- | --- |
| resource마다 generated method를 수작업 wrapping | 단독 기본으로 제외. 새 GVK마다 method/API class 연결을 유지해야 함 |
| 공식 DynamicClient와 공통 resource 작업 | 채택. discovery의 scope/plural/verb와 dict로 builtin·CRD·새 field 처리 |
| 자체 HTTP client 또는 SDK 모델 생성기 | 제외. 인증·transport·모델 유지 책임이 공식 SDK와 중복됨 |
| typed model을 high-level의 모든 응답에 강제 | 제외. SDK보다 새 server field가 역변환 과정에서 사라질 수 있음 |

단, SDK 소스에서 확인한 오류·payload 손실을 그대로 노출하지 않기 위해
아래의 작은 보정만 둔다. 보정 범위의 test 없이 구현 가능성을 주장하지 않는다.

## 공개 API에서 고정할 규칙

factory는 kubeconfig file/dict, in-cluster, Configuration, borrowed ApiClient를
명시적으로 구분한다. factory마다 전용 설정과 연결을 만들고 전역 기본값은
바꾸지 않는다. client default namespace는 생성 시 지정하며 기본은 `default`다.
client close 뒤 resource와 stream도 새 요청을 거부한다.

정규 진입점은 `client.resource(api_version, kind, *, namespace=...)`다.
편의 속성 pods/namespaces/secrets/service_accounts/deployments/services/
config_maps/jobs/cron_jobs도 같은 공통 작업을 쓴다. stable GVK를 명시하며
임의 beta/alpha 또는 preferred version으로 자동 치환하지 않는다.
body에서 선택한 namespace가 다음 요청의 bind를 바꾸는 숨은 상태는 없다.

| 작업 | 고정 규칙 |
| --- | --- |
| get/exists | 단일 객체 GET. 존재 확인에는 list 권한을 요구하지 않음 |
| list | 한 페이지의 items·metadata가 있는 dict 반환 |
| iter_items | continuation 기반 순차 iterator, snapshot 실패 시 종료 |
| create | 순수 POST. 409는 예외이며 upsert하지 않음 |
| patch | merge/json만 공개. merge가 기본, JSON Patch 배열을 그대로 전달 |
| replace | PUT. body의 resourceVersion 필수, conflict 자동 해결 없음 |
| apply | 단일 SSA PATCH. field manager 명시, force=False |
| delete | name 단일 DELETE. requested/already_absent와 server response 구분 |
| watch | 유한 stream context manager. print·자동 relist·자동 reconnect 없음 |
| wait_ready | Pod/Deployment의 명시적 준비 조건. 성공 시 최종 관측 dict 반환 |
| wait_deleted | 지정 UID의 소멸 대기. 같은 이름의 대체 객체는 별도 오류 |

strategic merge는 첫 공개 facade에서 제외한다. discovery만으로 builtin·CRD·
aggregated API의 strategic 지원을 신뢰성 있게 분류할 수 없기 때문이다.
필요한 사용자는 공식 typed API를 직접 호출한다. 일반 CRUD와 status/scale/
TokenRequest/exec 경로를 같은 resource operation으로 취급하지 않는다.

입력 dict를 복사하고 unknown field, 생략, null, 빈 mapping/list를 보존한다.
SDK model은 `ApiClient.sanitize_for_serialization`로 wire alias를 얻는다.
create/replace/apply는 bind된 GVK를 생략된 field에 보충할 수 있지만 다른
명시 GVK는 거부한다. name/namespace 같은 identity field의 null/빈 문자열은
일반 field 삭제 의도와 구분해 거부한다. create에는 generateName을 허용하며
apply에는 name이 필요하다. response 전체를 apply body로 재사용하지 않는다.

namespaced write는 explicit bind → body namespace → client default 순서다.
bind/body 충돌은 로컬 오류다. get/delete/wait는 bind 또는 default를 사용한다.
cluster resource는 explicit namespace/body namespace를 거부하고 default를
적용하지 않는다. 전체 namespace는 list/watch의 `all_namespaces=True`만
허용하고 explicit namespace와의 조합은 거부한다.

`exists=False`와 delete의 `already_absent`는 객체 미존재 404에 한정한다.
discovery 실패, namespace 미존재 404, 제거된 endpoint나 proxy의 모호한 404는
그대로 오류다. Kubernetes Status의 reason·details.name·details.kind/group이
요청 객체에 해당하는지 확인하고 분류할 근거가 없으면 미확인 404를 보존한다.
401/403/409/422/429/5xx와 transport 실패도 SDK 원인·status를 보존한다.

## SDK 소스에 맞춘 보정

`resources.py`에는 공식 `DynamicClient`를 좁게 확장한 내부 request 경계를
둔다. 별도 SDK 복사본이나 generated transport 내부 호출 계층은 만들지 않는다.
이 확장은 discovery 기본 timeout과 오류 의미를 보존하는 실제 책임에만 쓴다.

| 항목 | 최종 구현 방식 | 통과 근거/검증 |
| --- | --- | --- |
| field validation | 매 호출 새 query list에 `("fieldValidation", value)` 추가. public 값은 Ignore/Warn/Strict, write 기본은 Strict | 두 SDK에서 실제 wire query 확인 |
| empty JSON Patch | `DynamicClient.patch` 대신 discovered path의 `request("patch", body=..., content_type=...)` 사용 | `[]` body와 JSON Patch Content-Type 불변 |
| 발견 시 miss refresh | `LazyDiscoverer`의 기본 한 번 refresh 사용. facade의 중복 refresh 제거 | negative lookup의 discovery 요청 횟수 검사 |
| discovery 503/잘못된 JSON | discovery route의 raw response를 엄격히 decode/shape 검사; 오류는 자체 discovery 예외로 전파 | 일시 장애가 ResourceNotServed/False로 바뀌지 않음 |
| discovery timeout | 내부 request 경계가 기본 `_request_timeout`을 넣고 `/version`, API group/version 조회에도 적용 | cold lookup·refresh의 실제 transport timeout 검사 |
| SDK 36/37 종료 | owned client의 SDK close 후 36 HTTP pool clear, 37 rest close 사용 | response/pool/cache 종료 순서와 borrowed 보존 |
| transport retry | owned 설정의 `retries=0`, write replay 없음 | PUT/DELETE disconnect 시 wire 요청 횟수=1 |

discovery 경계는 `/version`, `/api`, `/apis`, core/group version discovery만
raw로 읽고 정상 JSON을 SDK의 ResourceInstance 또는 지정 serializer로 돌려준다.
status 오류·decode 오류·필수 list field 누락을 정상 빈 결과로 만들지 않는다.
raw response는 성공·실패 모두 consume/close/release한다. 일반 객체와 watch의
response는 각 호출/stream이 소유한다. discovery 실패를 GVK 미등록으로
바꾸는 SDK catch 경로에 자체 예외가 흡수되지 않도록 검증한다.

cache는 client별 TemporaryDirectory의 명시 파일을 쓰고 close 때 제거한다.
lazy discovery 전에 typed SDK 호출만 하는 client에도 discovery를 강제하지 않는다.
`refresh_discovery()` 뒤에는 기존 resource handle도 다음 요청에서 현재
descriptor를 다시 resolve한다. 오래된 scope/plural/verb를 계속 사용하지 않는다.

borrowed ApiClient는 facade가 설정·pool을 변경하거나 닫지 않는다.
동일한 no-retry 동작을 보장하려면 실제 transport의 retry가 비활성화된 공식
SDK client만 받는다. 기본 retry나 확인 불가 custom transport는 factory에서
구성 오류로 거부하고 Configuration.retries=0으로 생성하는 예를 제공한다.
정책을 몰래 바꾸는 것보다 이 조건을 API 명세로 드러낸다.

list/iteration은 scope·selector·limit를 유지하고 token을 `_continue`로 보낸다.
resourceVersion/resourceVersionMatch는 첫 페이지의 옵션이며 continuation
요청에서는 제거하고 token이 고정한 snapshot을 따른다. list metadata의 RV가
바뀌거나 token이 반복되면 오류다. 410에서 새 목록을 섞거나 자동으로 처음부터
재시작하지 않는다. RV는 숫자로 비교·증가시키지 않는다.

## Secret와 편의 기능의 책임

`manifests.py`에는 `namespace_manifest`, `opaque_secret`,
`docker_registry_secret`, `basic_auth_secret`, `service_account_manifest`,
`resource_requirements` 함수를 둔다. helper는 순수 body 생성/검증만 하며
create/apply를 선택하거나 cluster 호출을 하지 않는다.

Secret helper는 평문 `string_data`를 UTF-8 base64로 인코딩해 data만 반환한다.
기존 base64 data와 key가 겹치면 입력 오류다. generic create는 raw stringData를
허용하지만 Secret apply는 stringData를 거부하고 data/helper 사용을 안내한다.
apply가 사용자의 raw manifest를 숨겨진 변환으로 고치지 않는다. 같은 helper
결과를 create/apply에 사용하고 SSA 반복 적용·타 field manager conflict를 검증한다.
credentials·Secret body를 로그나 exception의 추가 메시지에 넣지 않는다.

새 resource requirements는 수량 문자열과 임의 resource key를 받아 공식
`V1ResourceRequirements`를 반환한다. SDK quantity parser로 유한·비음수
값을 검사하고 양쪽에 있는 request > limit은 오류다. extended resource의
세부 제약은 서버 검증도 필요하다. legacy Gi 단위 float·GPU alias·limit 상향
보정은 기존 API에만 남긴다. Namespace의 Istio/project labels는 명시 입력이다.

## write 이후 wait의 대상과 종료

`wait_ready(name, *, expected_uid=None, target_generation=None,
timeout_seconds=120, poll_interval=1.0, cancel_event=None)`를 제공한다.
name-only 호출은 최초 GET의 현재 UID/generation을 기준으로 하는 대기다.
write 결과의 완료를 확인하려면 응답 UID와 generation을 전달한다. 다른 UID는
`ResourceReplacedError`, 다른 target generation은 `ResourceChangedError`다.
동일 UID의 후속 revision을 원래 apply 완료로 합치지 않는다.

generation 기준의 rollout 완료는 Deployment에 제공한다. Pod는 UID와 현재
Ready condition만 보장하며 target_generation 입력을 거부한다. 상태가 특정
Pod spec revision을 관측했는지 추정하지 않는다. `wait_deleted(name, *,
expected_uid, timeout_seconds=120, poll_interval=1.0, cancel_event=None)`는
expected_uid를 필수로 받는다. timeout/poll 값은 양수·유한 값을 요구한다.

첫 구현의 wait는 GET 기반 유한 polling으로 한다. 별도의 generic watch API와
연결하지 않는다. 이 방식은 watch/list 권한이나 410 복구를 필요로 하지 않으며
현재의 readiness 확인 책임에 충분하다. event loss가 허용되지 않는 소비자는
generic watch의 list-RV 방식으로 직접 관리한다. 요청량은 기본 최대 약
1 GET/초/대기이며 이 값은 처리량 측정 결과가 아니다.

| 대상 | 성공·실패 기준 |
| --- | --- |
| Pod | Ready=True, deletionTimestamp 없음. Failed/Succeeded phase는 ready 대기의 terminal failure |
| Deployment | target generation 확인, observedGeneration >= target, updatedReplicas=desired, availableReplicas>=desired, 전체 replicas=desired |
| Deployment 실패 | ProgressDeadlineExceeded 등 명시 진행 실패. replica=0도 controller가 목표 generation을 관측한 뒤 판정 |
| wait_deleted | expected_uid 필수. 해당 이름의 객체 404는 성공(None), 다른 UID는 ResourceReplacedError |

monotonic deadline은 요청 시작·성공 판정의 종료 기준이다. 모든 GET 전 남은
예산을 확인하고 timeout을 남은 시간 이하로 줄인다. 응답 후에도 deadline을
다시 확인해 시간이 지난 Ready를 성공 처리하지 않는다. 취소는 요청 전후와
`Event.wait(min(poll_interval, remaining))`에서 확인한다. retry는 없다.

wait 진입 시 resource descriptor를 유한 기본 timeout으로 resolve한 뒤
deadline을 시작한다. timeout_seconds에는 cold discovery/refresh 시간이
포함되지 않는다. wait는 확정한 descriptor와 namespace를 그 실행 동안
유지한다. generic resource lookup 시간까지 포함하는 절대 실행 제한으로
설명하지 않는다. SDK 직접 호출의 timeout도 facade가 대신 보장하지 않는다.

동기 SDK의 socket timeout은 inactivity/연결 제한이며 DNS·credential plugin과
연속 수신을 포함한 절대 wall-clock 중단을 보장하지 않는다. 따라서
timeout_seconds를 강제 실행 중단 SLA로 문서화하지 않는다. 실행 중 요청의
취소 지연은 해당 transport timeout의 영향을 받는다. background worker를
추가해 강제 종료를 약속하지 않는다. 이 제한과 timeout 후 성공 금지는
fake slow transport와 실제 idle connection으로 검증한다.

generic watch는 기본 300초 유한 server timeout, 명시 connect/read timeout,
정상 EOF와 410/error 구분, context manager cleanup을 제공한다. SDK의 timeout
지정으로 자동 retry를 끄고 raw object/RV를 반환한다. BOOKMARK는 그대로
유지하며 이벤트 경계를 임의로 생성하지 않는다. named watch는 collection에
metadata.name selector를 넣고 사용자의 field selector를 덮어쓰지 않는다.
`stop()`·context exit·iterator close 뒤 SDK Watch와 response를 정리한다.

SDK가 malformed JSON을 무시하는 경우를 그대로 성공 stream으로 노출하지
않도록 작은 strict event parser를 검증한다. SDK Watch의 `unmarshal_event`
확장으로 JSON·event shape 오류를 명시 예외로 내고 raw_object/RV/ERROR 규칙을
유지한다. 이는 SDK 전체 watch 구현을 복사하는 제안이 아니다.

## 기본 사용 예

아래 코드는 구현할 API의 예이며 현재 패키지에서는 실행되지 않는다.

```python
from kubernetes_client import KubernetesClient
from kubernetes_client.manifests import opaque_secret

with KubernetesClient.from_kubeconfig(
    context="dev",
    default_namespace="demo",
    field_manager="example-app",
) as client:
    client.namespaces.apply({
        "apiVersion": "v1",
        "kind": "Namespace",
        "metadata": {"name": "demo"},
    })
    secrets = client.resource("v1", "Secret", namespace="demo")
    secrets.apply(opaque_secret(
        "credentials",
        string_data={"username": "example"},
    ))
    deployments = client.resource(
        "apps/v1", "Deployment", namespace="demo",
    )
    applied = deployments.apply({
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "api"},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": "api"}},
            "template": {
                "metadata": {"labels": {"app": "api"}},
                "spec": {"containers": [{
                    "name": "api", "image": "nginx:1.28.0",
                }]},
            },
        },
    })
    ready = deployments.wait_ready(
        "api",
        expected_uid=applied["metadata"]["uid"],
        target_generation=applied["metadata"]["generation"],
        timeout_seconds=120,
    )
```

예제 이미지는 API 형식 설명용이며 프로젝트의 배포 이미지 권장이 아니다.
실제 integration fixture는 검증한 image digest로 고정한다. bind된 namespace는
write/get/wait/delete에 동일하게 적용되며 apply가 bind를 변경하지 않는다.

## 최신 리소스의 구현·검증 범위

기본 SDK는 조회 당시 stable 36.0.3이다. 37.0.0b1은 별도 preview lane이다.
37 GA를 다시 확인해 지원 범위를 넓힌다. 최신 서버 지원은 discovery와 dict를
사용해 SDK 모델의 유무와 분리하지만 실제 서버 조합을 검증해야 한다.

| 범위 | 우선 검증 대상 | 준비 조건 |
| --- | --- | --- |
| Core/apps/batch | Namespace, Secret, SA, ConfigMap, Pod, Service, PVC, Deployment, Job, CronJob | create/patch/apply/get/list/delete, 같은 동작 규칙 |
| stable group | HPA autoscaling/v2, Ingress networking.k8s.io/v1, EndpointSlice discovery.k8s.io/v1, PDB policy/v1, RBAC, StorageClass, Lease | 각 scope, CRUD verb, admission와 permission |
| DRA stable | ResourceClaim/Template/Slice resource.k8s.io/v1 | discovery·dry-run. driver 없는 allocation을 Ready로 세지 않음 |
| 1.37 최신 stable | ClusterTrustBundle·PodCertificateRequest certificates.k8s.io/v1 | 36 SDK model 없음/37 model 있음; served 상태·권한·유효 manifest 별도 검증 |
| 최신 beta/alpha | Workload/PodGroup scheduling.k8s.io/v1beta1 등 정확한 GVK | 발견된 환경에만 opt-in, feature gate/version 기록 |
| CRD | namespaced/cluster test CRD, irregular plural, multiple served version, unknown nested fields | structural schema·RBAC·cache refresh·404/422/conflict |

최신성 증거로 1.37에 추가된 안정 GVK 하나 이상을 SDK 36 dict 경로로 실제
관리하고 필드 round trip을 검사한다. 기존 DRA 객체나 beta SDK import 성공만으로
이 조건을 충족했다고 하지 않는다. certificates의 승인·서명 같은 subresource
workflow는 generic CRUD 지원과 별도이며 첫 facade의 완료 조건에 넣지 않는다.
버전 근거는 [공식 조회 기록](sources.md)을 따른다.

## 단계별 실행과 완료 조건

단계는 P0→P1→P2, P2 후 P3/P4, 마지막 P5 순서다. 검증 실패를 다음 단계의
성공으로 덮지 않는다. 견적 기간·성능 수치는 측정 근거가 없어 지정하지 않는다.

| 단계 | 실제 수정 파일/작업 | 단계 종료 기준 |
| --- | --- | --- |
| P0 기존 동작/SDK 경계 | tests/test_compatibility.py 보존, characterization tests, wire probe를 회귀 사례로 이관 | 기존 동작 표, public signature, 보정의 실제 transport assertion 고정 |
| P1 인증/수명 | client.py, errors.py, __init__.py; isolated factories·lazy dynamic·owned/borrowed close | 두 host/token/context 격리, 전역 불변, 실패 cleanup, retry=0, cache/pool 종료 검증 |
| P2 공통 resource | resources.py; discovery 보정·namespace·dict·CRUD/SSA/pagination | SDK36/preview37의 wire body/query·오류·refresh·404·snapshot test 통과 |
| P3 manifest/quantities | manifests.py; 순수 helper·Secret data 출력·SDK resource requirements | 입력 불변, create/apply 동일 helper body, Secret conflict·수량 validation 검증 |
| P4 watch/wait | watch.py; strict stream, GET polling, expected UID/generation·deadline·취소 | 잘못된 success 없음, 예외·EOF·취소 cleanup, real idle/stop/finalizer 사례 검증 |
| P5 migration/release | README, docs/migration.md, pyproject/CI; unit/integration/package 지원표 | 필수 lane·필수 사례 통과, 깨끗한 wheel 설치/import, 미검증 조합 명시 |

phase마다 구현·테스트·문서 diff를 함께 검토한다. `base.py`와 `schema.py`의
legacy 동작 수정은 별도 명시적 scope가 생기기 전 이 작업에 섞지 않는다.
시험 도구의 runtime→dev extras 이동은 package 영향 검증과 함께 별도 작은
변경으로 수행하며 formatter나 일반 plugin framework를 도입하지 않는다.

| 단계 | 기획 권장 | 설계 권장 | 구현 권장 | 검증 권장 |
| --- | --- | --- | --- | --- |
| P0 | Astra/high | Astra/high | Sol/medium | Sol/high |
| P1 | 해당 없음 | Astra/high | Sol/high | Astra/high |
| P2 | 해당 없음 | Astra/high | Sol/high | Sol/high |
| P3 | 해당 없음 | Sol/medium | Sol/medium | Sol/high |
| P4 | 해당 없음 | Astra/high | Astra/high | Astra/high |
| P5 | Sol/medium | 해당 없음 | Sol/medium | Sol/high |

Astra=`gpt-6-astra`, Sol=`gpt-5.6-sol`. P2의 state/namespace/SSA 교차 판단과
P5 최종 지원 범위 판정은 Astra/high를 권장한다. 실제 모델·effort는 확인 불가며
이 권장표가 실제 실행값이나 사용자 설정 변경을 뜻하지 않는다.

## 필수 검증과 지원 판정

unit은 fake clock·제어 event·fake transport로 payload·query·scope·반환·실패를
검사한다. 테스트에 namespace 두 곳의 동일 이름, write 이후/최초 GET 이전
UID 교체·generation 증가, timeout 직후 Ready 응답, borrowed retry 설정,
empty JSON Patch, malformed discovery/event, repeated token, stale handle과
client close를 포함한다. 구현에서 계산한 값을 그대로 기대값으로 만들지 않는다.

| lane | 필수 범위 | 실패/미실행 처리 |
| --- | --- | --- |
| unit/package stable | Python 3.10–3.14 × SDK36 baseline/조회 시 최신 stable | 필수 실패는 release 차단; 안정판이 같으면 중복 lane 불필요 |
| preview SDK | 정확한 37.0.0b1 버전 지정, 공통 회귀·보정 test | preview 실패는 해당 조합을 지원표에서 제외하고 별도 기록 |
| server 1.35/1.36/1.37 | 안정 builtin 공통 동작·RBAC·SSA·CRD·삭제 정리 | 선언할 minor의 필수 사례 미실행/실패는 해당 지원 선언 차단 |
| 최신 1.37 | SDK36 generic 경로의 신규 stable GVK·field round trip | 미실행이면 최신 리소스 검증 완료라고 표시하지 않음 |
| gated/외부 addon | discovery된 beta/alpha·설치 CRD의 개별 사례 | skip 이유 기록, required case를 optional skip으로 바꾸지 않음 |

integration은 disposable cluster와 전용 namespace/cluster 객체를 사용한다.
fixture별 생성 이름/UID·최초 상태·cleanup을 추적하고 항상 finally 정리한다.
권한 검증은 허용 계정과 제한 계정을 분리한다. GET만 허용/목록 금지,
discovery 403, SSA 409, schema 422, finalizer 삭제 지연, UID precondition
충돌, transport 중단을 정상 성공과 구분한다. Kind/k3d 등 tool/image 가용성은
구현 시작에 확인하며 없는 최신 minor를 가상 실행 결과로 대체하지 않는다.

release 전에 unittest, 새 API type check, build, `twine check --strict`,
clean environment wheel import를 실행한다. 기존 publish workflow에 required
unit/package 조건을 연결하고 해당 서버 지원을 선언하려면 integration 결과도
필수 증거로 둔다. 전체 조합의 완전 호환을 pyproject 범위만으로 선언하지 않는다.

## 이번 작업에서 검증한 범위

기존 7개 unittest는 Python 3.14.4/Pydantic 2.13.5에서 SDK36.0.3과
37.0.0b1 각각 통과했다. 리뷰의 wire probe도 양쪽 SDK에서 조정자가 재실행해
모든 assertion을 확인했다. 원래 라이브러리·테스트·설정은 변경하지 않았다.
새 facade, live cluster, SSA/CRD/RBAC와 Python 3.10–3.13은 미구현·미실행이다.
리뷰의 설계 판단과 실제 검증을 구분하며 release-ready로 표시하지 않는다.
