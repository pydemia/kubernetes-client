# SDK·리소스 통합 독립 1차 리뷰

검토일: 2026-09-27 KST. 범위는 설정에서 실제 `ApiClient`, discovery,
scope·verb, 요청 body·query, 응답까지의 연결이다. 원본 설계·라이브러리는
수정하지 않았다. 다른 reviewer 보고서와 최종 계획은 읽지 않았다.

이 검증 단계에는 `gpt-6-astra / high`를 권장한다. SDK 버전별 transport와
discovery 오류가 공개 API 의미에 미치는 영향을 함께 판단해야 한다.
실제 runtime 모델·effort는 제공된 신뢰 가능한 metadata가 없어 확인 불가다.
설정 변경이나 적용 여부 확인을 위한 대기는 하지 않았다.

## 입력과 실제 읽은 범위

Git HEAD는 `a3031fab6a1608b01d13a856186369db24fbc973`이었다. 고정 입력
`input-v1/01-current-design.md`, `02-interface-design.md`,
`03-implementation-proposal.md`, `sources.md`를 전부 읽었다. SHA-256을
직접 계산했으며 [입력 manifest](README.md)의 네 값과 모두 일치했다.
검토 과정에서는 이 snapshot을 기준으로 줄 번호를 기록한다.

저장소에서는 `kubernetes_client/base.py`, `schema.py`, `__init__.py`,
`tests/test_compatibility.py`, `pyproject.toml`, `README.md`,
`.github/workflows/publish.yml`을 읽었다. 기존 7개 테스트는 모델 및 mock
중심이고 새 인증 경로·dynamic·SSA·CRD를 검증하지 않는다는 문서 설명과
일치한다. 이번 reviewer는 기존 unittest를 다시 실행하지 않았다.

skill은 `.worknote/inputs/skills/persona-cross-review.txt`와
`software-engineering.txt`의 고정 Hub 본문을 읽고 적용했다. 별도 skill
설치·라이브러리 구현은 하지 않았다.

설치된 공식 SDK 소스를 `inspect`로 읽었다. 공통 dynamic 모듈은 설치
패키지의 `kubernetes/dynamic/`에 있지만 upstream repository의 같은
소스는 `kubernetes/base/dynamic/`에 있다. 아래 링크의 `v36.0.3`를
`v37.0.0b1`로 바꿔 beta source를 확인할 수 있다.

