# v1.0.0 구현 검증 기록

검증일은 2026-09-27 KST다. 구현 기준은 `a3031fa`에서 시작한
`codex/v1-interface`이며 최종 코드 입력은
`review/input-v3.sha256`과 복원 가능한 `review/input-v3/`에 고정했다.
preview 배포 조건만 분리한 후속 CI 입력은 `review/input-v4/`다.
CI commit, tag, PyPI 공개 결과는 아래 배포 기록에 이어서 남긴다.

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

GitHub Actions와 PyPI 공개·공개 파일 설치는 아직 실행 전이다.
`verification.yml`의 안정 SDK unit/package/live cluster는 필수 배포 조건이며
preview job만 continue-on-error로 분리했다. publish는 tag checkout과 version
일치를 확인하고 기존 pypi environment Trusted Publishing을 사용한다.
