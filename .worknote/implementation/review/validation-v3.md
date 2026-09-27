# CI·integration fixture 한정 재검토: input-v3

검토일: 2026-09-27. 고정 입력은 `input-v3/`와 `input-v3.sha256`이다.
manifest의 모든 파일 SHA256을 재계산해 일치를 확인했다. manifest 자체의
SHA256은 다음과 같다.

`f639fa19da4caa1149ef63cde8dc02eccbd6cc1644334e3c1e9c1fb3969ea757`

다른 reviewer 보고서는 읽지 않았고 원본 구현은 변경하지 않았다.
CI·fixture·guide에 한정해 아래 파일을 읽었다. 줄 번호는 input-v3 기준이다.

- `.github/workflows/verification.yml`
  SHA256 `063d58f1a5e5cba70bf51d20551f3dbc69a0dea6942356846674a08cc3d519e9`
- `.github/workflows/publish.yml`
  SHA256 `ad258d9fc7bde07f2ebc7a52e724ee59bc8b953fe52a32f2feb1197767ae1474`
- `tests/integration/test_cluster.py`
  SHA256 `4791e08bed7a47f8038b041cdc8df3e44cc60b0f49b1c4418757fcd8f7687aac`
- `examples/quickstart.py`
  SHA256 `0e37946c5fd98958c5106f1c185913d090b92d628693b393ce11258bd9fd1226`
- `docs/validation.md`
  SHA256 `6867e56867a87e7d4f3ac04979c2a869079a3b6033b80aabea0e4260a99ede82`

이 한정 범위에서 새 release 차단 결함은 발견하지 못했다. 아래의 fixture와
guide 제어 probe는 실행했지만 실제 cluster·GitHub Actions·PyPI의 통과
판정은 하지 않는다.

## 실제 server version과 lane 값 비교

verification.yml:110–112는 kubeconfig와
`KUBERNETES_CLIENT_TEST_SERVER_VERSION=v${{ matrix.version }}`를 전달한다.
test_cluster.py:54–64는 실제 gitVersion을 이 값과 문자열 전체로 비교하고
불일치 시 명시적으로 AssertionError를 발생시킨다. 예상 값이 지정된 CI에서
다른 minor/patch를 시험하고 최신 사례를 skip한 채 성공하는 경로가 막힌다.
환경 변수 미지정의 수동 실행은 이 정확 비교를 요구하지 않는 기존 방식이다.

`validation-gates-v3.py`는 snapshot의 실제 setUpClass를 fake client로
실행했다. expected=v1.37.1에 대해 실제 값이 v1.37.1일 때만 진행했고
v1.37.0, v1.36.4, v1.37.1+other는 모두 AssertionError였다. 일반 Python과
python -O에서 같은 결과를 확인했으며 class cleanup도 호출됐다.
`raise AssertionError`를 사용하므로 최적화 옵션에 제거되는 assert가 아니다.

이 probe는 실제 API server를 조회하지 않았다. fixture의 LIVE 출력도
fake gitVersion을 사용한 함수의 기존 출력이며 실제 cluster 성공 로그가 아니다.

## 1.37.1 tarball 검사와 kind node build

verification.yml:87–93은 1.37.1 lane에서만 공식 `dl.k8s.io`의 linux-amd64
server tarball과 같은 버전의 .sha256을 받는다. 이어서 sha256sum --check를
실행하고 그 다음 줄에서 `kind build node-image --type file --arch amd64`를
호출한다. kind binary는 v0.33.0이며 build base는 tag와 아래 digest로 고정된다.

`8098fa3cae05bc15d9c4b93a566d19e1f8e65a25e26ebeb993b6cb41142cf791`

