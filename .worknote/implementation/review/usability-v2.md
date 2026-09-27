# 사용성·migration targeted recheck v2

검토일: 2026-09-27. v1의 독립 관측은 `usability-v1.md`에 그대로 유지합니다.
이 문서는 US-01/02/03 수정과 새 사용·migration 가이드의 후속 검사입니다.
다른 reviewer의 결과를 읽지 않았으며 코드·테스트·가이드를 수정하지 않았습니다.

## 입력과 실행 범위

고정 입력은 `input-v2/`와 `input-v2.sha256`입니다. 직접 계산한 SHA-256
26개가 모두 manifest와 일치했습니다. 아래 경로·줄 번호는 v2 snapshot을
기준으로 합니다. 새 입력을 v1과 같은 내용으로 취급하지 않았습니다.

`resources.py`, `manifests.py`, `client.py`, `watch.py`와 해당 interface
회귀 테스트를 읽었습니다. README, `docs/usage.md`, `docs/migration.md`,
`examples/quickstart.py`, `docs/validation.md`, pyproject, MANIFEST와 두 CI
workflow도 확인했습니다. 사용한 review 규칙은 앞서 읽은
`../../inputs/skills/persona-cross-review.txt`이며 모델 설정은 변경하지
않았습니다. 실제 모델·effort를 확인할 runtime metadata는 제공되지 않았습니다.

SDK 36.0.3과 37.0.0b1에서 동일한 targeted probe를 실행했습니다. Python은
3.14, Pydantic은 2.13.5이며 snapshot의 Wire를 사용했습니다. 명령 형식은
다음과 같습니다.

```powershell
uv run --no-project --python 3.14 --with kubernetes==36.0.3 `
  --with pydantic==2.13.5 python -
