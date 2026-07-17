"""검색된 상천 이력을 과거 이슈 회차와 종목 평가로 변환한다."""

from __future__ import annotations

import math
import re
from typing import Iterable, Mapping, Sequence

import pandas as pd

from app_utils import LIMIT_UP_THRESHOLD, convert_rise_rate, normalize_stock_code


EVENT_COLUMNS = [
    "종목키", "종목명", "날짜", "상승률", "출처", "근거문장",
    "매칭키워드", "일치유형", "관련도점수",
]

THEME_EVENT_COLUMNS = ["이슈", "날짜", "종목키", "종목명", "상승률", "상승이유", "원본테마"]
GENERIC_THEME_TERMS = {
    "", "-", "없음", "기타", "미분류", "테마없음", "개별", "개별주", "개별 이슈", "기타테마",
}
GENERIC_THEME_FOLDED = {term.casefold() for term in GENERIC_THEME_TERMS}
DEFAULT_THEME_CANONICAL = {
    "bio": "바이오",
    "biotech": "바이오",
    "2차 전지": "2차전지",
    "이차전지": "2차전지",
    "메가 프로젝트": "메가프로젝트",
    "인공지능": "AI",
}
THEME_SPLITTER = re.compile(r"[#,/|;>\n\r]+")


def prepare_issue_events(search_results: pd.DataFrame) -> pd.DataFrame:
    """검색과 직접 매칭된 유효한 상천 상승 이력만 남긴다."""
    if search_results is None or search_results.empty:
        return pd.DataFrame(columns=EVENT_COLUMNS)

    events = search_results.copy()
    if "출처" in events.columns:
        events = events[events["출처"] == "상천 이력"]
    date_values = events.get("날짜", pd.Series(pd.NaT, index=events.index))
    events["날짜"] = date_values.map(
        lambda value: pd.to_datetime(value, errors="coerce")
    ).dt.normalize()
    events["상승률"] = events.get("상승률", pd.Series(index=events.index, dtype=float)).apply(
        lambda value: convert_rise_rate(value)[0]
    )
    events = events.dropna(subset=["날짜", "상승률"])
    events = events[events["종목키"].fillna("").astype(str).str.strip().astype(bool)]
    if events.empty:
        return pd.DataFrame(columns=EVENT_COLUMNS)

    for column in EVENT_COLUMNS:
        if column not in events.columns:
            events[column] = None
    events = events.sort_values(
        ["종목키", "날짜", "관련도점수", "상승률"],
        ascending=[True, True, False, False],
    )
    events = events.drop_duplicates(["종목키", "날짜"], keep="first")
    return events[EVENT_COLUMNS].reset_index(drop=True)


def _trading_day_positions(
    trading_days: Iterable,
    matched_dates: Iterable,
) -> dict[pd.Timestamp, int]:
    all_days = pd.to_datetime(pd.Series(list(trading_days)), errors="coerce").dropna().dt.normalize()
    match_days = pd.to_datetime(pd.Series(list(matched_dates)), errors="coerce").dropna().dt.normalize()
    ordered = sorted(set(all_days.tolist()) | set(match_days.tolist()))
    return {day: position for position, day in enumerate(ordered)}


