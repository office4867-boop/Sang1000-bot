import pandas as pd

from search_engine import build_search_index, search_documents


def make_index(rows):
    frame = pd.DataFrame(rows)
    return build_search_index(frame)


def test_stock_name_code_and_old_name_search_keep_same_key():
    frame = pd.DataFrame(
        [{
            "날짜": "2026-01-02",
            "종목명": "새이름",
            "종목코드": 5930,
            "상승률": 0.12,
            "상승이유": "반도체 투자 확대",
            "테마": "반도체",
        }]
    )
    index = build_search_index(
        frame,
        name_aliases={"옛이름": "새이름"},
        stock_code_map={"옛이름": "005930", "새이름": "005930"},
    )

    by_name, _ = search_documents(index, "새이름")
    by_code, _ = search_documents(index, "005930")
    by_old_name, _ = search_documents(index, "옛이름")

    assert set(by_name["종목키"]) == {"005930"}
    assert set(by_code["종목키"]) == {"005930"}
    assert set(by_old_name["종목키"]) == {"005930"}


def test_exact_keyword_and_synonym_expansion_are_distinguished():
    index = make_index(
        [
            {"날짜": "2026-01-02", "종목명": "A", "종목코드": "000001", "상승률": 0.1, "상승이유": "HBM4 투자"},
            {"날짜": "2026-01-03", "종목명": "B", "종목코드": "000002", "상승률": 0.1, "상승이유": "고대역폭메모리 수요"},
        ]
    )
    aliases = {"HBM": ["HBM", "고대역폭메모리", "HBM4"]}
    result, applied = search_documents(index, "HBM", aliases=aliases)

    assert set(result["종목키"]) == {"000001", "000002"}
    assert "고대역폭메모리" in applied
    match_types = result.set_index("종목키")["일치유형"].to_dict()
    assert match_types["000001"] == "정확 일치"
    assert match_types["000002"] == "동의어 일치"


def test_and_or_search():
    index = make_index(
        [
            {"날짜": "2026-01-02", "종목명": "A", "종목코드": "1", "상승률": 0.1, "상승이유": "AI 반도체"},
            {"날짜": "2026-01-03", "종목명": "B", "종목코드": "2", "상승률": 0.1, "상승이유": "AI 자동차"},
        ]
    )

    and_result, _ = search_documents(index, "AI 반도체", operator="AND")
    or_result, _ = search_documents(index, "AI 반도체", operator="OR")

    assert and_result["종목명"].tolist() == ["A"]
    assert set(or_result["종목명"]) == {"A", "B"}


def test_literal_special_characters_are_safe():
    index = make_index(
        [{
            "날짜": "2026-01-02",
            "종목명": "특수문자",
            "종목코드": "000003",
            "상승률": 0.1,
            "상승이유": "C++ (원전) [HBM] 도구",
        }]
    )

    for query in ["C++", "(원전)", "[HBM]"]:
        result, _ = search_documents(index, query)
        assert result["종목명"].tolist() == ["특수문자"]


def test_source_date_and_minimum_rise_filters():
    index = make_index(
        [
            {"날짜": "2026-01-02", "종목명": "A", "종목코드": "1", "상승률": 0.05, "상승이유": "원전"},
            {"날짜": "2026-02-02", "종목명": "B", "종목코드": "2", "상승률": 0.2, "상승이유": "원전"},
        ]
    )
    result, _ = search_documents(
        index,
        "원전",
        sources=["상천 이력"],
        start_date="2026-02-01",
        end_date="2026-02-28",
        min_rise=15,
    )
    assert result["종목명"].tolist() == ["B"]
