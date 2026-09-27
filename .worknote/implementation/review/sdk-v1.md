# 공식 SDK·resource 통합 독립 리뷰

입력은 `input-v1/`과 `input-v1.sha256`이다. probe 실행 시 manifest의 모든
SHA-256이 일치했다. 설계 기준은 `.worknote/04-final-implementation-plan.md`다.
다른 reviewer의 보고서는 읽지 않았고 라이브러리와 고정 입력은 수정하지 않았다.

이번 검토는 SDK discovery, 정확한 GVK, namespace, wire payload/query,
pagination, SSA, HTTP 오류, borrowed retry와 SDK별 cleanup에 한정한다.
persona는 통합 개발자의 실패 관점을 뜻하며 전문가 자격을 주장하지 않는다.
실제 모델과 effort는 신뢰할 수 있는 runtime metadata가 없어 확인 불가다.
모델 설정은 변경하지 않았다.

사용한 규칙은 보관된
`.worknote/inputs/skills/persona-cross-review.txt`이며 원문 위치는
[persona-cross-review](https://skills.pydemia.ai/skills/persona-cross-review)다.

## 판정

SDK36.0.3과 37.0.0b1에서 같은 결함 네 건을 재현했다. SDK-I01과 SDK-I02는
출시 전 수정이 필요하다. SDK-I03과 SDK-I04도 고정 설계의 정확한 discovery와
오류 분류 규칙에 맞지 않는다. 기존 22개 unit test는 양 SDK에서 통과하지만
아래 재현 조건은 포함하지 않는다.

| ID | 중요도 | 영향 |
| --- | --- | --- |
| SDK-I01 | P1 | 무관한 group discovery 장애가 core 조회를 차단 |
| SDK-I02 | P1 | borrowed client에서 PUT·DELETE 재전송 허용 |
| SDK-I03 | P2 | SDK synthetic List descriptor를 served GVK로 오인 |
| SDK-I04 | P2 | malformed discovery를 미등록 또는 내부 오류로 분류 |

P1은 정상 작업 또는 명시한 write replay 금지 조건을 깨는 오류이며 P2는
특정 입력에서 공개 GVK·오류 의미가 틀리는 오류다. 이 중요도는 수정 우선순위다.

## SDK-I01 — core 조회가 무관한 API group의 discovery에 의존

- 위치: `input-v1/kubernetes_client/resources.py:137`의
  `dynamic.resources.search(api_version=self.api_version, kind=self.kind)`.
- 유형: SDK 검색 범위와 정확한 GVK 요구의 불일치. 실제 실행으로 재현했다.
- 실패 조건: `/api/v1`은 정상적으로 ConfigMap을 제공하지만 `/apis/apps/v1`이
  HTTP 503을 반환한다. `client.config_maps.get("demo")`가 객체 GET에 도달하지
  못하고 `DiscoveryRequestError(status=503)`를 반환한다.
- 양 SDK의 관측 route:
  `/version` → `/apis` → `/api/v1` → `/apis/apps/v1`.
  실제 ConfigMap URL은 호출하지 않았다. 재현의 apps group은 별도 group의
  실패를 제어하기 위한 fixture이며 실제 cluster 장애를 관측한 주장이 아니다.
- SDK 근거: 양 SDK의 `dynamic/discovery.py:296`
  `LazyDiscoverer.__build_search`는 없는 prefix와 group을 `*`로 바꾼다.
  `__search`의 wildcard 분기는 모든 group/version을 방문한다. 따라서 core
  `api_version="v1"` 검색도 이름이 v1인 grouped endpoint를 요청한다.
- 반증 검토: `resources.py:146`의 `group_version` 일치 검사는 결과를 받은
  뒤에만 실행하므로 무관한 discovery 요청과 그 실패를 막지 못한다.
  discovery 503을 빈 목록으로 바꾸지 않는 보정 자체는 타당하다.
  `test_negative_lookup_refreshes_once_and_stale_handle_refreshes`는 무관한
  group 실패를 제공하지 않아 이 의존성을 발견하지 못한다.
- 최소 수정: core 검색에 `prefix="api"`를 명시하고 grouped 검색에는
  `prefix="apis"`를 명시한다. 버전 fallback이나 discovery 오류 무시는
  추가하지 않는다.
- 통과 조건: 동일한 fixture에서 ConfigMap 객체 GET이 성공하고
  `/apis/apps/v1`은 호출하지 않는다. `apps/v1/Deployment` 요청 자체의 503은
  계속 `DiscoveryRequestError`로 전파되어야 한다.

## SDK-I02 — borrowed transport 검사가 기존 connection pool을 보지 않음

- 위치: `input-v1/kubernetes_client/client.py:66`의
  `pool.connection_pool_kw.get("retries")`.
- 유형: transport 상태 검증 누락. 실제 localhost TCP 연결에서 재현했다.
- 실패 조건: 공식 ApiClient의 manager 기본값은 `Retry(total=0)`이지만
  이미 생성된 해당 host의 `HTTPConnectionPool.retries`는
  `Retry(total=1, read=1, allowed_methods={"PUT"})`인 상태다.
  이 설정은 probe에서 명시적으로 구성했으며 SDK 기본값이라고 주장하지 않는다.
  facade factory와 각 요청의 `_ensure_open` 모두 이 borrowed client를 수용한다.
- 양 SDK의 실행 결과: 서버가 첫 PUT body를 읽은 뒤 응답 없이 연결을 닫자
  동일 replace URL로 PUT을 두 번 보냈고 최종 응답을 정상 반환했다.
  같은 조건의 DELETE도 두 번 보내고 `DeleteResult.action="requested"`였다.
- 비교 실행: owned client에서 실제 pool retry가 0인 경우 동일한 PUT·DELETE
  disconnect는 각각 한 번만 보내고 원래 `MaxRetryError`를 전파했다.
- SDK·transport 근거: SDK `RESTClientObject.request`는 요청마다
  `retries=0`을 전달하지 않는다. urllib3 2.8.0
  `poolmanager.py:425`의 `PoolManager.urlopen`이 선택한 pool에 위임하며
  `connectionpool.py:598`의 `HTTPConnectionPool.urlopen`은 별도 retry 옵션이
  없으면 `self.retries`를 사용한다. manager의 새 pool 생성 기본값만 확인하면
  현재 요청의 실제 retry 정책을 보장할 수 없다.
- 반증 검토: `from_configuration`은 새 pool을 retry 0으로 만들므로 정상적인
  owned factory에는 이 재현이 적용되지 않는다. borrowed 설정을 바꾸거나
  닫지 않는 정책은 유지된다. 기존 `test_borrowed_transport_and_close`는
  manager 기본값만 다르고 이미 만들어진 pool의 설정은 다루지 않는다.
- 최소 수정: borrowed factory가 manager와 실제 pool의 retry 비활성화를
  확인해야 한다. facade가 설정을 몰래 바꾸는 방식은 고정 설계와 충돌한다.
  사용할 host의 pool을 확인하거나 기존 pool을 안전하게 조사하는 방법을
  선택하고 SDK transport의 새 pool 생성 규칙과 함께 검증한다.
- 통과 조건: 이 borrowed fixture를 첫 요청 전에 `ConfigurationError`로
  거부하고 pool 설정과 연결 소유권을 바꾸지 않는다. 실제 retry가 0인 owned와
  borrowed client는 PUT·DELETE disconnect 시 wire 요청 횟수가 각각 1이다.

## SDK-I03 — synthetic ResourceList를 제외하지 못함

- 위치: `input-v1/kubernetes_client/resources.py:145`의 match filter,
  특히 `r.name.endswith("/" + self.kind)` 조건.
- 유형: SDK descriptor 종류와 served GVK의 혼동. 실제 실행으로 재현했다.
- 실패 조건: discovery에는 ConfigMap만 제공하고 ConfigMapList는 제공하지
  않는다. `client.resource("v1", "ConfigMapList").get("demo")`를 호출한다.
- 양 SDK의 관측 결과: `ResourceNotServedError` 대신
  `/api/v1/namespaces/default/configmaps/demo`를 GET하여 성공 dict를 반환한다.
  바인딩한 ConfigMapList와 실제 단일 ConfigMap endpoint가 다르다.
- SDK 근거: `dynamic/discovery.py:156`
  `Discoverer.get_resources_for_api_version`은 모든 Resource에 synthetic
  `ResourceList`를 추가한다. `dynamic/resource.py:226`
  `ResourceList.__getattr__`는 name, path, verbs 등을 base resource에 위임한다.
  따라서 synthetic descriptor의 name은 `configmaps`이고 현재 suffix filter를
  통과한다.
- 반증 검토: group/version와 kind 문자열 일치로는 이 SDK synthetic 객체를
  구분할 수 없다. 필터 앞의 주석은 ResourceList를 선택하지 말라고 설명하지만
  실제 `isinstance` 검사가 없다. 기존 테스트는 List kind를 bind하지 않는다.
- 최소 수정: 공식 `ResourceList` 인스턴스를 명시적으로 제외한다. Kind 문자열의
  `List` suffix만 금지하면 실제 discovery가 제공하는 사용자 정의 Kind까지
  제거할 수 있으므로 descriptor 종류를 기준으로 한다.
- 통과 조건: synthetic ConfigMapList는 객체 request 없이
  `ResourceNotServedError`를 반환한다. 실제 APIResource entry로 제공된
  이름이 List로 끝나는 Kind는 정확한 GVK로 접근할 수 있어야 한다.

## SDK-I04 — malformed discovery의 분류가 일관되지 않음

- 위치: `input-v1/kubernetes_client/resources.py:63`의
  `_validate_discovery` 및 `resources.py:57`의 serializer 호출.
- 유형: 유효하지 않은 응답의 shape 검증 누락. 실제 실행으로 재현했다.
- 실패 조건과 양 SDK의 관측:
  - `/api/v1`이 `{"resources": []}`를 반환한다. 필수 list 검사를 통과한 뒤
    SDK `ResourceInstance`가 root `kind`를 조회하다 `KeyError("kind")`를 낸다.
  - root kind가 `APIResourceList`이고 entry의 kind가 빈 문자열이면 string
    검사에 통과한다. ConfigMap 조회는 discovery를 한 차례 refresh한 뒤
    `ResourceNotServedError`로 끝나며 잘못된 discovery가 미등록으로 바뀐다.
- SDK 근거: 양 SDK `dynamic/resource.py:287`의
  `ResourceInstance.__init__`는 `instance["kind"]`를 바로 읽는다. 현재 facade
  검사는 root kind와 entry name/kind의 비어 있음 여부를 확인하지 않는다.
- 반증 검토: 잘못된 JSON과 resources list 누락은 이미
  `DiscoveryFormatError`를 낸다. raw response는 finally에서 정리된다.
  `test_discovery_errors_are_not_missing_resources`의 `{broken` 사례는 JSON
  decode만 검증하므로 JSON 이후 SDK serializer의 요구 조건은 검증하지 않는다.
- 최소 수정: serializer가 사용하는 root kind를 경로별로 검증하고
  APIResource name/kind와 사용하는 group/version 문자열의 필수 조건을
  명시한다. 모든 예외를 broadly 잡아 미등록으로 치환하지 않는다.
- 통과 조건: 위 두 응답 모두 `DiscoveryFormatError`로 종료하고
  `ResourceNotServedError`, `KeyError` 또는 성공으로 분류하지 않는다.
  오류 후 response 정리와 재시도 가능한 client 상태도 유지한다.

## 실행 근거와 보존 자료

실행 환경은 Windows, CPython 3.14.4, Pydantic 2.13.5, urllib3 2.8.0이다.
공식 PyPI SDK를 정확한 버전으로 uv에 지정했다. 로컬 설치된 소스를 직접 읽었고
실행한 SDK version은 probe 출력에도 기록했다.

- `sdk-probe-v1.py`: 고정 입력을 import하는 재현 코드. 라이브러리 수정 없이
  pool manager request를 fixture로 바꾸거나 localhost HTTP server를 사용한다.
- `sdk-probe-v1-sdk36.jsonl`: 36.0.3 실제 실행 관측값.
- `sdk-probe-v1-sdk37.jsonl`: 37.0.0b1 실제 실행 관측값.
- 각 probe에서 snapshot SHA-256 일치 여부도 다시 검사했다.

SDK source root는 다음 uv cache의 `Lib/site-packages`다.

| SDK | uv archive directory |
| --- | --- |
| 36.0.3 | `C:/Users/pydemia/AppData/Local/uv/cache/archive-v0/zWLTr_6Ac9Shdx44QmYL4` |
| 37.0.0b1 | `C:/Users/pydemia/AppData/Local/uv/cache/archive-v0/51BPr06SNUCUuoJPfuPfV` |

읽은 공식 SDK 범위는 `dynamic/client.py`, `dynamic/discovery.py`,
`dynamic/resource.py`, `client/api_client.py`, `client/rest.py`,
`config/kube_config.py`와 `config/incluster_config.py`의 관련 함수다.
watch의 `Watch.stream`, `stop`, 초기화도 SDK response 소유권을 확인하기 위해
읽었다. urllib3는 `PoolManager.urlopen`과 `HTTPConnectionPool.urlopen`을 읽었다.

고정 입력에서는 `client.py`, `resources.py`, `errors.py`, `watch.py`,
`__init__.py`, `tests/test_interface.py`, README와 pyproject를 읽었다.
legacy compatibility test는 전체 test discovery로 실행했고 legacy 구현은
이번 SDK 통합 지적의 대상으로 삼지 않았다.

재현 명령은 repository root에서 다음과 같다. SDK37에는 버전만
`37.0.0b1`로 바꾼다.

```powershell
uv run --no-project --python 3.14 --with kubernetes==36.0.3 --with pydantic==2.13.5 python .worknote/implementation/review/sdk-probe-v1.py
```

unit 명령은 `input-v1/`에서 실행했다.

```powershell
uv run --no-project --python 3.14 --with kubernetes==36.0.3 --with pydantic==2.13.5 python -m unittest discover -s tests
```

| 검사 | 36.0.3 | 37.0.0b1 | 검증 종류 |
| --- | --- | --- | --- |
| snapshot SHA-256 | 전부 일치 | 전부 일치 | 실제 실행 |
| 기존 22 unit test | 통과 | 통과 | 실제 실행 |
| discovery·synthetic List 재현 | 동일 결함 | 동일 결함 | 실제 SDK + fake HTTPResponse |
| borrowed PUT·DELETE 재전송 | 각각 2회 | 각각 2회 | 실제 TCP/urllib3/SDK transport |
| owned PUT·DELETE disconnect | 각각 1회·MaxRetryError | 각각 1회·MaxRetryError | 실제 TCP/urllib3/SDK transport |

## 확인한 동작과 제외한 의심

다음은 위 결함이 없는 입력에 대해 실행된 unit과 SDK 소스로 확인한 범위다.
실제 API server admission, RBAC나 SSA field ownership 검증을 뜻하지 않는다.

- namespace의 bind/body/default 우선순위, 충돌 거부와 후속 get의 bind 불변,
  cluster resource namespace 거부는 실제 unit으로 확인했다.
- dict의 unknown/null/빈 list와 공식 model wire alias 보존, empty JSON Patch
  `[]`, JSON Patch Content-Type, fieldValidation Strict, SSA fieldManager와
  force=False query는 실제 SDK request를 경유한 unit으로 확인했다.
- pagination continuation에서 selector/limit를 유지하고 첫 페이지의 RV와
  resourceVersionMatch를 제거하는 동작, 반복 token 거부는 실제 unit으로
  확인했다. 410은 ApiException 전파 경로가 있으며 자동 relist는 없다.
  서버 410 응답을 가진 pagination은 이 reviewer가 별도 실행하지 않았다.
- 객체 404에만 exists=False와 already_absent를 반환하고 namespace 404와
  모호한 404는 보존하는 동작을 실제 unit으로 확인했다.
- discovery 503과 broken JSON 보정은 동작하며 정당한 failure를 숨기지 않는다.
  SDK-I01은 이 보정을 제거하는 요청이 아니다.
- refresh 후 오래된 handle이 plural을 다시 resolve하며 negative lookup은
  SDK의 한 번 refresh를 사용한다. cold discovery timeout 전달도 unit의
  실제 SDK transport argument로 확인했다.
- SDK36 `ApiClient.close`는 async pool만 정리하고 SDK37은 rest close까지
  호출한다. facade의 SDK36 clear 보정, owned cache 삭제, borrowed close 보존은
  소스와 실제 unit 결과가 일치했다.
- kubeconfig·in-cluster refresh hook의 deepcopy가 token을 잘못된 Configuration에
  쓰는 의심은 제외했다. SDK hook은 호출 시 받은 client_configuration에
  `_set_config`를 적용한다. 실제 exec/OIDC token refresh는 실행하지 않았다.
- preferredVersion이 빈 dict인 discovery도 현재 validator를 통과하지만
  정확한 version 조회 자체는 실행 성공했다. 이 관측은 별도 결함으로 세지 않았다.

신규 Kubernetes 1.37 stable GVK, 실제 CRD·RBAC·SSA ownership, live cluster,
Python 3.10–3.13, wheel/package validation은 이 reviewer가 실행하지 않았다.
watch의 cross-thread stop과 finalizer cleanup도 여기서는 완료로 판정하지 않는다.
동일 모델 agent들의 동의나 SDK import 성공을 이 미검증 범위의 증거로 삼지 않는다.
