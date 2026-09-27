# 배포 README 링크·project.urls 한정 검사 v5

검토일: 2026-09-27. 고정 입력은 `input-v5/README.md`와
`input-v5/pyproject.toml`, `input-v5.sha256`입니다. 다른 reviewer의 자료를
읽지 않았으며 원본 파일·이전 보고서를 변경하지 않았습니다. 이번 범위는
배포 README의 링크와 project.urls이며 예제 본문·runtime·테스트의
재검증이 아닙니다.

## 고정 입력 확인

Python hashlib로 두 파일의 SHA-256을 직접 계산했고 manifest와 일치했습니다.

```text
README.md
07229e3f02951f51fe8551d4980731567c545da0a87517ede526108a3a298e3f

pyproject.toml
cbedcdf370907b8c9aca970407f077174f935dd61519918008bd5dcde7a14931
```

Python 3.14의 tomllib로 pyproject를 읽었습니다. project.version은 1.0.0이며
project.urls는 다음 값으로 파싱됐습니다.

| metadata key | 확인한 대상 |
| --- | --- |
| Repository | https://github.com/pydemia/kubernetes-client |
| Documentation | https://github.com/pydemia/kubernetes-client/blob/v1.0.0/docs/usage.md |
| Issues | https://github.com/pydemia/kubernetes-client/issues |

README의 Markdown 링크를 추출해 절대 HTTPS URL인지 검사했습니다.
프로젝트 문서·예제·복구 기록 링크 5개는 모두 같은 repository의
`blob/v1.0.0/` 경로였고 pyproject의 version과 일치했습니다.

| README 대상 | tag 아래 경로 | 현재 작업 트리 파일 |
| --- | --- | --- |
| quickstart.py | examples/quickstart.py | 존재 |
| 사용 가이드 | docs/usage.md | 존재 |
| 이관 가이드 | docs/migration.md | 존재 |
| 검증·배포 가이드 | docs/validation.md | 존재 |
| RECOVERY.md | RECOVERY.md | 존재 |

파일 존재 검사는 해당 경로가 실제 프로젝트 파일인지 확인한 것입니다.
아직 만들어지지 않은 tag가 그 파일을 포함한다고 검증한 결과는 아닙니다.
공식 SDK repository 링크도 절대 HTTPS URL이며 상대 프로젝트 링크는
README에서 남지 않았습니다.

## 원격 응답과 판정

urllib.request의 HTTP HEAD로 다음 응답을 직접 확인했습니다. 네트워크 요청은
read-only이며 tag·repository·issue를 생성하거나 수정하지 않았습니다.

- Repository URL: HTTP 200.
- Issues URL: HTTP 200.
- GitHub API의 `git/ref/tags/v1.0.0`: HTTP 404.
- README의 v1.0.0 blob 링크 5개: 모두 HTTP 404.

v1.0.0 tag를 아직 생성하지 않았다는 조정자의 상태와 원격 응답이
일치합니다. URL의 repository·version·파일 경로는 올바르며 PyPI에서
repository 상대 경로를 요구하던 문제는 파일 내용에서 제거됐습니다.
이번 변경은 채택 가능하다고 판정합니다. 다만 현재 tag 링크가 열리는
상태는 아니므로 원격 문서 접근까지 검증 완료로 표시하지 않습니다.

tag 생성 뒤에는 Documentation URL과 README의 tag 링크 5개가 HTTP 200을
반환하고 의도한 release 파일을 보여주는지 확인해야 합니다. 동일한 URL의
상태를 후속 확인하면 되며 링크를 다른 branch로 바꿀 필요는 없습니다.

## 실제 확인·미확인 범위

직접 확인한 것은 두 hash, TOML 문법과 project.urls 값, README 링크의
scheme·repository·version·파일 경로 및 현재 원격 HTTP 응답입니다.
wheel의 Project-URL metadata, PyPI에 표시되는 링크, 공개 PyPI 설치는
이번 reviewer가 검사하지 않았습니다. 최종 unit 10조합·latest live·wheel
설치가 완료됐다는 내용은 조정자가 제공한 상태이며 이 reviewer의 실행
결과로 재기록하지 않았습니다.

실제 모델·effort를 확인할 runtime metadata는 제공되지 않았으며 설정을
변경하지 않았습니다. release tag와 PyPI 공개의 완료 여부는 이번 파일
검사의 통과와 구분합니다.
