# SDK·리소스 통합 국소 후속 검토

검토일: 2026-09-27 KST. 1차 finding SDK-01–05를 최종 v2에서 어떻게
보정했는지만 대조했다. 전체 설계 리뷰를 반복하지 않았으며 1차 보고서,
원본 설계, 라이브러리를 수정하지 않았다.

같은 SDK 통합 검증 phase의 권장값은 `gpt-6-astra / high`다. 실제 모델과
effort는 신뢰 가능한 runtime metadata가 없어 확인 불가다. 설정은 변경하지
않았다. 1차의 skill 적용 범위와 source 기준을 그대로 사용한다.

## 고정 입력

두 파일을 직접 SHA-256으로 확인했으며 요청받은 값과 일치했다.

| 입력 | SHA-256 |
| --- | --- |
| `input-v2/04-final-implementation-plan.md` | `20ED861547D49369A85659435F3478233D2465AF0DACBAFA571F81CDB5359291` |
| `input-v2/decisions.md` | `898943E090D80434279579C75E76C0E740B94ABE60D1E11BC4E6A86C63D00201` |

줄 번호는 위 고정 입력 기준이다. Git 코드 기준은 여전히
`a3031fab6a1608b01d13a856186369db24fbc973`이다. 판정 기록에서는 자신의
SDK-01–05 행과 관련 보정 설명을 대조했다. wrapper·cluster 실행 결과로
해석하지 않는다.

## 원 지적별 판정

| finding | v2 위치 | 국소 판정 |
| --- | --- | --- |
| SDK-01 | 최종 계획 85–104행; decisions 14행 | 설계 방향 해결, 구현 검증 이관 |
| SDK-02 | 최종 계획 91행; decisions 15행 | fieldValidation 모순 해결, 구현 검증 이관 |
| SDK-03 | 최종 계획 51,92행; decisions 16행 | 우회 경로 해결, 구현 검증 이관 |
| SDK-04 | 최종 계획 95,176–187행; decisions 17행 | timeout 책임·보장 범위 해결, 구현 검증 이관 |
| SDK-05 | 최종 계획 51,59–62행; decisions 18행 | strategic 제외로 해결 |

SDK-01: discovery에만 raw decode·shape 검증을 적용하고 자체 discovery
예외로 오류를 전파하는 보정은 SDK의 503/JSON 오류 치환을 막을 수 있다.
36.0.3 및 37.0.0b1 `dynamic/discovery.py:156–167`의 catch 대상인
`ServiceUnavailableError`, `JSONDecodeError`와 다른 자체 예외를 사용해야
한다. HTTP status 오류가 superclass request에서 먼저 발생하는 경우도 그
원인·status를 보존해 이 경계에서 처리해야 한다.

`/version`은 `discovery.py:136–144`의 지정 serializer가 raw JSON dict를
원한다. `/apis`와 resource discovery는 `ResourceInstance`의 attribute
조회 규칙을 사용한다. 최종 계획 99–104행의 지정 serializer 복귀와 오류
흡수 방지 검증은 이 차이를 반영한다. 정상 빈 `groups`/`resources` array는
허용하고 필수 field 누락·wrong type을 빈 배열로 바꾸지 않는다는 기준도
타당하다. raw response cleanup은 아직 코드로 구현하거나 검증하지 않았다.

SDK-02: 최종 계획 91행의 fresh `query_params`와 정확한 wire key는 양쪽
SDK에서 재현한 올바른 경로다. Strict 기본값과 Ignore/Warn 선택을 공개
규칙으로 고정했으므로 실제 query·서버 응답 검증이 P0/P2에 남는다. beta의
추가 mapper를 이유로 baseline SDK에 같은 keyword 지원을 가정하지 않는다.

SDK-03: 발견된 URL에 `DynamicClient.request`로 배열을 직접 전달하면
`serialize_body`의 `body or {}`를 피한다. 같은 SDK ApiClient 인증·REST
transport를 사용하며 empty array를 `{}`로 바꾸지 않으므로 기존 probe의
관측과 맞는다. 배열 내부에 namespace를 삽입하지 않고 URL scope를 명시하는
실제 wrapper regression은 미실행이다.

SDK-04: request 경계에서 discovery의 `_request_timeout` 기본값을 넣는
책임이 명시되었다. wait는 유한 기본 timeout으로 resolve한 뒤 deadline을
시작하고 cold discovery 시간을 포함하지 않는다고 176–180행에 적었다.
이는 1차의 빠진 timeout 경로를 보정하면서 보장 범위를 명시하는 선택이다.
182–187행은 socket timeout과 절대 wall-clock 제한도 구분한다. 실행 중
descriptor를 고정하므로 wait 내부에서 다시 무제한 discovery를 시작하는
설계를 약속하지 않는다. 실제 초기화·refresh transport timeout과 GET의
남은 예산 연결은 구현 검증으로 남는다.

SDK-05: common patch를 merge/json으로 제한하고 strategic를 SDK escape
hatch로 넘겨 CRD 목록 권한이나 불확실한 builtin 판별이 필요하지 않게
했다. APIResource에 strategic 지원 flag가 없다는 source 관측과 맞으며
이 보정으로 추가 설계 선결은 생기지 않았다.

