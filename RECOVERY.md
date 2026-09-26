# 저장소 복구 기록

이 기록은 0.1.8 복구 커밋 `f5e691b` 기준입니다. 현재 개발 버전 0.1.9에는
호환성 수정이 반영되어 원본 wheel과 파일 내용이 다릅니다.

복구 당시 Python 패키지 파일은 PyPI의
`kubernetes_client-0.1.8-py3-none-any.whl`에서 추출했습니다. 원래 Git 이력과
0.1.8을 빌드할 때 사용한 소스 전용 파일은 배포 파일에 없어 복원할 수 없습니다.

참조한 PyPI 파일
([0.1.0](https://pypi.org/project/kubernetes-client/0.1.0/#files),
[0.1.8](https://pypi.org/project/kubernetes-client/0.1.8/#files)):

| 버전 | 파일 | SHA-256 |
| --- | --- | --- |
| 0.1.0 | `kubernetes-client-0.1.0.tar.gz` | `4b06ad5c05f1d89f54260255a0464942cab7695443d7b70cd636d810a50b7069` |
| 0.1.8 | `kubernetes_client-0.1.8-py3-none-any.whl` | `c4fe424ab0f195b5f0c4c42851b9f37ed649ea2b9082506f6949c4d6cfb19e13` |

두 파일은 PyPI에서 내려받아 게시된 SHA-256 값과 대조했습니다.
복구 커밋의 `kubernetes_client/` 파일은 0.1.8 wheel과 바이트 단위로
같습니다.
별도 가상환경에 wheel을 설치한 뒤 `site-packages`의 Python 파일 7개와도
대조했습니다.

0.1.0 소스에는 `kubernetes-client/__init__.py`와 `__version__.py`만
있었습니다. 0.1.8 wheel에서는 패키지 디렉터리가 `kubernetes_client`로
바뀌고 `base.py`, `enums.py`, `kfserving.py`, `schema.py`, `utils.py`가
추가됐습니다. `__init__.py`는 `KubernetesManager`를 내보냅니다.

복구 당시 `pyproject.toml`은 새로 작성했습니다. 패키지명, 버전, Python
요구 버전, 작성자 이메일, 설명과 의존성은 0.1.8 wheel의 `METADATA`에
따랐습니다.
0.1.0 소스 배포본의 `setup.py`에서 setuptools 기반 빌드 방식을
확인했습니다. 원본 0.1.8 `setup.py`, 요구 사항 파일, 테스트와 배포
절차는 확인할 수 없어 임의로 재현하지 않았습니다.

0.1.8 복구 커밋에서 wheel과 sdist를 빌드했습니다. 새 wheel의 패키지 파일
7개는 원본 wheel과 같고, 이름·버전·설명·작성자 이메일·Python 요구 버전·
의존성도 일치합니다. Python 3.11, NumPy 1.23.5, Pydantic 1.10.26에서
원본 wheel의 import와 `encode_b64`/`decode_b64`를 확인했습니다.

Python 3.13에서 최신 의존성을 설치한 환경은 import에 실패했습니다.
`table-logger` 0.3.6이 NumPy 2.5.3에서 제거된 `np.float`를 참조하기
때문입니다. 원본 wheel에서 확인한 문제이며 복구한 Python 파일은 수정하지
않았습니다.
