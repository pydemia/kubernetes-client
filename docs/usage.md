# 사용 가이드

## 인증과 연결 수명

`from_kubeconfig(config_file=None, context=None, persist_config=False)`는 전용
Configuration에 선택한 context를 읽습니다. `from_kubeconfig_dict(config_dict,
context=...)`, `from_incluster()`, `from_configuration(configuration)`도 명시적으로
선택합니다. 전역 기본 설정을 바꾸거나 인증 실패를 다른 경로로 자동 우회하지 않습니다.

factory 옵션은 `default_namespace="default"`, `field_manager="kubernetes-client"`,
`request_timeout=(5.0, 30.0)`입니다. timeout은 connect/read inactivity 제한입니다.
kubeconfig context namespace를 자동으로 기본 namespace에 반영하지 않습니다.

`with` 또는 `close()`가 직접 생성한 ApiClient·HTTP pool·discovery cache와 watch를
정리합니다. close는 idempotent이며 이후 기존 handle도 새 요청을 거부합니다.
discovery는 최초 resource 작업에서 시작하며 client별 임시 cache를 사용합니다.
typed SDK만 사용하면 discovery를 실행하지 않습니다.

외부 ApiClient는 Configuration.retries=0으로 생성한 뒤
`KubernetesClient.from_api_client(api)`에 전달합니다. manager와 이미 생성된 pool의
retry를 검사하며 기본 retry나 확인 불가 transport는 거부합니다. borrowed client의
설정을 바꾸거나 닫지 않습니다. 사용 중 retry 정책도 변경하지 마세요. facade는
429·5xx·disconnect·conflict를 자동 재시도하지 않습니다.

## Namespace와 manifest

namespaced write는 resource bind → body.metadata.namespace → client default
순서로 선택합니다. bind와 body가 다르면 오류입니다. get/delete/wait는 bind 또는
client default를 사용합니다. body namespace는 handle의 상태를 바꾸지 않습니다.
cluster resource에는 bind나 body.metadata.namespace를 줄 수 없으며 None이나 빈 문자열도
거부합니다. 전체 namespace list/watch는 `all_namespaces=True`로 선택하고 명시
bind와 함께 쓰지 않습니다. bool 옵션에는 bool을 전달합니다.

dict를 복사하여 unknown field, null, 빈 목록·mapping을 보존합니다. SDK model은
`ApiClient.sanitize_for_serialization`의 wire alias를 사용합니다. model의 None은
생략될 수 있으므로 field 삭제 patch는 dict를 쓰세요. create/replace/apply의
생략된 GVK는 bind 값으로 채우고 다른 명시 GVK는 거부합니다. name/namespace 등
identity의 null/빈 값은 거부합니다.

| 작업 | 반환·요청 규칙 |
| --- | --- |
| get(name) | 단일 객체 dict |
| exists(name) | 단일 GET. 객체 미존재로 확인된 Status 404만 False |
| list(...) | items/metadata가 있는 한 페이지 dict |
| iter_items(...) | continuation 기반 items iterator |
| create(body) | POST, name 또는 generateName 필요, 409 전파 |
| patch(name, body, patch_type="merge") | merge dict 또는 patch_type="json" 배열 |
| replace(body) | PUT, metadata.name/resourceVersion 필수 |
| apply(body, field_manager=None, force=False) | 단일 SSA PATCH, name 필수 |
| delete(name, ...) | DeleteResult(action, response) |

list/iter_items 옵션은 label_selector, field_selector, limit, continue_token,
resource_version, resource_version_match입니다. RV는 opaque string입니다.
continuation 이후 초기 RV/match를 제거하고 token의 snapshot을 따릅니다. RV 변경,
token 반복, 410에서 종료하며 새 snapshot으로 자동 재시작하지 않습니다.

write의 field_validation은 Strict(기본)/Warn/Ignore, dry_run="All"은 서버
dry-run입니다. merge-patch+json이 기본 patch이며 JSON Patch의 빈 배열도 보존합니다.
strategic merge와 status/scale은 공식 SDK로 호출합니다. replace conflict는 사용자가
최신 객체를 읽어 변경 의도를 판단합니다. SSA force=False가 기본이며 ownership
conflict는 409로 전달합니다. response 전체 대신 의도한 manifest를 apply하세요.

delete는 expected_uid/resource_version precondition, propagation_policy와
grace_period_seconds를 받습니다. requested는 삭제 요청 수락이며 finalizer 완료를
뜻하지 않습니다. ignore_not_found=True의 already_absent도 객체 Status 404에만
적용합니다. namespace 미존재·모호한 proxy 404는 오류입니다. 삭제 완료는 동일 UID의
wait_deleted로 확인합니다.

## Secret와 resource 수량

namespace_manifest, opaque_secret, docker_registry_secret, basic_auth_secret,
service_account_manifest는 순수 dict builder입니다. 네트워크나 upsert를 수행하지
않습니다. Namespace의 Istio·project label은 호출자가 명시합니다.

