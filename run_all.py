# 사람인 + 고용24 + LinkedIn 크롤러를 전부 실행하고
# 1) 소스별 csv/json 저장
# 2) all_jobs.csv / all_jobs.json 으로 통합 저장 (대시보드 job_board.html이 읽는 파일)

import os

import pandas as pd

import saramin
import work24
import linkedin

KEYWORDS = ["AI", "애널리스트", "데이터사이언스", "머신러닝", "ML", "SQL", "openCV"]
# server.py가 환경변수로 페이지수를 조절할 수 있게 함 (기본 10)
MAX_PAGES = int(os.environ.get("MAX_PAGES", "10"))

# 통합 파일에 들어갈 공통 컬럼
COMMON_COLS = ["출처", "검색어", "공고 이름", "회사 이름", "회사 위치", "게시일", "마감일", "링크"]


def run_source(name, module):
    """크롤러 모듈 하나를 전체 키워드로 실행하고 소스별 파일 저장"""
    rows = []
    for kw in KEYWORDS:
        rows.extend(module.crawling_data(kw, max_pages=MAX_PAGES))

    df = pd.DataFrame(rows)
    if df.empty:
        print(f"[{name}] 수집된 공고 없음")
        return df

    df = df.drop_duplicates(subset=["링크"]).reset_index(drop=True)
    print(f"[{name}] {len(df)}건 수집")

    filename = {"사람인": "saramin_result", "고용24": "work24_result", "LinkedIn": "linkedin_result"}[name]
    df.to_csv(f"./{filename}.csv", index=False, encoding="utf-8-sig")
    df.to_json(f"./{filename}.json", orient="records", force_ascii=False, indent=2)

    df["출처"] = name
    return df


if __name__ == "__main__":
    frames = []
    for name, module in [("사람인", saramin), ("고용24", work24), ("LinkedIn", linkedin)]:
        frames.append(run_source(name, module))

    merged = pd.concat(frames, ignore_index=True)

    # 소스마다 컬럼이 조금씩 달라서 공통 컬럼으로 정리 (없는 컬럼은 빈칸)
    for col in COMMON_COLS:
        if col not in merged.columns:
            merged[col] = ""
    merged = merged[COMMON_COLS].fillna("")

    print(merged["출처"].value_counts())
    print(f"통합 {len(merged)}건 저장")

    merged.to_csv("./all_jobs.csv", index=False, encoding="utf-8-sig")
    merged.to_json("./all_jobs.json", orient="records", force_ascii=False, indent=2)
