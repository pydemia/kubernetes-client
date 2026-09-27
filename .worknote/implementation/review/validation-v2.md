# 검증·운영 관점 targeted 재검토: input-v2

검토일: 2026-09-27. 이전 독립 리뷰의 V1–V4와 release gate를 재검토했다.
다른 reviewer의 보고서는 읽지 않았으며 검토 대상 구현을 수정하지 않았다.
고정 입력 `input-v2/`의 모든 파일 hash를 `input-v2.sha256`과 대조해 일치를
확인했다. 아래 경로와 줄 번호는 모두 해당 snapshot에 대한 것이다.

Python 3.14/Pydantic 2.13.5에서 SDK36.0.3과 SDK37.0.0b1을 각각 사용했다.
각 lane에서 snapshot의 32개 unit/socket 테스트가 통과했고 기존 독립 제어
probe 및 실제 HTTP probe도 input-v2에 적용했다. 이전 네 지적의 실패는
재현되지 않았다. split UTF-8의 정상 처리도 확인했다.

## V1 — 해결 확인: watch의 EOF·UTF-8 검사

수정 위치: `kubernetes_client/watch.py:63–85`, `132–140`.
`_StrictResponse`가 SDK line decoder 전에 strict incremental UTF-8 decoder와
마지막 newline 이후 tail을 검사한다.

기존 입력 `b'{"type":"MODIFIED","object":'`는 이제
`ResponseFormatError("Unterminated watch event at EOF")`로 끝난다.
metadata.name의 `b"bad\xffname"`도 `Invalid watch UTF-8` 오류로 끝난다.
양 SDK에서 두 오류 뒤 response.closed=True, client._streams의 수=0이었다.

정상 ADDED 이벤트의 `"한글"` UTF-8 bytes를 한 글자의 첫 byte와 둘째 byte
뒤에서 나누어 세 segment로 제공했다. 양 SDK 모두 원문 `"한글"`과 RV를
반환했으며 EOF 뒤 response가 닫혔다. 올바른 multi-byte 문자의 분할 수신이
손상으로 분류되지 않는 것을 별도로 확인했다.

관련 회귀 테스트 `tests/test_interface.py:224–258`도 suite에서 실행됐다.
이 테스트는 malformed EOF·UTF-8, iterator 종료 및 split UTF-8을 포함한다.
이 범위에서 V1의 남은 실패는 발견하지 못했다.

## V2 — 원래 경합 해결 확인, reader 종료까지 cleanup 지연

수정 위치: `kubernetes_client/watch.py:182–194`.
close는 먼저 `_closed=True`로 표시하며 실행 중인 generator에는 직접 close를
호출하지 않는다. reader finally가 `_finish()`를 수행한다.

이전과 동일하게 Event로 response.stream 실행 중 reader를 멈춘 상태에서
다른 thread가 stop을 호출했다. 양 SDK에서 stop_error=None,
closed=True였으며 `generator already executing`은 발생하지 않았다.
reader가 멈춰 있는 동안에는 client._streams에 1개가 남았다. Event를
재개한 뒤 reader는 빈 결과로 끝났고 finished=True, 등록 수=0이었다.

실제 localhost의 idle chunked HTTP에서도 stop을 실행했다. 두 SDK 모두
stop 호출의 예외가 없었으며 reader는 ReadTimeoutError로 끝난 뒤 닫힘과
등록 제거를 완료했다. 정상 이벤트 이후 idle/stop을 다루는 repository의
`tests/test_transport.py:109–136`도 양 SDK에서 통과했다.

원래 지적한 실행 중 generator.close 예외는 해결됐다. cleanup이 stop 호출
즉시 끝난다는 판정은 하지 않는다. 실행 중 synchronous read의 종료에
따라 정리가 지연될 수 있고 이 요청은 transport 오류로 끝날 수 있다.
이를 즉시 취소나 wall-clock 강제 종료로 설명해서는 안 된다. TLS read,
credential plugin 지연과 모든 가능한 thread interleaving은 미검증이다.

## V3 — 해결 확인: generation에 맞는 실패 condition 판정

수정 위치: `kubernetes_client/watch.py:294–304`.
observedGeneration이 target보다 작으면 terminal condition을 검사하기 전에
False를 반환한다.

이전 입력 metadata.generation=2, observedGeneration=1과
ProgressDeadlineExceeded를 계속 제공한 경우 즉시 ResourceNotReadyError가
나던 동작은 사라졌고 WaitTimeoutError로 끝났다.

같은 이전 status 다음에 target generation=2의 준비 완료 status를 제공하면
두 GET 뒤 성공했다. 반대로 observedGeneration=2의 동일 실패 condition을
제공하면 한 GET 뒤 ResourceNotReadyError로 끝났다. 두 SDK에서 모두
실행했으며 오래된 실패를 무시하는 것과 현재 실패를 유지하는 것을 구분했다.
회귀 테스트 `tests/test_interface.py:260–282`도 통과했다.

## V4 — 해결 확인: 시작 전 iterator.close