def group_issue_cycles(
    search_results: pd.DataFrame,
    trading_days: Iterable,
    max_trading_day_gap: int = 3,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """매칭 날짜 간격이 지정 거래일 이내이면 하나의 이슈 회차로 묶는다."""
    events = prepare_issue_events(search_results)
    if events.empty:
        return (
            pd.DataFrame(columns=["회차", "시작일", "종료일", "동시상승종목수"]),
            pd.DataFrame(columns=[*EVENT_COLUMNS, "회차", "회차내순위"]),
            events,
        )

    positions = _trading_day_positions(trading_days, events["날짜"])
    unique_dates = sorted(events["날짜"].dropna().unique())
    cycle_for_date: dict[pd.Timestamp, int] = {}
    cycle_number = 1
    previous_date = None
    for date_value in unique_dates:
        date = pd.Timestamp(date_value).normalize()
        if previous_date is not None:
            gap = positions[date] - positions[previous_date]
            if gap > max_trading_day_gap:
                cycle_number += 1
        cycle_for_date[date] = cycle_number
        previous_date = date

    events["회차번호"] = events["날짜"].map(cycle_for_date)
    events["회차"] = events["회차번호"].map(lambda value: f"{int(value)}회차")

    member_rows: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []
    for current_number, cycle_events in events.groupby("회차번호", sort=True):
        cycle_events = cycle_events.sort_values(
            ["상승률", "관련도점수"], ascending=[False, False]
        )
        members = cycle_events.drop_duplicates("종목키", keep="first").copy()
        members["회차내순위"] = (
            members["상승률"].rank(method="min", ascending=False).astype(int)
        )
        member_rows.append(members)

        leader = members.sort_values(
            ["상승률", "관련도점수"], ascending=[False, False]
        ).iloc[0]
        core = cycle_events.sort_values(
            ["관련도점수", "상승률"], ascending=[False, False]
        ).iloc[0]
        start_date = cycle_events["날짜"].min()
        end_date = cycle_events["날짜"].max()
        stock_count = int(members["종목키"].nunique())
        label = (
            start_date.strftime("%Y-%m-%d")
            if start_date == end_date
            else f"{start_date:%Y-%m-%d}~{end_date:%Y-%m-%d}"
        )
        summary_rows.append(
            {
                "회차번호": int(current_number),
                "회차": f"{int(current_number)}회차",
                "회차레이블": label,
                "시작일": start_date,
                "종료일": end_date,
                "분류": "테마 확산" if stock_count >= 2 else "개별 반응",
                "동시상승종목수": stock_count,
                "평균상승률": float(members["상승률"].mean()),
                "중앙상승률": float(members["상승률"].median()),
                "15%이상종목수": int((members["상승률"] >= 15.0).sum()),
                "상한가수": int((members["상승률"] >= LIMIT_UP_THRESHOLD).sum()),
                "대장주": leader["종목명"],
                "최고상승률": float(leader["상승률"]),
                "핵심매칭문장": core.get("근거문장", ""),
            }
        )

    members = pd.concat(member_rows, ignore_index=True)
    summaries = pd.DataFrame(summary_rows).sort_values("시작일", ascending=False).reset_index(drop=True)
    return summaries, members, events.drop(columns=["회차번호"], errors="ignore")


def calculate_repetition_score(cycle_count: int) -> float:
    """서로 다른 회차 수를 25점으로 변환한다."""
    anchors = {0: 0.0, 1: 5.0, 2: 12.0, 3: 18.0}
    return anchors.get(int(cycle_count), 25.0)


def calculate_leadership_score(ranks: Iterable[float]) -> float:
    """회차 내 순위의 역수를 평균해 20점 주도성으로 변환한다."""
    valid = [float(rank) for rank in ranks if pd.notna(rank) and float(rank) > 0]
    if not valid:
        return 0.0
    return min(20.0, 20.0 * sum(1.0 / rank for rank in valid) / len(valid))


def calculate_recency_score(last_date, reference_date, half_life_days: int = 365) -> float:
    if pd.isna(last_date) or pd.isna(reference_date):
        return 0.0
    age = max(0, (pd.Timestamp(reference_date) - pd.Timestamp(last_date)).days)
    return 5.0 * math.pow(0.5, age / half_life_days)


def score_stocks(
    search_results: pd.DataFrame,
    cycle_summaries: pd.DataFrame,
    cycle_members: pd.DataFrame,
    reference_date=None,
) -> pd.DataFrame:
    """관련도 40·반복 25·주도 20·확산 10·최근 5점으로 평가한다."""
    if search_results is None or search_results.empty:
        return pd.DataFrame(
            columns=["순위", "종목키", "종목명", "종합점수", "관련도", "부각회차수"]
        )

    if reference_date is None:
        dated = pd.to_datetime(search_results.get("날짜"), errors="coerce").dropna()
        reference_date = dated.max() if not dated.empty else pd.Timestamp.today().normalize()

    summary_by_cycle = (
        cycle_summaries.set_index("회차")["동시상승종목수"].to_dict()
        if cycle_summaries is not None and not cycle_summaries.empty
        else {}
    )
    rows: list[dict[str, object]] = []
    for stock_key, matches in search_results.groupby("종목키", sort=False):
        stock_name = matches["종목명"].dropna().astype(str).iloc[0]
        max_relevance = float(pd.to_numeric(matches["관련도점수"], errors="coerce").fillna(0).max())
        match_count = int(len(matches))
        relevance_score = min(40.0, max_relevance * 0.36 + min(match_count, 4))

        if cycle_members is not None and not cycle_members.empty:
            member_rows = cycle_members[cycle_members["종목키"] == stock_key].copy()
        else:
            member_rows = pd.DataFrame()
        cycle_count = int(member_rows["회차"].nunique()) if not member_rows.empty else 0
        repetition_score = calculate_repetition_score(cycle_count)
        ranks = member_rows["회차내순위"].tolist() if not member_rows.empty else []
        leadership_score = calculate_leadership_score(ranks)

        if not member_rows.empty:
            diffusion_values = [
                min(10.0, max(0, summary_by_cycle.get(cycle, 1) - 1) / 4 * 10.0)
                for cycle in member_rows["회차"].drop_duplicates()
            ]
            diffusion_score = sum(diffusion_values) / len(diffusion_values)
            last_date = pd.to_datetime(member_rows["날짜"], errors="coerce").max()
            highest_rise = float(pd.to_numeric(member_rows["상승률"], errors="coerce").max())
            leader_count = int((member_rows["회차내순위"] == 1).sum())
            average_rank = float(member_rows["회차내순위"].mean())
        else:
            diffusion_score = 0.0
            last_date = pd.NaT
            highest_rise = float("nan")
            leader_count = 0
            average_rank = float("nan")

        recency_score = calculate_recency_score(last_date, reference_date)
        total = relevance_score + repetition_score + leadership_score + diffusion_score + recency_score
        rows.append(
            {
                "종목키": stock_key,
                "종목명": stock_name,
                "종합점수": round(total, 2),
                "관련도": round(relevance_score, 2),
                "반복성점수": round(repetition_score, 2),
                "주도성점수": round(leadership_score, 2),
                "확산점수": round(diffusion_score, 2),
                "최근성점수": round(recency_score, 2),
                "부각회차수": cycle_count,
                "대장횟수": leader_count,
                "평균순위": round(average_rank, 2) if pd.notna(average_rank) else None,
                "최고상승률": round(highest_rise, 2) if pd.notna(highest_rise) else None,
                "최근부각일": last_date,
                "매칭건수": match_count,
            }
        )

    ranking = pd.DataFrame(rows).sort_values(
        ["종합점수", "관련도", "최근부각일"],
        ascending=[False, False, False],
        na_position="last",
    ).reset_index(drop=True)
    ranking.insert(0, "순위", range(1, len(ranking) + 1))
    return ranking


def build_reaction_matrix(cycle_members: pd.DataFrame) -> pd.DataFrame:
    """종목×이슈 회차의 회차 내 최고 상승률 매트릭스를 만든다."""
    if cycle_members is None or cycle_members.empty:
        return pd.DataFrame()
    matrix_source = cycle_members.copy()
    matrix_source["종목표시"] = matrix_source.apply(
        lambda row: f"{row['종목명']} ({row['종목키']})", axis=1
    )
    matrix = matrix_source.pivot_table(
        index="종목표시",
        columns="회차",
        values="상승률",
        aggfunc="max",
    )
    ordered_columns = sorted(
        matrix.columns,
        key=lambda value: int(str(value).replace("회차", "")),
    )
    return matrix.reindex(columns=ordered_columns)


def _alias_representatives(
    aliases: Mapping[str, Sequence[str]] | None,
) -> dict[str, str]:
    representatives: dict[str, str] = {}
    for representative, terms in (aliases or {}).items():
        representative = str(representative).strip()
        for term in [representative, *terms]:
            text = str(term).strip()
            if text:
                representatives[text.casefold()] = representative
    return representatives


def extract_theme_terms(
    value,
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> list[str]:
    """상천 테마 문자열을 검색 가능한 이슈 단위로 정규화한다."""
    return _extract_theme_terms_with_map(value, _alias_representatives(aliases))


def _extract_theme_terms_with_map(value, alias_map: Mapping[str, str]) -> list[str]:
    if value is None or pd.isna(value):
        return []
    original = str(value).strip()
    if not original or original.casefold() in GENERIC_THEME_FOLDED:
        return []

    terms: list[str] = []
    seen: set[str] = set()
    for raw_part in THEME_SPLITTER.split(original):
        part = re.sub(r"\s+", " ", raw_part).strip(" ._-·")
        if not part:
            continue

        parenthetical = [
            re.sub(r"\s+", " ", item).strip()
            for item in re.findall(r"\(([^()]*)\)", part)
            if item.strip()
        ]
        if part.count("(") != part.count(")"):
            continue
        canonical = alias_map.get(part.casefold()) or DEFAULT_THEME_CANONICAL.get(part.casefold())
        if not canonical:
            canonical = next(
                (alias_map[item.casefold()] for item in parenthetical if item.casefold() in alias_map),
                part,
            )
        canonical = re.sub(r"\s+", " ", canonical).strip()
        folded = canonical.casefold()
        if (
            not canonical
            or folded in GENERIC_THEME_FOLDED
            or folded.startswith("개별주")
            or folded.startswith("개별 이슈")
            or len(canonical) > 60
            or folded in seen
        ):
            continue
        terms.append(canonical)
        seen.add(folded)
    return terms


def build_theme_event_index(
    df_sangcheon: pd.DataFrame,
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> pd.DataFrame:
    """상천 행의 테마를 이슈별·날짜별·종목별 이벤트로 펼친다."""
    if df_sangcheon is None or df_sangcheon.empty or "테마" not in df_sangcheon.columns:
        return pd.DataFrame(columns=THEME_EVENT_COLUMNS)

    alias_map = _alias_representatives(aliases)
    records: list[dict[str, object]] = []
    for _, row in df_sangcheon.iterrows():
        date = pd.to_datetime(row.get("날짜"), errors="coerce")
        rise, _ = convert_rise_rate(row.get("상승률"))
        stock_name = "" if pd.isna(row.get("종목명")) else str(row.get("종목명")).strip()
        stock_key = "" if pd.isna(row.get("__stock_key")) else str(row.get("__stock_key")).strip()
        stock_key = stock_key or normalize_stock_code(row.get("종목코드")) or stock_name
        if pd.isna(date) or rise is None or not stock_key or not stock_name:
            continue

        raw_theme = row.get("테마")
        for issue in _extract_theme_terms_with_map(raw_theme, alias_map):
            records.append(
                {
                    "이슈": issue,
                    "날짜": pd.Timestamp(date).normalize(),
                    "종목키": stock_key,
                    "종목명": stock_name,
                    "상승률": float(rise),
                    "상승이유": "" if pd.isna(row.get("상승이유")) else str(row.get("상승이유")).strip(),
                    "원본테마": "" if pd.isna(raw_theme) else str(raw_theme).strip(),
                }
            )

    if not records:
        return pd.DataFrame(columns=THEME_EVENT_COLUMNS)
    events = pd.DataFrame.from_records(records, columns=THEME_EVENT_COLUMNS)
    events = events.sort_values("상승률", ascending=False).drop_duplicates(
        ["이슈", "날짜", "종목키"], keep="first"
    )
    return events.sort_values(["날짜", "이슈"], ascending=[False, True]).reset_index(drop=True)


def _assign_theme_cycles(
    events: pd.DataFrame,
    trading_days: Iterable,
    max_trading_day_gap: int = 3,
) -> pd.DataFrame:
    if events.empty:
        result = events.copy()
        result["회차번호"] = pd.Series(dtype="int64")
        return result

    result = events.copy()
    positions = _trading_day_positions(trading_days, result["날짜"])
    cycle_values = pd.Series(index=result.index, dtype="int64")
    for _, issue_rows in result.groupby("이슈", sort=False):
        cycle_number = 1
        previous_date = None
        cycle_by_date: dict[pd.Timestamp, int] = {}
        for raw_date in sorted(issue_rows["날짜"].dropna().unique()):
            date = pd.Timestamp(raw_date).normalize()
            if previous_date is not None and positions[date] - positions[previous_date] > max_trading_day_gap:
                cycle_number += 1
            cycle_by_date[date] = cycle_number
            previous_date = date
        cycle_values.loc[issue_rows.index] = issue_rows["날짜"].map(cycle_by_date).astype(int)
    result["회차번호"] = cycle_values.astype(int)
    return result


def _log_normalize(value: float, maximum: float) -> float:
    if value <= 0 or maximum <= 0:
        return 0.0
    return math.log1p(value) / math.log1p(maximum)


def _summarize_hot_period(
    events: pd.DataFrame,
    trading_days: Sequence[pd.Timestamp],
    period_end: pd.Timestamp,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if events.empty:
        return pd.DataFrame(), _assign_theme_cycles(events, trading_days)

    with_cycles = _assign_theme_cycles(events, trading_days)
    trading_positions = {
        pd.Timestamp(day).normalize(): position for position, day in enumerate(trading_days)
    }
    end_position = trading_positions.get(pd.Timestamp(period_end).normalize(), len(trading_positions) - 1)
    period_length = max(1, len([day for day in trading_days if day <= period_end]))
    half_life = max(5.0, period_length / 3.0)

    rows: list[dict[str, object]] = []
    for issue, issue_rows in with_cycles.groupby("이슈", sort=False):
        stock_cycle_counts = issue_rows.groupby("종목키")["회차번호"].nunique()
        leader = issue_rows.sort_values(["상승률", "날짜"], ascending=[False, False]).iloc[0]
        recent_date = issue_rows["날짜"].max()
        recent_position = trading_positions.get(pd.Timestamp(recent_date).normalize(), end_position)
        rows.append(
            {
                "이슈": issue,
                "상승종목수": int(issue_rows["종목키"].nunique()),
                "부각거래일수": int(issue_rows["날짜"].nunique()),
                "부각회차수": int(issue_rows["회차번호"].nunique()),
                "반복종목수": int((stock_cycle_counts >= 2).sum()),
                "평균상승률": float(issue_rows["상승률"].mean()),
                "중앙상승률": float(issue_rows["상승률"].median()),
                "15%이상종목수": int((issue_rows["상승률"] >= 15.0).sum()),
                "상한가수": int((issue_rows["상승률"] >= LIMIT_UP_THRESHOLD).sum()),
                "대장주": leader["종목명"],
                "최고상승률": float(leader["상승률"]),
                "최근부각일": recent_date,
                "최근거래일간격": max(0, end_position - recent_position),
                "최근성기준": half_life,
            }
        )

    summary = pd.DataFrame(rows)
    maxima = {
        column: float(summary[column].max())
        for column in ["상승종목수", "부각거래일수", "부각회차수", "반복종목수"]
    }
    scored_rows: list[dict[str, object]] = []
    for _, row in summary.iterrows():
        breadth = 30.0 * _log_normalize(row["상승종목수"], maxima["상승종목수"])
        activity = 25.0 * (
            0.65 * _log_normalize(row["부각회차수"], maxima["부각회차수"])
            + 0.35 * _log_normalize(row["부각거래일수"], maxima["부각거래일수"])
        )
        repeat_ratio = row["반복종목수"] / max(1, row["상승종목수"])
        repeat = 20.0 * (
            0.65 * _log_normalize(row["반복종목수"], maxima["반복종목수"])
            + 0.35 * min(1.0, repeat_ratio)
        )
        strength = 15.0 * (
            0.45 * min(1.0, max(0.0, row["평균상승률"]) / 20.0)
            + 0.55 * min(1.0, max(0.0, row["중앙상승률"]) / 15.0)
        )
        recency = 10.0 * math.pow(0.5, row["최근거래일간격"] / row["최근성기준"])
        scored = row.to_dict()
        scored.update(
            {
                "확산점수": round(breadth, 2),
                "활동점수": round(activity, 2),
                "반복점수": round(repeat, 2),
                "강도점수": round(strength, 2),
                "최근성점수": round(recency, 2),
                "핫점수": round(breadth + activity + repeat + strength + recency, 2),
            }
        )
        scored_rows.append(scored)
    return pd.DataFrame(scored_rows), with_cycles


def analyze_hot_issues(
    theme_events: pd.DataFrame,
    trading_days: Iterable,
    start_date,
    end_date,
    compare_previous: bool = True,
    min_stocks: int = 2,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """선택 거래기간의 핫이슈 순위와 이전 동일 거래기간 비교를 계산한다."""
    ordered_days = sorted(
        set(pd.to_datetime(pd.Series(list(trading_days)), errors="coerce").dropna().dt.normalize())
    )
    if not ordered_days:
        return pd.DataFrame(), pd.DataFrame(columns=THEME_EVENT_COLUMNS), {}

    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    current_days = [day for day in ordered_days if start <= day <= end]
    if not current_days:
        return pd.DataFrame(), pd.DataFrame(columns=THEME_EVENT_COLUMNS), {
            "시작일": start, "종료일": end, "거래일수": 0,
        }
    start, end = current_days[0], current_days[-1]

    event_dates = pd.to_datetime(theme_events.get("날짜"), errors="coerce").dt.normalize()
    current_events = theme_events[event_dates.between(start, end)].copy()
    current_summary, current_events = _summarize_hot_period(current_events, current_days, end)
    if not current_summary.empty:
        current_summary = current_summary[current_summary["상승종목수"] >= int(min_stocks)].copy()

    previous_start = previous_end = pd.NaT
    previous_summary = pd.DataFrame()
    if compare_previous:
        start_position = ordered_days.index(start)
        previous_days = ordered_days[max(0, start_position - len(current_days)):start_position]
        if previous_days:
            previous_start, previous_end = previous_days[0], previous_days[-1]
            previous_events = theme_events[event_dates.between(previous_start, previous_end)].copy()
            previous_summary, _ = _summarize_hot_period(previous_events, previous_days, previous_end)

    previous_scores = (
        previous_summary.set_index("이슈")["핫점수"].to_dict()
        if not previous_summary.empty
        else {}
    )
    if not current_summary.empty:
        current_summary["이전기간점수"] = current_summary["이슈"].map(previous_scores).fillna(0.0)
        current_summary["점수변화"] = current_summary["핫점수"] - current_summary["이전기간점수"]

        def status_for(row):
            if row["이슈"] not in previous_scores:
                return "신규 부각"
            if row["점수변화"] >= 8:
                return "확산"
            if row["점수변화"] <= -8:
                return "관심 약화"
            if row["부각회차수"] >= 2 and row["반복종목수"] >= 1:
                return "반복 부각"
            return "현재 부각"

        current_summary["상태"] = current_summary.apply(status_for, axis=1)
        current_summary = current_summary.sort_values(
            ["핫점수", "상승종목수", "최근부각일"],
            ascending=[False, False, False],
        ).reset_index(drop=True)
        current_summary.insert(0, "순위", range(1, len(current_summary) + 1))

    metadata = {
        "시작일": start,
        "종료일": end,
        "거래일수": len(current_days),
        "이전시작일": previous_start,
        "이전종료일": previous_end,
        "비교여부": bool(compare_previous and pd.notna(previous_start)),
    }
    return current_summary, current_events, metadata
