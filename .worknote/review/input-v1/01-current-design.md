# 현재 라이브러리의 설계와 사용방식

기준: Git `a3031fa`, `kubernetes-client` 0.9.0.
이는 소스에서 재구성한 설계다. 복구 전 작성자의 설계 의도나 외부 사용처를
확인했다는 뜻은 아니다. 복구 범위는 [RECOVERY.md](../RECOVERY.md)에 있다.

## 공개 진입점과 의존성

`from kubernetes_client import KubernetesManager`가 유일한 최상위 export다.
`base.py`의 클래스가 인증, 리소스 생성·수정, 존재 확인, watch, Secret
내용 생성과 리소스 수량 변환을 함께 담당한다.

| 구성 | 확인한 책임 |
| --- | --- |
| `base.py:49` | `KubernetesManager`, `CoreV1Api` 직접 호출 |
| `schema.py:50,70` | Pydantic `Spec`, `ResourceSpec`과 SDK 수량 직렬화 |
| `enums.py` | Pod·Service·Tekton 등 상태 문자열; API 관리 기능은 아님 |
| `utils.py:4` | service-account 경로 존재 여부로 in-cluster 환경 판별 |
| `kfserving.py` | 빈 파일; KServe/CRD 관리 구현 없음 |
| `tests/test_compatibility.py` | 모델·직렬화·일부 메타데이터 patch·watch 회귀 검증 |

`pyproject.toml`은 Python `>=3.10,<3.15`, SDK `>=36.0.3,<38`,
Pydantic `>=2.13.5,<3`을 지정한다. `mypy`, `coverage`, `pytest-cov`도
runtime dependencies에 들어 있다. 별도 formatter·lint·type-check 실행
설정은 없다. 배포 workflow는 Python 3.14에서 unittest, build,
`twine check --strict`를 수행한다.

## 인증과 연결 수명

생성자 `base.py:129`의 현재 선택 순서는 다음과 같다.

1. truthy `config_dict`: `load_kube_config_from_dict(config_dict)` 호출.
2. `config_file`이 있거나 in-cluster로 판별되지 않으면 kubeconfig 로드.
3. 그 외에는 전달한 `configuration`으로 `ApiClient`를 생성하거나
   in-cluster 설정을 전역으로 로드.

첫 경로는 `context`, `configuration`, `persist_config`를 전달하지 않는다.
둘째 경로는 loader에 `configuration`을 전달하지만 `CoreV1Api()`에는
명시적인 `ApiClient(configuration)`을 전달하지 않는다. 전달한 설정이
실제 요청에 사용된다고 일반적으로 보장할 수 없다. `set_default_config`
(`base.py:59`)는 설정 객체를 반환하며 SDK의 전역 기본값을 설정하지 않는다.
`username`과 `password` 인자는 사용하지 않는다.

`crd_client: CustomObjectsApi`는 annotation만 있고 생성하지 않는다.
연결 종료 메서드나 context manager가 없다. SDK escape hatch는 실제로
생성된 `manager.client`, 즉 `CoreV1Api`뿐이다.

## 리소스별 메서드와 실제 결과

| 작업 | SDK 호출/후속 동작 | 실제 반환 |
| --- | --- | --- |
| `check_ns_exists` | 전체 Namespace 목록의 이름 비교 | `bool` |
| `check_sa_exists`, `check_secret_exists` | namespace 전체 목록의 이름 비교 | `bool` |
| `create_namespace` | create 후 2초 polling, list로 존재 확인, read | `None`; 읽은 객체도 반환하지 않음 |
| `patch_namespace` | read 후 labels/annotations 병합, patch | `V1Namespace` |
| `prepare_namespace` | 존재하면 patch, 없으면 create | SDK Namespace 객체 |
| `prepare_ns_resource_management` | 이름 없는 LimitRange 생성 body | `None`; 실제 서버 수락은 미검증 |
| `create_secret`, `patch_secret` | 해당 SDK 메서드 호출 | `V1Secret` |
| `prepare_secret` | list 기반 분기 후 create 또는 patch | `V1Secret` |
| `create_opaque_secret` | `prepare_secret` 호출 | `V1Secret`; 기존 객체 수정 가능 |
| Docker config/basic auth/image pull Secret | 내용을 만든 뒤 `prepare_secret` | `V1Secret`; 이름 문자열이 아님 |
| ServiceAccount create/patch/prepare | SDK 반환값을 버림 | `None` |
| `watch_pod` | namespaced list watch 후 대상 이름 필터링 | 표준 출력; 이벤트 반환 없음 |
| `build_resource_spec` | Pydantic 모델을 SDK 객체로 직렬화 | `V1ResourceRequirements` |
| base64 encode/decode | UTF-8 문자열 인코딩·디코딩 | `str` |

