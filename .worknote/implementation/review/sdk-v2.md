# 공식 SDK·resource 통합 targeted recheck

입력은 `input-v2/`와 `input-v2.sha256`이다. 양 SDK probe에서 모든 파일의
SHA-256이 일치했다. `sdk-v1.md`의 원래 관측과 구분한 후속 재검증이며 다른
reviewer의 보고서는 읽지 않았다. 라이브러리와 고정 입력을 수정하지 않았다.
실제 모델·effort는 확인 불가이며 설정을 변경하지 않았다.

검토 대상은 SDK-I01–I04의 수정, malformed discovery, 실제 existing pool retry,
synthetic와 실제 APIResource의 List suffix 구분, `docs/usage.md`의 SDK 경계다.

## 판정

| 원래 ID | input-v2 판정 | 양 SDK의 실제 실행 결과 |
| --- | --- | --- |
| SDK-I01 P1 | 해결 | core 조회는 무관한 group endpoint를 호출하지 않음 |
| SDK-I02 P1 | 해결 | retry 1인 기존 pool을 wire 요청 전에 거부하며 설정 불변 |
| SDK-I03 P2 | 해결 | synthetic List 거부, 실제 APIResource List suffix 허용 |
| SDK-I04 P2 | 부분 해결 | 원래 사례는 format 오류, 빈 group version은 여전히 미등록 오류 |

CPython 3.14.4, Pydantic 2.13.5, urllib3 2.8.0에서 SDK36.0.3과 37.0.0b1을
각각 실행했다. 고정 입력의 전체 unit 32개는 두 SDK에서 모두 통과했다.
아래 빈 group version 사례는 현재 unit에 없으며 이 reviewer의 probe에서 재현했다.

## SDK-I01 재검증

`input-v2/kubernetes_client/resources.py:179`의 `_resolve`가 apiVersion을
group/version으로 나누고 `prefix="api"` 또는 `"apis"`를 지정한다.

기존 fixture처럼 `/api/v1`은 정상이고 `/apis/apps/v1`은 503인 상태에서
ConfigMap get은 다음 요청만 보내고 성공한다.

```text
/version → /apis → /api/v1
→ /api/v1/namespaces/default/configmaps/demo
```

반대로 실제 요청 대상인 apps/v1 Deployment를 get하면 `/apis/apps/v1`의
503이 그대로 `DiscoveryRequestError(status=503)`로 전달된다. 무관한 endpoint를
검색에서 제외한 수정이며 discovery 오류를 무시하는 회귀는 없다.
이 판정은 실제 SDK를 경유한 제어 HTTPResponse fixture의 실행 결과다.

## SDK-I02 재검증

`input-v2/kubernetes_client/client.py:100`은 manager 기본 retry뿐 아니라
`pool.pools`에 이미 있는 connection pool의 retry도 검사한다.

기존 재현과 동일하게 manager는 Retry(total=0), 실제 pool은 Retry(total=1)로
구성한 공식 ApiClient를 factory에 전달하면 `ConfigurationError`가 발생한다.
PUT·DELETE 각각 wire 요청 수는 0이고 pool retry total은 1로 유지된다.
borrowed 설정을 수정해서 통과시키지 않는다.

retry가 0인 정상 owned 및 borrowed client는 실제 localhost TCP server가 첫
body 수신 뒤 응답 없이 연결을 종료할 때 PUT·DELETE를 각각 한 번만 보낸다.
두 경우 모두 원래 `MaxRetryError`가 전달된다. factory 거부와 no-replay 동작을
구분해 직접 실행했다. 성공한 borrowed facade의 close가 ApiClient를 닫지 않는
동작은 repository unit과 `client.py:256`의 ownership 분기에서 확인했다.

## SDK-I03 재검증

`input-v2/kubernetes_client/resources.py:202`는 공식 `ResourceList` 인스턴스를
명시적으로 제외한다. discovery가 ConfigMap만 제공할 때 synthetic ConfigMapList
get은 `ResourceNotServedError`이며 객체 URL을 호출하지 않는다.

반증용 fixture에서는 ConfigMap의 synthetic ConfigMapList와 별도로
APIResource entry `name="actualconfigmaplists", kind="ConfigMapList"`를 제공했다.
같은 kind 문자열의 두 descriptor가 함께 있어도 실제 APIResource를 선택하여
`/api/v1/namespaces/default/actualconfigmaplists/demo`를 GET했다.
문자열의 List suffix를 일괄 금지하지 않았음을 확인했다.

이는 SDK가 보는 실제 APIResource descriptor와 synthetic descriptor를 구분한
fixture 검증이다. List suffix Kind를 가진 live CRD를 새로 만든 검증은 아니다.

## SDK-I04 재검증과 잔존 조건

`input-v2/kubernetes_client/resources.py:81`의 validator는 root kind,
APIResource name/kind의 빈 문자열, preferredVersion의 필수 field를 추가로
확인한다. 원래 재현의 root kind 누락, 빈 resource kind, 빈 preferredVersion dict는
양 SDK 모두 `DiscoveryFormatError`로 종료했다. 각 response도 닫혔다.

