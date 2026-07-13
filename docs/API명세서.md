# JobScope API 명세서

> v1.3 · 2026-07-13 · Base URL: `http://localhost:8010` (server.py, FastAPI)

## 인증
없음 (로컬 전용 서버, `127.0.0.1` 바인딩)

## 공통 사항
- 응답 형식: JSON (API) / HTML·JSON 파일 (정적)
- `/`, `*.html`, `*.json` 응답에는 `Cache-Control: no-store`가 붙음 (항상 최신 보장)

---

## 1. POST /api/crawl — 전체 크롤링 실행

사람인 → 고용24 → LinkedIn 크롤러 3개를 백그라운드 서브프로세스로 일괄 실행한다.
(3개 소스는 내부적으로 병렬 처리)

### Request

| 파라미터 | 위치 | 타입 | 기본값 | 설명 |
|---|---|---|---|---|
| pages | query | int | 10 | 키워드당 최대 페이지 수 (환경변수 MAX_PAGES로 전달됨) |

```bash
curl -X POST "http://localhost:8010/api/crawl"
curl -X POST "http://localhost:8010/api/crawl?pages=3"   # 빠른 수집
```

### Response

**200 OK** — 크롤링 시작됨 (비동기, 완료는 status로 확인)
```json
{ "ok": true, "message": "크롤링 시작 (키워드당 최대 10페이지)" }
```

**409 Conflict** — 이미 크롤링 진행 중
```json
{ "ok": false, "message": "이미 크롤링이 돌고 있어요" }
```

---

## 2. GET /api/crawl/status — 크롤링 진행 상태

대시보드가 3초 간격으로 폴링하는 엔드포인트.

```bash
curl "http://localhost:8010/api/crawl/status"
```

### Response — 200 OK

```json
{
  "running": true,
  "started_at": "2026-07-13 17:00:01",
  "finished_at": null,
  "returncode": null,
  "progress": "[사람인] 'M&A' 완료 (4/36)"
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| running | bool | 크롤링 진행 중 여부 |
| started_at / finished_at | str\|null | 시작/종료 시각 |
| returncode | int\|null | 종료 코드 (0=성공, null=진행 중/미실행) |
| progress | str | `crawl_log.txt`의 마지막 로그 줄 |

상태 판별:
- `running=true` → 진행 중
- `running=false, returncode=0` → 성공 (all_jobs.json 갱신됨)
- `running=false, returncode≠0` → 실패 (crawl_log.txt 확인)

---

## 3. GET / — 대시보드

`job_board.html`을 반환한다.

## 4. 정적 파일 (StaticFiles)

API 라우트에 매칭되지 않는 경로는 프로젝트 폴더에서 파일을 찾아 서빙한다.

| 경로 | 내용 |
|---|---|
| `/job_board.html` | 대시보드 (= `/`) |
| `/all_jobs.json` | 통합 수집 결과 (대시보드 데이터 소스) |
| `/saramin_result.json` `/work24_result.json` `/linkedin_result.json` | 소스별 결과 |
| `/crawl_log.txt` | 최근 크롤링 로그 |

---

## 5. 외부 연동

### Slack Incoming Webhook (run_and_notify.py)
- 발신: `POST {SLACK_WEBHOOK_URL}` · Body `{"text": "<요약 메시지>"}`
- 메시지 구성: 총건수 / 소스별 건수 / 신규 공고 수 + 미리보기 5건(링크)
- URL 설정: 환경변수 `SLACK_WEBHOOK_URL` 또는 프로젝트 폴더의 `slack_webhook.txt`

### Figma 캡처 (수동/요청 시)
- `job_board.html` head의 `capture.js`가 `#figmacapture=<id>` 해시 URL로 열리면
  페이지를 직렬화해 `mcp.figma.com`으로 제출 → Figma 파일에 디자인 페이지 추가
- 캡처 ID는 1회용 (Figma MCP `generate_figma_design`으로 발급)
