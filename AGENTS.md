# dadam-downloads — 에이전트 지침

회사 홈페이지(`dadam-next.js`) 다운로드 페이지용 대용량 PDF 저장소 (카탈로그·시험성적서).

- PDF 원본은 GitHub Release `catalog-v1` / `test-reports-v1` 에 올리고 뺀다. 저장소에 PDF 커밋하지 말 것.
- `.github/workflows/process-release.yml` 이 자동으로 썸네일(`*.thumb.jpg`)·저화질 프리뷰(`*.preview.pdf`) 생성, `catalog.json` 갱신·커밋 (30분 주기 + 수동 실행 가능).
- `catalog.json` 형식을 바꾸면 홈페이지가 깨짐 → 바꾸기 전에 `dadam-next.js` 쪽 읽는 코드도 같이 확인.
- 코드 주석은 한국어.
