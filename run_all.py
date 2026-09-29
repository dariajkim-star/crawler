# 사람인 + 고용24 + LinkedIn + WWR + 피플앤잡 크롤러를 전부 실행하고
# 1) 소스별 csv/json 저장
# 2) all_jobs.csv / all_jobs.json 으로 통합 저장 (대시보드 job_board.html이 읽는 파일)
#
# 효율화: 소스 3개를 스레드로 "동시에" 크롤링 (사이트별 요청 간격 2초는 그대로 유지)
# 키워드/직군은 config.py에서 관리

import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import pandas as pd

import saramin
import work24
import linkedin
import weworkremotely
import peoplenjob
from config import ALL_KEYWORDS, KEYWORD_TO_CATEGORY, MAX_PAGES
from scoring import is_noise, normalize_deadline, score_job

BASE_DIR = Path(__file__).parent
BACKUP_DIR = BASE_DIR / "backups"

# 부분 실패 방어: 직전 결과의 이 비율 미만으로 줄면 덮어쓰지 않는다.
# 소스 하나만 살아남아도 통합 파일이 그 크기로 교체되던 문제를 막는다.
SHRINK_GUARD_RATIO = 0.5
BACKUP_KEEP = 7  # 통합 파일 백업 보관 개수

# 통합 파일에 들어갈 공통 컬럼
COMMON_COLS = ["출처", "직군", "검색어", "공고 이름", "회사 이름", "회사 위치",
               "게시일", "마감일", "링크", "점수", "워치리스트"]

SOURCES = [
    ("사람인", saramin, "saramin_result"),
    ("고용24", work24, "work24_result"),
    ("LinkedIn", linkedin, "linkedin_result"),
    ("WWR", weworkremotely, "weworkremotely_result"),
    ("피플앤잡", peoplenjob, "peoplenjob_result"),
]


def previous_row_count():
    """직전 all_jobs.csv의 행수 (헤더 제외). 없으면 0."""
    p = BASE_DIR / "all_jobs.csv"
    if not p.exists():
        return 0
    try:
        with open(p, encoding="utf-8-sig") as f:
            return max(sum(1 for _ in f) - 1, 0)
    except OSError:
        return 0


def backup_previous():
    """직전 통합 파일을 사본으로 남기고 오래된 백업을 정리.

    부분 실패한 결과가 멀쩡한 파일을 덮어쓴 경우 되돌릴 수 있게 한다.
    """
    src = BASE_DIR / "all_jobs.csv"
    if not src.exists():
        return
    try:
        BACKUP_DIR.mkdir(exist_ok=True)
        stamp = datetime.fromtimestamp(src.stat().st_mtime).strftime("%Y%m%d_%H%M%S")
        shutil.copy2(src, BACKUP_DIR / f"all_jobs_{stamp}.csv")
        for old in sorted(BACKUP_DIR.glob("all_jobs_*.csv"))[:-BACKUP_KEEP]:
            old.unlink()
    except OSError as e:
        print(f"백업 실패 → 계속 진행 ({type(e).__name__}: {e})", flush=True)


def dedup_by_link(df, label):
    """링크 없는 행을 세어서 버린 뒤, 링크 기준으로 중복 제거.

    drop_duplicates(subset=["링크"])만 쓰면 빈 링크끼리 서로 중복으로 취급돼
    첫 행만 남고 나머지가 로그 한 줄 없이 사라진다. 링크가 없는 공고는 열 수도
    없고 history.ingest도 건너뛰므로, 몇 건을 왜 버렸는지 남기고 먼저 제외한다.
    """
    if df.empty or "링크" not in df.columns:
        return df
    link = df["링크"].fillna("").astype(str).str.strip()
    missing = int((link == "").sum())
    if missing:
        print(f"[{label}] 링크 없는 공고 {missing}건 제외 (파싱 실패 추정)", flush=True)
    df = df[link != ""]
    return df.drop_duplicates(subset=["링크"]).reset_index(drop=True)


def safe_score(row):
    """한 행의 스코어링 실패가 그날 크롤링 전체를 날리지 않도록 감싼다."""
    try:
        return score_job(row)
    except Exception as e:
        print(f"스코어링 실패 → 0점 처리 ({type(e).__name__}: {e})", flush=True)
        return 0, False, []


def run_source(name, module, filename):
    """크롤러 모듈 하나를 전체 키워드로 실행하고 소스별 파일 저장.

    반환: (DataFrame, 실패한 키워드 수)
    """
    rows = []
    failed = 0

    if not getattr(module, "SUPPORTS_KEYWORD_SEARCH", True):
        # 사이트가 키워드 검색을 지원하지 않는 경우(피플앤잡): 키워드마다 돌면 같은
        # 목록을 41번 받아 낭비되고, 첫 키워드가 전체를 선점해 직군이 오분류된다.
        # 목록을 한 번만 받고 직군은 크롤러가 제목 매칭으로 채운다.
        try:
            rows = module.crawling_data(max_pages=MAX_PAGES)
            print(f"[{name}] 목록 1회 수집 완료 (키워드 검색 미지원 사이트)", flush=True)
        except Exception as e:
            failed = len(ALL_KEYWORDS)
            print(f"[{name}] 목록 수집 실패 ({type(e).__name__}: {e})", flush=True)
    else:
        for i, kw in enumerate(ALL_KEYWORDS, 1):
            # 사이트가 일시적으로 응답하지 않아도(타임아웃 등) 키워드 하나만 건너뛰고 계속 진행
            try:
                rows.extend(module.crawling_data(kw, max_pages=MAX_PAGES))
                # 병렬 실행 시 tqdm 진행바가 섞여 보이므로, 읽기 쉬운 완료 로그를 따로 남김
                print(f"[{name}] '{kw}' 완료 ({i}/{len(ALL_KEYWORDS)})", flush=True)
            except Exception as e:
                failed += 1
                print(f"[{name}] '{kw}' 실패 → 건너뜀 ({type(e).__name__}: {e})", flush=True)
        if failed:
            print(f"[{name}] 키워드 {failed}/{len(ALL_KEYWORDS)}개 실패", flush=True)

    df = pd.DataFrame(rows)
    if df.empty:
        print(f"[{name}] 수집된 공고 없음", flush=True)
        return df, failed

    df = dedup_by_link(df, name)
    if df.empty:
        print(f"[{name}] 링크 있는 공고 없음", flush=True)
        return df, failed
    df["직군"] = df["검색어"].map(KEYWORD_TO_CATEGORY).fillna("기타")
    df["출처"] = name  # 소스별 파일에도 출처가 들어가도록 저장 전에 붙인다
    print(f"[{name}] {len(df)}건 수집", flush=True)

    df.to_csv(BASE_DIR / f"{filename}.csv", index=False, encoding="utf-8-sig")
    df.to_json(BASE_DIR / f"{filename}.json", orient="records", force_ascii=False, indent=2)

    return df, failed