```

37 lane은 SDK 인수만 `kubernetes==37.0.0b1`로 바꿨습니다. 두 환경에서
아래 회귀 테스트도 직접 실행하여 각각 2개 모두 통과했습니다.

- `InterfaceTests.test_single_object_names_and_boolean_options`
- `ManifestTests.test_pure_helpers_and_secret_encoding`

전체 unittest·socket·integration·package 검사를 이번 reviewer가 다시
실행한 것은 아닙니다. 실제 cluster에서 guide를 실행했다는 내용은 조정자가
제공한 상태이며 이 reviewer의 독립 실행 결과로 세지 않았습니다.

## 기존 finding의 재판정

| ID | v1 중요도 | targeted recheck 판정 |
| --- | --- | --- |
| US-01 | P1 | 해결. invalid name이 collection path로 전달되지 않음 |
| US-02 | P2 | 해결. Secret 이름의 문자열 분해를 거부함 |
| US-03 | P2 | 해결. scope·404 옵션에 실제 bool만 허용함 |

### US-01: 단일 객체 name 검증

`resources.py:323–335`, `:437–447`, `:541–553`의 public named operation은
resolve 전에 `required_string`을 호출합니다. 내부 collection 요청의 name
생략은 유지되어 list와 충돌하지 않습니다.

None, 빈 문자열, 공백, 숫자 1, False를 get/exists/merge patch/JSON patch/
delete에 각각 전달했습니다. SDK별 25개 호출 모두 ValueError였고 cold
discovery를 포함해 wire 요청은 0개였습니다. v1에서 관측했던 collection
DELETE와 잘못된 exists=True가 재현되지 않았습니다.

`docs/usage.md:37–48`은 get을 단일 객체 dict, exists를 단일 GET으로
설명하고 identity의 null/빈 값 거부도 명시합니다. 수정 구현과 일치합니다.
v1의 수정 방향과 pass 기준을 충족하므로 해결 판정을 제안합니다.

### US-02: image pull Secret 입력

`manifests.py:133–139`는 list/tuple만 허용하고 각 이름도 검증합니다.
문자열, bytes, mapping은 두 SDK 환경에서 모두 ValueError였습니다. 빈
list/tuple은 빈 참조를, `['registry']`와 `('registry',)`는 정확히
`[{"name": "registry"}]`를 반환했습니다.

`docs/usage.md:80`은 list/tuple을 명시하고 `docs/migration.md:27–28`은
Secret 이름 목록이며 registry credential을 생성하지 않는다고 설명합니다.
v1에서 우려한 문자별 참조와 문서의 입력 모호함이 제거됐으므로 해결 판정을
제안합니다. 오류 메시지에는 list라고 쓰여 있지만 tuple 허용은 문서와 실행
양쪽에서 확인했습니다. 별도 finding으로 올릴 의미 차이는 아닙니다.

### US-03: bool 옵션

`resources.py:220–222`의 공통 namespace 선택과 `:551–553`의 delete
진입점에서 bool 타입을 검사합니다. 문자열 `"false"`, 숫자 0, None, 빈
list를 list/iter_items/watch의 all_namespaces와 delete의 ignore_not_found에
각각 전달했습니다. SDK별 16개 호출이 모두 ValueError였고 discovery를
미리 완료한 뒤 객체·collection 요청은 0개였습니다.

all_namespaces=False는 `/api/v1/namespaces/team/configmaps`, True는
`/api/v1/configmaps`를 선택했습니다. 확인된 객체 Status 404에서 실제
ignore_not_found=True는 already_absent, False는 ApiRequestError(status=404)를
반환했습니다. 기존 bool 동작도 보존됐습니다.

`docs/usage.md:30–32`는 명시 bind와 전체 namespace의 충돌 및 bool 사용을
설명합니다. v1 실패 조건과 false 문자열의 잘못된 성공이 제거됐으므로
해결 판정을 제안합니다. cold list/watch의 discovery는 입력 검사보다 먼저
진행할 수 있습니다. 객체 요청을 막는다는 관측과 전체 wire 요청이 없다는
관측을 구분했습니다.

## 새 guide에서 확인한 사항

README의 factory·explicit Secret bind·apply/get 예제는 구현 signature와
namespace 선택에 맞습니다. 이미 존재하는 demo namespace가 전제임을
명시하므로 namespace 생성을 생략한 실패로 세지 않았습니다. v1.0.0 표기는
pyproject와 일치합니다. 공개 PyPI 설치 성공은 미검증이며 공개 작업은 아직
완료되지 않았다는 조정자의 상태를 유지합니다.

usage는 SDK model의 None 생략과 dict의 null 보존, POST create와 SSA,
replace의 resourceVersion, response 전체의 apply 재사용 금지, 404 분류,
Secret data 변환과 수량 초과 오류를 구현과 같은 의미로 설명합니다.
wait는 write의 UID·Deployment generation과 name-only의 최초 관측을
구별하며 cold discovery 시간 및 동기 transport timeout의 한계도 명시합니다.
watch의 raw event/RV, selector 합성, 엄격한 framing과 cleanup 설명은 v2
구현에 대응합니다. 이 항목들은 코드·문서 대조이며 이번에 모두 별도 실행한
결과라는 뜻은 아닙니다.

migration은 실제 legacy의 prepare_namespace와 Secret helper가 upsert였음을
분명히 설명하고 새 create의 POST·409와 apply의 ownership을 구별합니다.
legacy의 반환·예외·Gi/GPU 수량 보정을 변경한다고 주장하지 않습니다.

`docs/validation.md`의 unit/server matrix와 publish 선행 검증 설명은 읽은
workflow 구성과 일치합니다. 검증 기록 링크의 대상은 이번 고정 입력 밖에
있으므로 그 문서의 실제 실행 결과는 독립 검증하지 않았습니다. CI 구성은
실행 증거와 구분하며 release tag, PyPI 공개, 공개 후 clean install이 별도
상태라는 설명을 그대로 적용했습니다.

### US-04 / P2 — 최적화 실행에서 quickstart의 Secret 삭제가 생략됩니다

- 유형: 새 guide에서 실행으로 확인한 예제 동작 문제입니다.
- 위치: `examples/quickstart.py:23–37`, 특히 `:32–36`.
- 실패 조건: `python -O examples/quickstart.py ...`로 실행하거나 같은 효과의
  PYTHONOPTIMIZE 설정을 사용합니다. 삭제 호출 자체가 assert 표현식 안에
  있어 Python 최적화가 assert 전체를 제거합니다.
- 영향: 최초 Secret apply 뒤 DELETE 없이 wait_deleted를 호출합니다.
  Secret이 계속 존재하면 기본 120초를 기다린 뒤 timeout이 발생합니다.
  UID를 지정한 삭제·정리 예제라는 README의 작업 순서를 수행하지 않습니다.
  finally의 Namespace 정리는 남아 있으므로 모든 cleanup이 사라진다는
  지적은 아닙니다.

실행 증거: snapshot의 예제 원문을 compile(optimize=0/1)한 뒤 기록용
FakeClient를 넣어 `run`을 실행했습니다. 실제 cluster는 호출하지 않았습니다.
삭제되지 않은 Secret의 wait를 FakeClient가 즉시 실패시켜 호출 순서를
확인했으며 실제 120초 timeout을 측정한 것은 아닙니다.

```text
optimize=0: 성공
namespace.create → secret.apply → secret.get → secret.apply
→ secret.delete → secret.wait_deleted → secret.exists
→ namespace.delete → namespace.wait_deleted

