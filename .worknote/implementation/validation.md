# v1.0.0 구현 검증 기록

검증일은 2026-09-27 KST다. 구현 기준은 `a3031fa`에서 시작한
`codex/v1-interface`이며 최종 코드 입력은
`review/input-v3.sha256`과 복원 가능한 `review/input-v3/`에 고정했다.
preview 배포 조건만 분리한 후속 CI 입력은 `review/input-v4/`다.
PyPI README의 절대 가이드 링크와 project.urls의 입력은 `review/input-v5/`다.
CI commit, tag와 PyPI 공개 결과는 아래 배포 기록에 남겼다.

## 적용 기준과 버전 확인

사용한 Hub skill의 본문과 필요한 style reference는
`../inputs/skills/`에 보존했다. software-engineering,
pydemia-coding-style, persona-cross-review를 적용했으며 원본 SDK나
legacy `base.py`·schema·quantity 보정 동작을 변경하지 않았다.
단계별 모델·effort 추천은 실행 설정을 바꾸는 지시가 아니다.
실제 모델과 effort의 신뢰 가능한 runtime metadata는 확인할 수 없었다.

- [공식 SDK releases](https://github.com/kubernetes-client/python/releases)와
  [PyPI SDK metadata](https://pypi.org/pypi/kubernetes/json): 안정판 36.0.3,
  preview 37.0.0b1. 의존성은 `kubernetes>=36.0.3,<38`이다.
- [공식 Kubernetes stable 표시](https://dl.k8s.io/release/stable.txt):
  재조회 값 `v1.37.1`. release blog의 1.37 minor와 현재 patch를 구분했다.
- [kind v0.33.0 releases](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0):
  공식 1.35.8/1.36.4/1.37.0 node digest를 확인했다.
  1.37.1 node tag는 registry에 없어 공식 release tarball로 빌드했다.
- [ClusterTrustBundle API](https://kubernetes.io/docs/reference/kubernetes-api/authentication-resources/cluster-trust-bundle-v1/):
  1.37의 `certificates.k8s.io/v1`을 SDK36의 dict 경로로 실제 관리했다.

## 최종 로컬 실행

unit은 SDK의 실제 serializer·DynamicClient·Watch를 사용한 wire fixture와
localhost HTTP socket 시험이다. live integration과 혼합하지 않는다.
`validation/unit-final-*.txt`에 원문을 보존했다.

| Python | SDK36.0.3 | SDK37.0.0b1 |
| --- | --- | --- |
| 3.10.20 | 33개 통과 | 33개 통과 |
| 3.11.15 | 33개 통과 | 33개 통과 |
| 3.12.13 | 33개 통과 | 33개 통과 |
| 3.13.13 | 33개 통과 | 33개 통과 |
| 3.14.4 | 33개 통과 | 33개 통과 |

기존 회귀 7개를 포함한다. retry가 설정된 기존 pool 거부, GET 기반 exists,
collection DELETE 예방, namespace 상태, unknown/null/empty 보존, SSA query,
pagination snapshot, malformed discovery, watch UTF-8·EOF·BOOKMARK·410,
중단·read timeout, 늦은 Ready·UID·generation 경합을 검사했다.
socket에서 PUT/DELETE disconnect의 실제 요청 횟수는 각각 1회였다.

mypy는 새 파일 5개의 typed 코드와 untyped 함수 본문에서 통과했다.
`--follow-imports=skip --ignore-missing-imports --check-untyped-defs`를 사용했다.
SDK에 없는 stub과 legacy 전체의 strict type 검증을 뜻하지 않는다.
ruff format은 새 파일에만 79자 설정으로 적용했다.

실클러스터는 별도 kubeconfig를 둔 local Docker Desktop linux/arm64 kind다.
아래 최종 실행은 Python3.14.4/Pydantic2.13.5이며 서버의 정확한 gitVersion을
assertion으로 확인했다. 원문은 `validation/integration-final-*.txt`다.

| 서버 | SDK | 결과 |
| --- | --- | --- |
| 1.35.8 | 36.0.3 | 7개 통과, 1.37 전용 사례 1개 skip |
| 1.36.4 | 36.0.3 | 7개 통과, 1.37 전용 사례 1개 skip |
| 1.37.1 | 36.0.3 | 8개 통과 |
| 1.37.1 | 37.0.0b1 | 8개 통과 |

1.37.0 양 SDK의 8개 사전 실행도 통과했지만 latest patch 완료의 근거는
1.37.1의 최종 실행이다. builtin API group·DRA 객체, irregular plural의
namespaced/cluster CRD와 v1/v2·schema·unknown nested null/목록, GET-only RBAC와
discovery 403, SSA ownership conflict/force, finalizer·UID precondition·replacement,
Pod/Deployment readiness와 generation을 확인했다.
실제 allocation driver나 certificate signer controller의 완료는 시험하지 않았다.

로컬 cgroup v1 환경의 kubelet 거부는 시험 cluster에서만
`failCgroupV1=false`로 해소했다. Windows kind node build는 docker cp의 Linux
목적지에 Windows 절대 경로를 넣어 실패했고 WSL Linux kind0.33.0에서 성공했다.
`validation/node-build-1371.txt`와 `cluster-create-1371.txt`에 보존했다.
기본 사용자 kubeconfig는 변경하지 않았다.
RBAC는 허용 권한을 더하므로 discovery 403 시험은 disposable cluster의
system:discovery rules를 잠시 비운 뒤 finally에서 원복한다.
1.35의 controller 갱신과 PDB replace가 충돌한 최초 시험은 실패였다.
시험 fixture가 현재 RV를 최대 5회 다시 읽도록 고친 뒤 최종 실행이 통과했다.
facade의 write retry는 추가하지 않았다.

## 리뷰와 패키지·예제

세 reviewer의 독립 1차 원문은 `review/*-v1.md`다. 공유 소스는 읽기 전용으로
고정했으며 다른 reviewer의 1차 보고서를 읽도록 하지 않았다.
v2/v3은 해당 finding만 재검증한 후속 결과다. raw report와 probe, SHA256,
실행 JSONL을 보존했으며 판정과 설계 변경 이유는 `decisions.md`에 기록했다.
같은 모델의 reviewer 동의를 정확성의 증거로 계산하지 않았다.

US-01–05, SDK-I01–04, V1–4는 모두 채택하고 관련 범위에서 해결했다.
SDK-I04는 v2에서 부분 해결이었고 v3에서 malformed 25개·정상 2개를
양 SDK로 검증한 뒤 해결했다. 실클러스터·패키지·배포는 reviewer가 실행한
fake probe와 구분하여 조정자가 별도로 검사했다.

- wheel/sdist의 최종 build와 `twine check --strict` 모두 통과했다.
- 별도 새 venv에 wheel을 설치하고 저장소 밖에서 두 공개 class의 import,
  metadata·모듈 버전 1.0.0, Configuration 기반 생성/종료를 확인했다.
  `uv pip check`도 통과했으며 SDK36.0.3/Pydantic2.13.5가 설치됐다.
- 그 설치 환경으로 1.37.1의 quickstart를 일반 Python과 `python -O`에서
  실행했다. 생성·반복 apply·get·UID delete·wait·exists·namespace 정리가
  모두 완료됐다. README의 Python block도 그대로 실행해 Secret data를 확인했다.

build·twine·wheel 설치/import/check와 예제 원문 결과는 `validation/`에 있다.
메타데이터의 범위가 미래 SDK 패치나 모든 API·addon의 호환을 보장하지 않는다.
preview 통과는 안정판 지원 선언으로 확장하지 않는다.

## 배포 상태

GitHub Actions [preflight 실행](https://github.com/pydemia/kubernetes-client/actions/runs/36313840842)은
`398d3601a4b888303de33b8e956eae4abdc39ba6`에서 14개 job이 모두 성공했다.
preview 6개도 개별 success를 확인했다. Linux amd64의 실제 1.35.8/1.36.4/1.37.1,
Python 3.10–3.14 양 SDK unit과 package lane을 실행했으며
`validation/github-preflight.json`에 job 원문 metadata를 보존했다.
이후 변경은 README 링크와 project.urls, 리뷰·실행 기록뿐이며 runtime 코드는 같다.
최종 tag를 publish workflow에서 다시 검증했다.
`verification.yml`의 안정 SDK unit/package/live cluster는 필수 배포 조건이며
preview job만 continue-on-error로 분리했다. publish는 tag checkout과 version
일치를 확인하고 기존 pypi environment Trusted Publishing을 사용한다.

release commit은 `fcda918cd47611dae88a29872481be6854611a75`다.
main을 fast-forward하고 annotated v1.0.0 tag를 같은 commit에 push했다.
원격 tag object는 `523752e2eb37784ed085be1ceb1c9505b7a4dfc3`이며 peeled commit의
일치를 별도로 확인했다. tag를 덮어쓰거나 배포 뒤 수정하지 않았다.

| 실행 | 실제 결과 |
| --- | --- |
| [main 검증](https://github.com/pydemia/kubernetes-client/actions/runs/36314121631) | success |
| [v1.0.0 tag 검증](https://github.com/pydemia/kubernetes-client/actions/runs/36314123691) | success |
| [Publish to PyPI](https://github.com/pydemia/kubernetes-client/actions/runs/36314152373) | 16개 job 모두 success; verify 14개, build, publish |

publish는 `--ref main`, input tag `v1.0.0`으로 dispatch했다.
preview 6개 job도 개별 success다. 필수 stable gate를 우회하지 않았고
기존 Trusted Publishing 외에 수동 PyPI token을 추가하지 않았다.
GitHub의 pypi environment protection_rules는 비어 있었다.
job metadata는 `validation/github-publish.json`, 실제 로그의 검증 부분은
`github-publish-summary.txt`에 보존했다.

[PyPI v1.0.0](https://pypi.org/project/kubernetes-client/1.0.0/)의 JSON metadata와
공개 파일을 직접 조회했다. 업로드 시각은 2026-09-27 10:59:52/53 UTC이며
두 파일의 실제 다운로드 bytes가 PyPI SHA256과 일치했다.

| 파일 | 공개 SHA256 |
| --- | --- |
| kubernetes_client-1.0.0-py3-none-any.whl | 363af5e6c97cdf45e04475d333650f438da90633a8d3ff0ea8382642a22f48e0 |
| kubernetes_client-1.0.0.tar.gz | 62bb77c0ae44cefd5b3d47a5eb4e8b97f150f1c5544fb09c684767800416bef1 |

공개 wheel의 모든 package .py bytes가 v1.0.0 Git blob과 일치하고 공개
sdist의 README·pyproject·가이드·예제도 같은 tag와 일치했다.
두 archive에서 .worknote가 제외됐음을 확인했다.
로컬 Windows build와 GitHub Linux build의 archive hash가 같다고 가정하지 않았다.

새 Python3.14.4 venv에 `uv pip install --no-cache --index-url
https://pypi.org/simple --python <venv-python> kubernetes-client==1.0.0`으로
공개 버전을 설치했다. SDK36.0.3/Pydantic2.13.5가 선택됐고
`uv pip check`가 통과했다. 저장소 밖에서 import·metadata/모듈 버전 1.0.0,
Secret/quantity helper·Configuration client 생성/종료·Documentation URL을
확인하고 그 설치본을 대상으로 회귀 33개를 실행해 모두 통과했다.
실행 원문은 `pypi-release.json`, `pypi-install.txt`, `pypi-check.txt`,
`pypi-import.txt`, `pypi-unit.txt`, `pypi-archive.txt`다.

tag 생성 후 README의 가이드·예제·RECOVERY 링크 5개는 모두 HTTP200이었다.
`release-tag-links.txt`에 결과를 기록했다. 직접 생성한 disposable cluster
kc-v1-135/136/137/1371은 모두 삭제했고 기존 cluster·application container는
유지했다. 이후 commit은 실행 기록 갱신이며 공개된 runtime/tag를 바꾸지 않는다.
