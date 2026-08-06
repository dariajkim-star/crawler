# JobScope — 채용공고 크롤러 & 대시보드

사람인 · 고용24 · LinkedIn · We Work Remotely · 피플앤잡 다섯 곳의 채용공고를
**금융/컨설팅/AI 직군 키워드**로 매일 자동 수집해서 CSV/JSON으로 저장하고,
웹 대시보드와 **슬랙 알림**으로 보여주는 프로젝트.

📄 상세 문서: [개발명세서](docs/개발명세서.md) · [API 명세서](docs/API명세서.md)

## 시스템 아키텍처

```
                       ┌──────────────┐
                       │  config.py   │  키워드/직군, 워치리스트, 스킬,
                       │  (단일 설정)  │  가중치, 노이즈 필터, MAX_PAGES
                       └──────┬───────┘
                              │ ALL_KEYWORDS · KEYWORD_TO_CATEGORY
    ┌──────────┬──────────────┼──────────────┬──────────┐   ← ThreadPoolExecutor
    ▼          ▼              ▼              ▼          ▼
┌────────┐┌────────┐┌──────────────┐┌─────────────┐┌──────────┐
│saramin ││ work24 ││   linkedin   ││weworkremotely││peoplenjob│
│ HTML   ││ HTML   ││ guest API    ││    HTML      ││   HTML   │  requests
└───┬────┘└───┬────┘└──────┬───────┘└──────┬───────┘└────┬─────┘  + BS4
    │         │            │               │             │        sleep 2s
    │         └─── *_result.csv / *_result.json (소스별) ─┘
    └───────────────────────┬─────────────────────────────┘
                            ▼
                   ┌─────────────────┐
                   │    run_all.py   │  링크 중복제거 → 직군 매핑 →
                   │  (통합 파이프)   │  is_noise() 필터 → score_job()
                   └───┬─────────┬───┘
                       │         │ scoring.py (점수 = 직군가중치×10
                       │         │            +스킬5×n +워치30 +신규10 +임박5)
                       ▼         ▼
             all_jobs.csv   all_jobs.json ──→ job_board.html (대시보드)
                       │                      server.py (FastAPI, 버튼 크롤링)
                       ▼
       ┌───────────────────────────────┐
       │      run_and_notify.py        │  매일 17:00 스케줄러
       │  history.py → jobs_history.db │  first_seen/last_seen/seen_count
       │  jd_match.py (Top 12건 JD 열람)│  → 신규공고·신규회사 판정
       │  → Slack (웹훅/토큰)           │
       └───────────────┬───────────────┘
                       ▼
             weekly_report.py  (월 09:00) → Obsidian .md + Slack
```

### 크롤러별 메트릭스

| | 사람인 | 고용24 | LinkedIn | WWR | 피플앤잡 |
|---|---|---|---|---|---|
| 방식 | HTML `div.item_recruit` | HTML `tr[id^=list]` | guest API | HTML `li.new-listing-container` | HTML `div.jd-card` |
| 페이징 | `recruitPage=N` | `currentPageNo` | `start=0,25,50…` | 없음(단일 페이지) | `page=N` |
| 페이지당 | ~20건 | 10건 | 25건 | ~34건(전체) | 30건 |
| 요청 간격 | 2초 | 2초 | 2초 + 429 백오프 | 2초 | 2초 |
| 게시일 | ○ | ✕ | ○ | ○ (상대날짜 환산) | ○ |
| 마감일 | ○ (`MM/DD`) | ○ (`YYYY-MM-DD`) | ✕ | ✕ | ○ (`YYYY-MM-DD`) |
| 특이사항 | `rec_idx` 링크 정규화 | 제목 한정 검색 | 한국 지역 필터 | 광고 카드 제외 | JD 본문까지 검색 매칭 |

## 파일 구성