optimize=1: 삭제 생략을 확인하고 fake wait가 실패
namespace.create → secret.apply → secret.wait_deleted
→ namespace.delete → namespace.wait_deleted
```

반증 검토: 정상 Python 실행은 DELETE까지 호출했으며 조정자의 live guide
실행도 이 정상 경로를 검증합니다. 최적화 경로에서는 그 보호가 적용되지
않습니다. Namespace의 finally와 UID precondition은 여전히 유지됩니다.

채택 제안: API 호출을 assert 밖에서 실행하고 반환값만 검증하십시오.
삭제뿐 아니라 조회·반복 apply도 assert 안에 있으므로 같은 방식으로
바꾸면 예제의 의도한 순서가 일정해집니다. normal/optimized compile 양쪽에서
동일한 API 호출 순서가 나오는 것이 pass 기준입니다. 이 개선은 facade 동작을
바꾸지 않는 작은 guide 수정입니다.

조정자 판정: 미판정입니다.

### US-05 / P3 — migration의 namespace field 경로가 한 곳 잘못됐습니다

`docs/migration.md:22`의 `body.namespace`는 구현이 읽는
`body.metadata.namespace`와 다릅니다. `resources.py:223–225`와 usage의
namespace 설명은 metadata 안의 field를 사용합니다. 코드·문서 검사로
확인했으며 추가 서버 실행이 필요한 문제는 아닙니다.

채택 제안: 해당 field 표기만 `body.metadata.namespace`로 바꾸십시오.
다른 namespace 문단과 README 예제에는 같은 오기가 없습니다. 후속
get/wait/delete에서 동일한 namespace를 bind하라는 문장 자체는 정확합니다.

조정자 판정: 미판정입니다.

## 남은 검증 범위

US-01/02/03은 이번 snapshot과 두 SDK의 targeted 실행에서 해결됐습니다.
새 finding은 quickstart 최적화 경로와 migration의 field 표기에 한정합니다.
v1에서 보류한 malformed Deployment status의 TypeError는 이번 수정 대상으로
요청되지 않았으므로 재검증하지 않았습니다.

이 reviewer는 실제 cluster, PyPI 공개·설치, CI 실행, wheel·sdist 검사,
Python 3.10–3.13을 실행하지 않았습니다. 그 범위를 통과 또는 release 완료로
확대해 해석하지 않습니다.
