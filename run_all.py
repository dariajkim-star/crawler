# 사람인 + 고용24 + LinkedIn 크롤러를 전부 실행하고
# 1) 소스별 csv/json 저장
# 2) all_jobs.csv / all_jobs.json 으로 통합 저장 (대시보드 job_board.html이 읽는 파일)
#
# 효율화: 소스 3개를 스레드로 "동시에" 크롤링 (사이트별 요청 간격 2초는 그대로 유지)
# 키워드/직군은 config.py에서 관리

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

import saramin
import work24
import linkedin
from config import ALL_KEYWORDS, KEYWORD_TO_CATEGORY, MAX_PAGES
from scoring import is_noise, score_job

BASE_DIR = Path(__file__).parent

# 통합 파일에 들어갈 공통 컬럼
COMMON_COLS = ["출처", "직군", "검색어", "공고 이름", "회사 이름", "회사 위치",
               "게시일", "마감일", "링크", "점수", "워치리스트"]

SOURCES = [
    ("사람인", saramin, "saramin_result"),
    ("고용24", work24, "work24_result"),
    ("LinkedIn", linkedin, "linkedin_result"),
]


def run_source(name, module, filename):
    """크롤러 모듈 하나를 전체 키워드로 실행하고 소스별 파일 저장"""
    rows = []
    for i, kw in enumerate(ALL_KEYWORDS, 1):
        rows.extend(module.crawling_data(kw, max_pages=MAX_PAGES))
        # 병렬 실행 시 tqdm 진행바가 섞여 보이므로, 읽기 쉬운 완료 로그를 따로 남김
        print(f"[{name}] '{kw}' 완료 ({i}/{len(ALL_KEYWORDS)})", flush=True)

    df = pd.DataFrame(rows)
    if df.empty:
        print(f"[{name}] 수집된 공고 없음", flush=True)
        return df

    df = df.drop_duplicates(subset=["링크"]).reset_index(drop=True)
    df["직군"] = df["검색어"].map(KEYWORD_TO_CATEGORY).fillna("기타")
    print(f"[{name}] {len(df)}건 수집", flush=True)

    df.to_csv(BASE_DIR / f"{filename}.csv", index=False, encoding="utf-8-sig")
    df.to_json(BASE_DIR / f"{filename}.json", orient="records", force_ascii=False, indent=2)

    df["출처"] = name
    return df


def main():
    # 소스 3개를 병렬로 (같은 사이트에 동시 요청하는 게 아니므로 각 사이트 부담은 동일)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(run_source, name, module, filename)
                   for name, module, filename in SOURCES]
        frames = [f.result() for f in futures]

    merged = pd.concat(frames, ignore_index=True)

    # 노이즈 필터: 제목에 제외 키워드(보험영업 등)가 있으면 버림
    before = len(merged)
    merged = merged[~merged["공고 이름"].map(is_noise)].reset_index(drop=True)
    print(f"노이즈 필터: {before - len(merged)}건 제외", flush=True)

    # 스코어링 (신규 가점은 이력DB를 아는 run_and_notify에서 반영)
    scored = merged.apply(lambda r: score_job(r), axis=1)
    merged["점수"] = [s[0] for s in scored]
    merged["워치리스트"] = [s[1] for s in scored]

    # 소스마다 컬럼이 조금씩 달라서 공통 컬럼으로 정리 (없는 컬럼은 빈칸)
    for col in COMMON_COLS:
        if col not in merged.columns:
            merged[col] = ""
    merged = merged[COMMON_COLS].fillna("")

    print(merged["출처"].value_counts(), flush=True)
    print(f"통합 {len(merged)}건 저장", flush=True)

    merged.to_csv(BASE_DIR / "all_jobs.csv", index=False, encoding="utf-8-sig")
    merged.to_json(BASE_DIR / "all_jobs.json", orient="records", force_ascii=False, indent=2)
    return merged


if __name__ == "__main__":
    main()
