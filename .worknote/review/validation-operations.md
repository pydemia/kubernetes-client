# 검증·운영 독립 1차 리뷰

검토일: 2026-09-27 KST. 기준 Git은
`a3031fab6a1608b01d13a856186369db24fbc973`이다. 검토 중 HEAD가 이 기준과
일치함을 확인했다. 고정 입력 v1만 읽었으며 다른 reviewer의 보고서와 최종
구현계획은 읽지 않았다. 원본 문서와 라이브러리를 수정하지 않았다.

이 관점의 권장은 gpt-6-astra / high다. SDK transport와 watch, 객체 수명의
조합을 확인해야 하기 때문이다. 실제 runtime 모델과 effort는 확인 불가다.

## 입력과 읽은 범위

아래 파일의 본문을 읽고 SHA-256이 review manifest와 일치함을 확인했다.
위치 표기는 `input-v1/`에 보존된 원문의 행 번호다.

| 입력 | SHA-256 |
| --- | --- |
| `01-current-design.md` | `229F05B9C9D7722636F94493C532A84D0EFE40755E1819C94CD9A503DD8CA227` |
| `02-interface-design.md` | `F5D79E6C123F717BAA3A0A68951B9A6FB0BC4ADB7DBF90C8482243858525D486` |
| `03-implementation-proposal.md` | `7E7F9C488D4220A9D3B114FDA4B33EA0F3219118FBBFAC7044DAA910AD427938` |
| `sources.md` | `E4D2331AE7BF89CE8250677B6CEA0622379F42C04245A8F95C9D8A4FD4CB8788` |

Skill은 `inputs/skills/persona-cross-review.txt`와
`inputs/skills/software-engineering.txt`를 읽었다. 저장소에서는
`kubernetes_client/base.py:49–306,542–655`,
`tests/test_compatibility.py:1–162`, `pyproject.toml:1–28`,
`.github/workflows/publish.yml:1–76`을 대조했다. README와 RECOVERY는 보조
자료로 확인했으며 외부 소비자의 실제 사용법은 검증하지 않았다.

SDK 주장은 uv의 독립 환경에 설치된 `kubernetes==36.0.3` 소스와 실제
호출로 확인했다. Python은 3.14.4, 함께 설치된 urllib3는 2.8.0,
Pydantic은 2.13.5였다. SDK 소스는 설치 패키지의 `kubernetes/` 기준 경로로
표기하고 동일 release의 공식 source 링크를 붙였다.

## OPS-01 — 전체 deadline과 취소 보장의 실행 범위를 결정해야 한다

분류: **설계 선결**. 유형: 빠진 동작 규칙과 실증 필요.
P0에서 결정하고 P4 완료 판정에 반영해야 한다. P1–P3 전체를 막는 지적은
아니다.

근거는 `02-interface-design.md:183,252–271`과
`03-implementation-proposal.md:123–140`이다. 문서는 monotonic deadline으로
network/stream 시간까지 제한한다고 쓰면서 background thread는 필요 없다고
정한다(`02:70–71`). 그러나 유한 `timeout_seconds`와
`_request_timeout=(connect, read)`만으로 이 보장은 성립하지 않는다.

