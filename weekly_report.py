# 주간 채용시장 리포트 -> Obsidian 볼트에 .md로 저장 + 슬랙 링크 알림
# 이력 DB(jobs_history.db) 기반: 직군별 신규 공고량, 처음 등장한 회사, 반복 채용 회사
# 스케줄: 매주 월요일 09:00 (JobScope_Weekly_Report)
#
# 수동 실행: python weekly_report.py

import os
import time
from pathlib import Path

BASE_DIR = Path(__file__).parent
os.chdir(BASE_DIR)

# Obsidian 볼트 경로
OB_VAULT = Path(r"C:\Users\s0506\OneDrive\바탕 화면\GitHub_Projects\ob_storage\JobScope")
OB_VAULT.mkdir(parents=True, exist_ok=True)

import history  # noqa: E402
from run_and_notify import send_slack  # noqa: E402


def build_report():
    today = time.strftime("%Y-%m-%d")
    by_cat, week_total, all_time = history.weekly_counts(days=7)
    by_src = history.weekly_source_counts(days=7)
    new_comps = history.new_companies_since(days=7, limit=20)
    repeats = history.repeat_companies(days=30, limit=15)

    lines = [
        f"# JobScope 주간 채용시장 리포트 ({today})",
        "",
        f"> 누적 수집 공고 {all_time:,}건 · 최근 7일 신규 {week_total:,}건 · 수집 소스 {len(by_src)}곳",
        "",
        "## 1. 소스별 수집 현황 (최근 7일)",
        "",
        "| 출처 | 신규 공고 | 누적 |",
        "|---|---|---|",
    ]
    for src, new_cnt, total_cnt in by_src:
        lines.append(f"| {src or '기타'} | {new_cnt:,} | {total_cnt:,} |")

    lines += [
        "",
        "## 2. 직군별 신규 공고 (최근 7일)",
        "",
        "| 직군 | 신규 공고 |",
        "|---|---|",
    ]
    for cat, cnt in by_cat:
        lines.append(f"| {cat or '기타'} | {cnt:,} |")

    lines += [
        "",
        "## 3. 이번 주 처음 등장한 회사 (경쟁 적은 신규 포지션 후보)",
        "",
    ]
    if new_comps:
        for company, first_seen, cnt, title, link in new_comps:
            lines.append(f"- **{company}** ({first_seen}, 공고 {cnt}건) — [{title[:50]}]({link})")
    else:
        lines.append("- 없음")

    lines += [
        "",
        "## 4. 반복 채용 회사 Top 15 (최근 30일 — 상시채용/대량채용 시그널)",
        "",
        "| 회사 | 공고 수 | 직군 수 |",
        "|---|---|---|",
    ]
    for company, cnt, cats in repeats:
        lines.append(f"| {company} | {cnt} | {cats} |")

    lines += [
        "",
        "---",
        "관련 노트: [[JobScope_채용공고_크롤러]]",
        "",
    ]
    return today, "\n".join(lines)


def main():
    today, md = build_report()
    out = OB_VAULT / f"JobScope_주간리포트_{today}.md"
    out.write_text(md, encoding="utf-8")
    print(f"리포트 저장: {out}")

    send_slack(f":bar_chart: *JobScope 주간 리포트 생성 완료*\n"
               f"Obsidian → `{out.name}` (직군별 추이 · 신규 등장 회사 · 반복 채용 회사)")


if __name__ == "__main__":
    main()
