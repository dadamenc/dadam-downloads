# dadam-downloads
Large download assets for dadamenc website (catalogs, test reports)

## 사용법

`catalog-v1` / `test-reports-v1` release 페이지에서 원본 PDF를 올리거나 빼면 됨
(Edit release → 파일 드래그). 그 외 아무것도 할 필요 없음.

`.github/workflows/process-release.yml`이 자동으로:
- 새 PDF마다 썸네일(`*.thumb.jpg`)과 저화질 프리뷰(`*.preview.pdf`)를 만들어 같은
  release에 올림
- 전체 목록을 `catalog.json`에 정리해서 커밋함 (dadam-next.js 웹사이트가 이 파일을
  읽어서 다운로드 페이지를 구성함)

release 편집 이벤트가 안 잡힐 때를 대비해 30분마다도 한 번씩 돌고, 필요하면
Actions 탭에서 "Process release PDFs" 워크플로우를 수동 실행(Run workflow)해도 됨.
