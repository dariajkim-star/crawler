# JD 도구 분석: 모건스탠리 / 외국계 IBD / 증권사 / 데이터 애널리스트 / 퀀트
# 기존 크롤러(linkedin.py, saramin.py)의 crawling_data를 그대로 재사용하고,
# LinkedIn 게스트 API로 각 공고의 JD 본문을 추가 수집해서
# JD에 등장하는 프로그램/툴 빈도를 CSV로 저장한다.
#
# 실행: python jd_tools.py
# 출력: ibd_quant_jobs.csv (공고 목록), jd_tools_frequency.csv (툴 빈도)

import re
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup
from tqdm import tqdm

from linkedin import HEADERS, clean_text
from linkedin import crawling_data as li_crawl
from saramin import crawling_data as sr_crawl

# ── 1. 검색 설계 ────────────────────────────────────────────────
# 카테고리 → (소스, 키워드) 목록
SEARCH_PLAN = {
    "모건스탠리": [("linkedin", "Morgan Stanley")],
    "외국계IBD": [("linkedin", "Investment Banking"), ("linkedin", "IBD")],
    "증권사": [("linkedin", "증권"), ("saramin", "증권사")],
    "데이터애널리스트": [("linkedin", "Data Analyst"), ("saramin", "데이터 애널리스트")],
    "퀀트": [("linkedin", "Quant"), ("saramin", "퀀트")],
}
LI_PAGES = 4       # 카테고리별 LinkedIn 최대 4페이지(100건)
SR_PAGES = 3       # 사람인 3페이지
JD_FETCH_LIMIT = 50  # 카테고리별 JD 본문 수집 상한 (예의는 국룰)

# 모건스탠리 카테고리는 회사명 필터 (키워드 검색이라 타사 공고도 섞임)
MS_COMPANY = re.compile(r"morgan\s*stanley", re.I)

# ── 2. JD에서 찾을 프로그램/툴 사전 ─────────────────────────────
# 표기: 정식 명칭 → 매칭 정규식 (대소문자 무시)
TOOL_PATTERNS = {
    # 오피스/기본
    "Excel": r"excel|엑셀",
    "PowerPoint": r"power\s*point|파워포인트|\bppt\b",
    "Word": r"\bms\s*word\b|워드프로세서",
    "VBA": r"\bvba\b",
    # 금융 단말/DB
    "Bloomberg": r"bloomberg|블룸버그",
    "FactSet": r"factset",
    "Capital IQ": r"capital\s*iq|capiq",
    "Refinitiv/Eikon": r"refinitiv|eikon|\blseg\b",
    "Wind": r"\bwind\s*(terminal|financial)",
    "DART/공시": r"\bdart\b|전자공시",
    # 언어
    "Python": r"python|파이썬",
    "R": r"(?<![A-Za-z])R(?![A-Za-z&+#])(?:\s*(?:프로그래밍|언어|programming|studio)|\s*[,/)및]|$)",
    "SQL": r"\bsql\b|\bmysql\b|postgre|\bmssql\b|oracle\s*db|\btsql\b",
    "C++": r"c\+\+",
    "C#": r"c#|c샵",
    "Java": r"\bjava\b(?!script)",
    "JavaScript": r"javascript|typescript",
    "Scala": r"\bscala\b",
    "MATLAB": r"matlab",
    "SAS": r"\bsas\b",
    "SPSS": r"spss",
    "kdb+/q": r"kdb\+?",
    # 데이터/ML 스택
    "pandas/NumPy": r"pandas|numpy",
    "PyTorch": r"pytorch",
    "TensorFlow": r"tensorflow",
    "scikit-learn": r"scikit|sklearn",
    "Spark": r"\bspark\b",
    "Hadoop": r"hadoop",
    "Kafka": r"kafka",
    "Airflow": r"airflow",
    "Snowflake": r"snowflake",
    "Databricks": r"databricks",
    "BigQuery": r"bigquery",
    # BI/시각화
    "Tableau": r"tableau|태블로",
    "Power BI": r"power\s*bi",
    "Looker": r"looker",
    # 인프라/협업
    "AWS": r"\baws\b|amazon\s*web",
    "GCP": r"\bgcp\b|google\s*cloud",
    "Azure": r"azure",
    "Docker": r"docker",
    "Kubernetes": r"kubernetes|\bk8s\b",
    "Git": r"\bgit\b|github|gitlab",
    "Linux": r"linux|unix",
    "Jira/Confluence": r"jira|confluence",
}
COMPILED = {name: re.compile(pat, re.I) for name, pat in TOOL_PATTERNS.items()}

# ── 3. LinkedIn JD 본문 수집 ────────────────────────────────────
JD_API = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"


def extract_job_id(link: str):
    m = re.search(r"-(\d{8,})$", link.rstrip("/"))
    return m.group(1) if m else None


