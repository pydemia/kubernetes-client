# 사용성·migration 독립 리뷰 v1

검토일: 2026-09-27. persona는 새 API 사용과 legacy migration에서 발생할
사용자 실패를 확인하는 reviewer입니다. 다른 reviewer의 결과는 읽지
않았습니다. 코드·테스트·설정은 수정하지 않았습니다.

## 입력과 검사 범위

고정 입력은 `input-v1/`의 16개 파일과 `input-v1.sha256`입니다. SHA-256을
직접 계산했으며 16개 모두 manifest와 일치했습니다. 아래 줄 번호는 현재
작업 트리가 아니라 이 snapshot을 기준으로 합니다.

기준 설계는 `../../04-final-implementation-plan.md`입니다. 읽은 시점의
SHA-256은 다음과 같습니다.

```text
82CF430949B414EE348114E94F98CBB5948143FE8335FE76BDC365EF41DBA7C6
```

`../../inputs/skills/persona-cross-review.txt`의 독립 1차 검토 규칙을
읽었습니다. skill snapshot SHA-256은 다음과 같습니다.

```text
3F91A340FAABC663C5C290D735670251EEB3F331B6E4AC999692A31C9FCBEED1
```

읽은 구현은 `client.py`, `resources.py`, `manifests.py`, `watch.py`,
`errors.py`, `__init__.py`, `base.py`입니다. 두 테스트 파일, `pyproject.toml`,
README도 읽었습니다. `schema.py`, `enums.py`, `utils.py`는 기준 commit과의
내용 비교에 사용했습니다. 실제 모델·effort를 확인할 runtime metadata는
제공되지 않았으며 설정을 변경하지 않았습니다.

namespace 선택, 입력과 반환의 일관성, 객체 부재와 오류의 구별, helper 입력
검증, legacy 보존을 검토했습니다. 원래 README는 갱신 전이며 migration
가이드는 후속 단계라는 조건을 적용했습니다. 그 문서가 아직 없다는 사실과
snapshot의 버전이 0.9.0이라는 사실은 구현 결함으로 세지 않았습니다.

## 채택 제안

### US-01 / P1 — 누락된 name이 단일 객체 요청을 collection 요청으로 바꿉니다

- 유형: 실행으로 확인한 동작 규칙 위반. 첫 공개 release 전 수정 제안입니다.
- 위치: `input-v1/kubernetes_client/resources.py:225–230`, `:243–257`,
  `:336–337`, `:381–408`.
- 실패 조건: 설정 조회 등의 결과가 `None`인 상태에서 `get`, `exists`,
  `patch`, `delete`의 name 인수로 전달합니다. `_request`는 `name is not
  None`인 경우만 검증하므로 `None`이 SDK의 collection path로 전달됩니다.
- 영향: `get(None)`은 목록을 단일 객체처럼 반환하고 `exists(None)`은
  collection GET 성공만으로 True를 반환합니다. `delete(None)`은 collection
  DELETE를 전송합니다. 실제 삭제 여부는 서버와 `deletecollection` RBAC에
  달려 있지만 충분한 권한이 있으면 해당 namespace의 여러 객체를 삭제하는
  요청입니다. name 단일 DELETE라는 설계 규칙을 위반합니다.

실행 증거: snapshot의 `tests/test_interface.py`에 있는 `Wire`를 사용했습니다.
client default namespace는 `team`이며 실제 cluster는 호출하지 않았습니다.
SDK 36.0.3과 37.0.0b1에서 동일한 결과를 확인했습니다.

```text
get(None)     -> GET /api/v1/namespaces/team/configmaps
exists(None)  -> GET /api/v1/namespaces/team/configmaps, True
patch(None, {"data": {"x": "y"}})
              -> PATCH /api/v1/namespaces/team/configmaps
delete(None)  -> DELETE /api/v1/namespaces/team/configmaps
              -> DeleteResult(action='requested', ...)
```

공식 SDK 36.0.3의 설치된 `Resource.path` 소스를 읽어 name이 없으면 base
path를 선택함을 확인했습니다. 같은 SDK의
`CoreV1Api.delete_collection_namespaced_config_map_with_http_info`가 사용하는
endpoint도 `/api/v1/namespaces/{namespace}/configmaps`, `DELETE`입니다.
따라서 단순히 잘못된 URL을 보내는 위험으로만 분류할 수 없습니다. 실제
cluster에서 collection 삭제를 실행한 것은 아닙니다.

