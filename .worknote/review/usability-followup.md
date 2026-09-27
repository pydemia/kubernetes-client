# 사용성·기존 API 이관 국소 후속 검토

검토일: 2026-09-27 KST. 1차 독립 리뷰의 USR-01/02/03에 대한 수정만
확인했습니다. 이 문서는 조정자의 판정을 받은 뒤 수행한 국소 재검토이며
새로운 독립 1차 리뷰가 아닙니다. 1차 보고서는 변경하지 않았습니다.
원본 설계·라이브러리도 수정하지 않았습니다.

동일 검증 단계의 권장은 1차의 `gpt-6-astra / high`를 유지합니다.
실제 runtime 모델과 reasoning effort는 모두 확인 불가입니다.

## 고정 입력과 읽은 위치

아래 두 파일의 SHA-256을 직접 계산해 전달받은 값과 일치함을 확인했습니다.
본문은 전체 읽되 판단 범위는 자신의 세 지적, 해당 판정과 기본 예제에
한정했습니다. 다른 persona의 판정을 재검토하거나 전체 설계를 다시
검증하지 않았습니다.

| 입력 | SHA-256 |
| --- | --- |
| `.worknote/review/input-v2/04-final-implementation-plan.md` | `20ED861547D49369A85659435F3478233D2465AF0DACBAFA571F81CDB5359291` |
| `.worknote/review/input-v2/decisions.md` | `898943E090D80434279579C75E76C0E740B94ABE60D1E11BC4E6A86C63D00201` |

비교 기준은 `.worknote/review/usability.md`의 USR-01/02/03과 그 보고서에
기록한 v1 snapshot·Git revision입니다. v2는 새 고정 입력이며 v1 줄 번호를
v2에 그대로 적용하지 않았습니다.

## USR-01 — 설계상 해결, 구현 검증 이관

관련 위치는 최종 계획 `:56–57`, `:143–169`, `:242–247`, `:309–313`과
판정 기록 `:11`, `:23–25`, `:32`입니다.

name-only 대기는 최초 GET의 현재 UID/generation을 기준으로 한다고
명시했습니다. write 완료 확인에는 응답의 `expected_uid`와 Deployment의
`target_generation`을 전달하며 다른 UID와 generation을 각각
ResourceReplacedError와 ResourceChangedError로 분리합니다. 기본 예제도
apply 응답에서 두 값을 꺼내 wait_ready에 전달합니다. wait_ready의 성공
반환이 최종 관측 dict라는 규칙도 추가되었습니다.

따라서 최초 write의 UID=A가 첫 GET 전에 B로 교체되는 1차 실패 조건은
expected_uid 비교로 막을 수 있고 같은 UID의 generation 증가도 원래 apply의
완료에 합치지 않습니다. Pod는 target_generation을 거부하고 UID와 현재 Ready
condition만 보장합니다. 특정 Pod spec revision의 관측을 보장한다고 설명하지
않으므로 Deployment와 Pod의 보장 범위를 구분한 수정은 일관됩니다.

잔존 설계 선결은 없습니다. 실제 비교 순서·반환·예외 구현은 P4에서 검증해야
합니다. 필수 사례는 write 응답 후 첫 GET 전 UID 교체와 generation 증가,
name-only 호출의 현재 객체 기준 동작, Pod target_generation 거부,
기대 UID의 Ready 성공과 최종 dict 반환입니다. 계획 `:310–311`에 경합
사례가 포함되어 있으나 실행된 테스트 결과로 보지는 않았습니다.

wait_deleted의 expected_uid 필수 규칙도 write 대상과 이름 재사용을 구분하지만
이 메서드의 전체 운영·timeout 규칙은 이번 국소 사용성 검토에 포함하지
않았습니다.

## USR-02 — 설계상 해결, 예제의 namespace 연결 확인

관련 위치는 최종 계획 `:39–43`, `:71–75`, `:209–226`, `:227–252`와
판정 기록 `:12`입니다.

get/delete/wait가 bind 또는 client default를 사용한다고 명시하고 body에서
선택한 namespace가 후속 bind를 바꾸지 않는다고 적었습니다. 기본 예제는
factory default를 demo로 지정하며 Secret와 Deployment에도 각각 demo를
explicit resource bind합니다. Deployment apply와 wait는 같은 resource
handle에서 수행하므로 다른 namespace의 동명 객체를 기다리는 1차 실패
조건이 제거되었습니다. Secret helper에 namespace를 넣지 않아도 bind가
복사한 body에 namespace를 보충하는 기존 규칙과 일치합니다.

잔존 설계 선결은 없습니다. 예제는 현재 실행 불가능한 제안 API로 표시되어
있습니다. P2 검증에서는 default가 default이고 manifest가 demo인 조건,
bind/body 충돌, 두 namespace의 같은 이름을 포함해 write/get/wait/delete의
실제 요청 경로가 지정한 namespace를 쓰는지 확인해야 합니다. 계획
`:250–252`, `:310`이 그 규칙과 사례를 기록하고 있습니다.

## USR-03 — 출력 책임 해결, SSA 실행 검증 이관

관련 위치는 최종 계획 `:125–135`, `:219–223`, `:285`, `:323–328`과
판정 기록 `:13`입니다.

helper가 평문 string_data를 UTF-8 base64로 인코딩해 data만 반환하도록
확정했습니다. base64 data와 동일 key의 평문 입력은 거부합니다. generic
create는 raw stringData를 허용하고 Secret apply는 이를 거부하므로 일반
manifest를 숨겨진 변환으로 수정하지 않습니다. 같은 helper body를 create와
apply에 사용할 수 있으며 예제의 opaque_secret 출력을 그대로 apply하는
경로도 이 규칙에 맞습니다.

1차의 변환 책임 모호함은 해결되었습니다. helper의 data 출력·key 충돌·입력
불변·HTTP payload와 raw Secret apply의 입력 오류는 P3/P2 구현 검증으로
남습니다. 실제 SSA 반복 적용·다른 field manager conflict와 server 오류는
계획된 integration 검증으로 이관합니다. 해당 테스트를 실행하거나 SSA
안전성이 실클러스터에서 확인되었다고 판정하지 않았습니다.

## 검토 결과의 한계

세 지적의 설계 수정과 기본 예제가 일치하며 해당 수정으로 새로 발생한 설계
선결은 발견하지 못했습니다. 이것은 구현 완료나 테스트 통과 판정이 아닙니다.
이번 후속 검토는 파일 읽기·hash 확인과 규칙 대조만 수행했습니다.
새 facade 실행, unit/type check, SDK transport probe, 실제 클러스터·RBAC·SSA
검증은 수행하지 않았습니다. 코드 수정과 외부 소비자 확인도 하지 않았습니다.
