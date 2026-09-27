# 사용성·기존 API 이관 1차 독립 리뷰

검토일: 2026-09-27 KST. 검토 입력은 `input-v1/`의 고정 snapshot과
Git `a3031fab6a1608b01d13a856186369db24fbc973`입니다.
검토한 코드·테스트·설정의 working tree와 해당 revision 사이에 diff가 없음을
확인했습니다. 다른 reviewer의 보고서와 최종 구현계획은 읽지 않았습니다.
이 보고서만 작성했으며 원본 설계·라이브러리는 수정하지 않았습니다.

검증 단계 권장은 `gpt-6-astra / high`입니다. write 이후 wait의 대상과
namespace, 기존 반환·오류 동작을 함께 대조해야 하기 때문입니다.
실제 runtime 모델과 reasoning effort는 모두 확인 불가입니다.

## 판단과 착수 가능한 범위

새 `KubernetesClient`와 기존 `KubernetesManager`를 병행하고 새 진입점에서
create-only, patch, SSA를 구분하는 방향은 기존 API를 직접 치환하는 것보다
명시적입니다. SDK model을 복제하지 않고 dict 응답과 같은 연결의 SDK 호출을
제공하는 방식도 최신 필드와 기존 typed 사용을 구분합니다.

P0 characterization과 P1 인증·수명 작업은 착수 가능합니다. P2의 일반 CRUD,
namespace 충돌 검사와 dict 보존 규칙도 구현 기준이 있습니다. P4의 wait는
USR-01의 보장 범위를 정한 뒤 공개 signature를 고정해야 합니다. USR-02는
기본 workflow 예제에서 namespace를 고정하는 작은 문서 변경으로 해결할 수
있습니다. USR-03은 P3의 helper 출력과 회귀 검증으로 이관할 사항입니다.

| ID | 해결 시점 | 유형 | 영향 |
| --- | --- | --- | --- |
| USR-01 | 설계 선결 | 빠진 동작 규칙·조건부 위험 | write한 객체와 wait가 관측하는 객체의 연결이 끊길 수 있음 |
| USR-02 | 설계 선결 | 사용 예의 빠진 전제 | body namespace로 쓴 뒤 default namespace의 다른 객체를 기다릴 수 있음 |
| USR-03 | 구현 검증 | helper 출력의 실증 필요 | 평문 Secret helper를 그대로 apply하는 기본 예제의 SSA 규칙 확인 필요 |

## USR-01 — write 응답과 wait의 대상이 연결되지 않습니다

입력 v1 근거는 `02-interface-design.md:238–239`, `:260–270`과
`03-implementation-proposal.md:128–131`입니다. 특히 구현안은 이름이 같은
대체 객체를 원래 작업의 성공으로 세지 않는다고 적고 있으나 wait는 최초
GET에서 UID/generation을 선택합니다. write 응답을 받는 옵션은 없습니다.
기준 코드 `kubernetes_client/base.py:79–127`은 이름으로 Pod 이벤트를
출력할 뿐이며 `tests/test_compatibility.py:86–121`도 typed/dict 이벤트와
출력만 검증합니다. 기존 동작에서 write-target association이 보장된다는
근거는 없습니다.

실패 조건은 다음과 같습니다. `demo/api` apply가 UID=A, generation=7을
반환한 뒤 다른 주체가 이를 삭제하고 같은 이름의 UID=B를 만듭니다.
사용자가 이름만으로 `wait_ready("api")`를 호출하면 최초 GET은 B를 읽고
B의 UID를 고정합니다. B가 Ready이면 대기가 성공할 수 있습니다. 같은 UID의
generation=8 업데이트가 GET 전에 발생하는 경우에도 최초 목표가 8로 바뀝니다.
이는 아직 구현하지 않은 API의 설계 경로에서 도출한 조건부 사례이며 실제
클러스터에서 재현한 결과는 아닙니다.