SDK 36.0.3의
[Watch.stream](https://github.com/kubernetes-client/python/blob/v36.0.3/kubernetes/base/watch/watch.py#L151)
193–245행에서 `timeout_seconds`는 자동 재연결 여부를 바꾸는 조건이다.
stream은 `iter_resp_lines`와 HTTP response read에 머문다. 47–76행의 parser는
줄바꿈이 도착해야 이벤트를 반환한다.
[RESTClientObject.request](https://github.com/kubernetes-client/python/blob/v36.0.3/kubernetes/client/rest.py#L108)
145–148행은 tuple을 connect/read timeout으로 바꾼다. urllib3의
[Timeout 명세](https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html#urllib3.util.Timeout)는
read/total timeout이 응답 전체의 wall-clock 시간이 아니라 연속 read 사이의
시간을 제한한다고 설명하며 DNS resolver의 별도 제약도 명시한다.

실패 조건은 다음과 같다. 서버 또는 중간 proxy가 read timeout보다 자주 작은
chunk를 보내고 줄바꿈을 지연한다 → 동기 `next(stream)`이 반환하지 않는다 →
caller의 monotonic deadline 검사가 실행되지 않아 목표 시간이 지난 후에도
대기가 지속된다. 로컬 chunked HTTP server로 SDK Watch와 REST를 실제 호출해
connect=50ms/read=80ms에서 첫 BOOKMARK까지 305ms가 걸리는 것을 확인했다.
이는 새 facade의 실패를 실행한 결과가 아니라 SDK timeout의 범위를 재현한
결과다.

첫 lazy discovery도 별도 경로다. SDK
[discovery.py](https://github.com/kubernetes-client/python/blob/v36.0.3/kubernetes/base/dynamic/discovery.py)
116,143,164행은 `/apis`, `/version`, group discovery를
`_request_timeout` 없이 호출한다. CRUD 호출에만 tuple을 넣으면 첫 리소스
선택과 refresh는 기본 5초/30초 규칙 밖에 남는다. 입력 설계의 namespace나
UID 검사로는 이 blocking 구간을 제한할 수 없다.

반증 검토: 유한 watch timeout과 남은 시간 안에서만 새 요청을 시작하는 규칙은
정상 API server와 이벤트가 반환되는 구간을 제어한다. P4의 이벤트 없는 read
timeout과 실클러스터 연결 중단 검증도 적절하다. 다만 이는 byte trickle,
discovery, DNS·credential 처리까지 포함한 절대 종료 보장의 증거가 아니다.
SDK 36.0.3 `Watch.stop` 87–102행에는 열린 socket의 shutdown 경로가 있지만
deadline을 검사하는 주체가 blocking read와 같은 thread라면 이 메서드까지
실행할 수 없다. 외부 취소 입력과 취소 확인 시점도 공개 API에서 정하지 않았다.

최소 수정은 공개 보장의 범위를 먼저 정하는 것이다. 동기 SDK 범위를 유지하면
이를 협조적 deadline으로 명시하고 초기 discovery·GET·다음 watch마다 남은
시간을 반영해야 한다. 절대 wall-clock 종료를 유지하려면 blocking 작업을
중단할 주체와 response 소유권을 P0에서 실증하고 background thread 제외
범위를 수정해야 한다. 취소가 KeyboardInterrupt/caller 예외만 뜻하는지,
별도 cancel 입력을 제공하는지도 정해야 한다. 구현 전인 기능을 취소 지원
완료로 표시하지 않는다.

판정 사례는 silent response, 줄바꿈 없는 trickle, discovery 지연, 최초 GET
지연, credential 갱신 지연, deadline 직전의 정상 이벤트다. 선택한 시간 보장에
맞게 종료 상태와 cleanup을 검증하고 지원하지 않는 blocking 범위는 명시한다.
fake clock으로 분기만 통과한 결과를 network 시간 보장의 통과로 계산하지
않는다. 실클러스터 watch 테스트 외에 로컬 fault server 검증을 남겨야 한다.

## OPS-02 — SDK transport의 PUT/DELETE retry가 현재 쓰기 규칙과 충돌한다

분류: **설계 선결**. 유형: SDK 동작과 제안 보장의 불일치.
P0 transport 표와 P1 연결 정책에서 결정해야 한다.

`02-interface-design.md:192`는 write 자동 retry가 없다고 정한다.
`03-implementation-proposal.md:67–75,85`도 단일 write 호출과 conflict
비재시도를 계획한다. 그러나 factory가 SDK 기본 Configuration을 사용하거나
호출자의 retry 설정을 복사하면 HTTP 재전송은 별도로 발생한다.

SDK 36.0.3
[rest.py](https://github.com/kubernetes-client/python/blob/v36.0.3/kubernetes/client/rest.py#L65)
69–70행은 `Configuration.retries`가 주어졌을 때만 pool 옵션을 넣는다.
기본값은 None이다. 설치한 urllib3 2.8.0의 실제 connection pool에서
`Retry(total=3)`와 allowed methods `DELETE, GET, HEAD, OPTIONS, PUT, TRACE`를
확인했다. Retry.increment에 read timeout을 주면 PUT/DELETE는 retry 예산을
감소시키고 PATCH는 해당 read timeout을 그대로 낸다. 이는 SDK source 관측뿐
아니라 로컬 HTTP 실행으로도 확인했다.

재현 조건은 payload를 읽은 HTTP server가 첫 세 번의 PUT 연결을 응답 전에
닫고 네 번째에 200을 반환하는 것이다. SDK의 기본 `ApiClient.call_api`를
한 번 호출했는데 server는 동일 payload 네 개를 받았고 caller는
`{'ok': True}`를 반환받았다. 읽기와 쓰기 경합을 해결하는 SSA·RV·UID
precondition은 이미 수락된 작업의 transport 재전송 횟수를 제한하지 않는다.
특히 `replace` 또는 `delete`가 응답 유실 후 자동 재전송되면 caller가 단일
요청으로 이해한 상태와 서버의 관측 횟수가 달라진다.

반증 검토: wrapper 수준의 write loop가 없고 409에서 apply/force로 바꾸지
않는 설계는 유효하다. 유한 watch timeout은 Watch 자체의 재연결을 막는다.
그러나 둘 다 urllib3의 request retry 정책을 바꾸지 않는다. `sources.md:46–49`의
pool 수명·watch timeout 조사도 retry 설정을 확정하지는 않았다.

최소 수정은 wrapper의 한 번 호출과 transport 재전송을 구분해 문구를 바꾸거나
owned ApiClient에서 transport retries를 명시적으로 비활성화하는 것이다.
borrowed ApiClient는 기존 pool 정책을 변경하지 않는다는 수명 규칙이 있으므로
그 경로의 보장 범위 또는 필요한 입력 조건을 별도로 정한다. 전역 설정이나
다른 client의 pool을 수정하는 해결은 쓰지 않는다.

검증 기대 결과: 수정된 owned client로 같은 PUT fault server를 호출하면
서버의 수신 횟수가 한 번이고 통신 실패가 반환되어야 한다. DELETE에도 같은
검증을 적용한다. borrowed connection의 retry 값이 그대로 남는지 확인하고
문서가 그 동작과 일치해야 한다. 단순히 mock SDK 메서드의 call_count가 1인
것을 transport의 단일 전송 증거로 삼지 않는다.

## OPS-03 — 삭제 요청 대상 UID를 wait_deleted에 연결하는 규칙이 필요하다

분류: **설계 선결**. 유형: 빠진 입출력 규칙.
P0 공개 signature와 P4 상태 표에서 결정해야 하며 CRUD 착수는 가능하다.

`02-interface-design.md:160–163`의 DeleteResult는 action과 response만
정한다. `02:265–268`은 최초 GET에서 UID를 얻고 `wait_deleted`도 UID 기준으로
삭제 완료와 이름 재사용을 구분한다고 설명한다.
`03-implementation-proposal.md:128–136`은 watch 중 삭제·재생성을 검사하지만
delete 응답과 wait의 최초 GET 사이에서 이름이 재사용되는 사례는 없다.
공개 메서드 표에는 `wait_deleted` signature도 없다.

구체적인 조건은 UID A의 객체를 delete한 후 A가 사라지고 같은 namespace/name의
UID B가 생성되는 것이다. 이때 이름만 받은 wait가 최초 GET으로 B를 읽으면
B를 자기 대기 대상이라고 고정할 수 있다. 이후 UID 비교가 모두 맞더라도
이미 삭제된 A의 완료를 확인하는 대신 B가 사라질 때까지 기다리거나 timeout을
낸다. 아직 facade 구현이 없으므로 이 결과는 설계에서 가능한 경로이며 실행한
버그로 표시하지 않는다.

대조한 source는 기준 Git `kubernetes_client/base.py:202–229`와
`tests/test_compatibility.py:86–121`이다. 현재 코드에는 delete/wait_deleted가
없고 legacy watch 테스트도 최초 UID를 다루지 않는다. Kubernetes의
[object identity 문서](https://kubernetes.io/docs/concepts/overview/working-with-objects/names/#uids)는
UID가 삭제·재생성된 같은 이름의 객체를 구분하는 식별자라고 설명한다.

반증 검토: delete의 UID/RV precondition은 잘못된 객체를 삭제하지 않게 하고
watch 시작 후 UID 교체를 거부하는 규칙도 유효하다. 두 보호 장치 모두 delete와
최초 wait GET 사이에 이미 발생한 교체를 식별하려면 원래 UID 입력이 필요하다.
최초 GET의 UID를 보존하는 것만으로는 원래 A와 B를 구분할 수 없다.

최소 수정은 호출자가 기존 read/apply 결과의 UID를 전달하는 `expected_uid`
입력을 정의하거나 DeleteResult와 명시적인 target을 연결하는 것이다.
UID를 생략하면 대기를 시작할 때 조회한 객체를 대상으로 한다는 별도 의미를
정한다. 최초 404, 최초 UID 불일치, target UID의 DELETED, finalizer가 남은
동일 UID, 403/410을 결과·오류 표에 적는다. 이름 재사용을 발견했을 때 원래
객체의 소멸과 대체 객체의 존재를 어떻게 반환할지도 정해야 한다.

검증 기대 결과: A 삭제 → B 생성 → wait 시작 순서를 barrier 또는 fake
transport로 고정한다. expected_uid=A인 wait는 B의 삭제를 기다리지 않고
정한 replacement 결과·오류를 반환해야 한다. 최종 snapshot에서 B가 여전히
존재하더라도 새 객체의 성공이나 새 객체 삭제로 바뀌면 안 된다. 처음부터 A가
없던 경우도 권한 실패와 구분해 검증한다.

## 착수 가능한 범위와 구현 검증으로 남긴 항목

명시 factory, 설정 격리, namespace 선택, generic CRUD·SSA, dict 보존,
Secret helper와 legacy 보존 방향은 이 관점에서 착수할 수 있다. 위 지적은
보장 문구와 실제 transport/UID 경로를 맞추는 작업이다. controller,
무손실 watch 재연결이나 일괄 rollback을 추가로 요구하지 않는다.

| 범위 | 입력에 이미 있는 보호 장치 | 구현에서 확인할 결과 |
| --- | --- | --- |
| RBAC·discovery | `02:135–139,188–192`, `03:73–75`의 실패 보존 | 단일 GET 권한만 있는 계정의 exists, watch 403, discovery 403이 False/빈 결과가 아님 |
| 410 | `02:256–270`의 오류 종료와 자동 relist 제외 | HTTP 410과 ERROR 410이 각각 종료하고 stream close/release; caller의 새 조회가 별도 동작임 |
| namespace | `02:123–133`의 scope·sentinel 규칙 | cluster-scope write에 namespace 오류 시 전송 없음; default, body, bind와 all_namespaces의 조합 |
| pagination | `02:151–152`, `03:89`의 selector/RV 보존 | items가 빈 페이지여도 continue가 있으면 다음 조회; 마지막 token 공백 종료; 만료 410은 중간 성공 목록으로 숨기지 않음 |
| connection cleanup | `02:96–98`, `03:52–59`의 소유권·실패 정리 | ApiClient.close는 thread pool만 닫으므로 owned HTTP pool도 실제 종료; borrowed pool 보존; caller 예외·iterator 조기 종료·ERROR 종료의 response 반환 |
| readiness | `02:260–271`, `03:133–140`의 generation·UID·실패 구분 | Ready Unknown, replica=0, observedGeneration 지연, ProgressDeadlineExceeded, deletion/recreation에서 성공을 잘못 내지 않음 |
| 최신 리소스 | `02:24–42,281–284`, `03:99–104`의 discovery·dict 경로 | 최신 서버의 실제 served GVK/schema와 payload를 기록; 새 필드를 SDK model로 축소하지 않음; 외부 DRA driver가 없으면 할당 완료를 주장하지 않음 |
| release | `03:154–165`의 matrix와 필수 integration | 지원 조합별 실행/skip/실패/미실행을 구분; 필수 integration이 skip이면 배포 gate 통과로 보지 않음 |

위 항목은 구현 검증 목록이며 새 facade가 통과했다는 뜻이 아니다. SDK
`discovery.py:165–167`은 503/JSONDecodeError를 빈 resources로 바꾸는 경로를
갖고 있어 facade의 실패 보존 문구를 SDK에 그대로 위임할 수 있는지는 P0에서
별도로 검증해야 한다. 이 항목은 transport의 종료 시점보다 discovery 결과의
분류 문제이므로 SDK 통합 판정에서 처리할 사항으로 남긴다.

## 제외한 주요 의심과 검증 한계

delete 2xx를 실제 소멸이라고 부른다는 의심은 `DeleteResult`의 명시적인
수락/소멸 구분으로 반증되어 지적으로 남기지 않았다. 410을 최신 RV로 바꿔
무손실이라고 주장한다는 의심도 자동 relist 제외 규칙으로 반증되었다.
RBAC 실패를 exists=False로 처리한다는 의심과 namespace 자동 fallback 의심도
고정 입력의 규칙이 이미 막는다. watch 재연결의 자체 구현이나 CRD readiness
추정은 요구 범위가 아니므로 필수 기능으로 추가하지 않는다.

실제로 실행한 것은 기존 unittest 7개와 아래 SDK 경계 probe다.

| 실행 | 결과 |
| --- | --- |
| Python 3.14.4 / SDK 36.0.3 / Pydantic 2.13.5의 기존 unittest | 7개 통과, 0.007초 |
| SDK 기본 pool retry inspection | total=3, PUT/DELETE read retry 허용 확인 |
| 로컬 fault HTTP server와 실제 ApiClient PUT | SDK 호출 1회 → 동일 body 수신 4회 → 200 반환 재현 |
| 로컬 chunked server와 실제 SDK Watch | read=80ms, 첫 BOOKMARK까지 305ms; read timeout이 전체 deadline 아님을 재현 |
| Kubernetes 공식 releases 페이지 재조회 | stable 1.37.0, release date 2026-08-26 확인 |
| PyPI JSON 재조회, yanked 제외, prerelease stage 순서 구분 | stable 36.0.3, prerelease 37.0.0b1 및 upload time이 sources와 일치 |

unittest 명령은 다음과 같다. SDK probe도 같은 uv 환경에서 stdin Python을
실행했으며 source 파일을 프로젝트에 추가하지 않았다.

```powershell
uv run --no-project --python 3.14 --with kubernetes==36.0.3 --with pydantic==2.13.5 python -X utf8 -m unittest discover -s tests -v
```

PUT 재현은 localhost의 ThreadingHTTPServer가 do_PUT에서 Content-Length만큼
body를 기록한 후 처음 세 요청에 socket shutdown/close를 수행하고 네 번째
요청에 JSON 200을 보내는 구성이다. 호출은 다음과 같으며 Configuration에는
localhost host만 지정하고 retries를 설정하지 않았다.

```python
api.call_api(
    "/item", "PUT", body={"value": 1},
    header_params={"Content-Type": "application/json"},
    response_types_map={200: "object"},
    _request_timeout=(0.5, 0.5),
    _return_http_data_only=True,
)
```

trickle 재현은 BOOKMARK JSON의 앞 아홉 byte를 byte당 30ms 간격의 HTTP chunk로
보낸 뒤 나머지 JSON과 줄바꿈을 보내는 구성이다. 타이머는 fault 조건을
만들기 위한 의도적인 pacing이며 운영 unit test의 동기화 방식으로 권장하지
않는다. Watch의 source 함수는 아래처럼 실제 RESTClient의 raw response를
반환한다.

```python
def read_resource(**kwargs):
    """Return raw HTTP response from the local chunked test server."""
    return api.rest_client.GET(
        api.configuration.host + "/watch",
        query_params=[("timeoutSeconds", kwargs["timeout_seconds"])],
        _preload_content=kwargs["_preload_content"],
        _request_timeout=kwargs["_request_timeout"],
    )

stream = watch.Watch().stream(
    read_resource,
    timeout_seconds=1,
    _request_timeout=(0.05, 0.08),
)
```

초기 probe 중 stdout encoding과 response_types_map 누락으로 실패한 호출은
수정 후 재실행했다. PyPI 정렬 probe도 prerelease stage를 a < b < rc로
명시한 뒤 다시 확인했다. 위 표는 성공적으로 완료한 최종 실행만 기록한다.
실제 Kubernetes cluster, RBAC 계정, admission, SSA conflict, CRD,
실클러스터 watch/finalizer, Python 3.10–3.13, SDK 37 beta, wheel/build는
이번 reviewer가 실행하지 않았다. 기존 7개 테스트 성공을 이 범위의 통과나
새 API 구현 완료로 계산하지 않는다.

외부 근거는
[Kubernetes releases](https://kubernetes.io/releases/),
[SDK compatibility](https://github.com/kubernetes-client/python#compatibility),
[PyPI JSON](https://pypi.org/pypi/kubernetes/json),
[API concepts](https://kubernetes.io/docs/reference/using-api/api-concepts/),
[Deployment status](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#deployment-status)를
2026-09-27에 확인했다. 구현 착수·배포 시 최신성은 다시 확인해야 한다.