def main(force_write=None):
    """전체 크롤링 후 통합 파일 저장. 반환한 DataFrame의 .attrs에 실패 요약이 담긴다.

    force_write: 급감 가드를 무시하고 덮어쓸지. None이면 환경변수 FORCE_WRITE로 결정.
    """
    if force_write is None:
        force_write = os.environ.get("FORCE_WRITE", "").strip() not in ("", "0")

    # 소스들을 병렬로 (같은 사이트에 동시 요청하는 게 아니므로 각 사이트 부담은 동일)
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        futures = {pool.submit(run_source, name, module, filename): name
                   for name, module, filename in SOURCES}
        frames, failures, counts = [], {}, {}
        for f, name in futures.items():
            # 소스 하나가 통째로 죽어도 나머지 소스가 모은 결과는 살린다
            try:
                df, failed = f.result()
                failures[name] = failed
                counts[name] = len(df)
                frames.append(df)
            except Exception as e:
                failures[name] = len(ALL_KEYWORDS)  # 통째로 실패 = 전 키워드 실패
                counts[name] = 0
                print(f"[{name}] 소스 전체 실패 → 제외 ({type(e).__name__}: {e})", flush=True)

    # 0건인 소스는 예외 없이도 나올 수 있다(차단 페이지를 200 OK로 받으면 목록이 비어
    # 조용히 종료됨). 실패 카운트가 아니라 실제 수집 건수로 판정해야 잡힌다.
    dead = [n for n, _, _ in SOURCES if counts.get(n, 0) == 0]
    if dead:
        print(f"경고: 소스 {', '.join(dead)} 가 한 건도 수집하지 못했습니다", flush=True)

    frames = [df for df in frames if not df.empty]
    if not frames:
        raise RuntimeError("모든 소스 크롤링 실패 — all_jobs 파일을 갱신하지 않음")

    merged = pd.concat(frames, ignore_index=True)

    # 소스 간 중복·빈 링크도 한 번 더 정리 (같은 공고가 두 사이트에 올라오는 경우)
    merged = dedup_by_link(merged, "통합")

    # 노이즈 필터: 제목에 제외 키워드(보험영업 등)가 있으면 버림
    before = len(merged)
    merged = merged[~merged["공고 이름"].map(is_noise)].reset_index(drop=True)
    print(f"노이즈 필터: {before - len(merged)}건 제외", flush=True)

    # 마감일 포맷 통일: 소스마다 '~ 09/30(수)' · '2026-09-30' · '오늘마감' · 센티넬이
    # 섞여 있어 대시보드에서 정렬·필터가 불가능했다. ISO 또는 '상시채용'으로 맞춘다.
    if "마감일" in merged.columns:
        merged["마감일"] = merged["마감일"].map(normalize_deadline)

    # 스코어링 (신규 가점은 이력DB를 아는 run_and_notify에서 반영)
    scored = merged.apply(safe_score, axis=1)
    merged["점수"] = [s[0] for s in scored]
    merged["워치리스트"] = [s[1] for s in scored]

    # 소스마다 컬럼이 조금씩 달라서 공통 컬럼으로 정리 (없는 컬럼은 빈칸)
    for col in COMMON_COLS:
        if col not in merged.columns:
            merged[col] = ""
    merged = merged[COMMON_COLS].fillna("")

    print(merged["출처"].value_counts(), flush=True)

    # 급감 가드: 소스 차단/부분 실패로 쪼그라든 결과가 멀쩡한 파일을 덮어쓰는 것을 막는다
    prev = previous_row_count()
    if prev and len(merged) < prev * SHRINK_GUARD_RATIO and not force_write:
        raise RuntimeError(
            f"통합 결과가 {prev:,}건에서 {len(merged):,}건으로 급감해 저장을 중단했습니다. "
            f"소스 차단이나 부분 실패가 의심됩니다. 키워드 실패: {failures}. "
            f"의도한 결과라면 FORCE_WRITE=1 로 다시 실행하세요."
        )

    backup_previous()
    print(f"통합 {len(merged)}건 저장", flush=True)
    merged.to_csv(BASE_DIR / "all_jobs.csv", index=False, encoding="utf-8-sig")
    merged.to_json(BASE_DIR / "all_jobs.json", orient="records", force_ascii=False, indent=2)

    merged.attrs["failures"] = failures
    merged.attrs["dead_sources"] = dead
    return merged


if __name__ == "__main__":
    main()
