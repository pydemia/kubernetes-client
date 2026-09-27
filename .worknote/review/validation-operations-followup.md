# 검증·운영 국소 후속 검토

검토일: 2026-09-27 KST. 이번 검토는 독립 1차 결과를 수정하지 않고 OPS-01,
OPS-02, OPS-03의 반영과 조정자 추가 관측 COORD-02만 확인한다. 전체 설계의
새 독립 리뷰나 구현 검증으로 해석하지 않는다. 라이브러리와 원본 문서는
변경하지 않았다. runtime 모델과 effort는 확인 불가다.

## 고정 입력

`input-v2/`의 아래 두 파일을 읽고 실제 SHA-256이 요청값과 일치함을 확인했다.
위치는 새 snapshot의 행 번호이며 v1의 행 번호를 재사용하지 않는다.

| 파일 | SHA-256 |
| --- | --- |
| `04-final-implementation-plan.md` | `20ED861547D49369A85659435F3478233D2465AF0DACBAFA571F81CDB5359291` |
| `decisions.md` | `898943E090D80434279579C75E76C0E740B94ABE60D1E11BC4E6A86C63D00201` |

내용 판단의 코드 기준은 기존과 같은 Git
`a3031fab6a1608b01d13a856186369db24fbc973`이다. SDK 36.0.3/urllib3 2.8.0의
소스 관측과 local fault-server 실행은 1차 보고서의 근거를 사용했다. 이번에는
source 실험, unittest, 실클러스터 테스트를 반복하지 않았다.

## OPS-01 — 설계 지적 해소, 구현 검증으로 이관

수정 위치는 최종 계획 145–187행과 판정 기록 19,28–31행이다. 대기를 GET
기반 유한 polling으로 바꾸고 generic watch의 수명과 분리했다. descriptor를
기본 timeout으로 resolve한 뒤 deadline을 시작하며 cold discovery/refresh를
`timeout_seconds`에 포함하지 않는다고 명시했다. 95행은 discovery 자체에도
request timeout을 전달하는 별도 보정을 정한다.

171–174행은 매 GET 전 남은 예산 검사와 timeout 감소, 응답 후 deadline 검사,
cancel Event의 요청 전후 검사와 `Event.wait` 확인 시점을 고정한다.
182–187행은 DNS, credential plugin, 연속 수신을 포함한 절대 wall-clock 중단을
보장하지 않으며 실행 중 취소도 transport에 영향을 받는다고 제한한다. 따라서
단순 socket timeout을 절대 실행 제한이라고 부르던 문제가 해소되었다.
엄격한 중단 SLA를 새 요구로 추가할 필요가 없다.

남은 것은 실제 실행 검증이다. deadline 뒤 도착한 Ready 응답이 성공으로
반환되지 않아야 한다. GET 전에 설정된 Event, GET 진행 중 설정된 Event,
poll interval 중 설정된 Event가 각 확인 지점에서 취소로 끝나야 한다.
discovery 지연과 최초 GET 지연은 문서의 서로 다른 예산 규칙대로 동작해야
한다. 취소 입력이 즉시 socket을 중단한다고 테스트나 문서에서 확대 해석하면
안 된다. 이를 확인한 실행 결과는 아직 없으며 새 설계 선결은 발견하지 않았다.

## OPS-02 — 설계 지적 해소, 구현 검증으로 이관

수정 위치는 최종 계획 97,111–115행과 판정 기록 20행이다. owned connection은
Configuration.retries=0으로 생성한다. borrowed connection은 실제 transport가
no-retry라는 조건을 확인하고 기본 retry 또는 확인 불가 custom transport를
factory에서 거부한다. 외부 설정과 pool을 변경하지 않는 원래 소유권 규칙도
남겼다.

