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
| [ResourceClaim API](https://kubernetes.io/docs/reference/kubernetes-api/workload-resources/resource-claim-v1/) | DRA stable GVK와 driver에 따른 준비 상태 |
| [Deployment](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/) | rollout·replica·generation·진행 실패 조건 |
| [Pod lifecycle](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/) | phase와 Ready condition의 차이 |

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