공식 [kind image build 문서](https://kind.sigs.k8s.io/docs/user/quick-start/#building-images)는
release tarball의 file build 경로를 제공한다. GitHub의 Linux 기본 run
shell은 bash -e이므로 checksum 검사의 nonzero 종료 뒤 다음 build 명령을
실행하지 않는 구성이다.
[GitHub shell 규칙](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idstepsshell)

2026-09-27에 다음 공식 checksum URL을 PowerShell Invoke-WebRequest로
직접 조회해 HTTP200과 64자리 checksum을 확인했다.
[Kubernetes v1.37.1 amd64 checksum](https://dl.k8s.io/v1.37.1/kubernetes-server-linux-amd64.tar.gz.sha256)

`09d6de07da48e16c0fc044d7bd19c5df0c4de7d62d27f5aa648345e80f311e18`

tarball bytes를 이 agent가 받아 hash를 계산하거나 amd64 kind build를 실행한
것은 아니다. 원격 checksum의 조회 성공과 workflow의 검사 순서를 확인했다.
조정자가 전달한 ARM64 node build 성공도 이 agent의 독립 재실행 결과로
기록하지 않는다. node image 생성 후 실제 cluster 동작은 별도 실행 증거가
필요하다.

verification.yml:94–108은 최신 lane에 방금 만든 wrapper-node:v1.37.1을
선택하고 다른 minor에는 기존 node digest를 지정한다. cluster의 kubeconfig를
별도 경로에 생성하며 120초 준비 대기와 always 삭제 단계(120–122)가 있다.

## publish reusable gate

publish.yml:16–22는 release tag를 ref로 reusable verification에 전달하고
build는 verify의 성공을 필요로 한다. publish도 build 성공을 필요로 한다
(65–66). verification에는 10개 unit 조합, baseline package 검사, 4개
cluster lane이 남아 있으며 실패를 숨기는 continue-on-error나 downstream
job의 always 조건은 없다. GitHub의 needs 규칙과도 맞는 연결이다.
[GitHub needs 규칙](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idneeds)

release tag checkout와 version 일치, distribution build/twine strict는
publish.yml:25–56에서 유지된다. docs/validation.md:30–34와 42–46은 최신
patch tarball build, 검증 이후 게시, tag와 게시 상태의 구분을 설명한다.
설정과 문서 설명은 확인한 범위에서 일치한다.

이 판정은 workflow 구성 검사다. GitHub에 workflow를 실행하거나 실패 lane이
게시를 차단하는 것을 실제 서비스에서 재현하지 않았다. PyPI도 미배포 상태다.

## python -O guide lane

verification.yml:113–116은 integration 다음에 일반 guide와 python -O guide를
각기 다른 namespace로 실행한다. quickstart.py:22–35는 round trip,
재적용 UID, delete 결과, wait 뒤 exists를 명시적 if/raise로 확인한다.
필요한 apply·get·delete·wait·exists 호출이 assert 안에 들어 있지 않다.
finally의 namespace UID 기반 delete/wait는 36–40에 유지된다.

snapshot의 실제 guide.run에 fake client를 제공해 정상 경로와 roundtrip,
reapply UID, delete action, exists 실패를 각각 실행했다. 일반 Python과 -O
모두 정상 경로에서 apply 두 번, get, delete, wait_deleted, exists를 호출했다.
각 실패는 RuntimeError였고 namespace delete/wait와 client.close가 끝까지
호출됐다. 따라서 최적화 옵션 때문에 검증·반복 apply가 사라지는 실패는
제어 probe에서 발견하지 못했다. 실제 Secret/namespace 정리의 완료를 이
fake 결과만으로 주장하지 않는다.

재현 파일은 review 디렉터리의 `validation-gates-v3.py`다. Python3.14,
SDK36.0.3, Pydantic2.13.5와 cryptography를 사용해 다음 두 모드로 실행했다.

```powershell
uv run --no-project --python 3.14 --with kubernetes==36.0.3 --with pydantic==2.13.5 --with cryptography python -X utf8 .worknote/implementation/review/validation-gates-v3.py
uv run --no-project --python 3.14 --with kubernetes==36.0.3 --with pydantic==2.13.5 --with cryptography python -O -X utf8 .worknote/implementation/review/validation-gates-v3.py
```

두 process는 exit 0이었다. 이 단계에서 unit 전체, SDK37 반복, 실제 cluster
integration, clean wheel 설치, GitHub-hosted amd64 build/matrix, PyPI 게시와
게시 후 설치를 실행하지 않았다. 모델·effort는 변경하지 않았으며 실제
runtime 값은 확인 불가다.
