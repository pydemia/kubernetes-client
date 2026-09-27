# 근거와 검증 기록

조회일: 2026-09-27 KST. repository 기준: `a3031fa`.
외부 문서는 조회 당시 정보이며 구현 착수·배포 때 다시 확인한다.

## 버전 확인

| 대상 | 확인 결과 | 근거 |
| --- | --- | --- |
| Kubernetes | 1.37.0 stable, 2026-08-26 릴리스 | [공식 releases](https://kubernetes.io/releases/) |
| Python SDK stable | 36.0.3, Python >=3.10 | [PyPI](https://pypi.org/project/kubernetes/36.0.3/), [JSON metadata](https://pypi.org/pypi/kubernetes/json) |
| Python SDK prerelease | 37.0.0b1, 2026-09-24 게시 | [PyPI prerelease](https://pypi.org/project/kubernetes/37.0.0b1/) |
| SDK/서버 대응 | 36 계열→1.36, 37 계열→1.37 | [공식 compatibility matrix](https://github.com/kubernetes-client/python#compatibility) |

PyPI JSON의 release 파일 upload time과 yanked 값을 확인했다.
36.0.3 upload는 `2026-07-13T20:38:10.172959Z`, 37.0.0b1은
`2026-09-24T00:15:16.852513Z`; 둘 다 조회된 파일은 yanked가 아니었다.
최신 서버 버전과 최신 안정 SDK 버전을 하나의 값으로 표시하지 않는다.

## 공식 API와 소스

| 근거 | 이 설계에서 확인하는 내용 |
| --- | --- |
| [DynamicClient v36.0.3](https://github.com/kubernetes-client/python/blob/v36.0.3/kubernetes/base/dynamic/client.py) | discovery, CRUD, SSA, query parameter와 timeout 전달 |
| [Discovery v36.0.3](https://github.com/kubernetes-client/python/blob/v36.0.3/kubernetes/base/dynamic/discovery.py) | host 기반 기본 cache, miss refresh, 정확한 GVK 선택 |
| [Resource v36.0.3](https://github.com/kubernetes-client/python/blob/v36.0.3/kubernetes/base/dynamic/resource.py) | ResourceInstance wire dict와 subresource |
| [Watch v36.0.3](https://github.com/kubernetes-client/python/blob/v36.0.3/kubernetes/base/watch/watch.py) | timeout 지정 시 retry 비활성화, response close/release |
| [ApiClient v36.0.3](https://github.com/kubernetes-client/python/blob/v36.0.3/kubernetes/client/api_client.py) | 모델 wire 직렬화와 close의 범위 |
| [API concepts](https://kubernetes.io/docs/reference/using-api/api-concepts/) | resourceVersion, pagination, watch와 410, request 의미 |
| [Server-Side Apply](https://kubernetes.io/docs/reference/using-api/server-side-apply/) | fieldManager, conflict, omission과 field ownership |
| [Deprecated API migration](https://kubernetes.io/docs/reference/using-api/deprecation-guide/) | 제거된 API를 신규 기본으로 선택하지 않는 기준 |
| [ResourceClaim API](https://kubernetes.io/docs/reference/kubernetes-api/resource/resource-claim-v1/) | DRA stable GVK와 driver에 따른 준비 상태 |
| [Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) | rollout·replica·generation·진행 실패 조건 |
| [Pod lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/) | phase와 Ready condition의 차이 |
| [1.37 변경 기록](https://github.com/kubernetes/kubernetes/blob/v1.37.0/CHANGELOG/CHANGELOG-1.37.md) | certificates GA, scheduling beta 등 실제 최신성 사례 |
| [37 beta generated API 목록](https://github.com/kubernetes-client/python/blob/v37.0.0b1/kubernetes/README.md) | 36 generated API와의 resource route 차이 |

SDK 36.0.3 설치 소스에서 직접 확인한 사항:

- `serialize_body`는 `.to_dict()`를 호출할 수 있다. facade의 공식 모델 입력은
  그 전에 `sanitize_for_serialization`로 wire alias를 만들어야 한다.
- patch의 SDK 기본값은 strategic merge이고 SSA는 apply content type을 강제한다.
- request mapper는 `_continue`, `field_manager`, `force_conflicts`,
  `dry_run`, `_request_timeout`을 처리한다. `field_validation`은 자동
  query 매핑에 없으며 지원하려면 명시적인 `query_params`를 사용해야 한다.
- `LazyDiscoverer.search`는 miss에서 이미 invalidate 후 재검색한다.
  facade가 이를 다시 감싸면 refresh 횟수가 늘어난다.
- `ApiClient.close()`는 thread pool을 닫는다. HTTP pool 정리까지 같은
  메서드로 해결된다고 추정하지 않고 `rest_client.pool_manager` 수명을 검사한다.
- dynamic watch convenience signature에는 `_request_timeout`이 없다.
  직접 `Watch.stream(resource.get, ...)` 구성의 query·response 수명을 검증한다.

37.0.0b1 설치 소스도 대조했다. 이 버전의 generated transport는
`param_serialize`와 `call_api`를 사용하며 `ApiClient.close()`가
`rest_client.close()`를 호출한다. facade가 generated transport 내부 signature를
공통이라고 가정하지 않고 DynamicClient의 public request를 경계로 사용해야 한다.

최신성 사례는 기존 DRA 리소스만으로 충분하지 않다. 두 tagged README의 POST
route 차이와 설치 모델 목록을 대조해 다음을 확인했다.

| GVK | scope | 36.0.3 generated model | 37.0.0b1 generated model |
| --- | --- | --- | --- |
| `certificates.k8s.io/v1 ClusterTrustBundle` | cluster | 없음 | `V1ClusterTrustBundle` 있음 |
| `certificates.k8s.io/v1 PodCertificateRequest` | namespaced | 없음 | `V1PodCertificateRequest` 있음 |

1.37 변경 기록은 PodCertificateRequest의 GA와 기존 beta field 일부 제거,
Workload/PodGroup의 `scheduling.k8s.io/v1beta1` 승격을 설명한다.
실제 served 상태·feature gate·body schema는 해당 cluster에서 별도 검증한다.

이는 소스 관측이며 새 facade를 구현·실행한 결과가 아니다.

## 적용한 skill

Hub 페이지의 렌더링된 본문을 읽었다. GitHub raw source는 404를 반환해
사용하지 못했다. Hub의 개별 skill 표시 revision은 `cbdb600e1eeb`,
홈 catalog 표시 revision은 `0d81b43cb934`였다. 동일 revision이라고 합치지
않는다. 본문과 실제 표시 metadata의 snapshot을 `inputs/skills/`에 보존한다.
Hub를 읽어 적용했으며 전역 skill 설치나 모델 설정 변경은 하지 않았다.

| skill | 적용 범위 |
| --- | --- |
| [software-engineering](https://skills.pydemia.ai/skills/software-engineering) | 저장소 분석, 최소 범위, 사실/제안 구분, 단계별 모델 권장 |
| [pydemia-coding-style](https://skills.pydemia.ai/skills/pydemia-coding-style) | dictionary, design, workflow, markdown references; 책임·상태·한국어 기록 |
| [persona-cross-review](https://skills.pydemia.ai/skills/persona-cross-review) | 고정 입력, 역할별 독립 agent, 반증과 교차 판정, 후속 재검토 |

추천 모델을 실제 적용 모델로 기록하지 않는다. 신뢰할 수 있는 runtime
metadata에 구체적 모델과 effort가 제공되지 않아 실제 설정은 확인 불가다.
동시 실행은 조정자 1명과 reviewer 3명으로 제한한다. reviewer는 입력을
읽기만 하고 자기 보고서에만 쓴다. 1차 판단은 서로의 보고서를 읽지 않는다.

## 실제 실행

Python은 uv가 관리하는 3.14.4를 사용했다. shell의 `python.exe`는 Windows
App Execution Alias이므로 검증에는 `uv run --no-project`를 사용했다.

```powershell
uv run --no-project --python 3.14 --with 'kubernetes==36.0.3' --with 'pydantic==2.13.5' python -m unittest discover -s tests -v
uv run --no-project --python 3.14 --with 'kubernetes==37.0.0b1' --with 'pydantic==2.13.5' python -m unittest discover -s tests -v
```

각각 기존 7개 테스트가 성공했다. 사용 환경은 ephemeral uv environment이며
프로젝트 dependency metadata를 수정하지 않았다. inspect로 설치한 stable
SDK의 dynamic·watch·configuration·ApiClient 소스를 확인했다.

실제 클러스터, RBAC, admission, SSA conflict, CRD, Kubernetes 1.37 신규
resource, Python 3.10–3.13은 이번 실행에서 검증하지 않았다. 문서의 새로운
API는 제안이므로 현재 패키지의 실행 가능한 예제로 표시하지 않는다.

## 리뷰 재현 결과

SDK reviewer가 보존한 [probe](review/sdk-transport-probe.py)를 조정자가
두 환경에서 각각 재실행했다. Python 3.14.4, urllib3 2.8.0,
Pydantic 2.13.5, SDK 36.0.3/37.0.0b1에서 모든 assertion이 성공했다.
이는 실제 클러스터 호출이 아닌 fake HTTP transport의 관측이다.

```powershell
uv run --no-project --python 3.14 --with 'kubernetes==36.0.3' --with 'pydantic==2.13.5' python .worknote/review/sdk-transport-probe.py
uv run --no-project --python 3.14 --with 'kubernetes==37.0.0b1' --with 'pydantic==2.13.5' python .worknote/review/sdk-transport-probe.py
```

관측 결과:

- `field_validation="Strict"`는 wire query에서 빠진다. 명시한
  `query_params=[("fieldValidation", "Strict")]`는 전달된다.
- `DynamicClient.patch(body=[])`는 `{}` body와 strategic content type으로
  바뀐다. `DynamicClient.request` 직접 호출은 `[]`와 JSON Patch를 보존한다.
- 관련 group/version discovery의 503은 두 요청 후 `ResourceNotFoundError`가
  된다. 통신 실패를 unsupported로 판정하지 않는 보정이 필요하다.
- `ResourceInstance.to_dict()`는 관측한 unknown nested field의 null/빈 list를
  유지한다. 이 사례가 모든 schema·서버의 round trip을 증명하지는 않는다.

추가로 조정자가 양쪽 SDK의 `Configuration.retries=0`이 transport에
`Retry(total=0, ...)`로 들어가는 것을 확인했다. 기본 urllib3 retry의 허용
메서드에는 PUT/DELETE가 있다. SDK 36은 rest close가 없고 37은 존재한다.
borrowed client의 실제 retry 설정과 stream 전체 deadline은 별도 조건이다.

v2 후속 검토에서 SDK36의 resourceVersionMatch mapper 부재가 추가로 확인되어
fresh query로 전달하는 v3 보정을 했다. 조정자는 양쪽 SDK의 fake transport에서
`resourceVersionMatch=NotOlderThan`, `resourceVersion=123`이 각각 한 번
전달되고 원래 query list가 변하지 않음을 검사했다. 초기 fake response의
status 누락으로 실패한 probe는 status=200을 명시한 뒤 재실행해 성공했다.
이 실행은 continuation·서버 snapshot 일관성 자체를 검증하지 않는다.

운영 reviewer는 SDK36의 실제 로컬 fault HTTP server에서 PUT 재전송과
chunked watch read timeout의 제한을 확인했다. 구성·관측 결과·미실행 범위는
[운영 보고서](review/validation-operations.md)에 있다. 조정자가 그 fault server를
다시 실행했다는 뜻은 아니다.

## 산출물 검수

문서의 상대 링크는 실제 파일 존재를 확인했고 Python 예제와 보존한 probe는
AST 구문 검사를 통과했다. 예제 구문 성공을 새 API 실행 성공으로 계산하지 않는다.
일반 Markdown의 79자 기준, trailing whitespace, UTF-8/LF를 확인했다.
원본 snapshot의 상대 링크는 원래 문서 위치 기준으로 해석했다.
v1/v2/v3 입력 SHA-256은 리뷰 manifest와 일치하며 최종 계획은 v3와 같다.
리뷰 보고서의 의미는 변경하지 않고 필요한 개행만 LF로 맞췄다.

사용성·운영 reviewer는 v2에서 자신의 설계 지적 해소를 확인했다. SDK reviewer는
v3에서 마지막 query 매핑 지적 해소를 확인했다. 모두 실제 facade·클러스터
검증은 구현 단계에 남겼다. `git diff --exit-code`로 라이브러리·기존 테스트·
패키지 설정·기존 문서·workflow에 변경이 없음을 확인했다.
