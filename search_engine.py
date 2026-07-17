"""상천봇의 종목코드 기반 통합 리터럴 검색 엔진."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pandas as pd

from app_utils import convert_rise_rate, normalize_stock_code


DOCUMENT_COLUMNS = [
    "종목키",
    "종목명",
    "날짜",
    "출처",
    "상승률",
    "검색본문",
    "근거문장",
    "검색필드",
]


def _clean_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() in {"nan", "none", "nat"} else text


def load_keyword_aliases(path: str | Path = "keyword_aliases.json") -> dict[str, list[str]]:
    """확장 가능한 JSON 형식과 단순 사전 형식을 모두 읽는다."""
    alias_path = Path(path)
    if not alias_path.exists():
        return {}

    try:
        with alias_path.open(encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, ValueError, TypeError):
        return {}

    entries = raw.get("aliases", raw) if isinstance(raw, dict) else {}
    result: dict[str, list[str]] = {}
    for representative, value in entries.items():
        if representative in {"version", "description"}:
            continue
        if isinstance(value, dict):
            terms = value.get("terms", [])
        else:
            terms = value
        if isinstance(terms, str):
            terms = [terms]
        if not isinstance(terms, list):
            continue

        cleaned: list[str] = []
        seen: set[str] = set()
        for term in [representative, *terms]:
            text = _clean_text(term)
            folded = text.casefold()
            if text and folded not in seen:
                cleaned.append(text)
                seen.add(folded)
        if cleaned:
            result[str(representative)] = cleaned
    return result


def expand_query_terms(
    query: str,
    aliases: Mapping[str, Sequence[str]] | None = None,
) -> tuple[list[dict[str, object]], list[str]]:
    """원 검색어별 동의어 그룹과 실제 적용된 연관어를 반환한다."""
    query = _clean_text(query)
    if not query:
        return [], []

    aliases = aliases or {}
    alias_by_folded = {str(key).casefold(): list(value) for key, value in aliases.items()}
    full_match = alias_by_folded.get(query.casefold())
    originals = [query] if full_match else query.split()

    groups: list[dict[str, object]] = []
    applied: list[str] = []
    for original in originals:
        expanded = alias_by_folded.get(original.casefold(), [original])
        terms: list[str] = []
        seen: set[str] = set()
        for term in [original, *expanded]:
            text = _clean_text(term)
            folded = text.casefold()
            if text and folded not in seen:
                terms.append(text)
                seen.add(folded)
        groups.append({"original": original, "terms": terms})
        if len(terms) > 1:
            applied.extend(terms)

    deduped_applied: list[str] = []
    seen_applied: set[str] = set()
    for term in applied:
        folded = term.casefold()
        if folded not in seen_applied:
            deduped_applied.append(term)
            seen_applied.add(folded)
    return groups, deduped_applied


def build_stock_alias_lookup(
    name_aliases: Mapping[str, str] | None,
    stock_code_map: Mapping[str, str] | None,
) -> dict[str, list[str]]:
    """종목코드별 현재·과거 사명 검색어를 만든다."""
    stock_code_map = stock_code_map or {}
    names_by_key: defaultdict[str, set[str]] = defaultdict(set)

    for name, raw_code in stock_code_map.items():
        code = normalize_stock_code(raw_code)
        cleaned_name = _clean_text(name)
        if code and cleaned_name:
            names_by_key[code].add(cleaned_name)

    for old_name, new_name in (name_aliases or {}).items():
        old_text = _clean_text(old_name)
        new_text = _clean_text(new_name)
        code = normalize_stock_code(stock_code_map.get(old_text, ""))
        if not code:
            code = normalize_stock_code(stock_code_map.get(new_text, ""))
        if code:
            names_by_key[code].update(name for name in [old_text, new_text] if name)

    return {key: sorted(names) for key, names in names_by_key.items()}


def _preferred_names_by_key(
    name_aliases: Mapping[str, str] | None,
    stock_code_map: Mapping[str, str] | None,
) -> dict[str, str]:
    aliases = name_aliases or {}
    code_map = stock_code_map or {}
    preferred: dict[str, str] = {}
    for old_name, next_name in aliases.items():
        current = _clean_text(next_name)
        seen = {_clean_text(old_name)}
        while current in aliases and current not in seen:
            seen.add(current)
            following = _clean_text(aliases.get(current))
            if not following or following == current:
                break
            current = following
        code = normalize_stock_code(code_map.get(_clean_text(old_name), ""))
        if not code:
            code = normalize_stock_code(code_map.get(current, ""))
        if code and current:
            preferred[code] = current
    return preferred


def _row_stock_identity(row: pd.Series) -> tuple[str, str]:
    name = _clean_text(row.get("종목명"))
    existing_key = _clean_text(row.get("__stock_key"))
    code = normalize_stock_code(row.get("종목코드"))
    return existing_key or code or name, name


def _make_documents(
    frame: pd.DataFrame | None,
    source: str,
    text_columns: Sequence[str],
    evidence_columns: Sequence[str],
    aliases_by_key: Mapping[str, Sequence[str]],
    dynamic_source: bool = False,
) -> list[dict[str, object]]:
    if frame is None or frame.empty or "종목명" not in frame.columns:
        return []

    available_text = [column for column in text_columns if column in frame.columns]
    available_evidence = [column for column in evidence_columns if column in frame.columns]
    documents: list[dict[str, object]] = []

    for _, row in frame.iterrows():
        stock_key, stock_name = _row_stock_identity(row)
        if not stock_key or not stock_name:
            continue

        parts: list[str] = [f"종목키: {stock_key}"]
        used_fields: list[str] = ["종목키"]
        for column in available_text:
            value = _clean_text(row.get(column))
            if value:
                parts.append(f"{column}: {value}")
                used_fields.append(column)

        alias_names = aliases_by_key.get(stock_key, [])
        if alias_names:
            parts.append(f"구 사명·별칭: {' '.join(alias_names)}")

        evidence_parts = [
            _clean_text(row.get(column))
            for column in available_evidence
            if _clean_text(row.get(column))
        ]
        evidence = "\n".join(evidence_parts) or "\n".join(parts)
        if not parts:
            continue

        rise_value, _ = convert_rise_rate(row.get("상승률"))
        row_source = _clean_text(row.get("__source")) if dynamic_source else source
        documents.append(
            {
                "종목키": stock_key,
                "종목명": stock_name,
                "날짜": pd.to_datetime(row.get("날짜"), errors="coerce"),
                "출처": row_source or source,
                "상승률": rise_value,
                "검색본문": "\n".join(parts),
                "근거문장": evidence,
                "검색필드": ", ".join(used_fields),
            }
        )
    return documents


def build_search_index(
    df_sangcheon: pd.DataFrame,
    df_signal: pd.DataFrame | None = None,
    df_themes: pd.DataFrame | None = None,
    df_company_overview: pd.DataFrame | None = None,
    df_analysis: pd.DataFrame | None = None,
    name_aliases: Mapping[str, str] | None = None,
    stock_code_map: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """여러 엑셀 스키마를 표준 검색 문서 구조로 통합한다."""
    aliases_by_key = build_stock_alias_lookup(name_aliases, stock_code_map)
    documents: list[dict[str, object]] = []

    documents.extend(
        _make_documents(
            df_sangcheon,
            "상천 이력",
            ["종목명", "종목코드", "테마", "상승이유"],
            ["상승이유", "테마"],
            aliases_by_key,
        )
    )
    documents.extend(
        _make_documents(
            df_signal,
            "시그널리포트 테마",
            [
                "종목명", "종목코드", "대분류", "중분류", "테마", "핵심테마",
                "주요뉴스", "주요사업", "재무구조", "디지털자산관련구체적사업영역",
            ],
            ["주요뉴스", "주요사업", "재무구조", "디지털자산관련구체적사업영역", "테마", "핵심테마"],
            aliases_by_key,
            dynamic_source=True,
        )
    )
    documents.extend(
        _make_documents(
            df_themes,
            "종목 테마·기업개요",
            ["종목명", "종목코드", "테마_전체", "테마", "기업개요", "핵심요약"],
            ["테마_전체", "테마", "기업개요", "핵심요약"],
            aliases_by_key,
        )
    )
    documents.extend(
        _make_documents(
            df_company_overview,
            "기업 핵심요약",
            ["종목명", "종목코드", "기업개요", "핵심요약", "핵심요약(3줄정리)"],
            ["기업개요", "핵심요약", "핵심요약(3줄정리)"],
            aliases_by_key,
        )
    )
    documents.extend(
        _make_documents(
            df_analysis,
            "테마별 상세분석",
            ["종목명", "종목코드", "테마명", "분석결과"],
            ["테마명", "분석결과"],
            aliases_by_key,
        )
    )

    if not documents:
        return pd.DataFrame(columns=DOCUMENT_COLUMNS)

    index = pd.DataFrame.from_records(documents, columns=DOCUMENT_COLUMNS)
    index["날짜"] = pd.to_datetime(index["날짜"], errors="coerce")
    index["상승률"] = pd.to_numeric(index["상승률"], errors="coerce")
    preferred_names = _preferred_names_by_key(name_aliases, stock_code_map)
    if preferred_names:
        index["종목명"] = index.apply(
            lambda row: preferred_names.get(str(row["종목키"]), row["종목명"]), axis=1
        )
    index = index.drop_duplicates(
        subset=["종목키", "날짜", "출처", "검색본문"], keep="first"
    ).reset_index(drop=True)
    return index


def search_documents(
    search_index: pd.DataFrame,
    query: str,
    aliases: Mapping[str, Sequence[str]] | None = None,
    operator: str = "AND",
    sources: Iterable[str] | None = None,
    start_date=None,
    end_date=None,
    min_rise: float = 0.0,
    sort_by: str = "관련도순",
) -> tuple[pd.DataFrame, list[str]]:
    """정규식 해석 없이 검색하고 매칭 근거와 관련도 점수를 붙인다."""
    groups, applied_terms = expand_query_terms(query, aliases)
    if search_index is None or search_index.empty or not groups:
        empty = pd.DataFrame(columns=[*DOCUMENT_COLUMNS, "관련도점수", "매칭키워드", "일치유형", "정확일치여부"])
        return empty, applied_terms

    body = search_index["검색본문"].fillna("").astype(str)
    term_masks: dict[str, pd.Series] = {}
    for group in groups:
        for term in group["terms"]:
            folded = str(term).casefold()
            if folded not in term_masks:
                term_masks[folded] = body.str.contains(str(term), case=False, regex=False, na=False)

    group_masks: list[pd.Series] = []
    for group in groups:
        group_mask = pd.Series(False, index=search_index.index)
        for term in group["terms"]:
            group_mask |= term_masks[str(term).casefold()]
        group_masks.append(group_mask)

    match_mask = group_masks[0].copy()
    if operator.upper() == "OR":
        for group_mask in group_masks[1:]:
            match_mask |= group_mask
    else:
        for group_mask in group_masks[1:]:
            match_mask &= group_mask

    source_values = [str(value) for value in (sources or []) if str(value)]
    if source_values:
        match_mask &= search_index["출처"].isin(source_values)

    dates = pd.to_datetime(search_index["날짜"], errors="coerce")
    if start_date is not None:
        match_mask &= dates.ge(pd.Timestamp(start_date))
    if end_date is not None:
        match_mask &= dates.le(pd.Timestamp(end_date))

    rises = pd.to_numeric(search_index["상승률"], errors="coerce")
    if min_rise and float(min_rise) > 0:
        match_mask &= rises.ge(float(min_rise))

    matched = search_index.loc[match_mask].copy()
    if matched.empty:
        for column in ["관련도점수", "매칭키워드", "일치유형", "정확일치여부"]:
            matched[column] = pd.Series(dtype="object")
        return matched, applied_terms

    full_query_mask = body.str.contains(_clean_text(query), case=False, regex=False, na=False)
    result_scores: list[float] = []
    result_terms: list[list[str]] = []
    result_types: list[str] = []
    exact_flags: list[bool] = []

    for row_index in matched.index:
        score = 25.0 if bool(full_query_mask.loc[row_index]) else 0.0
        matched_terms: list[str] = []
        exact_group_count = 0
        synonym_group_count = 0
        for group in groups:
            original = str(group["original"])
            original_matched = bool(term_masks[original.casefold()].loc[row_index])
            synonym_matches = [
                str(term)
                for term in group["terms"]
                if str(term).casefold() != original.casefold()
                and bool(term_masks[str(term).casefold()].loc[row_index])
            ]
            if original_matched:
                exact_group_count += 1
                score += 30.0
                matched_terms.append(original)
            elif synonym_matches:
                synonym_group_count += 1
                score += 16.0
            if synonym_matches:
                score += min(12.0, 4.0 * len(synonym_matches))
                matched_terms.extend(synonym_matches)

        if matched.at[row_index, "출처"] == "상천 이력":
            score += 5.0
        exact_all = exact_group_count == len(groups)
        if exact_all:
            match_type = "정확 일치"
        elif exact_group_count:
            match_type = "정확+동의어 일치"
        else:
            match_type = "동의어 일치"

        deduped_terms = list(dict.fromkeys(matched_terms))
        result_scores.append(min(100.0, score))
        result_terms.append(deduped_terms)
        result_types.append(match_type)
        exact_flags.append(exact_all)

    matched["관련도점수"] = result_scores
    matched["매칭키워드"] = result_terms
    matched["일치유형"] = result_types
    matched["정확일치여부"] = exact_flags

    if sort_by == "최신순":
        sort_columns, ascending = ["날짜", "관련도점수"], [False, False]
    elif sort_by == "최고 상승률순":
        sort_columns, ascending = ["상승률", "관련도점수", "날짜"], [False, False, False]
    else:
        sort_columns, ascending = ["관련도점수", "날짜", "상승률"], [False, False, False]
    matched = matched.sort_values(sort_columns, ascending=ascending, na_position="last")
    return matched.reset_index(drop=True), applied_terms
