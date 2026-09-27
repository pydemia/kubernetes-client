# 검증과 배포

필수 unit은 legacy 회귀, 새 인터페이스, SDK wire query/body, localhost socket의
no-replay·watch timeout/stop을 검사합니다. `tests/integration`은 실제 disposable
cluster를 사용하며 fake test와 구분합니다.

```shell
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
python -m mypy kubernetes_client/client.py kubernetes_client/resources.py kubernetes_client/watch.py kubernetes_client/manifests.py kubernetes_client/errors.py --follow-imports=skip --ignore-missing-imports --check-untyped-defs
python -m build
python -m twine check --strict dist/*
```

mypy는 새 facade 파일의 typed code와 untyped 함수 본문을 확인합니다. 공식 SDK가
제공하지 않는 type stub과 legacy 전체를 strict type 검사한 결과는 아닙니다.

`KUBERNETES_CLIENT_TEST_CONFIG`에 별도 kubeconfig를 지정한 뒤 실행하세요.
integration은 cluster CRD/RBAC/StorageClass/ResourceSlice를 생성하고 기본
system:discovery 권한을 잠시 바꾼 뒤 원복합니다. 반드시 disposable cluster를
사용하세요. 기본 사용자 context나 운영 cluster를 대상으로 삼지 않습니다.

```shell
python -m unittest discover -s tests/integration -v
python examples/quickstart.py --kubeconfig /path/to/test-config --namespace guide-example
```

GitHub Actions의 Verify interface workflow는 Python 3.10–3.14와 SDK36.0.3/
37.0.0b1 unit matrix를 실행합니다. preview lane은 안정 SDK의 지원 선언과 구분합니다.
integration은 kind v0.33.0으로 서버 1.35.8/1.36.4/1.37.1의 안정 SDK와
1.37.1의 preview SDK를 시험합니다. 1.35.8/1.36.4는 공식 node digest를 사용하고
1.37.1은 SHA256을 확인한 공식 release tarball과 고정 base image로 빌드합니다.
ClusterTrustBundle 신규 stable 사례는
1.37 lane의 필수 조건이며 다른 minor에서는 적용되지 않는 항목으로 skip합니다.

실제 실행 결과와 고정 revision은
[검증 기록](https://github.com/pydemia/kubernetes-client/blob/main/.worknote/implementation/validation.md)에 기록합니다. metadata의
dependency 범위가 그 안의 모든 패치·미래 SDK·모든 API와 addon의 완전 호환을
뜻하지 않습니다. alpha/beta, 외부 driver의 allocation, 인증 plugin 전체와
certificate signer controller workflow는 개별 환경에서 별도로 검증해야 합니다.

Publish to PyPI workflow는 release tag를 checkout하고 Verify interface의 unit,
package와 실제 cluster lane이 통과한 뒤 wheel/sdist를 다시 build/check합니다.
버전과 tag가 일치해야 하며 pypi environment의 Trusted Publishing으로 업로드합니다.
tag를 만드는 작업과 PyPI에 실제 공개하는 작업은 별도 상태입니다. 공개 후에는
깨끗한 환경에서 PyPI의 해당 버전을 설치하고 metadata·import·버전을 확인합니다.
