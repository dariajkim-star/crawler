# JobScope — 채용공고 크롤러 & 대시보드

사람인 · 고용24 · LinkedIn 세 곳의 채용공고를 키워드로 크롤링해서 CSV/JSON으로 저장하고,
프로페셔널한 채용보드 스타일의 웹 대시보드(JobScope)로 보여주는 프로젝트.

## 파일 구성

| 파일 | 설명 |
|---|---|
| `saramin.py` | 사람인 크롤러 (키워드 × 최대 10페이지, 페이지당 40건) |
| `work24.py` | 고용24(work24.go.kr) 크롤러 (페이지당 10건, 연봉·경력·근무형태 포함) |
| `linkedin.py` | LinkedIn 크롤러 — 로그인 불필요한 공개(게스트) API 사용 |
| `run_all.py` | **크롤러 3개 일괄 실행** → 소스별 파일 + `all_jobs.csv/json` 통합 저장 |
| `server.py` | 대시보드 서버 (FastAPI) — 웹에서 버튼 한 번으로 전체 크롤링 실행 |
| `job_board.html` | JobScope 대시보드 — 출처/키워드/지역 필터, 검색, 정렬 |
| `crawler_competition.py` / `crawler_multiple.py` | (수업용) 청원24 크롤링 연습 코드 |
| `musinsa.py`, `streamlit_component.py` | (수업용) 기타 연습 코드 |

## 사용법

### 1. 크롤링만 돌리기 (터미널)
```bash
python run_all.py
```
- 기본 키워드: `AI, 애널리스트, 데이터사이언스, 머신러닝, ML, SQL, openCV` (`run_all.py`의 `KEYWORDS`에서 수정)
- 키워드당 최대 10페이지 (환경변수 `MAX_PAGES`로 조절)
- 결과: `saramin_result.csv/json`, `work24_result.csv/json`, `linkedin_result.csv/json`, 통합 `all_jobs.csv/json`
- 개별 실행도 가능: `python saramin.py`, `python work24.py`, `python linkedin.py`

### 2. 대시보드 + 버튼 크롤링 (추천)
```bash
python server.py
# → http://localhost:8010
```
- 대시보드 우측 상단의 **[🔄 전체 크롤링 실행]** 버튼을 누르면 크롤러 3개가 순서대로 돌고,
  진행 상황이 버튼 옆에 표시되다가 끝나면 데이터가 자동 새로고침됨 (전체 약 10분)
- 크롤링 로그: `crawl_log.txt`
- API: `POST /api/crawl?pages=10` (크롤링 시작), `GET /api/crawl/status` (진행 상태)
- 참고: `python -m http.server`로 열면 보기만 가능하고 버튼은 동작 안 함

### 3. Figma 연동
- 대시보드 화면이 Figma 파일로 캡처되어 있음: [JobScope 채용보드](https://www.figma.com/design/eDHh7mwNAqrb6AHVdulrNZ)
- `job_board.html` head에 Figma 캡처 스크립트가 상주 → 데이터 갱신 후 브라우저의 캡처 툴바에서 재캡처 가능
  (또는 Claude에게 "Figma로 다시 캡처해줘"라고 요청)

## 필요한 패키지
```bash
pip install requests beautifulsoup4 pandas tqdm fastapi uvicorn
```

## 수집 데이터 (2026-07-08 실행 기준)

| 출처 | 건수 |
|---|---|
| 사람인 | 2,568 |
| LinkedIn | 259 |
| 고용24 | 135 |
| **통합 (중복 제거)** | **2,962** |

(공고는 실시간으로 등록/마감되므로 실행 시점마다 건수가 달라짐)

통합 컬럼: `출처, 검색어, 공고 이름, 회사 이름, 회사 위치, 게시일, 마감일, 링크`

## 변경 이력
- **2026-07-08 (v1.2)**: `server.py` 추가 — 대시보드에서 버튼 한 번으로 전체 크롤링 실행 + 진행상태 표시 + 완료 시 자동 새로고침. json fetch에 `cache: no-store` 적용(크롤링 직후 브라우저가 캐시된 옛 데이터를 보여주던 문제 수정). README 작성.
- **2026-07-08 (v1.1)**: `work24.py`(고용24) 신규, `saramin.py` 저장/페이징 개선, `run_all.py` 통합 실행, 대시보드 3개 소스 필터/뱃지, Figma 재캡처(node 2-2).
- **2026-07-07 (v1.0)**: `linkedin.py` 신규, JobScope 대시보드(`job_board.html`) 제작, Figma 디자인 푸시(node 1-2).

## 주의
- 크롤링 대상 사이트의 이용약관을 준수하고, 요청 간격(2초 sleep)을 지켜 개인 학습/구직 용도로만 사용할 것.
- LinkedIn은 비공식 엔드포인트라 응답 구조가 바뀌면 `parse_jobs()`의 셀렉터를 수정해야 함.
