# 구현 중 판정

기준 코드는 `a3031fa`, 설계 기준은 `../04-final-implementation-plan.md`다.
독립 리뷰 입력과 원문은 `review/input-v1`과 `review/*-v1.md`에 보존했다.
원래 설계 리뷰 기록은 변경하지 않는다.

| 지적 | 판정·수정 | 검증 |
| --- | --- | --- |
| US-01 | 채택. 단일 get/exists/patch/delete의 name을 요청 전에 검증 | invalid name에서는 discovery·객체 요청 모두 없음 |
| US-02 | 채택. image_pull_secrets는 list/tuple만 허용 | 문자열을 참조 배열로 분해하지 않음 |
| US-03 | 채택. all_namespaces와 ignore_not_found는 bool만 허용 | 문자열 false를 True로 취급하지 않음 |
| SDK-I01 | 채택. discovery prefix와 group/version을 명시 | core 조회에서 apps/version endpoint를 방문하지 않음 |
| SDK-I02 | 채택. manager와 이미 생성된 connection pool의 retry를 검사 | 설정 변경 없이 borrowed factory에서 거부 |
| SDK-I03 | 채택. 공식 ResourceList 인스턴스를 제외 | synthetic List kind에 단일 객체 요청을 보내지 않음 |
| SDK-I04 | 채택. discovery root kind와 필수 문자열/목록을 검증 | malformed 응답을 명시 format 오류로 분류 |
| V1 | 채택. SDK line decoder 앞에서 UTF-8과 최종 newline을 검증 | 잘못된 UTF-8·truncated EOF와 정상 분할 Unicode 구분 |
| V2 | 채택. 실행 중 generator를 닫지 않고 stop/response 종료 후 finally 정리 | 제어 probe와 실제 idle socket stop |
| V3 | 채택. controller가 target generation을 관측한 뒤 실패 condition 판정 | 이전 generation의 실패를 새 rollout 실패로 세지 않음 |
| V4 | 채택. watch 자체를 iterator로 제공해 시작 전 close도 정리 | first next 전 iterator.close와 client.close |
| US-04 | 채택. quickstart의 HTTP 작업을 assert 밖에서 실행 | python -O로도 apply/get/delete/wait 동일 실행 |
| US-05 | 채택. migration의 namespace field를 metadata.namespace로 명시 | 실제 manifest 경로와 가이드 일치 |

V1의 입력 보정은 원래 계획의 `Watch.unmarshal_event` 확장만으로 해결되지
않았다. SDK가 그 메서드 호출 전에 UTF-8 오류를 대체하고 마지막 미완성 줄을
버리기 때문이다. 작은 response stream adapter에서 incremental UTF-8 decode와
line framing을 검증한다. SDK의 Watch.stream, ERROR/EOF/timeout와 response
종료 흐름은 재사용하며 SDK watch 구현을 복제하지 않는다.

로컬 Docker Desktop 4.34.3은 cgroup v1을 제공한다. Kubernetes 1.37 kubelet의
기본 cgroup v1 거부 때문에 첫 kind 생성이 실패했다. 별도 disposable cluster
`kc-v1-137`에만 `KubeletConfiguration.failCgroupV1=false`를 적용해 생성했다.
이 설정은 라이브러리 동작이나 일반 배포 환경 권장이 아니다. kind v0.33.0의
공식 1.37.0 node image digest를 사용했다. 사용자 kubeconfig는 변경하지 않았다.

RBAC는 허용 권한을 더하는 모델이므로 임의 impersonation group만 지정해도
기본 discovery 권한을 제거할 수 없었다. 실클러스터 discovery 403 시험은
시험 cluster의 system:discovery rules를 잠시 비우고 finally에서 원복한다.
이 integration suite는 disposable cluster에서만 실행해야 한다.

SDK-I04는 v2 후속 리뷰에서 빈 group version의 분류가 남아 부분 해결이었다.
group name/version과 preferredVersion의 비어 있음, groupVersion의 일치와
preferred version의 served 목록 포함 여부를 검증하도록 보완했다.

2026-09-27 공식 stable.txt 재조회 값은 v1.37.1이었다. kind v0.33.0의 공식
node 목록에는 1.37.0이 있으나 1.37.1 tag는 registry에 없었다. latest patch
검증에는 공식 release tarball을 kind build node-image --type url로 빌드한다.
node tag 존재나 release blog의 minor 표기만으로 최신 patch를 추정하지 않는다.

v3 한정 재검토로 SDK-I04의 malformed 25개·정상 2개 양 SDK 사례와
US-04/05가 해결됐음을 확인했다. 조정자도 최종 33 unit의 10개 조합,
1.37.1 실클러스터 양 SDK 8개, 설치한 wheel로 README와 일반/-O quickstart를
실행했다. reviewer의 제어 probe를 live cluster 성공 근거로 대신하지 않았다.

목표에서 preview 검증과 안정 배포 조건을 구분하도록 요청했으므로 v4에서
preview matrix job만 continue-on-error=True로 분리했다. 안정 SDK36.0.3의
unit/package와 모든 stable server lane은 여전히 필수 조건이다.
조정자는 원문·GitHub 공식 의미·validation-v4를 대조해 채택했다.
workflow 전체의 성공만으로 preview 통과를 표시하지 않고 개별 job을 확인한다.

package archive 대조가 v4 guide 변경을 포함하지 않은 이전 sdist에서 한 번
실패했다. guide 변경 후 재빌드하고 source 일치·포함·worknote 제외를 재검사해
통과했다. 이 실패는 코드나 runtime 호환성 실패로 분류하지 않는다.

PyPI description에서 상대 repository 링크를 해석할 기준이 없으므로 README의
가이드·예제·RECOVERY 링크를 v1.0.0 tag의 절대 URL로 바꿨다. project.urls도
같은 repository·documentation·issues를 지정했다. runtime 코드·예제 본문과
의존성은 변경하지 않았다. v5 사용성 한정 검토와 재빌드·twine·archive metadata
검사·wheel 재설치로 확인했다. tag 생성 전 원격 blob 404는 배포 후 재확인한다.