다만 `resources.py:122`와 `resources.py:129`는 group version과 preferred
version의 field가 문자열인지만 확인한다. 빈 version인 아래 `/apis` 응답은
형식 검사를 통과한다.

```json
{
  "kind": "APIGroupList",
  "groups": [{
    "name": "apps",
    "versions": [{"groupVersion": "apps/", "version": ""}],
    "preferredVersion": {"groupVersion": "apps/", "version": ""}
  }]
}
```

실패 조건 → 실행 경로 → 관측 영향은 다음과 같다.

`client.deployments.get("demo")` → validator 통과 → SDK가 빈 version을 cache에
등록 → v1 검색 miss → discovery 한 번 refresh →
`ResourceNotServedError("Resource not served: apps/v1/Deployment")`.

양 SDK에서 `/version`, `/apis`를 각각 두 번 호출하고 grouped resource URL은
호출하지 않았다. response cleanup은 성공했다. 유효하지 않은 discovery와
실제로 GVK가 제공되지 않는 상황의 구분이 아직 깨지므로 SDK-I04는 부분 해결이다.
실제 cluster가 이 응답을 보냈다는 주장은 아니며 malformed response의 분류를
검증한 제어 fixture다.

최소 수정은 group의 versions와 preferredVersion에서 사용하는 groupVersion과
version을 비어 있지 않은 문자열로 검증하고 실패 시 DiscoveryFormatError를
내는 것이다. 광범위한 예외 catch나 미등록 fallback은 필요하지 않다.
동일 입력의 통과 조건은 DiscoveryFormatError, refresh 없음, response 정리다.
문서 `docs/usage.md:93`의 malformed 응답과 미등록 GVK를 구분한다는 설명도
이 사례까지 충족해야 한다. 원래 P2 중요도와 수정 책임은 SDK-I04에 유지한다.

## 사용 문서와 SDK 경계

SDK-I04의 잔존 조건을 제외하면 이번 검토 범위에서 문서와 구현이 일치했다.

- `docs/usage.md:17`: typed SDK만 사용하면 discovery를 실행하지 않는다는
  설명을 직접 실행했다. facade의 ApiClient를 CoreV1Api에 전달해 단일 get을
  호출했을 때 `_dynamic`은 None이고 객체 URL만 호출했다.
- `docs/usage.md:19`: borrowed manager와 existing pool 검사, 설정 보존,
  facade no-retry 설명은 앞의 실제 pool 및 TCP 재검증과 일치한다. 사용 중
  retry 정책을 변경하지 말라는 조건도 문서에 명시되어 있다.
- `docs/usage.md:93`: 정확한 group/version과 synthetic 제외는 SDK-I01/I03
  재검증으로 확인했다. malformed의 빈 group version 사례는 위와 같이 남아 있다.
- `docs/usage.md:131`: typed SDK 직접 호출의 timeout은 호출자 책임이라는
  설명을 직접 실행했다. facade request_timeout=(1, 1)이어도 별도 옵션 없는
  CoreV1Api get의 실제 pool request timeout은 None이었다.
- SDK-I04를 제외한 discovery 503 분류와 owned/borrowed disconnect 예외는
  문서의 별도 discovery 오류 및 원래 urllib3 transport 오류 설명과 일치한다.
- exec/attach에 별도로 소유한 ApiClient를 사용하라는 설명은 같은 ApiClient를
  facade transport 검사 아래 유지하는 구현과 맞는다. exec/attach 호출 자체는
  실행하지 않았다.

## 보존한 실행 근거와 범위

- `sdk-probe-v2.py`: v1 probe를 input-v2에 적용하고 정상 borrowed disconnect,
  실제 APIResource List suffix, typed SDK와 빈 group version 반증을 추가했다.
- `sdk-probe-v2-sdk36.jsonl`, `sdk-probe-v2-sdk37.jsonl`: 해당 버전의 관측값,
  snapshot hash 검사, response cleanup, 실제 wire request count를 보존했다.
- `input-v2/tests/test_interface.py`의 SDK 관련 regression과
  `tests/test_transport.py`를 읽고 전체 32 unit을 양 SDK에서 직접 실행했다.

repository root의 probe 실행 예시는 다음과 같다. SDK37은 버전만 바꾼다.

```powershell
uv run --no-project --python 3.14 --with kubernetes==36.0.3 --with pydantic==2.13.5 python .worknote/implementation/review/sdk-probe-v2.py
```

unit은 `input-v2/`에서 실행했다.

```powershell
uv run --no-project --python 3.14 --with kubernetes==36.0.3 --with pydantic==2.13.5 python -m unittest discover -s tests
```

이 reviewer는 live cluster, 신규 1.37 stable GVK, 실제 CRD·RBAC·SSA ownership,
Python 3.10–3.13, wheel/package validation과 배포를 다시 실행하지 않았다.
조정자가 수행한 lane의 완료 여부와 배포 판정은 별도 실행 기록으로 판단한다.
