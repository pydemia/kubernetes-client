# 사용성 targeted recheck v3

검토일: 2026-09-27. 검토 범위는 v2의 US-04와 US-05 두 항목입니다.
`usability-v1.md`와 `usability-v2.md`는 유지했습니다. 다른 reviewer의
보고서를 읽지 않았으며 원본 구현·문서·예제는 수정하지 않았습니다.

## 입력과 hash

고정 입력은 `input-v3/`와 `input-v3.sha256`입니다. manifest의 26개 파일을
직접 SHA-256 검사했으며 모두 일치했습니다. 내용 판단에 사용한 자료는
`examples/quickstart.py`, `docs/migration.md`와 namespace 선택을 담당하는
`kubernetes_client/resources.py`의 해당 부분입니다.

```text
examples/quickstart.py
0e37946c5fd98958c5106f1c185913d090b92d628693b393ce11258bd9fd1226

docs/migration.md
66886aa3a5032360df33afc5b82ff9339d32a156a884d0c4c185002c80ae2a91
```

아래 줄 번호는 v3 snapshot 기준입니다. 기존에 읽은 persona-cross-review
규칙을 적용했으며 모델 설정은 변경하지 않았습니다. 실제 모델·effort를
확인할 runtime metadata는 제공되지 않았습니다.

## 판정

| ID | 기존 중요도 | v3 한정 재검토 |
| --- | --- | --- |
| US-04 | P2 | 해결. 최적화 실행에서도 API 호출 순서가 유지됨 |
| US-05 | P3 | 해결. namespace의 metadata field 경로가 구현과 일치함 |

US-04의 수정 위치는 `examples/quickstart.py:23–35`입니다. 조회, 반복
apply, UID를 지정한 delete와 exists가 일반 실행문으로 옮겨졌습니다.
검사도 if/RuntimeError로 작성되어 최적화 실행에서 제거되지 않습니다.
Namespace 삭제·wait는 기존 finally 안에 유지됩니다.

v2에서 사용한 방식대로 snapshot의 예제를 compile(optimize=0/1)하고
기록용 FakeClient를 넣어 run을 실행했습니다. 두 실행 모두 성공했으며
아래 순서가 같았습니다. 특히 Secret 삭제가 wait_deleted보다 먼저
실행됐고 조회·반복 apply·exists도 빠지지 않았습니다.

```text
namespace.create → secret.apply → secret.get → secret.apply
→ secret.delete → secret.wait_deleted → secret.exists
→ namespace.delete → namespace.wait_deleted
```

실제 `python -O` 프로세스에서도 같은 snapshot 원문을 기본 compile 옵션으로
실행했습니다. `sys.flags.optimize == 1`을 확인하고 동일한 호출 순서를
관측했습니다. probe의 판정은 assert가 아닌 if/예외를 사용하여 최적화가
검사 자체를 생략하지 못하도록 했습니다. 이전의 삭제 없는 대기는 재현되지
않았으므로 US-04 해결 판정을 제안합니다.

US-05의 수정 위치는 `docs/migration.md:22`입니다. 잘못된 body.namespace가
body.metadata.namespace로 바뀌었습니다. `resources.py:249–251`에서 읽는
field 경로와 일치하며 후속 get/wait/delete에 같은 namespace를 bind하라는
설명도 유지됩니다. 코드·문서 검사로 확인했으며 서버 실행은 필요하지 않은
표기 수정입니다. US-05 해결 판정을 제안합니다.

## 실제 실행 범위

Python 3.14, SDK 36.0.3, Pydantic 2.13.5에서 compile(optimize=0/1) probe와
별도의 실제 python -O probe를 실행했습니다. 후자의 명령 형식은 다음과
같습니다.

```powershell
uv run --no-project --python 3.14 --with kubernetes==36.0.3 `
  --with pydantic==2.13.5 python -O -
```

FakeClient는 예제의 API 호출 순서, Secret 삭제 전 wait 금지와 UID 전달을
확인했습니다. 실제 HTTP 요청·API server·cleanup 성공을 검증한 것은
아닙니다. SDK37, 전체 unittest, integration, package, PyPI 공개·설치를
이번 한정 재검토에서 실행하지 않았습니다. v3의 다른 변경과 기존 US-01/02/03은
재검토 범위 밖이며 이 결과를 전체 release 완료 판정으로 확대하지 않습니다.