반증 검토: 빈 문자열·공백·숫자는 `_request`의 `required_string`에서
거부합니다. apply/replace는 body name을 필수 검사하고 wait도 name을
검사합니다. 이 보호 장치는 단일 요청 method가 `None`을 받는 경우를
막지 못합니다. merge patch body에 metadata.name이 있으면 충돌 검사에
걸리지만 일반적인 partial patch와 JSON Patch에는 그 보호가 없습니다.
기존 22개 테스트에는 named operation의 `None` 사례가 없습니다.

채택 제안: 단일 객체 public method의 진입점에서 name을 검증하십시오.
collection 요청을 수행하는 내부 `_request`에는 name 생략을 계속 허용할
수 있습니다. pass 기준은 `get/exists/patch/delete(None)`이 ValueError를
발생시키고 객체·collection 요청을 보내지 않는 것입니다. 특히 merge/JSON
patch 양쪽과 delete의 기본 옵션을 포함한 회귀 검사가 필요합니다.

조정자 판정: 미판정입니다.

### US-02 / P2 — Secret 이름 문자열이 문자별 참조로 바뀝니다

- 유형: 실행으로 확인한 helper 입력 검증 누락. 첫 공개 release 전 수정
  제안입니다.
- 위치: `input-v1/kubernetes_client/manifests.py:98–102`.
- 실패 조건: `service_account_manifest("worker",
  image_pull_secrets="registry")`처럼 하나의 Secret 이름을 문자열로
  전달하면 문자열을 iterable로 처리합니다.
- 영향: helper가 유효해 보이는 manifest를 반환하므로 API 요청이 성공할
  수 있습니다. 이후 ServiceAccount를 사용하는 Pod에는 원래 `registry`
  Secret 대신 문자 한 개로 된 여러 이름이 전달됩니다. 의도한 인증 정보가
  적용되지 않아 image pull이 실패할 수 있으며 잘못된 참조가 원인임을
  사용 시점에 추적해야 합니다.

실행 증거: 두 SDK 환경에서 순수 helper를 직접 호출했습니다.

```python
service_account_manifest("worker", image_pull_secrets="registry")
# imagePullSecrets:
# [{"name": "r"}, {"name": "e"}, {"name": "g"}, {"name": "i"},
#  {"name": "s"}, {"name": "t"}, {"name": "r"}, {"name": "y"}]
```

반증 검토: 원소에 `required_string`을 적용하지만 각 문자는 정상 문자열이라
검증을 통과합니다. `image_pull_secrets=["registry"]`는 올바른 참조 하나를
생성했습니다. legacy의 `_set_image_pull_secret_refs`는 문자열 입력을
ValueError로 거부합니다. 기존 helper 테스트에는 image pull Secret 입력이
없습니다. 실제 image pull 실패를 cluster에서 실행한 것은 아닙니다.

채택 제안: 문자열·bytes·mapping을 이름 sequence로 받지 않도록 입력을
검증하십시오. 허용할 sequence 종류를 정하고 그 동작을 migration 가이드에
명시하면 충분하며 별도 일반화 계층은 필요하지 않습니다. 문자열 입력은
ValueError를 발생시키고 빈 sequence와 `['registry']`는 각각 빈 참조와
정확한 참조 하나를 반환해야 합니다.

조정자 판정: 미판정입니다.

### US-03 / P2 — bool 옵션의 문자열 값이 요청 범위와 실패 판정을 바꿉니다

- 유형: 실행으로 확인한 입력·오류 일관성 문제. 첫 공개 release 전 수정
  제안입니다.
- 위치: `input-v1/kubernetes_client/resources.py:162–175`, `:381`,
  `:413–415`; watch 전달 경로는 `input-v1/kubernetes_client/watch.py:55–56`.
- 실패 조건: 환경 변수나 설정 파일에서 읽은 문자열 `"false"`를
  `all_namespaces` 또는 `ignore_not_found`에 전달합니다. 타입 검사 없이
  truthiness로 분기하므로 문자열이 True로 취급됩니다.
- 영향: default namespace `team`에서 요청하려던 list/watch가 전체
  namespace collection으로 바뀝니다. 제한된 계정은 불필요한 403을 받고
  넓은 권한의 계정은 의도하지 않은 namespace의 객체도 처리할 수 있습니다.
  `ignore_not_found="false"`는 보존하려던 객체 404를 `already_absent`로
  바꾸므로 호출자가 잘못된 설정과 의도한 오류 무시를 구별할 수 없습니다.

실행 증거: list는 SDK 36.0.3과 37.0.0b1에서 재현했습니다. 아래 watch와
404 delete 비교는 SDK 36.0.3에서 실행했습니다.

```text
list(all_namespaces="false")  -> GET /api/v1/configmaps
list(all_namespaces=False)    -> GET /api/v1/namespaces/team/configmaps
watch(all_namespaces="false") -> GET /api/v1/configmaps, BOOKMARK 반환
delete("demo", ignore_not_found="false")
                             -> DeleteResult('already_absent', None)
delete("demo", ignore_not_found=False)
                             -> ApiRequestError(status=404)
```