반증 검토: UID 고정과 generation 확인은 최초 GET 이후의 재생성·지연된
status를 막습니다. 이 보호 장치는 write 응답과 최초 GET 사이를 보호하지
않습니다. 반대로 API의 목적이 호출 시점의 현재 객체 대기라면 이 동작은
잘못이 아닙니다. 문제는 그 범위와 구현안의 원래 작업 보장이 구분되어 있지
않다는 점입니다. 최신 generation까지 무조건 동일 작업으로 취급할지 여부도
문서에서 확정하지 않았습니다.

최소 수정은 두 의미 중 제공할 의미를 먼저 적는 것입니다. 이름만 받은 wait는
최초 GET에서 고정한 객체의 현재 상태를 기다린다고 정의할 수 있습니다.
write한 객체의 완료를 보장하려면 apply/create 반환의 UID와 목표 generation을
명시적으로 받는 옵션 또는 동일한 정보를 받는 작은 target 입력을 추가해야
합니다. 후자의 경우 상위 generation이 관측될 때 성공을 허용할지, 작업이
교체되었다는 오류를 낼지도 함께 정해야 합니다. 이 선택을 새 background
controller나 reconcile loop로 확장할 필요는 없습니다. wait 성공 반환이
관측한 최종 dict인지 여부도 P0 signature 목록에 포함해야 합니다.

판정 사례는 A 반환 직후 B로 교체, 같은 UID에서 generation 증가, 최초 GET
이후 UID 변경, 이미 Ready인 목표 객체입니다. 이름만 받은 wait와 write 대상이
제공된 wait의 기대 결과를 각각 고정하고 둘의 보장 범위를 설명해야 합니다.
원래 write의 완료를 보장한다고 문서화한 경로에서는 B의 Ready로 성공해서는
안 됩니다.

## USR-02 — 기본 예제의 write와 후속 wait namespace가 다를 수 있습니다

입력 v1 근거는 `02-interface-design.md:123–133`, `:226–243`, `:265–270`과
`03-implementation-proposal.md:144–145`입니다. write는 body namespace를
선택할 수 있으나 이름을 받는 후속 조회는 bind 또는 client default를 씁니다.
앞의 factory 예제 `02-interface-design.md:80–85`는 default를 demo로 두지만
별도의 helper 예제는 그 client를 계속 쓴다는 전제를 명시하지 않습니다.
기준 코드 `kubernetes_client/base.py:436–453`, `:602–622`, `:79–98`의
기존 Secret·ServiceAccount·Pod 호출은 각 호출에 namespace를 직접 전달합니다.
기존 사용 예도 `01-current-design.md:108–121`에서 demo를 반복 지정합니다.

구체 입력은 `default_namespace="default"`인 client와
`metadata.namespace="demo"`, `metadata.name="api"`인 Deployment manifest입니다.
예제대로 `client.deployments.apply(deployment_manifest)`는 demo에 쓰고
`client.deployments.wait_ready("api")`의 최초 GET은 default를 조회합니다.
default에 같은 이름이 없으면 404로 작업이 끝나며 Ready 객체가 있으면 다른
Deployment의 준비 상태로 완료될 수 있습니다. 후속 delete를 같은 방식으로
호출하는 사용법까지 안내하면 다른 namespace의 객체를 대상으로 할 수 있습니다.

반증 검토: bind/body 불일치 오류와 client default 규칙은 각각의 요청에는
일관되게 적용됩니다. demo default로 만든 client를 쓴다면 해당 예제도
성립합니다. 다만 body에서 선택한 namespace가 resource object를 영구 bind한다는
동작은 설계에 없으므로 apply가 후속 wait의 namespace를 바꾼다고 기대할 수
없습니다. 숨은 상태로 namespace를 바꾸는 구현은 최소 수정이 아닙니다.

최소 수정은 예제 안에서 같은 namespace를 쓰도록 명시하는 것입니다.
`client.resource("apps/v1", "Deployment", namespace="demo")`로 얻은 객체에
apply와 wait를 연속 호출하거나 예제 client의 factory와
`default_namespace="demo"`를 함께 보여주면 됩니다. wait에도 get과 동일한
namespace 선택 규칙이 적용된다는 문장을 추가해야 합니다. 별도의 bind 편의
메서드를 필수로 추가할 필요는 없습니다.

