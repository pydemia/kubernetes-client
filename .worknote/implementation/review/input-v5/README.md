# kubernetes-client

공식 [kubernetes/python](https://github.com/kubernetes-client/python) SDK에
인증 격리와 공통 리소스 작업을 더한 Python 라이브러리입니다. v1.0.0의
기본 인터페이스는 `KubernetesClient`입니다. 정확한 GVK를 discovery에서 찾고
builtin·CRD 응답을 Kubernetes wire key의 dict로 반환합니다.

```shell
python -m pip install kubernetes-client==1.0.0
```

```python
from kubernetes_client import KubernetesClient
from kubernetes_client.manifests import opaque_secret

with KubernetesClient.from_kubeconfig(
    default_namespace="demo", field_manager="example-app",
) as client:
    secrets = client.resource("v1", "Secret", namespace="demo")
    applied = secrets.apply(opaque_secret(
        "credentials", string_data={"username": "example"},
    ))
    current = secrets.get("credentials")
```

위 예제는 이미 존재하는 `demo` namespace에 Secret을 적용합니다. kubeconfig의
namespace 대신 factory의 `default_namespace`가 기본값을 정합니다.
namespace 생성부터 UID를 지정한 삭제·정리까지 실행하는
[quickstart.py](https://github.com/pydemia/kubernetes-client/blob/v1.0.0/examples/quickstart.py)도 제공합니다.

```shell
python examples/quickstart.py --kubeconfig /path/to/config --namespace wrapper-demo
```

`resource(api_version, kind, namespace=...)`가 정규 진입점입니다.
pods/namespaces/secrets/service_accounts/deployments/services/config_maps/
jobs/cron_jobs는 stable GVK를 지정한 편의 속성입니다. 같은
get/exists/list/iter_items/create/patch/replace/apply/delete/watch를 사용하며
Pod·Deployment에는 GET 기반 wait_ready도 제공합니다.

create는 POST만 보내고 apply는 Server-Side Apply를 보냅니다. 409 conflict를
자동 해결하거나 다른 API version으로 바꾸지 않습니다. write의 기본
field validation은 Strict이며 transport retry는 비활성화합니다.
unknown field를 보존하지만 실제 허용 field·verb·권한은 서버와 CRD가 결정합니다.

- [사용 가이드](https://github.com/pydemia/kubernetes-client/blob/v1.0.0/docs/usage.md): 인증, namespace, CRUD·SSA, Secret, CRD,
  watch·wait, SDK 직접 호출과 오류 처리
- [이관 가이드](https://github.com/pydemia/kubernetes-client/blob/v1.0.0/docs/migration.md): KubernetesManager와 새 API의 동작 차이
- [검증·배포 가이드](https://github.com/pydemia/kubernetes-client/blob/v1.0.0/docs/validation.md): 검증 조합과 재현 명령

기존 `from kubernetes_client import KubernetesManager`는 유지합니다.
기존 모델 반환, prepare 동작, 예외 처리와 resource quantity 보정도 유지합니다.
소스 복구 경위는 [RECOVERY.md](https://github.com/pydemia/kubernetes-client/blob/v1.0.0/RECOVERY.md)에 기록되어 있습니다.
