# SDK-I04 discovery group/version 한정 재검증

고정 입력은 `input-v3/`와 `input-v3.sha256`이다. 양 SDK 실행에서 manifest의
26개 파일 SHA-256이 모두 일치했다. 자체 v1/v2 관측과 v3 수정본만 비교했고
다른 reviewer의 보고서는 읽지 않았다. 원본 구현과 고정 입력은 수정하지 않았다.
실제 모델·effort는 확인 불가이며 설정을 변경하지 않았다.

SDK-I04의 v2 잔존 조건은 이번 한정 범위에서 해결됐다. v2에서 빈 group version이
ResourceNotServedError로 분류됐으나 v3에서는 DiscoveryFormatError로 종료한다.
추가한 공백·불일치·preferredVersion 조건도 양 SDK에서 같은 결과를 확인했다.

## 수정과 실행 결과

`input-v3/kubernetes_client/resources.py:126`은 served version의 두 field가
빈 문자열이 아니고 양끝에 공백이 없는지 검사한다. 이어 groupVersion이
`group.name/version`과 일치하는지 검사한다.
`resources.py:141`은 preferredVersion에 같은 문자열 검사를 적용하고
`resources.py:151`은 그 두 field의 조합이 served versions에 포함되는지 확인한다.

아래 25개 오류 입력을 공식 SDK36.0.3과 37.0.0b1에 각각 전달했다.

| 입력 범위 | 사례 수 | 실제 결과 |
| --- | --- | --- |
| version의 빈 값, space/tab/newline, 양끝 공백 | 7 | DiscoveryFormatError |
| groupVersion의 빈 값, space/tab, 양끝 공백 | 5 | DiscoveryFormatError |
| group 이름 또는 version과 groupVersion 불일치 | 2 | DiscoveryFormatError |
| preferredVersion 두 field의 빈 값·공백 | 8 | DiscoveryFormatError |
| preferred version이 미제공 또는 field 조합 모순 | 2 | DiscoveryFormatError |
| 빈 served versions 목록 | 1 | DiscoveryFormatError |

각 오류 사례는 `/version`과 `/apis`만 한 번씩 호출했다. refresh하거나
grouped resource endpoint를 호출하지 않았으며 ResourceNotServedError와 내부
KeyError로 치환되지 않았다. response는 모두 닫혔고 실패한 dynamic/cache는
client에 남지 않았다. fixture를 정상 discovery로 바꾼 뒤 같은 client의
Deployment get이 성공하는 것도 각 사례에서 실행했다.

유효한 단일 served version과 복수 served version을 별도로 실행했다. 후자는
v1/v2를 제공하며 preferredVersion이 v2인 입력이다. 두 경우 모두 명시적으로
요청한 apps/v1 Deployment의 아래 endpoint를 조회했고 v2로 치환하지 않았다.

```text
/apis/apps/v1/namespaces/default/deployments/demo
```

이 실행은 원래 미등록 GVK와 invalid discovery를 구분하는 보정의 실패 조건을
해결했음을 보여준다. APIGroup schema의 모든 문법·값 제약을 검증했다는 뜻은
아니다. 이번 probe는 빈 값·공백 전용 값·양끝 공백, field 불일치와 served 목록
포함 여부로 범위를 고정했다.

## 실행 근거

Windows의 CPython 3.14.4, Pydantic 2.13.5, urllib3 2.8.0에서 실행했다.
제어 fixture는 실제 SDK DynamicClient·ApiClient·RESTClientObject를 경유하며
pool request에서 HTTPResponse를 제공한다. 실제 Kubernetes API server가 해당
malformed discovery를 보냈다는 주장은 아니다.

- `sdk-probe-v3.py`: 25개 오류 사례와 정상 사례 2개에 assertion을 둔 코드.
- `sdk-probe-v3-sdk36.jsonl`, `sdk-probe-v3-sdk37.jsonl`: version, 환경,
  manifest hash 일치 여부와 각 사례의 route·분류·정리·회복 결과.
- `input-v3/tests/test_interface.py:227`의 추가 regression을 읽고 전체
  unit 33개를 각 SDK에서 직접 실행했다. 양쪽 모두 통과했다.

repository root에서 probe를 실행한다. SDK37은 버전만 37.0.0b1로 바꾼다.

```powershell
uv run --no-project --python 3.14 --with kubernetes==36.0.3 --with pydantic==2.13.5 python .worknote/implementation/review/sdk-probe-v3.py
```

unit은 `input-v3/`에서 실행했다.

```powershell
uv run --no-project --python 3.14 --with kubernetes==36.0.3 --with pydantic==2.13.5 python -m unittest discover -s tests
```

SDK-I01/I02/I03의 전용 v2 probe, 실제 CRD·SSA·RBAC·신규 1.37 GVK와 live cluster,
Python 3.10–3.13, wheel/package 검증 및 배포는 이번 한정 재검증에서 다시
실행하지 않았다. 이들 판정과 실행 범위는 자체 v1/v2 기록과 조정자의 별도
실행 근거를 유지한다.
