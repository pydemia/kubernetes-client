# preview 배포 조건 분리 한정 검토: input-v4

검토일: 2026-09-27. v3 보고서의 판정은 변경하지 않았다. input-v4의 두 파일만
v3와 비교하고 GitHub 공식 규칙을 확인했다. 원본 구현·workflow를 수정하거나
다른 reviewer 보고서를 읽지 않았다. 두 파일의 hash는 manifest와 일치했다.

- `.github/workflows/verification.yml`
  SHA256 `e070d962a1f4592e3f287dcf21b883c67f4a65e37b2f98e82587d7322c19d4f9`
- `docs/validation.md`
  SHA256 `9fd1d6c170267d2ab755928295af49fc7f7ca1a8e1608d3da5f153d9e25979db`

manifest 자체 SHA256:
`ea74dd77e9d1bc9672865dcf4f6db09dcb378786be8056b6b29186047979d96f`

verification.yml:19와 61에 job 수준의 아래 조건이 각각 추가됐다.

```yaml
continue-on-error: ${{ matrix.sdk == '37.0.0b1' }}
```

matrix 값이 36.0.3인 모든 unit·integration job에는 False가 적용된다.
따라서 안정 SDK의 unit, baseline package 검사, 세 server lane의 실패는
verification 실패로 남고 기존 publish의 verify→build→publish 경로를
차단한다. preview SDK37.0.0b1의 unit·1.37.1 integration job에는 True가
적용돼 그 실패만으로 workflow 전체를 실패시키지 않는다. matrix별 조건은
GitHub가 공식 예제로 제공하는 job 수준의 continue-on-error 방식과 맞는다.
[GitHub 공식 규칙](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#jobsjob_idcontinue-on-error)

두 matrix의 fail-fast=False는 유지된다. 이는 다른 matrix job을 조기 취소하지
않는 조건이며 안정 실패를 성공으로 바꾸는 설정은 아니다. step 명령에
`|| true`나 exit code를 성공으로 바꾸는 조치는 추가되지 않았다. preview는
별도 matrix job과 step 로그로 조사할 수 있지만 workflow 전체의 녹색 상태를
preview 통과 증거로 사용해서는 안 된다. 별도 preview 요약 파일이나 결과
artifact를 생성하는 단계는 없다.

docs/validation.md:28–30은 preview를 안정 지원 선언·배포 필수 조건에서
제외하고 실패 결과를 별도로 확인하도록 명시한다. 43–44의 publish 조건도
안정 SDK unit/package/cluster의 통과로 한정됐다. 정적 구성과 문서의 의미는
일치하며 한정 범위의 새 차단 결함은 발견하지 못했다.

수행한 검증은 hash 대조, 두 파일 diff, 공식 GitHub 의미의 확인이다.
GitHub에서 의도적인 안정/preview 실패를 실행하거나 reusable 호출의 결과와
UI 표시를 실측하지 않았다. CI 성공·실패 lane 검증 완료나 PyPI 게시 완료로
판정하지 않는다.