수정 위치: `kubernetes_client/watch.py:158–168`, `182–194`.
iterator가 facade 자신을 반환해 첫 next 이전의 close도 facade.close로 간다.

기존 `iter(stream).close()` probe는 두 SDK에서 closed=True, 등록 수=0,
SDK ApiClient.close 호출 수=1이었다. 생성 전 response는 없으며 Watch의
SDK client가 종료됐다. V4의 원래 실패는 재현되지 않았다.

## release gate: 구성 검사와 실행 상태

직접 읽은 gate는 `.github/workflows/verification.yml`, `publish.yml`,
`docs/validation.md`와 호출되는 `tests/integration/test_cluster.py`다.

verification.yml:21–35는 Python3.10–3.14 × SDK36.0.3/37.0.0b1에서 정확한
SDK를 설치하고 regression/interface/socket suite를 실행한다. 36–56은
Python3.14/SDK36 lane에서 새 API mypy, build, twine strict, 별도 venv의
wheel metadata·공개 import·1.0.0 버전 일치를 검사한다. package 검사를
모든 Python의 clean wheel import로 확대했다는 뜻은 아니다.

verification.yml:62–99는 고정 node digest의 1.35.8/1.36.4/1.37.0 stable
lane과 1.37.0 preview lane을 생성한다. 각 lane은 명시 kubeconfig 환경
변수로 integration과 guide example을 실행한다. tests/integration:37은
변수가 없으면 오류를 내며 suite 전체를 optional skip으로 바꾸지 않는다.
ClusterTrustBundle 사례(563–604)는 실제 v1.37 server에서 discovery와
create/get/patch/field round trip을 직접 검사한다. API가 없거나 작업이
실패하면 오류다. 1.35/1.36에서는 명시적으로 해당 최신 사례만 skip한다.

publish.yml:16–22는 release tag를 ref로 verification workflow에 전달하고
build가 verify를 필요로 한다. publish는 build를 필요로 한다(65–66).
따라서 현재 구성에는 unit/package/cluster 검증을 건너뛰는 publish 경로가
없다. tag와 project version 일치 검사가 있고(36–47) distribution도 다시
build/twine strict 검사한다(53–56). `continue-on-error`나 강제 성공 처리도
확인한 gate에는 없다. preview 실패도 현재 구성에서는 게시를 차단한다.

docs/validation.md:28–44는 이 matrix와 순서를 설명하며 preview 지원,
tag 생성, PyPI 게시, 게시 후 clean install을 구분한다. 구성 내용과
문서 설명은 검토한 범위에서 맞는다. 각 lane의 실제 server version은
로그에 기록되지만 matrix version과 직접 비교하는 assertion은 없으므로
고정 node digest의 실제 내용은 조정자의 live 실행 증거로 확인해야 한다.

이 부분은 파일과 호출 관계를 검사한 결과다. GitHub Actions workflow를
실제로 실행하거나 실패 lane이 downstream을 차단하는 것을 GitHub에서
실험하지 않았다. 실제 disposable cluster 및 package 검증은 조정자 범위다.
그 실행 결과나 PyPI 배포 완료를 이 보고서에서 주장하지 않는다.

## 재현 파일과 추가 검증 한계

`validation-probe-v2.py`와 `validation-transport-v2.py`는 기존 v1 probe를
input-v2로 고정한 파일이다. V3은 수정 후 무한히 같은 상태를 기다리지
않도록 유한 timeout과 이전→완료/현재 실패의 후속 사례를 추가했다.
실행 명령의 SDK를 36.0.3과 37.0.0b1로 각각 지정했다.

```powershell
uv run --no-project --python 3.14 --with kubernetes==36.0.3 --with pydantic==2.13.5 python -X utf8 .worknote/implementation/review/validation-probe-v2.py
uv run --no-project --python 3.14 --with kubernetes==36.0.3 --with pydantic==2.13.5 python -X utf8 .worknote/implementation/review/validation-transport-v2.py
```

실제 HTTP PUT·DELETE disconnect는 양 SDK에서 각각 1회 요청 뒤
MaxRetryError였고 자동 replay가 없었다. wait idle timeout_seconds=0.05
probe는 1회 GET 뒤 약 0.055–0.078초에 MaxRetryError로 끝났다. 이 측정은
남은 예산의 socket timeout 적용을 확인한 것으로 절대 실행 제한의 증거가
아니다. server 측 ConnectionAbortedError traceback은 끊긴 연결의 진단이며
probe process는 exit 0이었다.

양 SDK의 32개 suite에는 기존 UID/generation/deadline/404/410/EOF 회귀도
포함된다. 이 재검토에서는 새 release 차단 결함을 발견하지 못했으나 전체
thread 상태 공간, TLS, 실제 cluster finalizer/SSA/RBAC/CRD 및
Python3.10–3.13, GitHub-hosted matrix, 게시 후 PyPI 설치는 직접 실행하지
않았다. 모델·effort는 기존 설정을 유지했고 실제 runtime 값은 확인 불가다.
