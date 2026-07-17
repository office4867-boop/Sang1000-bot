import pandas as pd

from issue_analysis import (
    analyze_hot_issues,
    build_theme_event_index,
    calculate_leadership_score,
    extract_theme_terms,
    group_issue_cycles,
    prepare_issue_events,
    score_stocks,
)


def result_row(stock_key, name, date, rise, relevance=80, source="상천 이력"):
    return {
        "종목키": stock_key,
        "종목명": name,
        "날짜": date,
        "출처": source,
        "상승률": rise,
        "검색본문": "원전",
        "근거문장": "원전 수주 기대",
        "검색필드": "상승이유",
        "관련도점수": relevance,
        "매칭키워드": ["원전"],
        "일치유형": "정확 일치",
        "정확일치여부": True,
    }


def test_dates_three_trading_days_apart_are_same_cycle():
    trading_days = pd.bdate_range("2026-01-02", periods=6)
    results = pd.DataFrame(
        [
            result_row("000001", "A", trading_days[0], 10),
            result_row("000002", "B", trading_days[3], 15),
        ]
    )
    summaries, members, _ = group_issue_cycles(results, trading_days)

    assert len(summaries) == 1
    assert len(members) == 2
    assert summaries.iloc[0]["분류"] == "테마 확산"


def test_gap_over_three_trading_days_starts_new_cycle():
    trading_days = pd.bdate_range("2026-01-02", periods=7)
    results = pd.DataFrame(
        [
            result_row("000001", "A", trading_days[0], 10),
            result_row("000001", "A", trading_days[4], 12),
        ]
    )
    summaries, _, _ = group_issue_cycles(results, trading_days)
    assert len(summaries) == 2


def test_single_stock_cycle_is_kept_as_individual_reaction():
    trading_days = pd.bdate_range("2026-01-02", periods=3)
    results = pd.DataFrame([result_row("000001", "A", trading_days[0], 29.9)])
    summaries, members, _ = group_issue_cycles(results, trading_days)

    assert len(summaries) == 1
    assert summaries.iloc[0]["분류"] == "개별 반응"
    assert summaries.iloc[0]["상한가수"] == 1
    assert members.iloc[0]["회차내순위"] == 1


def test_invalid_dates_and_blank_rises_are_dropped():
    results = pd.DataFrame(
        [
            result_row("000001", "A", "not-a-date", 10),
            result_row("000002", "B", "2026-01-02", None),
            result_row("000003", "C", "2026-01-03", "$+7.22\\%$"),
        ]
    )
    events = prepare_issue_events(results)
    assert events[["종목키", "상승률"]].values.tolist() == [["000003", 7.22]]


def test_repetition_and_leadership_scores_reward_recurrence_and_rank():
    trading_days = pd.bdate_range("2026-01-02", periods=8)
    results = pd.DataFrame(
        [
            result_row("000001", "반복주", trading_days[0], 20),
            result_row("000002", "단발주", trading_days[0], 10),
            result_row("000001", "반복주", trading_days[5], 15),
        ]
    )
    summaries, members, _ = group_issue_cycles(results, trading_days)
    ranking = score_stocks(results, summaries, members, reference_date=trading_days[-1])
    scores = ranking.set_index("종목키")

    assert scores.loc["000001", "반복성점수"] > scores.loc["000002", "반복성점수"]
    assert calculate_leadership_score([1]) > calculate_leadership_score([2])


def test_unmatched_static_high_rise_does_not_change_matched_highest_rise():
    trading_days = pd.bdate_range("2026-01-02", periods=3)
    results = pd.DataFrame(
        [
            result_row("000001", "A", trading_days[0], 10),
            result_row("000001", "A", None, 99, source="종목 테마·기업개요"),
        ]
    )
    summaries, members, _ = group_issue_cycles(results, trading_days)
    ranking = score_stocks(results, summaries, members, reference_date=trading_days[-1])
    assert ranking.iloc[0]["최고상승률"] == 10


def test_theme_terms_are_canonicalized_and_generic_individual_tags_removed():
    aliases = {"원전": ["원전", "원자력"]}
    terms = extract_theme_terms(
        "개별주/바이오/BIO/이차전지/에너지 (원전)", aliases
    )
    assert terms == ["바이오", "2차전지", "원전"]


def test_hot_issue_score_rewards_breadth_cycles_and_repeat_stocks():
    trading_days = pd.bdate_range("2026-01-02", periods=10)
    rows = [
        {"날짜": trading_days[0], "종목명": "A", "종목코드": "1", "상승률": 0.2, "테마": "반도체", "상승이유": "반도체"},
        {"날짜": trading_days[3], "종목명": "B", "종목코드": "2", "상승률": 0.15, "테마": "반도체", "상승이유": "반도체"},
        {"날짜": trading_days[8], "종목명": "A", "종목코드": "1", "상승률": 0.12, "테마": "반도체", "상승이유": "반도체"},
        {"날짜": trading_days[9], "종목명": "C", "종목코드": "3", "상승률": 0.1, "테마": "로봇", "상승이유": "로봇"},
    ]
    events = build_theme_event_index(pd.DataFrame(rows))
    ranking, _, _ = analyze_hot_issues(
        events, trading_days, trading_days[0], trading_days[-1], compare_previous=False, min_stocks=1
    )
    by_issue = ranking.set_index("이슈")

    assert by_issue.loc["반도체", "부각회차수"] == 2
    assert by_issue.loc["반도체", "반복종목수"] == 1
    assert by_issue.loc["반도체", "핫점수"] > by_issue.loc["로봇", "핫점수"]


def test_hot_issue_previous_period_marks_new_issue():
    trading_days = pd.bdate_range("2026-01-02", periods=10)
    rows = [
        {"날짜": trading_days[2], "종목명": "A", "종목코드": "1", "상승률": 0.1, "테마": "로봇"},
        {"날짜": trading_days[7], "종목명": "B", "종목코드": "2", "상승률": 0.2, "테마": "원전"},
    ]
    events = build_theme_event_index(pd.DataFrame(rows))
    ranking, _, metadata = analyze_hot_issues(
        events, trading_days, trading_days[5], trading_days[-1], compare_previous=True, min_stocks=1
    )

    assert ranking.iloc[0]["이슈"] == "원전"
    assert ranking.iloc[0]["상태"] == "신규 부각"
    assert metadata["비교여부"] is True
