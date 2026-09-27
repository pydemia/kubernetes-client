# 검증·운영 관점 독립 리뷰: input-v1

검토일: 2026-09-27. 이 보고서는 다른 reviewer의 결과를 읽지 않고 작성했다.
원본 구현은 변경하지 않았으며 별도 probe와 이 보고서만 추가했다.
현재 구현의 watch 종료·decode와 Deployment 실패 판정에 release 전 수정이
필요한 P1 세 건, iterator 종료에 P2 한 건을 확인했다.

## 입력과 실제 검토 범위

기준은 `.worknote/04-final-implementation-plan.md`와
`.worknote/implementation/review/input-v1/` snapshot이다. 저장된
`input-v1.sha256`의 모든 항목을 재계산해 일치를 확인했다. 아래 줄 번호는
작업 중인 루트 코드가 아니라 해당 snapshot의 파일을 가리킨다.

최종 계획 SHA256:
`82CF430949B414EE348114E94F98CBB5948143FE8335FE76BDC365EF41DBA7C6`.
적용 Skill은 `.worknote/inputs/skills/persona-cross-review.txt`이며 SHA256은
`3F91A340FAABC663C5C290D735670251EEB3F331B6E4AC999692A31C9FCBEED1`이다.

직접 읽은 구현은 `client.py`, `resources.py`, `watch.py`, `errors.py`다.
`tests/test_interface.py`, `README.md`, `pyproject.toml`도 확인했다.
`tests/test_compatibility.py`는 suite 실행으로 검증했다. 공식 SDK 36.0.3과
37.0.0b1의 설치된 `kubernetes/watch/watch.py`, `ApiClient.close`도 읽었다.
자격증명·일반 CRUD의 전체 독립 리뷰, 문서·package, 실제 cluster integration은
조정자의 작업 범위이며 이 보고서의 통과 판정에 포함하지 않는다.

이 관점은 wait의 UID/generation/deadline/cancel, watch의 EOF/410/stop 및
cleanup, transport replay·idle timeout을 담당한다. 해당 교차 검증에는
`gpt-6-astra / high`를 권장한다. 실제 모델·effort는 신뢰할 수 있는 runtime
metadata가 제공되지 않아 확인 불가다. 실행 설정은 변경하지 않았다.

## V1 — P1: strict watch가 마지막 불완전 JSON과 UTF-8 손상을 놓친다

위치: `kubernetes_client/watch.py:19–43`, `79–86`.
유형: 구현 결함. 두 SDK에서 직접 실행해 재현했다.

입력 `b'{"type":"MODIFIED","object":'`를 stream segment로 받은 뒤 EOF가
오면 `list(stream)`은 `[]`를 반환하고 정상 종료한다. 동일하게 정상 이벤트
뒤에 불완전한 마지막 JSON이 붙어도 마지막 부분은 검사되지 않는다. SDK의
`iter_resp_lines`가 newline이 없는 잔여 buffer를 EOF에서 버리기 때문에
`_StrictWatch.unmarshal_event`가 그 bytes를 받지 못한다.

SDK line decoder는 `errors="replace"`로 UTF-8을 읽는다. 이벤트 JSON의
metadata.name에 `b"bad\xffname"`을 넣으면 facade는 `"bad�name"`을 정상
ADDED 이벤트로 반환한다. `unmarshal_event`의 UnicodeError catch는 이미
대체된 문자열을 받으므로 이 손상을 검출하지 못한다.

기존 테스트 `tests/test_interface.py:332–335`는 newline으로 끝나는
`b"{broken\n"`만 검사한다. 따라서 parser가 직접 받은 malformed JSON은
거부하지만 실제 decoder 이전의 손실은 막지 못한다. response가 닫힌다는
사실도 stream이 온전했다는 근거가 되지 않는다.

관측 결과: 두 SDK 모두 `truncated_eof.events=[]`이며 예외가 없었다.
`utf8_replacement`에서는 `bad�name`이 들어 있는 정상 이벤트를 반환했다.
두 경우 모두 response는 닫혔다. SDK source의 함수 시작 줄은 36에서
`iter_resp_lines:47`, 37에서 `iter_resp_lines:55`다.

가장 작은 수정 방향은 line 분할 이전에 raw segment의 UTF-8과 EOF 잔여
buffer를 엄격히 검사하는 경계를 추가하는 것이다. SDK가 버린 값을 이후
JSON parser에서 확인하려 해서는 해결되지 않는다. 정상 EOF는 빈 잔여
buffer에 한정하고 마지막 segment의 잘린 JSON은 ResponseFormatError로
구분해야 한다. 잘못된 UTF-8을 묵시적으로 변경해서 반환해서도 안 된다.

