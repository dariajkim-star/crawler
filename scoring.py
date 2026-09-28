# 공고 스코어링 + 노이즈 필터
# 점수 = 직군 가중치×10 + 스킬 매칭 가점 + 워치리스트 가점 + 신규 가점 + 마감 임박 가점

import re
from datetime import datetime, timedelta
from functools import lru_cache

from config import WATCHLIST, MY_SKILLS, CATEGORY_WEIGHTS, EXCLUDE_TITLE_KEYWORDS


@lru_cache(maxsize=512)
def _term_pattern(term):
    """영문·숫자 용어면 단어 경계를 요구하는 정규식, 한글이 섞이면 None."""
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9&+.\- ]*", term):
        return re.compile(r"(?<![A-Za-z0-9])" + re.escape(term) + r"(?![A-Za-z0-9])",
                          re.IGNORECASE)
    return None


def contains_term(text, term):
    """text 안에 term이 있는지 판정.

    'AI' 같은 영문 약어를 단순 부분일치로 찾으면 hair · affairs · chain · training에
    전부 걸린다. 영문·숫자 용어는 단어 경계를 요구하고, 한글은 조사가 붙어 쓰이므로
    기존대로 부분일치를 쓴다.
    """
    t = str(text)
    p = _term_pattern(term)
    if p is not None:
        return p.search(t) is not None
    return term.lower() in t.lower()


def is_noise(title):
    """제목에 제외 키워드가 있으면 노이즈로 판정"""
    return any(contains_term(title, x) for x in EXCLUDE_TITLE_KEYWORDS)


def is_watchlist(company):
    """관심 회사 여부 (한글은 부분일치, 영문 약어는 단어 경계)"""
    return any(contains_term(company, w) for w in WATCHLIST)


def matched_skills(text):
    """텍스트에 포함된 내 스킬 키워드 목록"""
    return [s for s in MY_SKILLS if contains_term(text, s)]


# 마감일 자리에 들어오는 "상시채용" 표현들.
# 고용24는 상시채용을 먼 미래 날짜(2099-12-31 등)로 표기하므로 연도로도 걸러낸다.
ALWAYS_OPEN_WORDS = ("채용시", "상시", "수시", "진행예정")
ALWAYS_OPEN_YEARS = 2  # 오늘로부터 이 햇수 이상 뒤면 실제 마감일이 아니라고 본다


def parse_deadline(s):
    """마감일 문자열 -> datetime(마감일). 마감일이 없거나 못 읽으면 None.

    지원 형식
      '2026-09-06'          고용24 · 피플앤잡
      '~ 09/30(수)'         사람인 (연도 없음 -> 올해로 가정)
      '오늘마감' '23시마감'  사람인 -> 오늘
      '내일마감'             사람인 -> 내일
      '채용시' '상시채용'    -> None (마감 없음)
      '2099-12-31'          고용24의 상시채용 센티넬 -> None

    어떤 입력이 와도 예외를 던지지 않는다. 이 함수는 통합 단계의 apply()에서
    행마다 호출되므로, 한 행이 터지면 그날 크롤링 결과 전체가 저장되지 않는다.
    """
    s = str(s).strip()
    if not s or s.lower() == "nan":
        return None

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # 상대 표현 (사람인) — 가장 급한 공고들이라 반드시 먼저 잡는다
    if "오늘마감" in s or re.search(r"\d+\s*시\s*마감", s):
        return today
    if "내일마감" in s:
        return today + timedelta(days=1)
    if any(w in s for w in ALWAYS_OPEN_WORDS):
        return None

    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        try:
            d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None  # 02-30 같은 값
        return None if d.year >= today.year + ALWAYS_OPEN_YEARS else d

    # 연도 없는 MM/DD (사람인). 앞뒤 숫자를 배제해 '2026/09/29'의 '26/09' 오독을 막는다.
    m = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)", s)
    if m:
        try:
            d = datetime(today.year, int(m.group(1)), int(m.group(2)))
            if d < datetime.now() - timedelta(days=60):
                d = d.replace(year=d.year + 1)  # 연말에 본 내년 1월 공고
        except ValueError:
            return None  # 13/05, 02/30, 평년의 02/29
        return d
    return None


def normalize_deadline(s):
    """마감일 원문 -> 표시·정렬용 문자열.

    소스마다 포맷이 달라( '~ 09/30(수)' · '2026-09-30' · '오늘마감' · '2099-12-31' )
    대시보드에서 정렬·필터가 불가능했다. 실제 마감일은 ISO로, 상시채용류는
    '상시채용'으로 통일한다. 못 읽는 값은 원문을 그대로 남겨 정보를 잃지 않는다.
    """
    s = str(s).strip()
    if not s or s.lower() == "nan":
        return ""
    d = parse_deadline(s)
    if d:
        return d.strftime("%Y-%m-%d")
    if any(w in s for w in ALWAYS_OPEN_WORDS) or re.search(r"(\d{4})-\d{1,2}-\d{1,2}", s):
        return "상시채용"  # 상시 표현이거나 먼 미래 센티넬
    return s


def score_job(row, is_new=False):
    """공고 1건 점수화 -> (점수, 워치리스트여부, 제목매칭스킬)"""
    title = row.get("공고 이름", "")

    score = CATEGORY_WEIGHTS.get(row.get("직군", ""), 1) * 10

    skills = matched_skills(title)
    score += 5 * len(skills)

    watch = is_watchlist(row.get("회사 이름", ""))
    if watch:
        score += 30

    if is_new:
        score += 10

    deadline = parse_deadline(row.get("마감일", ""))
    if deadline:
        days_left = (deadline - datetime.now()).days
        if 0 <= days_left <= 3:
            score += 5  # 마감 임박

    return score, watch, skills