판정 사례는 default와 manifest namespace가 다른 client, bind와 body가
일치하는 client, bind/body 충돌, 두 namespace에 같은 이름이 있는 경우입니다.
기본 migration 예제에서는 write/get/wait/delete가 모두 동일한 namespace를
사용해야 하며 충돌 사례는 HTTP 요청 전 오류여야 합니다.

## USR-03 — Secret helper의 string_data 출력과 SSA 변환 책임을 검증해야 합니다

입력 v1 근거는 `02-interface-design.md:207–213`, `:234–237`과
`03-implementation-proposal.md:111–119`입니다. helper에는 `string_data`를
주지만 예제는 그 결과를 추가 변환 없이 apply합니다. 구현안은 동일 manifest를
create/apply에 사용하고 SSA body를 data로 변환한다고 요구합니다.
기준 코드 `kubernetes_client/base.py:342–365`, `:456–481`, `:504–517`은
SDK Secret의 string_data를 그대로 넘기며 새 helper 또는 SSA 변환 구현은
없습니다. 기존 테스트에는 Secret SSA 사례가 없습니다.

조건부 실패 입력은 `secret_manifest.opaque(...,
string_data={"username": "example"})`입니다. helper가 기존 방식처럼
stringData를 반환하고 generic apply가 원래 dict를 그대로 전달하면 계획에서
요구한 data 기반 SSA가 되지 않습니다. Kubernetes 공식 문서는 stringData와
SSA 조합의 문제를 별도로 설명합니다. 이는 ownership·반복 적용 검증이 필요한
근거이며 여기서 특정 conflict나 데이터 손실을 실측했다고 주장하지 않습니다.
[공식 Secret 문서](https://kubernetes.io/docs/concepts/configuration/secret/#basic-authentication-secret), 조회 2026-09-27.

반증 검토: 설계의 SSA data 인코딩 방침과 P3 완료 조건이 위험을 이미
인식합니다. 따라서 새로운 기능 누락으로 판정하지 않습니다. helper가 처음부터
string_data를 data로 인코딩해 반환하면 같은 manifest의 create/apply 조건도
충족할 수 있습니다. 다만 현재 문서에는 helper 출력과 generic apply의 변환
책임 중 어느 쪽을 구현할지 구체적으로 적지 않았습니다.

최소 수정·검증은 helper의 실제 출력이 data만 포함하는지 명시하고 해당 출력을
검증하는 것입니다. 이 방향이면 generic apply가 모든 Secret 입력을 몰래
변환할 필요가 없습니다. raw manifest의 stringData를 보존하는 일반 경로와
SSA 권장 helper 경로도 구분해 설명할 수 있습니다. 기본 예제의 HTTP payload에
stringData가 없는지, create/apply 모두 평문 입력의 UTF-8 base64 값이 같은지,
입력 dict가 불변인지 확인해야 합니다. data/string_data 동일 key는 helper에서
실패하고 서버 호출이 없어야 합니다. 다른 field manager와의 SSA conflict 및
같은 manifest 반복 적용은 계획된 실클러스터 검증으로 남습니다.

## 지적으로 남기지 않은 주요 의심

- 새 create가 legacy create_opaque_secret의 upsert를 그대로 수행하지 않는
  차이는 이미 create-only 규칙과 legacy 유지, migration 대상에 명시되어
  있습니다. 이를 회귀 결함으로 보지 않았습니다.
- SDK 객체의 attribute 접근을 dict key 접근으로 바꾸는 이관 비용은 있습니다.
  dict 응답과 typed SDK escape hatch를 선택한 이유가 명확하고 기존 반환을
  보존하므로 새 API까지 legacy model 반환으로 강제하지 않았습니다.
- prepare_namespace의 Istio/project labels, limits 자동 상향, ServiceAccount
  None 반환과 기존 RuntimeError를 새 API에 복사할 필요는 없습니다. 기존 API
  보존과 새 동작의 분리가 명시되어 있습니다. 외부 소비자도 읽지 못했으므로
  즉시 삭제 또는 자동 이관을 요구하지 않았습니다.
- CRD readiness, async, 일괄 rollback, TokenRequest를 필수 범위로 확대하지
  않았습니다. generic CRUD와 명시 SDK 호출의 범위가 문서에 있습니다.
- discovery·transport·watch timeout의 SDK 세부 구현 가능성은 다른 책임의
  검토 대상이며 이 보고서는 이를 실행 검증했다고 표시하지 않습니다.

## 읽은 범위와 재검증 자료

v1 문서 네 개는 전체 본문을 읽었습니다. hash는 직접 계산해 검토 README의
값과 일치함을 확인했습니다. 아래 경로는 저장소 루트 기준입니다.

| 고정 문서 | SHA-256 |
| --- | --- |
| `input-v1/01-current-design.md` | `229F05B9C9D7722636F94493C532A84D0EFE40755E1819C94CD9A503DD8CA227` |
| `input-v1/02-interface-design.md` | `F5D79E6C123F717BAA3A0A68951B9A6FB0BC4ADB7DBF90C8482243858525D486` |
| `input-v1/03-implementation-proposal.md` | `7E7F9C488D4220A9D3B114FDA4B33EA0F3219118FBBFAC7044DAA910AD427938` |
| `input-v1/sources.md` | `E4D2331AE7BF89CE8250677B6CEA0622379F42C04245A8F95C9D8A4FD4CB8788` |

문서 경로의 실제 prefix는 `.worknote/review/`입니다. 원문 snapshot은 이 위치에
보존되어 있으며 hash만으로 원문을 복원할 수 있다고 가정하지 않습니다.

| 기준 코드·설정, 읽은 줄 | SHA-256 |
| --- | --- |
| `kubernetes_client/base.py:1–655` | `98296538F22AB6F6432FB03863A7149A7A929CEFF39D31DAAA50E6FDBECFC855` |
| `kubernetes_client/schema.py:1–87` | `54558DE4D9FFE873F78D280A721438B75693C784F8C5060DDA087144427EF4C3` |
| `kubernetes_client/__init__.py:1` | `2388B5444F6B513B1B93382855BA9C3F670FFA9BDE40506BB99CE07D40806E90` |
| `kubernetes_client/utils.py:1–5` | `93C9CBC044CCBACB3F0A536188F6BBDAFB4F96C285492D4A88B31F16600CC742` |
| `kubernetes_client/enums.py:1–207` | `A9B3D2AD57D4D18BA34096876FF1E92F9412B5A927F9F260CA464D9B0F441FCE` |
| `tests/test_compatibility.py:1–162` | `CA6C36FC19F527F84D57F0DD37EB3E43371C61D73913FA872E8BA322BE7E712B` |
| `README.md:1–23` | `BA6B0980D084DD0A0DFFAAFA567E0BE7A9289F03515A3FE34A258DA966EA4122` |
| `pyproject.toml:1–28` | `40F4124D909EBA303FF485E626DCA9E900896962D81DF7198D8AC2705E8445FE` |
| `.github/workflows/publish.yml:1–76` | `364140DE1B7441C8224FF6D97E903A124305AACEDC151D9D99511A336C3639FD` |

적용 skill은 `.worknote/inputs/skills/persona-cross-review.txt`와
`software-engineering.txt`를 전체 읽었습니다. 각각의 SHA-256은
`3F91A340FAABC663C5C290D735670251EEB3F331B6E4AC999692A31C9FCBEED1`,
`EEF56ED9F9DA89C76D7726B26D0D616DE50F006D185B36776686888249D5BB94`입니다.
실행 규칙은 `.worknote/review/README.md`를 읽었습니다.

이번 reviewer는 unittest, type check, 패키지 build와 실제 클러스터 테스트를
실행하지 않았습니다. sources.md에 기록된 기존 테스트 성공은 조정자의 실행
기록이며 이 reviewer의 재실행 결과가 아닙니다. 외부 소비자, live RBAC,
SSA conflict, 최신 GVK, 새 facade의 실제 런타임 동작은 미검증입니다.