반증 검토: explicit namespace bind와 all_namespaces 조합의 충돌 검사는
존재합니다. 객체 미존재 404 분류도 엄격하며 잘못된 namespace/모호한 404를
삼키지 않습니다. 이 지적은 그 보호 장치가 아니라 bool 설정을 잘못 읽었을
때 다른 의미의 정상 요청·정상 결과가 나오는 문제입니다. `apply(force=...)`
와 `automount_service_account_token`에는 이미 bool 타입 검사가 있습니다.

채택 제안: all_namespaces와 ignore_not_found는 bool만 허용하고 그 외 값은
ValueError로 거부하십시오. 문자열을 자동 파싱할 필요는 없습니다.
list/iter_items/watch가 동일한 namespace 검사를 사용하게 유지하십시오.
`False/True`의 기존 동작과 `"false"/0/None`의 거부를 확인하면 됩니다.

조정자 판정: 미판정입니다.

## 확인한 보호 장치와 migration에 남길 규칙

namespace 선택은 explicit bind → body namespace → client default 순서이며
body namespace가 다음 get의 bind를 바꾸지 않습니다. 이 동작은 기존
namespace 테스트로 실행 확인했습니다. cluster resource에 namespace를
넣는 경우와 bind/body 충돌도 테스트가 거부합니다. 이 규칙 자체는 결함으로
세지 않았으며 쓰기 뒤 조회·wait 예제에는 같은 explicit bind를 쓰는 편이
사용자가 namespace를 잘못 선택하는 일을 줄입니다.

legacy의 `base.py`, `schema.py`, `enums.py`, `utils.py`를 설계 기준 commit
`a3031fab6a1608b01d13a856186369db24fbc973`과 비교했습니다. 줄바꿈을
LF로 정규화한 내용은 모두 같았습니다. import 유지와 수량 보정·별칭 등은
compatibility 테스트를 직접 실행해 확인했습니다. 이 검토에서 legacy의
동작 회귀를 발견하지 못했습니다. 알려진 기존 문제를 새 facade의 결함으로
옮기거나 기존 API 수정을 제안하지 않았습니다.

새 API의 wire-key dict 반환, 순수 manifest helper, POST create의 409,
merge/JSON patch와 SSA의 차이, UID/generation을 넘기는 wait는 의도한
설계입니다. migration 가이드는 이를 기존 model 반환, `prepare_*`의
동작, 수량 보정과 비교해야 합니다. 기존 `prepare_namespace/secret`는
create-or-patch이므로 모든 `prepare_*`를 create-only로 설명하면 안 됩니다.
Secret apply의 stringData 거부, borrowed client의 retries=0 조건도 실제
오류와 준비 예제를 함께 설명해야 합니다. 이는 후속 문서 단계의 작성
기준이며 현재 문서 누락 finding이 아닙니다.

## 실행 범위와 미검증

다음 환경에서 snapshot의 22개 unittest를 직접 실행했고 모두 통과했습니다.

```powershell
uv run --no-project --python 3.14 --with kubernetes==36.0.3 `
  --with pydantic==2.13.5 python -m unittest discover -s tests -v
```

US-01, US-02와 US-03의 list 재현은 같은 명령 형식에서 SDK를 각각
36.0.3과 37.0.0b1로 지정해 실행했습니다. fake wire는 snapshot의 테스트
도구를 import해 사용했으며 각 코드가 선택한 method/path와 반환을 직접
관측했습니다. US-03의 watch·delete 비교는 SDK36만 실행했습니다. 이번
reviewer가 SDK37 전체 unittest를 다시 실행한 것은 아닙니다.

실제 API server, collection 삭제, image pull, SSA/RBAC, Python 3.10–3.13,
wheel 설치·패키지 검사는 실행하지 않았습니다. 따라서 실제 파괴적 삭제나
image pull 장애가 발생했다고 주장하지 않습니다. 그 위험은 확인한 request
endpoint와 manifest 출력에 조건을 붙인 해석입니다.

추가로 SDK36 fake response의 Deployment `status.observedGeneration="2"`가
wait에서 `ResponseFormatError` 대신 TypeError를 발생시키는 현상을
확인했습니다(`watch.py:209`). 정상 Kubernetes Deployment 응답이 이
타입을 반환한다는 근거는 없으므로 별도 release 차단 finding으로 올리지
않았습니다. 잘못된 의존 응답에 대한 오류 분류를 강화하는 범위에서 검사할
수 있는 조건부 개선입니다.