Secret와 ServiceAccount의 API 오류는 일부 경로에서 `RuntimeError`로
바뀐다. Namespace와 watch는 SDK 예외가 전달된다. `check_*`는 권한이나
네트워크 실패를 `False`로 바꾸지는 않지만 단일 객체 확인에도 list 권한과
전체 목록 조회가 필요하다.

`prepare_*`는 read/list와 write 사이의 경합을 해결하지 않는다.
`create_*`라는 이름이 순수 생성과 upsert를 모두 뜻하며, 생성 성공,
서버 수락, 준비 완료의 의미도 통일되어 있지 않다.

## 메타데이터·Secret·수량 규칙

`patch_namespace`는 기존 labels/annotations를 유지하면서 truthy 입력을
병합한다. `None`과 `{}`는 같은 생략 동작을 한다. 키 삭제를 표현하는
API는 없다. 다른 patch 메서드는 같은 read·merge 절차를 쓰지 않는다.

`prepare_namespace`는 `istio-injection=enabled`와 `runtime/project-id`를
넣는다. 전달한 labels dict도 수정한다. node-selector annotation은
업무별 고정값이며 `use_ns_nodeselector=True`와 `annotations=None` 조합은
계산한 annotation을 body에 적용하지 않는다. 범용 Namespace 관리와 특정
업무의 배포 정책이 섞여 있다.

Secret은 `data`와 `string_data`를 SDK에 넘기며 wrapper가 둘의 충돌을
검증하지 않는다. image pull 경로는 `None` credential도 문자열로 바꾼다.
ServiceAccount secret 참조는 `V1ObjectReference`, image pull 참조는
`V1LocalObjectReference`로 만든다. TokenRequest API는 제공하지 않는다.

`Spec`은 CPU를 core 단위 수치, memory를 Gi 단위 수치, GPU를 NVIDIA
count로 받는다. 수량은 문자열로 직렬화하고 GPU key는 `nvidia.com/gpu`다.
`Spec()`에는 CPU=1, memory=2, GPU=0 기본값이 있지만
`build_resource_spec()`은 명시적으로 `None`을 넣어 빈 requests/limits를
만든다. request보다 작은 limit은 오류 대신 request까지 올리고 원래
`limits` 객체는 변경하지 않는다. 이 동작은 테스트로 고정되어 있다.
임의 resource key나 `500m`, `256Mi` 같은 직접 수량 입력은 지원하지 않는다.

## 기존 사용 예

아래는 현재 API의 사용 예다. 실제 클러스터 실행 결과는 아니다.

```python
from kubernetes_client import KubernetesManager

manager = KubernetesManager(config_file="/path/to/kubeconfig")
namespace = manager.prepare_namespace("demo", project_id=7)
secret = manager.create_opaque_secret(
    "credentials",
    namespace="demo",
    string_data={"username": "example"},
)
manager.prepare_service_account(
    "runner",
    namespace="demo",
    image_pull_secret_names=["registry"],
)
requirements = manager.build_resource_spec(cpu_req=0.5, mem_req=2)
manager.watch_pod("worker", namespace="demo", timeout_seconds=30)
```

Namespace와 Secret는 객체가 나오지만 ServiceAccount는 반환값이 없고 Pod는
출력만 한다. Deployment·Job·Service·ConfigMap·RBAC 등은 wrapper API가
없다. 최신 SDK를 설치하는 것만으로 새 high-level 기능이 생기지는 않는다.

## 검증된 범위와 설계에서 해결할 사항

2026-09-27에 Python 3.14.4, Pydantic 2.13.5에서 기존 unittest 7개를
SDK 36.0.3과 37.0.0b1 각각으로 실행해 모두 통과했다. 인증 생성자,
ServiceAccount 반환, CRD, SSA, 실제 RBAC, 삭제·준비 완료는 이 테스트의
검증 범위 밖이다. Python 3.10–3.13도 이번에는 실행하지 않았다.

설계에서는 인증 인스턴스 격리, 리소스별 동일한 CRUD 규칙, 명시적인
apply·wait, 신규 필드와 CRD 보존, 기존 공개 API 이관 기준을 정한다.
위 기존 문제는 이 문서 작업 중 수정하지 않는다.
