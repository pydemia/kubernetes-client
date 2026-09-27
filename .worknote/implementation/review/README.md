# 구현 리뷰 입력과 판정

기준 요구는 `../../04-final-implementation-plan.md`다. 입력은 미커밋 자료를
복사한 snapshot과 상대 경로 SHA256 manifest로 고정했다. 과거 입력과 보고서는
덮어쓰지 않았다. 실제 읽은 범위·실행·미검증은 각 raw report에 있다.

| 입력 | 범위 | 보고서 |
| --- | --- | --- |
| input-v1 | 최초 구현·테스트·metadata | usability/sdk/validation-v1.md |
| input-v2 | 최초 지적 수정·가이드·배포 workflow | usability/sdk/validation-v2.md |
| input-v3 | SDK-I04 잔존, US-04/05, latest patch 검증 설정 | usability/sdk/validation-v3.md |
| input-v4 | preview job의 배포 조건 분리, 검증 가이드 2개 파일 | validation-v4.md |
| input-v5 | PyPI README의 절대 가이드 URL과 project.urls | usability-v5.md |

사용성 reviewer는 facade 작업 완료·이관·예제, SDK reviewer는 정확한 GVK,
discovery·serializer·transport 수명, 검증 reviewer는 watch/wait 경합·오류·
실제 검증 근거와 배포 gate를 맡았다. 세 독립 1차 reviewer에게 서로의
보고서를 제공하지 않았고 각자 원본을 수정하지 않도록 했다.
후속 검토는 해당 finding·변경만 다룬다. 실제 모델·effort는 runtime metadata가
없어 확인 불가로 기록했으며 임의로 모델 설정을 바꾸지 않았다.

채택·수정·재검증 판정은 `../decisions.md`, 조정자가 별도로 실행한 matrix,
live cluster와 package·guide·배포 결과는 `../validation.md`에 연결했다.
독립 reviewer의 probe는 API server·GitHub Actions·PyPI 실행 증거가 아니다.