Secret helper는 string_data를 UTF-8 base64로 인코딩해 data만 반환합니다. 기존 data의
base64를 검증하고 양쪽 key 중복을 거부합니다. 같은 body를 create/apply에 씁니다.
raw create에는 stringData가 가능하지만 Secret apply는 stringData를 거부합니다.
basic_auth_secret(name, username, password)와 docker_registry_secret(name, server,
username, password)의 credential은 None을 거부하고 문자열로 변환합니다.
service_account_manifest의 image_pull_secrets는 이름의 list/tuple입니다.

`resource_requirements(requests={"cpu": "100m"}, limits={"cpu": "1"})`는 공식
V1ResourceRequirements를 반환합니다. 임의 resource key와 quantity 문자열을 받고
유한·비음수 값과 request <= limit를 검증합니다. limit를 자동으로 높이지 않으며
extended resource의 세부 제약은 서버도 검증합니다.

## CRD와 최신 GVK

`client.resource("example.com/v1", "Widget", namespace="demo")`처럼 정확한 GVK를
지정합니다. plural·scope·verb는 discovery에서 읽습니다. irregular plural과 여러
served version도 같은 방식이며 preferred/beta version으로 자동 치환하지 않습니다.
CRD 변경 후 refresh_discovery()를 호출하면 기존 handle도 다음 요청에서 새 descriptor를
찾습니다. 미등록 GVK, discovery 403/503, malformed 응답을 별도 오류로 구분합니다.

dict 경로는 SDK model보다 새 field를 보존합니다. generic CRUD의 성공은 driver
allocation, certificate 승인·서명이나 controller reconciliation 완료를 보장하지
않습니다. alpha/beta는 서버에서 정확한 version을 제공할 때만 명시적으로 선택합니다.

## Watch와 wait

`with resource.watch(...) as stream:` 안에서 iterate합니다. event는 type,
object(dict), resource_version입니다. 기본 server timeout은 300초이며 connect/read
timeout도 적용합니다. name은 collection의 metadata.name selector로 기존
field_selector에 더합니다. BOOKMARK를 보존하고 잘못된 UTF-8·JSON·event shape와
불완전 EOF는 오류입니다. 정상 EOF는 종료이며 410에서 자동 relist/reconnect하지
않습니다. 초기 snapshot은 제공하지 않으므로 list의 metadata.resourceVersion을
watch(resource_version=rv)에 전달하여 이어받습니다.

stop/context exit/iterator.close/client.close가 stream을 정리합니다. 진행 중 I/O를
stop하면 socket 종료에 따른 transport 오류가 나타날 수 있습니다.

wait_ready(name, expected_uid=None, target_generation=None, timeout_seconds=120,
poll_interval=1.0, cancel_event=None)는 GET polling입니다. write 완료 확인에는
응답 UID와 Deployment generation을 전달하세요. name-only는 최초 GET에서 관측한
객체를 기준으로 합니다. 다른 UID는 ResourceReplacedError, 다른 generation은
ResourceChangedError입니다. Pod는 Ready=True와 deletionTimestamp 없음으로 성공하며
Failed/Succeeded는 실패입니다. Pod에는 target_generation을 줄 수 없습니다.
Deployment는 controller의 목표 generation 관측과 updated/available/전체 replicas를
확인하고 이전 generation의 진행 실패를 새 rollout 실패로 세지 않습니다.

wait_deleted(name, expected_uid=...)는 UID가 필수이며 객체 404에서 None을 반환합니다.
같은 이름의 replacement는 완료가 아닙니다. timeout/poll 값은 양수·유한 값입니다.
discovery를 기본 timeout으로 끝낸 뒤 monotonic deadline을 시작합니다. 매 GET timeout을
남은 예산 이하로 줄이고 늦게 도착한 Ready는 성공하지 않습니다. threading.Event의
is_set/wait로 취소를 확인합니다. 동기 socket timeout은 DNS·credential plugin·연속
수신을 포함한 절대 중단 시간을 보장하지 않으며 실행 중 취소도 지연될 수 있습니다.

## SDK와 오류

client.api_client를 공식 CoreV1Api/AppsV1Api 등에 전달하면 typed model·subresource와
SDK 옵션을 쓸 수 있습니다. 직접 호출의 timeout은 호출자가 지정합니다. exec/attach는
SDK stream이 transport를 바꿀 수 있으므로 별도로 소유한 ApiClient를 사용하세요.

ApiRequestError는 status/reason/headers/body와 __cause__에 SDK 근거를 보존하며 자체
메시지는 HTTP status만 포함합니다. Secret body, credential과 SDK traceback을 그대로
로그에 남기지 마세요. transport 오류는 원래 urllib3 오류로 전달합니다. 로컬 입력은
ValueError, discovery/format/unsupported verb, wait timeout/cancel과 UID/generation
변경은 별도 오류입니다. 실패를 False나 빈 결과로 바꾸지 않습니다.