## 변경으로 생긴 국소 잔존 사항

### SDK-02-F1 — resourceVersionMatch도 SDK36에는 query 보정이 필요함

중요도: 설계 선결의 작은 보정. 유형: 추가 옵션의 버전별 wire 매핑 차이.
고정 입력의 최종 계획 117–121행은 resourceVersionMatch를 첫 페이지의
옵션으로 추가했으나 89–98행의 request 옵션 표에는 매핑 방식이 없다.

실패 조건: 첫 페이지에서 `resource_version_match="Exact"`를 요청하고
SDK36 DynamicClient에 keyword만 넘긴다 →
`dynamic/client.py:216–249`에 해당 mapper가 없어 요청에서 빠진다 →
호출자가 선택한 RV 조회 의미가 wire에 전달되지 않는다. beta의 같은 source
236–239행에는 mapper가 있다. 새 문서의 continuation에서 이 옵션을
제거하는 규칙은 적절하지만 첫 페이지 누락을 해결하지 않는다.

양쪽 SDK의 fake urllib3 transport로 이 차이를 직접 확인했다. Python
3.14.4, Pydantic 2.13.5, urllib3 2.8.0을 사용했으며 network는 호출하지
않았다.

| SDK | keyword 요청 | 명시 query 요청 |
| --- | --- | --- |
| 36.0.3 | `resourceVersion=10`만 존재 | `resourceVersionMatch=Exact`와 RV 존재 |
| 37.0.0b1 | match와 RV 모두 존재 | match와 RV 모두 존재 |

최소 수정: fresh query list에 `("resourceVersionMatch", value)`를 넣는
매핑을 명시한다. beta에서도 keyword를 함께 넘기지 않아 중복 key를 피한다.
continuation 요청에서는 이 query와 `resource_version`을 제거한다.
통과 사례는 SDK36/37에서 첫 페이지 match가 정확히 한 번 존재하고 후속
페이지에는 match/RV가 없으며 `_continue`·scope·selector는 유지되는 경우다.
명시 query 방식의 match count=1은 이번 ad hoc probe에서 확인했고 실제
wrapper pagination과 server snapshot은 아직 검증하지 않았다.

## 최신 certificates의 보조 확인과 미검증

최종 계획 264–272행은 최신 stable GVK를 SDK36 generic 경로에서 실제
관리하는 integration을 요구하며 approval/signing subresource 완료를
generic CRUD와 구분한다. SDK36 설치 source에는
`V1ClusterTrustBundle`·`V1PodCertificateRequest` stable model이 없고
SDK37.0.0b1에는 두 model과 CertificatesV1Api의 대응 메서드가 있음을
직접 확인했다. 따라서 SDK 모델 부재를 우회하는 dict 경로의 검증 사례로
설정할 수 있다. 실제 1.37 cluster의 served API·schema·권한·round trip은
확인하지 않았다. 별도 공식 v1 API 문서 URL 두 개는 web 도구에서 열리지
않았으므로 그 페이지를 추가 근거로 사용하지 않았다.

조정자는 기존 sdk-transport-probe.py의 양쪽 SDK assertion을 재실행했다고
알려 주었다. 이번 reviewer는 그 사실을 자신의 신규 wrapper 실행 결과로
기록하지 않는다. 새 facade·strict discovery adapter·cluster·pagination은
미구현·미실행이다. SDK-02-F1의 작은 매핑 명시 외에 SDK-01–05 수정 때문에
생긴 추가 설계 선결은 발견하지 못했다.

## v3 SDK-02-F1 국소 확인

새 고정 입력을 직접 SHA-256으로 확인했으며 요청받은 값과 일치했다.

| 입력 | SHA-256 |
| --- | --- |
| `input-v3/04-final-implementation-plan.md` | `82CF430949B414EE348114E94F98CBB5948143FE8335FE76BDC365EF41DBA7C6` |
| `input-v3/decisions.md` | `961F4234297782D9876146CA1BC9EDA27550ABDD5141353AF533B715778B7FC7` |

최종 계획 123–126행의 네 줄과 decisions 86–89행을 대조했다.
resourceVersionMatch를 fresh query에 직접 넣고 SDK37 keyword의 중복
전달을 피하며 continuation에서는 제거하도록 명시했다. 이는 SDK-02-F1의
최소 수정과 통과 기준을 반영한다. 판정은 **설계 잔존 해결, 구현 검증 이관**이다.

조정자는 status=200인 fake HTTPResponse로 양쪽 SDK에 RV/match를 보내
각각 wire에서 한 번 전달되고 입력 query가 불변임을 확인했다고 알려 주었다.
처음 fake response의 status 누락으로 실패한 뒤 수정해 재실행한 결과다.
이는 조정자의 실행 근거이며 이 reviewer의 추가 실험으로 기록하지 않는다.
실제 wrapper의 첫 페이지·continuation·서버 snapshot 검증은 여전히 미실행이다.
이 확인에서는 source 읽기, 실험, 전체 리뷰를 반복하지 않았다.