| 파일 | 설명 |
|---|---|
| `config.py` | **키워드/설정** — 직군(8개)×키워드(41개), 워치리스트, 내 스킬, 직군 가중치, 노이즈 제외어 |
| `saramin.py` | 사람인 크롤러 (페이지당 40건, 링크 rec_idx 정규화) |
| `work24.py` | 고용24 크롤러 (페이지당 10건, 연봉·경력·근무형태 포함) |
| `linkedin.py` | LinkedIn 크롤러 — 로그인 불필요한 공개(게스트) API |
| `weworkremotely.py` | We Work Remotely 크롤러 — 해외 원격직, 검색 결과 단일 페이지 |
| `peoplenjob.py` | 피플앤잡 크롤러 — 외국계기업 채용, 페이지당 30건 |
| `run_all.py` | **크롤러 5개 병렬 일괄 실행** → 노이즈 필터 → 스코어링 → `all_jobs.csv/json` 통합 |
| `scoring.py` | 공고 점수화 (직군 가중치 + 스킬/워치리스트/신규/마감임박 가점) + 노이즈 판정 |
| `history.py` | **이력 DB** (`jobs_history.db`, SQLite) — 신규 공고/처음 보는 회사/반복 채용 분석 |
| `jd_match.py` | Top 공고의 JD 상세를 열어 내 스킬 매칭 확인 |
| `run_and_notify.py` | 크롤링 + 이력 적재 + **슬랙 알림 (워치리스트 신규 + 오늘의 Top 10)** — 매일 17:00 |
| `weekly_report.py` | **주간 리포트** → Obsidian 저장 + 슬랙 알림 — 매주 월 09:00 |
| `server.py` | 대시보드 서버 (FastAPI) — 웹에서 버튼 한 번으로 전체 크롤링 |
| `job_board.html` | 대시보드 — 출처/직군/지역/내상태 필터, 추천순 정렬, ⭐관심기업, 북마크/지원함 |
| `docs/` | 개발명세서, API명세서 |
| `crawler_competition.py` 등 | (수업용) 연습 코드 |

## 수집 키워드 (config.py에서 수정)

| 직군 | 가중치 | 키워드 |
|---|---|---|
| IBD | 3 | IBD, IB, 투자은행, M&A, ECM, DCM, 기업금융, 인수합병 |
| 애널리스트 | 3 | 애널리스트, Analyst, 리서치센터, Equity Research, 크레딧 |
| 증권 | 3 | 증권, 자산운용, 펀드매니저, IPO, 트레이딩 |
| CFA | 2 | CFA |
| 컨설팅 | 2 | 전략컨설팅, 경영컨설팅 |
| AI | 2 | AI, 인공지능, 머신러닝, ML, 딥러닝, 데이터사이언스, LLM, openCV, 컴퓨터비전 |
| AI오케스트레이션 | 1 | AI 오케스트레이션, AI Agent, AI 에이전트, MLOps, LLMOps, RAG, LangChain |
| AX/DX | 1 | AX, AI 전환, 디지털전환, DX |

> 2026-08-06에 범용어라 노이즈가 많던 `채권`, `CPA`, `회계사`, `회계법인`, `컨설팅`, `컨설턴트`를 제외.
> `회계/CPA` 직군은 키워드가 모두 빠져 삭제됨 (스코어링용 `MY_SKILLS`의 CPA·회계는 그대로 유지).

## 사용법

### 1. 크롤링만 돌리기 (터미널)
```bash
python run_all.py                    # 전체 (41키워드 × 10페이지 × 5소스 병렬, 약 25분)
MAX_PAGES=3 python run_all.py        # 빠르게 (키워드당 3페이지)
```
- 결과: `saramin_result.*`, `work24_result.*`, `linkedin_result.*`, `weworkremotely_result.*`,
  `peoplenjob_result.*` + 통합 `all_jobs.csv/json`
- 개별 실행: `python saramin.py` 등

### 2. 대시보드 + 버튼 크롤링
```bash
python server.py
# → http://localhost:8010
```
- **[🔄 전체 크롤링 실행]** 버튼 → 진행상태 실시간 표시 → 완료 시 자동 새로고침
- API: `POST /api/crawl?pages=10`, `GET /api/crawl/status` ([API 명세서](docs/API명세서.md))

### 3. 매일 17:00 자동 크롤링 + 슬랙 알림
Windows 작업 스케줄러에 `JobScope_Daily_Crawl` 작업이 등록되어 있음 (매일 17:00 `run_and_notify.py` 실행).

**슬랙 알림 설정 — 완료됨 (2026-07-13):**
- 워크스페이스에 "JobScope 알리미" 앱(A0BHP0LSSG0) 생성·설치 완료, Webhook URL이 `slack_webhook.txt`에 저장됨
- 다른 채널로 바꾸려면: https://api.slack.com/apps/A0BHP0LSSG0 → Incoming Webhooks → Add New Webhook → 새 URL을 `slack_webhook.txt`에 교체
- 코드의 전송 우선순위: `slack_webhook.txt`(웹훅) → `slack_token.txt`(토큰, chat.postMessage) → 미설정 시 알림 생략

알림 내용: 총 수집 건수, 소스별 건수, **오늘 새로 뜬 공고 N건 + 미리보기 5건(링크)**. 실패 시에도 에러 알림이 옴.

스케줄 관리:
```powershell
schtasks /Query /TN "JobScope_Daily_Crawl"    # 확인
schtasks /Run   /TN "JobScope_Daily_Crawl"    # 즉시 실행 (테스트)
schtasks /Delete /TN "JobScope_Daily_Crawl" /F # 삭제
```