이는 wrapper 호출 횟수와 HTTP 재전송 횟수를 구분한 수정이다. factory가
Configuration의 현재 값만 확인하고 이미 만들어진 pool의 실제 retry 값을
검사하지 않는 구현은 이 계획을 충족하지 않는다. P1에서는 실제 pool을
검사해 기본 borrowed client 거부, retries=0으로 만든 공식 client 수락,
확인 불가 transport 거부와 외부 객체 불변을 검증해야 한다. P0/P1의
PUT/DELETE disconnect 사례에서는 wire 수신 횟수가 한 번이어야 한다.

설정 이후 외부 코드가 borrowed transport 정책을 바꾸는 동작까지 factory가
보장한다고 추정하지 않는다. no-retry 조건은 facade 사용 중 유지해야 하는
입력 조건으로 구현 문서에 남길 수 있다. 아직 새 factory나 no-retry wire
시험은 실행하지 않았으며 이 점을 새 설계 결함으로 세지 않았다.

## OPS-03 — 설계 지적 해소, 구현 검증으로 이관

수정 위치는 최종 계획 154–156,169,310–311행과 판정 기록 21,23–25행이다.
`wait_deleted`는 expected_uid를 필수로 받고 객체 404를 성공(None), 다른 UID를
ResourceReplacedError로 구분한다. delete와 최초 wait GET 사이의 교체 사례를
필수 시험에 넣어 watch 시작 후의 교체만 검증하던 범위를 보완했다.

P4에서는 A 삭제 → 같은 이름의 B 생성 → expected_uid=A로 wait 시작 순서를
고정해야 한다. 최초 GET의 B를 새 target으로 채택하거나 B가 삭제될 때까지
대기해서는 안 된다. 최초 객체 404, 모호한 endpoint/namespace 404, 403,
동일 UID의 finalizer 지연도 서로 구분해야 한다. v2의 77–81행은 객체 404의
분류 근거가 없을 때 오류를 보존하므로 이 규칙과 충돌하지 않는다.
공개 signature와 결과 규칙이 마련되었으며 새 구현의 통과 여부는 미검증이다.

## COORD-02 — 조정자 요청 후속 관측, 구현 검증으로 이관

독립 1차 발견으로 세지 않는다. 최종 계획 196–199,286,312행과 판정 기록
41,46–49행을 대상으로 검토했다. `Watch.unmarshal_event`를 좁게 확장해
malformed JSON과 event shape 오류를 예외로 종료하고 SDK의 raw_object,
resourceVersion, ERROR 처리 형식을 유지하는 방향은 타당하다.

SDK 36.0.3 `kubernetes/watch/watch.py:119–149`의 기본 parser는 JSON decode
실패를 None으로 바꾼다. 같은 파일 211–224행의 stream은 ERROR 처리에서
`raw_object`와 Status의 code/reason/message를 읽는다. 따라서 새 parser가
JSON을 엄격히 읽는 것만으로 완료된다고 판단해서는 안 된다.

P4에서 정상 ADDED/MODIFIED/DELETED, unknown nested field, 최소 metadata만
있는 BOOKMARK, HTTP 오류와 ERROR Status, 잘못된 JSON, 누락된 type/object,
잘못된 object 형태를 각각 검증해야 한다. BOOKMARK에 전체 resource 필드나
UID를 요구하지 않고 raw dict를 축소하지 않아야 한다. ERROR가 shape 검사 뒤
KeyError로 바뀌거나 SDK의 410 종료 규칙을 우회하면 안 된다. parser 예외에서도
response close/release가 실행되어야 한다. SDK 37의 동일 경로는 이번 후속
검토에서 실행하지 않았으며 두 SDK의 회귀 통과는 구현 단계의 조건으로 남는다.

세 OPS 항목의 v1 설계 문제는 v2에서 해소되었다. 이는 설계 보장과 입력이
명확해졌다는 판정이며 새 facade, 취소, no-retry, 삭제 대기 또는 parser의
구현 검증 성공을 뜻하지 않는다. 미구현·실클러스터 미실행 상태는 그대로다.
