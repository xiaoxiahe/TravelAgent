"""Travel date parsing helpers shared by web layer and planner."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

_WEEKDAY_CN = ("一", "二", "三", "四", "五", "六", "日")
_FLEXIBLE_DATE_HINTS = ("时间灵活", "黄历择日", "帮我择日", "灵活择日", "帮我黄历择日")


def parse_travel_date(text: str) -> str | None:
    """Parse a single travel date from free text."""
    text = (text or "").strip()
    if not text:
        return None

    iso_match = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", text)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
        return f"{year:04d}-{month:02d}-{day:02d}"

    cn_match = re.search(r"(\d{1,2})月(\d{1,2})日", text)
    if cn_match:
        month, day = map(int, cn_match.groups())
        year = datetime.now().year
        candidate = datetime(year, month, day).date()
        if candidate < datetime.now().date():
            year += 1
        return f"{year:04d}-{month:02d}-{day:02d}"

    month_early = re.search(r"(\d{1,2})\s*月初", text)
    if month_early:
        month = int(month_early.group(1))
        year = datetime.now().year
        if month < datetime.now().month:
            year += 1
        return f"{year:04d}-{month:02d}-05"

    month_mid = re.search(r"(\d{1,2})\s*月中", text)
    if month_mid:
        month = int(month_mid.group(1))
        year = datetime.now().year
        if month < datetime.now().month:
            year += 1
        return f"{year:04d}-{month:02d}-15"

    if "下周末" in text:
        return _upcoming_weekends()[1].isoformat()
    if "本周末" in text or "这周末" in text:
        return _upcoming_weekends()[0].isoformat()

    return None


def _upcoming_weekends(today: date | None = None) -> tuple[date, date]:
    """Return (this_weekend_saturday, next_weekend_saturday)."""
    today = today or datetime.now().date()
    if today.weekday() == 5:
        this_sat = today
    elif today.weekday() == 6:
        this_sat = today + timedelta(days=6)
    else:
        this_sat = today + timedelta(days=(5 - today.weekday()))
    return this_sat, this_sat + timedelta(days=7)


def _format_cn_date(d: date) -> str:
    return f"{d.month}月{d.day}日（周{_WEEKDAY_CN[d.weekday()]}）"


def is_flexible_travel_date(text: str) -> bool:
    text = (text or "").strip()
    return any(hint in text for hint in _FLEXIBLE_DATE_HINTS)


def build_travel_date_question() -> tuple[str, list[dict]]:
    """Build proactive travel-date question with clickable options."""
    today = datetime.now().date()
    this_sat, next_sat = _upcoming_weekends(today)

    target_month = today.month
    year = today.year
    if today.day > 20:
        target_month += 1
    if target_month > 12:
        target_month = 1
        year += 1

    options = [
        {
            "value": this_sat.isoformat(),
            "emoji": "📅",
            "label": f"本周末（{_format_cn_date(this_sat)}）",
            "desc": "最近一个周六出发",
        },
        {
            "value": next_sat.isoformat(),
            "emoji": "📅",
            "label": f"下周末（{_format_cn_date(next_sat)}）",
            "desc": "再下一周周六出发",
        },
        {
            "value": f"{target_month}月初",
            "emoji": "🗓️",
            "label": f"{target_month}月初",
            "desc": "时间大致在该月上旬",
        },
        {
            "value": f"{target_month}月中",
            "emoji": "🗓️",
            "label": f"{target_month}月中",
            "desc": "时间大致在该月中旬",
        },
        {
            "value": "时间灵活，帮我黄历择日",
            "emoji": "🔮",
            "label": "灵活择日",
            "desc": "按黄历推荐最佳出发日",
        },
    ]
    return "打算什么时候出发呢？（会结合黄历帮您择日）", options


def coerce_future_date(date_str: str) -> str:
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
    except ValueError:
        return date_str
    today = datetime.now().date()
    candidate = dt.replace(year=today.year)
    if candidate < today:
        candidate = dt.replace(year=today.year + 1)
    return candidate.isoformat()


def infer_travel_date(profile, conversation_summary: str = "") -> str:
    """Infer the best travel date from profile fields and conversation text."""
    if getattr(profile, "travel_date", None):
        return coerce_future_date(str(profile.travel_date))

    chunks: list[str] = []
    notes = getattr(profile, "notes", None)
    if notes:
        chunks.append(str(notes))
    if conversation_summary:
        chunks.append(conversation_summary)

    for chunk in chunks:
        parsed = parse_travel_date(chunk)
        if parsed:
            return coerce_future_date(parsed)
        for line in chunk.splitlines():
            line = line.strip()
            if not line:
                continue
            if "：" in line:
                line = line.split("：", 1)[-1].strip()
            parsed = parse_travel_date(line)
            if parsed:
                return coerce_future_date(parsed)

    return ""


def build_calendar_query_dates(primary_date: str, conversation_text: str = "") -> list[str]:
    """Build up to three dates for huangli lookup."""
    primary = coerce_future_date(primary_date)
    if not primary:
        return []

    base = datetime.strptime(primary, "%Y-%m-%d").date()
    dates = [primary]
    text = conversation_text or ""
    if "月初" in text or re.search(r"\d{1,2}\s*月初", text):
        offsets = (3, 7)
    else:
        offsets = (1, 2)

    for offset in offsets:
        candidate = (base + timedelta(days=offset)).isoformat()
        if candidate not in dates:
            dates.append(candidate)
    return dates[:3]


def upcoming_weekday_dates(count: int = 3) -> list[str]:
    today = datetime.now().date()
    dates: list[str] = []
    cursor = today + timedelta(days=1)
    while len(dates) < count and (cursor - today).days <= 21:
        if cursor.weekday() < 5:
            dates.append(cursor.isoformat())
        cursor += timedelta(days=1)
    return dates


def should_query_calendar(profile, conversation_summary: str = "") -> bool:
    if infer_travel_date(profile, conversation_summary):
        return True
    text = " ".join(
        part for part in [
            getattr(profile, "notes", "") or "",
            conversation_summary or "",
            getattr(profile, "travel_type", "") or "",
        ]
        if part
    )
    hints = ("月初", "月中", "出发", "出行", "择日", "黄历", "蜜月", "什么时候去", "几号", "时间灵活")
    return any(hint in text for hint in hints)