### 4. Figma 연동
- Figma 파일: [JobScope 채용보드](https://www.figma.com/design/eDHh7mwNAqrb6AHVdulrNZ)
- `job_board.html`에 캡처 스크립트 상주 → 데이터 갱신 후 Claude에게 "Figma로 캡처해줘" 요청 (또는 캡처 툴바에서 수동 재캡처)

## 필요한 패키지
```bash
pip install requests beautifulsoup4 pandas tqdm fastapi uvicorn
```

## 데이터 스키마 (all_jobs)
`출처, 직군, 검색어, 공고 이름, 회사 이름, 회사 위치, 게시일, 마감일, 링크`
(공고는 실시간으로 등록/마감되므로 실행 시점마다 건수가 달라짐)

## 스코어링 & 맞춤 알림 (v1.4)

**공고 점수** = 직군 가중치×10 + 제목 스킬 매칭(개당 +5) + 워치리스트(+30) + 신규(+10) + 마감 D-3(+5)

`config.py`에서 본인에 맞게 수정하는 것들:
- `WATCHLIST` — 관심 회사 (공고 뜨면 슬랙에 ⭐ 강조 + 점수 가점)
- `MY_SKILLS` — 내 무기 키워드 (제목 가점 + Top 10 공고의 JD 상세 매칭에 사용)
- `CATEGORY_WEIGHTS` — 직군 우선순위
- `EXCLUDE_TITLE_KEYWORDS` — 노이즈 제외어 (보험영업 등)

**매일 17:00 슬랙 알림**: 총건수 → ⭐관심 회사 신규 → 🏆오늘의 Top 10 (점수 + JD 스킬 매칭)
**매주 월 09:00 주간 리포트**: 직군별 추이 · 처음 등장한 회사(경쟁 적은 포지션) · 반복 채용 회사 → Obsidian `JobScope_주간리포트_날짜.md`

이력 DB(`jobs_history.db`)에 모든 공고의 최초/최종 목격일이 누적되므로, 데이터가 쌓일수록 신규 탐지와 주간 리포트가 정확해짐.

## 변경 이력
- **2026-08-06 (v1.5)**: 크롤러 2종 추가 — `weworkremotely.py`(해외 원격직), `peoplenjob.py`(외국계기업). 소스 3개 → **5개 병렬**. 노이즈가 많던 범용 키워드 6개(채권/CPA/회계사/회계법인/컨설팅/컨설턴트) 제외 → 직군 9→8, 키워드 47→41. README에 시스템 아키텍처·크롤러 메트릭스 추가.
- **2026-07-13 (v1.4)**: 구직 효율화 7종 — ①관심회사 워치리스트 ②공고 스코어링+슬랙 Top 10 ③SQLite 이력DB(신규/반복채용 분석) ④JD 상세 스킬 매칭 ⑤노이즈 블랙리스트 ⑥주간 리포트→Obsidian(월 09:00) ⑦대시보드 북마크/지원함+추천순 정렬. 사람인 링크 rec_idx 정규화로 중복 수집 버그 수정(-3,739건).
- **2026-07-13 (v1.3)**: 키워드 확장 (7개 → 직군 8개 × 36개, `config.py` 분리) · `직군` 컬럼/필터 추가 · **소스 3개 병렬 크롤링(~3배 빠름)** · `run_and_notify.py` + Windows 작업 스케줄러(매일 17:00) + 슬랙 알림(신규 공고 diff) · 개발명세서/API명세서 작성
- **2026-07-08 (v1.2)**: `server.py` 추가 — 버튼 한 번으로 전체 크롤링 + 진행상태 + 자동 새로고침. html/json 캐시 금지(no-store). README 작성.
- **2026-07-08 (v1.1)**: `work24.py`(고용24) 신규, `saramin.py` 저장/페이징 개선, `run_all.py` 통합, 대시보드 3소스 필터/뱃지, Figma 재캡처.
- **2026-07-07 (v1.0)**: `linkedin.py` 신규, JobScope 대시보드 제작, Figma 디자인 푸시.

## 주의
- 크롤링 대상 사이트의 이용약관을 준수하고, 요청 간격(2초)을 지켜 개인 학습/구직 용도로만 사용할 것.
- LinkedIn은 비공식 엔드포인트라 응답 구조가 바뀌면 `linkedin.py`의 `parse_jobs()` 셀렉터를 수정해야 함.
- 피플앤잡은 키워드가 JD 본문까지 매칭돼서 제목과 무관한 공고가 섞임 (직군 매핑/스코어링에서 걸러짐).
- `slack_webhook.txt`는 비밀값이므로 GitHub에 올리지 말 것 (.gitignore 권장).