통과 기준: 정상 EOF, 온전한 마지막 이벤트, 여러 segment로 나뉜 UTF-8,
첫/후속 이벤트의 불완전 JSON, 잘못된 UTF-8을 각각 검사한다. 손상된 경우
명시 예외와 response close/release를 확인하고 자동 reconnect가 없어야 한다.

## V2 — P1: reader가 실행 중일 때 stop이 generator 종료 예외를 낸다

위치: `kubernetes_client/watch.py:108–118`, 특히 `117`.
유형: 동시 종료 결함. 제어 Event를 사용한 재현은 두 SDK 모두 동일했다.

한 thread가 `list(stream)`의 response.stream 안에서 실행 중일 때 다른
thread가 `stream.stop()`을 호출한다. stop은 SDK stop과 response 종료 후
실행 중인 facade generator에 직접 `.close()`를 호출한다. Python은 이때
`ValueError: generator already executing`을 낸다. `_finish()`에도 도달하지
못해 stop 반환 시 `_closed=False`, client._streams에는 stream이 남는다.

probe의 reader를 재개하면 reader finally가 실행되어 나중에 정리된다.
이는 stop이 정리를 완료했다는 뜻이 아니며 reader가 실제로 돌아오는지에
종료가 의존한다. `KubernetesClient.close()`도 stream.close를 호출하므로
같은 예외가 client 종료로 전파될 수 있다. 첫 stream의 종료 예외가 나면
나머지 stream.close 호출을 건너뛴다는 점은 client.py:209–210에서 확인했다.

기존 테스트는 stream을 끝까지 list로 소진한 뒤 context를 종료한다.
실행 중 reader와 stop의 경합은 검사하지 않는다. SDK Watch.stop의 socket
shutdown 보호 장치도 facade generator의 실행 상태를 보호하지 않는다.

실제 로컬 HTTP의 idle chunked stream에서도 stop을 실행했다. 이 실행에서는
stop 호출 자체의 ValueError는 없었으나 reader는 ReadTimeoutError로 끝났다.
그 뒤 response 및 등록은 정리됐다. 이 관측을 모든 실제 socket에서
ValueError가 난다는 주장이나 즉시 취소가 보장된다는 주장으로 확대하지 않는다.
inactivity timeout에 따른 취소 지연 자체는 계획이 인정한 제한이다.

수정 방향: stop 요청과 reader가 소유한 generator의 최종 정리를 구분한다.
실행 중 generator에 다른 thread가 close를 호출하지 않도록 하고 response
종료·등록 해제·SDK close를 중복 호출에도 안전하게 완료해야 한다. client
종료가 한 stream의 실패 때문에 나머지 정리를 생략하지 않는지도 검사한다.

통과 기준: Event로 reader 실행 시점을 고정한 stop, client.close, 연속 stop,
두 stream 동시 종료를 검사한다. 외부 stop에서 generator 실행 예외가 없어야
하며 실제 idle socket에서도 모든 reader 종료와 close/release를 확인한다.

## V3 — P1: 이전 generation의 실패 condition으로 새 rollout을 실패시킨다

위치: `kubernetes_client/watch.py:203–209`.
유형: 상태 판정 결함. 두 SDK에서 직접 실행해 재현했다.

다음 응답으로 `wait_ready("demo", expected_uid="uid", target_generation=2)`를
호출하면 첫 GET 직후 ResourceNotReadyError가 발생한다.

```json
{
  "metadata": {"uid": "uid", "generation": 2},
  "spec": {"replicas": 1},
  "status": {
    "observedGeneration": 1,
    "conditions": [{
      "type": "Progressing",
      "status": "False",
      "reason": "ProgressDeadlineExceeded"
    }]
  }
}
```

현재 metadata는 target과 같지만 controller의 status는 이전 generation을
가리킨다. 새 spec이 저장되고 controller가 status를 갱신하기 전의 관측을
새 rollout의 terminal failure로 판정한다. observedGeneration >= target은
성공 조건에만 있고 진행 실패 condition 검사보다 뒤에 있다.

generation 변경 자체는 `_wait`에서 검사한다. 이 보호 장치는 metadata와
target의 불일치를 막지만 이전 status의 실패를 target에 귀속하는 문제는
막지 못한다. 기존 test_interface.py:301–306은 metadata generation 변경과
관측 완료된 replica=0만 검사하므로 이 상태를 포함하지 않는다.