def fetch_jd_text(link: str, retries: int = 3) -> str:
    """공고 상세의 JD 본문 텍스트. 429는 쉬었다 재시도 (linkedin.py와 동일한 예의)."""
    job_id = extract_job_id(link)
    if not job_id:
        return ""
    for attempt in range(retries):
        try:
            r = requests.get(JD_API.format(job_id=job_id), headers=HEADERS, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                body = soup.select_one("div.show-more-less-html__markup")
                return clean_text(body.get_text(" ")) if body else ""
            if r.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            return ""
        except requests.RequestException:
            time.sleep(3)
    return ""


# ── 4. 수집 실행 ────────────────────────────────────────────────
def collect_jobs() -> pd.DataFrame:
    rows = []
    for category, plans in SEARCH_PLAN.items():
        for source, kw in plans:
            if source == "linkedin":
                got = li_crawl(kw, max_pages=LI_PAGES)
            else:
                got = sr_crawl(kw, max_pages=SR_PAGES)
            for r in got:
                r["카테고리"] = category
                r["출처"] = "LinkedIn" if source == "linkedin" else "사람인"
                rows.append(r)

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["링크"]).reset_index(drop=True)

    # 모건스탠리 카테고리는 실제 모건스탠리 공고만
    is_ms = df["카테고리"] == "모건스탠리"
    df = df[~is_ms | df["회사 이름"].str.contains(MS_COMPANY, na=False)]
    return df.reset_index(drop=True)


def attach_jd(df: pd.DataFrame) -> pd.DataFrame:
    """LinkedIn 공고는 JD 본문, 사람인 공고는 제목+직무분야를 분석 텍스트로 사용."""
    texts = []
    fetched_per_cat: dict[str, int] = {}
    li_targets = df[df["출처"] == "LinkedIn"]

    jd_cache = {}
    for _, row in tqdm(li_targets.iterrows(), total=len(li_targets), desc="JD 본문 수집"):
        cat = row["카테고리"]
        if fetched_per_cat.get(cat, 0) >= JD_FETCH_LIMIT:
            continue
        text = fetch_jd_text(row["링크"])
        if text:
            jd_cache[row["링크"]] = text
            fetched_per_cat[cat] = fetched_per_cat.get(cat, 0) + 1
        time.sleep(1.5)  # 예의는 국룰

    for _, row in df.iterrows():
        if row["링크"] in jd_cache:
            texts.append(jd_cache[row["링크"]])
        elif row["출처"] == "사람인":
            texts.append(f"{row['공고 이름']} {row.get('직무분야', '')}")
        else:
            texts.append("")
    df["JD텍스트"] = texts
    df["JD수집"] = ["본문" if row["링크"] in jd_cache
                    else ("요약" if row["출처"] == "사람인" else "미수집")
                    for _, row in df.iterrows()]
    return df


# ── 5. 툴 빈도 집계 ─────────────────────────────────────────────
def count_tools(df: pd.DataFrame) -> pd.DataFrame:
    analyzed = df[df["JD텍스트"].str.len() > 0]
    categories = list(SEARCH_PLAN.keys())

    records = []
    for tool, pat in COMPILED.items():
        hit = analyzed["JD텍스트"].str.contains(pat)
        n = int(hit.sum())
        if n == 0:
            continue
        rec = {
            "프로그램": tool,
            "언급공고수": n,
            "언급비율%": round(n / len(analyzed) * 100, 1),
        }
        for cat in categories:
            sub = analyzed[analyzed["카테고리"] == cat]
            rec[cat] = int(sub["JD텍스트"].str.contains(pat).sum())
        records.append(rec)

    out = pd.DataFrame(records).sort_values("언급공고수", ascending=False).reset_index(drop=True)
    return out, len(analyzed)


if __name__ == "__main__":
    print("1/3 공고 수집...")
    df = collect_jobs()
    print(f"  수집 {len(df)}건 (중복 제거·모건스탠리 필터 후)")
    print(df["카테고리"].value_counts().to_string())

    print("2/3 JD 본문 수집 (LinkedIn 상세)...")
    df = attach_jd(df)
    print(df["JD수집"].value_counts().to_string())

    print("3/3 툴 빈도 집계...")
    freq, n_analyzed = count_tools(df)

    df.drop(columns=["JD텍스트"]).to_csv("./ibd_quant_jobs.csv", index=False, encoding="utf-8-sig")
    freq.to_csv("./jd_tools_frequency.csv", index=False, encoding="utf-8-sig")
    # JD 원문도 보존 (재분석용)
    df[df["JD수집"] == "본문"][["카테고리", "회사 이름", "공고 이름", "링크", "JD텍스트"]] \
        .to_json("./jd_texts.json", orient="records", force_ascii=False, indent=2)

    print(f"\n분석 공고 {n_analyzed}건 기준 상위 15개 프로그램:")
    print(freq.head(15).to_string(index=False))
    print("\n저장: ibd_quant_jobs.csv / jd_tools_frequency.csv / jd_texts.json")