| 약칭 | upstream source | 읽은 위치 |
| --- | --- | --- |
| D | [dynamic/client.py](https://github.com/kubernetes-client/python/blob/v36.0.3/kubernetes/base/dynamic/client.py) | 전체 request mapper, CRUD·SSA·watch·body serializer |
| G | [dynamic/discovery.py](https://github.com/kubernetes-client/python/blob/v36.0.3/kubernetes/base/dynamic/discovery.py) | cache 초기화, API group 조회, resource 조회, lazy search·refresh |
| R | [dynamic/resource.py](https://github.com/kubernetes-client/python/blob/v36.0.3/kubernetes/base/dynamic/resource.py) | Resource scope·path, ResourceInstance 생성·dict 변환 |
| A | [client/api_client.py](https://github.com/kubernetes-client/python/blob/v36.0.3/kubernetes/client/api_client.py) | 생성·close·serialization; beta의 call_api signature |
| T | [client/rest.py](https://github.com/kubernetes-client/python/blob/v36.0.3/kubernetes/client/rest.py) | HTTP pool·timeout·body·content type |
| C | [client/configuration.py](https://github.com/kubernetes-client/python/blob/v36.0.3/kubernetes/client/configuration.py) | deepcopy; beta의 변경된 copy 처리 |
| W | [watch/watch.py](https://github.com/kubernetes-client/python/blob/v36.0.3/kubernetes/base/watch/watch.py) | event·timeout retry·close/release 경로 |

공식 [API concepts](https://kubernetes.io/docs/reference/using-api/api-concepts/)
와 [SSA 문서](https://kubernetes.io/docs/reference/using-api/server-side-apply/)
도 열었다. APIResource 전용 문서 URL은 열리지 않아 그 페이지를 근거로
사용하지 않았다. APIResource 필드는 설치한 36.0.3의
`client/models/v1_api_resource.py`의 `openapi_types`에서 확인했다.

## 실행한 검증

Python 3.14.4, urllib3 2.8.0, Pydantic 2.13.5에서 SDK 36.0.3과
37.0.0b1을 각각 설치해 같은 probe를 실행했다. URL은 `unit.invalid`이며
`pool_manager.request`를 fake response로 치환했으므로 클러스터나 외부
서버에 HTTP 요청을 보내지 않았다. 재현 원문은
[sdk-transport-probe.py](sdk-transport-probe.py)에 보존했다.

```powershell
uv run --no-project --python 3.14 --with kubernetes==36.0.3 --with pydantic==2.13.5 python .worknote/review/sdk-transport-probe.py
uv run --no-project --python 3.14 --with kubernetes==37.0.0b1 --with pydantic==2.13.5 python .worknote/review/sdk-transport-probe.py
```

양쪽 모두 `ALL PROBES PASSED`로 종료했다. 이는 SDK의 실제 관측값을
고정한 assertion 성공이다. 새 wrapper가 구현되었거나 그 동작이 올바르다는
결과는 아니다.

| 입력·경로 | 양쪽 SDK에서 관측한 결과 |
| --- | --- |
| `field_validation="Strict"` keyword | 실제 URL에 `fieldValidation` 없음 |
| `query_params=[("fieldValidation", "Strict")]` | 실제 URL에 `fieldValidation=Strict` 있음 |
| `DynamicClient.patch(body=[], ...)` | wire body `{}`, content type strategic merge로 변경 |
| 같은 body를 `DynamicClient.request`에 직접 전달 | wire body `[]`, JSON Patch content type 유지 |
| 정확한 group/version discovery에 503 반복 | 최종 `ResourceNotFoundError`; 503 예외 전달 안 됨 |
| unknown nested field의 `ResourceInstance.to_dict()` | explicit null과 빈 list를 포함한 field 유지 |

discovery 503 probe의 요청 순서는 `/version`, `/apis`, 대상 group/version,
다시 `/version`, `/apis`, 대상 group/version이었다. SDK 자체의 miss refresh가
이미 한 번 실행되었다. 별도 소규모 fake transport 관측에서는 SDK 36.0.3의
처음 `/version`, `/apis` 요청의 urllib3 `timeout` 값이 모두 `None`이었다.

## 지적

### SDK-01 — Discovery 503을 리소스 미제공으로 바꾸는 SDK 경로

중요도: 설계 선결. 유형: upstream 동작과 설계 보장의 불일치.
P0에서 보정 방식을 정하고 P2 구현 전에 회귀 검증해야 한다.

고정 입력: `02-interface-design.md:135–139,188–192`,
`03-implementation-proposal.md:63–75,83`. 설계는 discovery 권한·통신
실패의 원인을 보존하고 5xx를 미존재로 바꾸지 않도록 약속한다.
G 36.0.3 및 37.0.0b1의 156–167행은 group/version discovery의
`ServiceUnavailableError`와 `JSONDecodeError`를 빈 resources로 바꾼다.
이후 lazy search 242–252행과 get 197–216행은 이를 miss로 처리한다.

실패 조건: discovery가 광고하는 `example.com/v1`에 `Widget`를 조회하고
그 group/version endpoint가 계속 503을 반환한다 → SDK가 빈 resource
목록으로 바꾼다 → 한 번 refresh 후 `ResourceNotFoundError`가 발생한다 →
facade가 이를 `ResourceNotServedError`로 치환하면 서버 장애를 API 미제공으로
잘못 보고한다. 양쪽 SDK에서 fake transport로 이 경로를 재현했다.

반증 검토: manifest unknown field 보존, 정확한 GVK, 403 원인 전달, 404
구분과 일반 write 자동 replay 금지는 이 경로를 해결하지 않는다.
`sources.md:44–45`는 refresh 중복을 인지하지만 503 치환은 언급하지 않는다.
`LazyDiscoverer`가 항상 원래 오류를 전달한다고 가정할 수 없다.

최소 수정: 공식 SDK는 유지하되 discovery request가 SDK의 빈 목록 치환에
도달하기 전에 실패를 구분하는 좁은 adapter 책임을 명시한다. 원래 status,
원인 예외와 요청 대상은 보존한다. 이 때문에 얇은 adapter/예외가 필요하다면
근거를 이 SDK 경로로 제한한다. 전체 discovery를 새로 작성하거나 SDK fork를
만들 필요는 없다. SDK miss refresh를 facade에서 다시 반복하지 않는다.

통과 사례: 정상 discovery의 진짜 빈 목록은 미제공 오류, discovery 503은
status=503의 원인 있는 오류, malformed discovery는 형식/응답 오류가 된다.
각각 resource write를 실행하지 않으며 lookup miss refresh는 전체 한 번이다.
객체 GET의 404와 이 실패를 혼동하지 않는다.

### SDK-02 — field validation keyword는 wire query에 전달되지 않음

중요도: 설계 선결. 유형: 문서 간 모순 및 실증된 SDK 요청 규칙 차이.
P2 request 옵션 표를 확정하기 전에 고쳐야 한다.

고정 입력: `02-interface-design.md:181–184`,
`03-implementation-proposal.md:67–71`, `sources.md:41–43`.
구현안은 `field_validation`을 SDK keyword로 매핑한다고 적지만 sources는
명시적 `query_params`가 필요하다고 적는다. D 36.0.3의 216–249행 및
37.0.0b1의 222–259행에는 `field_validation` mapper가 없다.

실패 조건: `create`/`patch`/`apply` 호출에 strict field validation을
요청한다 → facade가 `field_validation="Strict"`만 전달한다 → SDK가
keyword를 wire query에 넣지 않는다 → 호출자가 요청한 unknown field 거부
정책이 서버 기본 정책으로 바뀐다. 실제 서버가 반환할 warning/error는
검증하지 않았으나 옵션 누락 자체는 양쪽 SDK에서 재현했다.

반증 검토: dict body로 최신 field를 보존하거나 서버 schema에 검증을
맡기는 정책은 요청한 `fieldValidation` 값의 전달을 보장하지 않는다.
sources의 올바른 설명은 구현안의 잘못된 매핑 지시를 자동 수정하지 않는다.

최소 수정: 내부 옵션 표에 `field_validation → query_params`의
`("fieldValidation", value)`를 적고 public arbitrary kwargs는 추가하지
않는다. query list는 요청마다 새로 만들어 mapper의 append가 다른 요청으로
누적되지 않게 한다.

통과 사례: Strict/Warn/Ignore 값이 실제 URL에 정확히 한 번 등장하고 생략
시에는 query가 없다. 이를 양쪽 SDK fake transport로 확인한다. 실제 strict
unknown field 400 응답과 Warn warning은 P2 integration에서 별도 검증한다.

### SDK-03 — 빈 JSON Patch가 SDK를 지나면서 mapping으로 바뀜

중요도: 구현 검증. 유형: 공통 patch adapter에서 반드시 보호할 SDK 동작.
P0의 transport 검증과 P2 patch 회귀 기준에 넣어야 한다.

고정 입력: `02-interface-design.md:166–178`,
`03-implementation-proposal.md:68–71,86`. D 양쪽 SDK의 95–103행은
`serialize_body`에서 falsey body를 `{}`로 바꾼다. patch 134–145행이 이
함수를 호출한다. T 36.0.3의 158–163행, 37.0.0b1의 278–287행은 JSON
Patch content type인데 body가 list가 아니면 strategic merge로 바꾼다.

실패 조건: `patch(name, [], patch_type="json")` → facade가 일반
`DynamicClient.patch`를 호출한다 → body가 `{}`로 바뀐다 → REST transport가
content type을 strategic merge로 바꾼다 → 기본 리소스에서는 다른 작업이
요청되고 CRD에서는 지원하지 않는 patch가 전송될 수 있다. wire body와
content type 변화를 양쪽 SDK에서 재현했다.

반증 검토: input을 deep copy하거나 처음에 JSON Patch를 배열로 검사하는
것만으로는 SDK 내부 변경을 막지 못한다. `sources.md:38–39`는 모델 wire
alias 문제를 해결하지만 빈 list 변경을 해결하지 않는다. 아직 facade를
구현하지 않았으므로 이 문제를 현재 라이브러리의 발생한 장애로 보지 않는다.

최소 수정: JSON Patch는 발견된 URL·명시 namespace·검증한 이름으로
`DynamicClient.request`를 호출해 `[]`를 그대로 전달한다. 이 우회는 SDK
`ApiClient` transport와 인증을 계속 사용한다. JSON Patch 배열에는
`metadata.namespace`를 삽입하지 않는다.

통과 사례: 빈 배열은 wire body `[]`, content type JSON Patch이며 사용자
배열은 불변이다. nonempty JSON Patch도 같은 경로를 쓰고 namespaced와
cluster resource를 모두 확인한다. `{}` merge patch와 explicit null field는
각각 원래 형태를 유지한다. probe에서 direct request의 보호 동작을 확인했다.

### SDK-04 — Discovery 요청에는 facade의 timeout을 따로 연결해야 함

중요도: 구현 검증. 유형: 기본 timeout 보장의 빠진 연결 경로.
P1의 SDK adapter와 P4의 deadline 검증에 반영해야 한다.

고정 입력: `02-interface-design.md:183,265–270`,
`03-implementation-proposal.md:47–59,128–139`.
G의 116행, 143행, 164행은 `DynamicClient.request`에
`_request_timeout`을 전달하지 않는다. D는 양쪽 버전 모두 전달받은 값만
실제 ApiClient에 넘긴다. SDK 36.0.3 fake transport의 discovery 초기 두
요청에서 urllib3 timeout=None을 직접 관측했다. beta에도 인자 부재를
소스로 확인했으며 동일 timeout probe는 beta에서 실행하지 않았다.

실패 조건: 첫 resource 조회 또는 miss refresh에서 API server가 discovery
응답을 지연한다 → 실제 객체 get/write 전 discovery가 timeout 없이 기다린다
→ 객체 요청에 connect=5/read=30을 넣어도 public 동작의 기본 제한을
보장하지 못한다. `wait_ready` 내부에서 discovery가 시작되면 대기 deadline도
위반할 수 있다. 실제 지연 서버로 deadline 초과를 재현하지는 않았다.

반증 검토: lazy 초기화는 discovery 권한 요구 시점을 늦추지만 timeout을
설정하지 않는다. 개별 CRUD와 watch에 `_request_timeout`을 넣는 것만으로
초기화·refresh의 request는 제한되지 않는다.

최소 수정: discovery를 포함한 dynamic request 경계에서 기본 timeout을
적용한다. wait의 남은 시간 제한을 이 경로에도 전달할지, discovery를
deadline 시작 전에 해결하고 이를 명시할지 P4 signature/시작 규칙에서
확정한다. SDK generated 직접 호출에는 facade의 timeout을 보장한다고
확대해서 설명하지 않는다.

통과 사례: `/version`, `/apis`, group/version과 miss refresh 모두 실제
transport timeout 값이 유한하다. wait 내부 discovery도 선택한 deadline
규칙을 만족한다. owned/borrowed client의 외부 Configuration을 변경해
기본값을 구현하지 않는다.

### SDK-05 — Discovery의 patch verb만으로 CRD를 구분할 수 없음

중요도: 설계 선결. 유형: 조건부 위험 및 빠진 판별 규칙.
P2 공통 patch signature를 고정하기 전에 처리 범위를 정해야 한다.

고정 입력: `02-interface-design.md:166–168,216–217,275–279`,
`03-implementation-proposal.md:63–75`. 설계는 arbitrary discovered group을
관리하면서 CRD strategic patch를 요청 전에 거부하도록 요구한다. R의
Resource는 이름·scope·verbs 등을 갖지만 CRD 여부나 strategic patch 지원
flag가 없다. 설치한 36.0.3의 `V1APIResource.openapi_types`에도 이런 flag가
없다. G 양쪽의 177–190행은 APIResource 결과로 Resource를 만든다.
공식 API concepts는 CRD의 strategic patch 미지원과 일부 aggregated API
server의 별도 지원을 구분한다.

실패 조건: discovery와 특정 custom resource의 get/patch 권한만 가진
사용자가 strategic patch를 호출한다 → 이름·GVK·`verbs=["patch"]`만으로
CRD 여부를 판단할 수 없다 → group 이름으로 추측하면 오분류하고, CRD 목록
권한을 새로 요구하면 정상 custom resource CRUD까지 불필요한 403에 막힌다.
이 RBAC 실패는 실클러스터에서 실행하지 않았다.

반증 검토: exact GVK, plural·scope discovery와 verb 검사는 strategic
merge 지원 판별이 아니다. `apiextensions.k8s.io` group은 CRD 정의 resource의
group이지 모든 custom resource instance의 group이 아니다. SDK에 model이
없다는 이유만으로 CRD로 분류하면 최신 builtin도 잘못 분류된다.

최소 수정: 기본 공통 patch를 merge/json으로 제한하고 strategic는 공식 SDK
escape hatch로 시작하는 것이 현재 목표를 가장 적게 넓히는 선택이다.
strategic를 유지한다면 지원 여부가 불명일 때의 규칙을 먼저 적고 CRD 목록
권한을 일반 CRUD의 필수 권한으로 추가하지 않는다. 서버 415를 그대로
전달하는 선택은 가능하지만 이 경우 현재의 로컬 거부 약속을 수정해야 한다.

통과 사례: discovery·custom object 권한만으로 merge/json/SSA가 동작한다.
strategic 제외 시 로컬에서 명시적 unsupported 오류가 나며 HTTP 요청은 없다.
유지 시 CRD·최신 builtin·aggregated API를 각각 판별할 근거와 unsupported
응답이 테스트에 드러나야 한다.

## 착수 가능한 범위와 반증으로 제외한 주요 의심

P0 기존 동작 고정과 P1 명시 인증 factory는 착수 가능하다. 전용 Configuration
에 loader를 적용하고 그 객체로 ApiClient를 만드는 경로는 SDK에 있다.
`from_api_client`의 borrowed 수명과 owned 수명을 분리하는 방침도 성립한다.
SDK 36의 `ApiClient.close()`는 async pool만 정리하고 beta는 REST close도
호출하므로 P0/P1에서 버전별 실제 cleanup을 확인해야 한다. 이미
`sources.md:46–47`에 이 차이를 검증할 계획이 있어 별도 지적으로 세지 않았다.

P2의 dict 기반 exact GVK CRUD와 SSA는 위 지적의 보정 범위를 확정한 뒤
구현할 수 있다. SSA를 단일 PATCH로 요청하고 JSON dict를 apply YAML media
type으로 보내는 방식은 양쪽 SDK source와 공식 API 설명에 맞는다. generated
API 메서드명을 조합하거나 SDK 모델을 복제할 필요는 없다.

다음은 지적으로 채택하지 않았다.

- SDK 36에 최신 GVK 모델이 없으면 최신 리소스 관리가 불가능하다는 의심:
  dynamic discovery와 dict body 경로가 해결한다. 서버 feature gate·schema·
  RBAC에 따른 조건을 설계가 이미 명시한다.
- `ResourceInstance.to_dict()`가 모든 unknown field를 버린다는 의심:
  nested null·empty list를 포함한 round trip probe에서 유지됐다. list item에
  kind/apiVersion을 보충하는 SDK 동작은 있지만 현재 설계의 unknown field
  보존을 무효화하지 않는다.
- SSA가 SDK의 body encoder에서 처리되지 않는다는 의심: T 양쪽 버전에서
  JSON-compatible mapping을 apply YAML content type으로 보내는 경로가 있다.
- SDK model `.to_dict()`의 snake_case 문제: 설계의
  `sanitize_for_serialization` 선처리가 해결한다. 모델의 None 생략과 dict
  null 차이도 이미 설명되어 있다.
- whole namespace write, 자동 version fallback, lookup refresh 중복을 설계가
  당연히 허용한다는 의심: 현재 문서는 각각 거부·정확한 GVK·한 번 refresh를
  명시한다. SDK 내부 refresh를 다시 감싸지 않도록 P0 검증은 필요하다.
- sdk escape hatch가 구성상 불가능하다는 의심: 같은 ApiClient를 generated
  Api constructor에 주는 경로가 있다. exec/attach 공유 transport 제한도 이미
  명시되어 있어 별도 구조를 요구하지 않았다.

## 미실행·미확인

실클러스터 인증·exec token 갱신, CA, RBAC, admission, CRD 등록·삭제,
SSA field ownership/conflict, Secret 반복 apply, server schema pruning,
Kubernetes 1.37 신규 resource, workload wait/watch deadline은 실행하지
않았다. API server의 unknown field 보존은 client dict round trip 결과로
증명하지 않는다. Python 3.10–3.13과 build/install 검증도 하지 않았다.
runtime SDK probe 성공을 패키지 전체 버전 호환의 증거로 사용하지 않는다.

이 보고서는 고정 v1의 1차 독립 판단이다. 후속 문서의 채택·수정·반증은
조정자의 판정 기록이나 별도 국소 재검토로 연결해야 한다.