수정 방향: controller가 target generation을 관측했는지 확인한 후 해당
status의 terminal condition을 판정한다. 이전 generation의 실패 상태는
아직 target의 실패로 볼 수 없으므로 다음 GET을 기다려야 한다.

통과 기준: 이전 generation의 ProgressDeadlineExceeded 이후 target의 정상
완료 응답을 순차 제공하면 성공해야 한다. target을 관측한 동일 failure는
ResourceNotReadyError로 끝나야 하며 timeout/cancel/UID 교체 판정은 유지한다.

## V4 — P2: 첫 next 이전의 iterator.close가 stream을 정리하지 않는다

위치: `kubernetes_client/watch.py:92–103`.
유형: 수명 관리 결함. 두 SDK에서 직접 실행해 재현했다.

`stream = client.pods.watch(); iter(stream).close()`를 실행하면
`stream._closed=False`, `len(client._streams)=1`, SDK ApiClient.close 호출 수는
0이다. 반환한 `_events()` generator가 시작되기 전에 close되면 generator
몸체의 try/finally가 실행되지 않으므로 `_finish()`도 호출되지 않는다.

계획은 iterator close 뒤에도 SDK Watch와 response 정리를 요구한다.
이 경우 response는 아직 생성되지 않았지만 watch가 client에 등록되어 남고
SDK ApiClient도 stream 수명 끝에서 닫히지 않는다. client.close나 명시적인
stream.close는 정리하므로 모든 종료 경로의 누수라고 주장하지 않는다.

수정 방향: 반환 iterator의 close가 generator 시작 여부와 관계없이 facade
stream.close로 연결되게 한다. 단순히 generator 내부 finally를 추가하는
것으로는 시작 전 close를 처리할 수 없다.

통과 기준: iterator의 첫 next 전 close, 한 이벤트 후 close, context 시작
전 stream.close, 반복 close를 각각 실행한다. `_closed=True`, 등록 제거,
해당 SDK client와 생성된 response의 종료를 확인해야 한다.

## 실행과 반증

Python 3.14에서 SDK 36.0.3/Pydantic 2.13.5와 SDK 37.0.0b1/Pydantic 2.13.5로
snapshot의 `python -m unittest discover -s tests`를 각각 실행했다.
두 lane 모두 22개 테스트가 통과했다. 지적한 실패는 해당 suite 밖의
독립 probe에서 재현됐으며 기존 통과 결과와 구분한다.

재현 파일은 같은 review 디렉터리의 `validation-probe-v1.py`와
`validation-transport-v1.py`다. 두 파일 모두 sys.path를 input-v1로 고정한다.
다음 명령의 SDK 버전을 각각 36.0.3과 37.0.0b1로 지정해 실행했다.

```powershell
uv run --no-project --python 3.14 --with kubernetes==36.0.3 --with pydantic==2.13.5 python -X utf8 .worknote/implementation/review/validation-probe-v1.py
uv run --no-project --python 3.14 --with kubernetes==36.0.3 --with pydantic==2.13.5 python -X utf8 .worknote/implementation/review/validation-transport-v1.py
```

실제 로컬 HTTP에서 응답 전에 연결을 끊은 PUT와 DELETE는 두 SDK 모두 요청
횟수가 각각 1이며 MaxRetryError를 반환했다. write replay가 있다는 의심은
이 조건에서 반증됐다. wait의 GET에 body를 주지 않은 경우 timeout_seconds
0.05에 대해 약 0.054–0.066초 뒤 MaxRetryError가 났으며 GET은 1회였다.
요청 timeout을 줄이는 동작은 확인했지만 강제 wall-clock 중단을 입증한
결과로 취급하지 않는다. 테스트 서버의 연결 종료 traceback은 client가
끊은 idle 연결의 server 측 ConnectionAbortedError이며 process는 정상 종료했다.

기존 suite와 코드에서 UID 교체, 명시 generation 변경, 응답 뒤 deadline
재검사, 호출 전 cancel, 객체에 대응하는 404, BOOKMARK와 ERROR 410의 구분,
완전히 소진된 stream의 정상 EOF/cleanup은 확인했다. 다음은 실행하지 않았다:
실제 cluster의 finalizer 삭제 지연, wait 진행 중 Event 취소, DNS·credential
plugin 지연, TLS idle socket의 stop, Python 3.10–3.13, package 설치 및
server 1.35/1.36/1.37 integration. 이 항목은 통과가 아니라 미검증이다.
