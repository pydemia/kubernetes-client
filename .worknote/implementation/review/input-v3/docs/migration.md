# KubernetesManager에서 이관

v1.0.0은 기존 KubernetesManager를 유지하면서 KubernetesClient를 추가합니다.
base.py/schema.py의 기존 인증·반환·예외·수량 보정은 변경하지 않습니다.

| 기존 호출·동작 | 새 API에서 명시할 선택 |
| --- | --- |
| check_*_exists의 목록 조회 | resource.exists(name)의 단일 GET. GET/discovery 권한 필요 |
| prepare_namespace의 자동 label·create/patch | namespace_manifest에 label을 넣고 create 또는 apply 선택 |
| create_opaque_secret 등의 prepare 기반 upsert | opaque_secret으로 body 생성 후 secrets.create 또는 secrets.apply |
| service account 작업의 None 반환 | 새 create/patch/apply는 wire dict 반환 |
| model.metadata.name | 새 dict["metadata"]["name"] |
| watch_pod 출력 | with pods.watch(...)의 event를 호출자가 처리 |
| Gi float·GPU alias·limit 상향 | resource_requirements의 quantity string·명시 key·초과 오류 |
| 일부 ApiException의 RuntimeError wrapping | ApiRequestError의 status/body/cause 또는 원래 transport 오류 |

create는 이미 존재하면 409를 발생시키는 POST입니다. 반복 선언에는 apply를 선택하고
field_manager 이름을 workload별로 유지하세요. merge patch는 지정 field만 수정합니다.
apply의 생략 field와 ownership은 기존 read-modify-patch upsert와 다르므로 response
전체를 apply body로 재사용하지 않습니다. force=True는 타 manager의 field를 가져옵니다.

새 factory의 default_namespace와 resource bind를 명시하세요. body.metadata.namespace로 쓴
객체의 후속 get/wait/delete에는 같은 namespace를 bind합니다. cluster resource에는
namespace를 주지 않습니다. kubeconfig context namespace는 자동 적용하지 않습니다.

Secret helper는 string_data를 data로 인코딩하여 SSA에도 같은 body를 씁니다.
custom Secret type은 명시 manifest를 작성합니다. image_pull_secrets는 이름 목록이며
registry credential을 생성하지 않습니다. write 응답 UID와 Deployment generation을
wait_ready에 전달하고 delete에도 UID precondition을 사용한 뒤 같은 UID를 기다립니다.

전역 loader를 사용하던 코드는 factory와 with 블록으로 인증·수명을 명시합니다.
이미 있는 ApiClient는 Configuration.retries=0으로 만들어 from_api_client에 전달하며
외부 소유자가 수명을 관리합니다. 실행 예제는 [quickstart.py](../examples/quickstart.py),
입력·반환·오류와 timeout의 상세 규칙은 [사용 가이드](usage.md)를 따릅니다.
