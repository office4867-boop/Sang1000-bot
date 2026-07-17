"""상천봇 키워드 분석용 Streamlit UI 컴포넌트."""

from __future__ import annotations

import html
from typing import Iterable

import altair as alt
import pandas as pd
import streamlit as st


def apply_page_style() -> None:
    st.markdown(
        """
        <style>
        .block-container {max-width: 1420px; padding-top: 1.6rem; padding-bottom: 3rem;}
        html, body, [class*="css"] {font-size: 17px; line-height: 1.65;}
        div[data-testid="stMetric"] {
            background: #f7f9fc; border: 1px solid #e5eaf1; border-radius: 12px;
            padding: 0.8rem 1rem;
        }
        div[data-testid="stDataFrame"] {font-size: 0.96rem;}
        mark.keyword-hit {background: #ffe082; color: #111827; padding: 0.05rem 0.15rem; border-radius: 3px;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def highlight_literal_terms(text: object, terms: Iterable[str]) -> str:
    """원문을 먼저 구간으로 나눈 뒤 escape해 안전하게 강조한다."""
    original = "" if text is None or pd.isna(text) else str(text)
    candidates = sorted(
        {str(term) for term in terms if str(term).strip()},
        key=len,
        reverse=True,
    )
    if not original or not candidates:
        return html.escape(original).replace("\n", "<br>")

    lowered = original.lower()
    cursor = 0
    rendered: list[str] = []
    while cursor < len(original):
        found = []
        for term in candidates:
            position = lowered.find(term.lower(), cursor)
            if position >= 0:
                found.append((position, -len(term), term))
        if not found:
            rendered.append(html.escape(original[cursor:]))
            break
        position, _, term = min(found)
        rendered.append(html.escape(original[cursor:position]))
        end = position + len(term)
        rendered.append(
            f'<mark class="keyword-hit">{html.escape(original[position:end])}</mark>'
        )
        cursor = end
    return "".join(rendered).replace("\n", "<br>")


def _format_date(value) -> str:
    parsed = pd.to_datetime(value, errors="coerce")
    return "-" if pd.isna(parsed) else parsed.strftime("%Y-%m-%d")


def _preview(value: object, limit: int = 150) -> str:
    text = "" if value is None or pd.isna(value) else " ".join(str(value).split())
    return text if len(text) <= limit else f"{text[:limit].rstrip()}…"


def _matrix_style(matrix: pd.DataFrame):
    numeric = matrix.apply(pd.to_numeric, errors="coerce")
    maximum = numeric.max().max()
    maximum = float(maximum) if pd.notna(maximum) and maximum > 0 else 1.0

    def cell_style(value):
        if pd.isna(value):
            return "background-color: transparent; color: transparent"
        intensity = min(0.88, 0.12 + float(value) / maximum * 0.76)
        text_color = "white" if intensity >= 0.55 else "#7f1d1d"
        return f"background-color: rgba(220, 38, 38, {intensity:.2f}); color: {text_color}"

    return numeric.style.map(cell_style).format("{:.2f}%", na_rep="")


def render_keyword_dashboard(
    query: str,
    applied_terms: list[str],
    search_results: pd.DataFrame,
    cycle_summaries: pd.DataFrame,
    cycle_members: pd.DataFrame,
    ranking: pd.DataFrame,
    reaction_matrix: pd.DataFrame,
) -> str | None:
    """키워드 결과를 렌더링하고 상세화면으로 이동할 종목키를 반환한다."""
    if search_results is None or search_results.empty:
        st.warning(f"'{query}'와 일치하는 검색 문서가 없습니다.")
        return None

    st.markdown("---")
    st.subheader("과거 유사 이슈 분석")
    st.info(
        f"검색어: **{query}**  \n"
        f"적용된 연관어: **{', '.join(applied_terms) if applied_terms else '없음(원문만 검색)'}**"
    )

    recent_date = (
        cycle_summaries["종료일"].max()
        if cycle_summaries is not None and not cycle_summaries.empty
        else pd.NaT
    )
    strongest = None
    if cycle_summaries is not None and not cycle_summaries.empty:
        strongest = cycle_summaries.sort_values(
            ["평균상승률", "동시상승종목수"], ascending=False
        ).iloc[0]

    summary_columns = st.columns(5)
    summary_columns[0].metric("관련 종목", f"{ranking['종목키'].nunique():,}개")
    summary_columns[1].metric("과거 부각 회차", f"{len(cycle_summaries):,}회")
    summary_columns[2].metric("최근 부각일", _format_date(recent_date))
    summary_columns[3].metric(
        "가장 강했던 회차",
        strongest["회차레이블"] if strongest is not None else "-",
    )
    summary_columns[4].metric("매칭 근거", f"{len(search_results):,}건")

    rank_tab, cycles_tab, matrix_tab, evidence_tab = st.tabs(
        ["종목 순위", "과거 이슈 회차", "반응 매트릭스", "근거 문장"]
    )
    selected_key = None

    with rank_tab:
        if ranking.empty:
            st.caption("표시할 종목 순위가 없습니다.")
        else:
            display_columns = [
                "순위", "종목명", "종합점수", "관련도", "부각회차수", "대장횟수",
                "최고상승률", "최근부각일", "매칭건수",
            ]
            display = ranking[display_columns].copy()
            display["최근부각일"] = display["최근부각일"].apply(_format_date)
            st.caption("종합점수 = 관련도 40 + 반복성 25 + 주도성 20 + 확산 10 + 최근성 5")
            st.dataframe(display, hide_index=True, width="stretch")

            labels = {
                row["종목키"]: f"{int(row['순위'])}위 · {row['종목명']} ({row['종목키']})"
                for _, row in ranking.iterrows()
            }
            picked = st.selectbox(
                "상세정보로 이동할 종목",
                options=list(labels),
                format_func=lambda key: labels[key],
                key=f"keyword_stock_choice_{query}",
            )
            if st.button("선택 종목 상세보기", key=f"keyword_stock_open_{query}"):
                selected_key = picked

    with cycles_tab:
        if cycle_summaries is None or cycle_summaries.empty:
            st.caption("검색어와 직접 매칭된 날짜·상승률 이력이 없어 회차를 만들 수 없습니다.")
        else:
            timeline = cycle_summaries.copy()
            timeline["날짜"] = pd.to_datetime(timeline["시작일"])
            chart = (
                alt.Chart(timeline)
                .mark_circle(opacity=0.82)
                .encode(
                    x=alt.X("날짜:T", title="날짜"),
                    y=alt.Y("평균상승률:Q", title="평균 상승률(%)"),
                    size=alt.Size("동시상승종목수:Q", title="상승 종목 수"),
                    color=alt.Color("평균상승률:Q", scale=alt.Scale(scheme="reds"), title="평균 상승률"),
                    tooltip=["회차레이블", "분류", "동시상승종목수", "평균상승률", "대장주"],
                )
                .properties(height=310)
            )
            st.altair_chart(chart, width="stretch")

            for _, cycle in cycle_summaries.iterrows():
                title = (
                    f"{cycle['회차레이블']} · {cycle['분류']} · "
                    f"{int(cycle['동시상승종목수'])}종목"
                )
                with st.expander(title):
                    metrics = st.columns(5)
                    metrics[0].metric("평균 상승률", f"{cycle['평균상승률']:.2f}%")
                    metrics[1].metric("중앙 상승률", f"{cycle['중앙상승률']:.2f}%")
                    metrics[2].metric("대장주", cycle["대장주"])
                    metrics[3].metric("15% 이상", f"{int(cycle['15%이상종목수'])}개")
                    metrics[4].metric("상한가", f"{int(cycle['상한가수'])}개")
                    st.markdown(f"**핵심 매칭 문장**  \n{_preview(cycle['핵심매칭문장'], 260)}")
                    members = cycle_members[cycle_members["회차"] == cycle["회차"]].copy()
                    member_display = members[
                        ["회차내순위", "종목명", "상승률", "날짜", "일치유형", "근거문장"]
                    ].sort_values("회차내순위")
                    member_display["날짜"] = member_display["날짜"].apply(_format_date)
                    member_display["근거문장"] = member_display["근거문장"].apply(_preview)
                    st.dataframe(member_display, hide_index=True, width="stretch")

    with matrix_tab:
        if reaction_matrix is None or reaction_matrix.empty:
            st.caption("반응 매트릭스를 만들 수 있는 상승 이력이 없습니다.")
        else:
            show_all = st.checkbox(
                "전체 종목·회차 보기",
                value=False,
                key=f"keyword_matrix_all_{query}",
                help="기본 화면은 종합점수 상위 20종목과 최근 12회차만 표시합니다.",
            )
            matrix = reaction_matrix.copy()
            if not show_all:
                top_labels = [
                    f"{row['종목명']} ({row['종목키']})"
                    for _, row in ranking.head(20).iterrows()
                ]
                latest_cycles = cycle_summaries.head(12)["회차"].tolist()
                matrix = matrix.reindex(
                    index=[label for label in top_labels if label in matrix.index],
                    columns=[cycle for cycle in latest_cycles if cycle in matrix.columns],
                )
            st.caption("셀은 해당 종목의 회차 내 최고 상승률이며, 빈칸은 매칭 이력이 없음을 뜻합니다.")
            st.dataframe(_matrix_style(matrix), width="stretch")

    with evidence_tab:
        show_all_evidence = len(search_results) <= 100 or st.checkbox(
            f"근거 {len(search_results):,}건 전체 보기",
            value=False,
            key=f"keyword_evidence_all_{query}",
        )
        evidence_rows = search_results if show_all_evidence else search_results.head(100)
        if not show_all_evidence:
            st.caption("관련도 상위 100건을 표시하고 있습니다.")

        for index, row in evidence_rows.iterrows():
            terms = row.get("매칭키워드") or []
            rise = row.get("상승률")
            rise_text = f" · {float(rise):.2f}%" if pd.notna(rise) else ""
            title = (
                f"{row['종목명']} · {_format_date(row.get('날짜'))}{rise_text} · "
                f"{row['출처']} · {_preview(row.get('근거문장'), 90)}"
            )
            with st.expander(title):
                st.caption(
                    f"일치 방식: {row.get('일치유형', '-')} | "
                    f"매칭 키워드: {', '.join(map(str, terms)) or '-'} | "
                    f"관련도: {float(row.get('관련도점수', 0)):.1f}"
                )
                st.markdown(
                    highlight_literal_terms(row.get("근거문장", ""), terms),
                    unsafe_allow_html=True,
                )

    return selected_key


def render_hot_issue_dashboard(
    ranking: pd.DataFrame,
    issue_events: pd.DataFrame,
    metadata: dict[str, object],
) -> str | None:
    """기간별 핫이슈 순위와 근거 이력을 표시하고 선택 이슈를 반환한다."""
    if ranking is None or ranking.empty:
        st.warning("선택한 기간과 최소 종목 수 조건에 맞는 핫이슈가 없습니다.")
        return None

    start_text = _format_date(metadata.get("시작일"))
    end_text = _format_date(metadata.get("종료일"))
    top_issue = ranking.iloc[0]
    summary_columns = st.columns(5)
    summary_columns[0].metric("분석 기간", f"{start_text}~{end_text}")
    summary_columns[1].metric("거래일", f"{int(metadata.get('거래일수', 0))}일")
    summary_columns[2].metric("포착 이슈", f"{len(ranking):,}개")
    summary_columns[3].metric("1위 이슈", top_issue["이슈"])
    summary_columns[4].metric("1위 점수", f"{top_issue['핫점수']:.1f}점")

    if metadata.get("비교여부"):
        st.caption(
            f"이전 동일 거래기간 {_format_date(metadata.get('이전시작일'))}"
            f"~{_format_date(metadata.get('이전종료일'))}과 비교합니다."
        )
    st.caption(
        "핫점수 = 상승 종목 확산 30 + 부각 거래일·회차 25 + 반복 종목 20 + "
        "평균·중앙 상승 강도 15 + 최근성 10"
    )

    chart_data = ranking.head(20).copy()
    chart = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X("핫점수:Q", title="핫점수"),
            y=alt.Y("이슈:N", sort="-x", title=None),
            color=alt.Color("상태:N", title="상태"),
            tooltip=[
                "순위", "이슈", "핫점수", "상태", "상승종목수", "부각회차수",
                "반복종목수", "평균상승률", "대장주", "최근부각일",
            ],
        )
        .properties(height=max(320, min(680, len(chart_data) * 28)))
    )
    st.altair_chart(chart, width="stretch")

    display_columns = [
        "순위", "이슈", "핫점수", "상태", "상승종목수", "부각거래일수", "부각회차수",
        "반복종목수", "평균상승률", "중앙상승률", "15%이상종목수", "상한가수",
        "대장주", "최근부각일", "점수변화",
    ]
    display = ranking[display_columns].copy()
    display["최근부각일"] = display["최근부각일"].apply(_format_date)
    st.dataframe(display, hide_index=True, width="stretch")

    labels = {
        row["이슈"]: (
            f"{int(row['순위'])}위 · {row['이슈']} · {row['핫점수']:.1f}점 · "
            f"{int(row['상승종목수'])}종목"
        )
        for _, row in ranking.iterrows()
    }
    selected_issue = st.selectbox(
        "상세 분석할 이슈",
        options=list(labels),
        format_func=lambda issue: labels[issue],
        key=f"hot_issue_choice_{start_text}_{end_text}",
    )

    selected_summary = ranking[ranking["이슈"] == selected_issue].iloc[0]
    metrics = st.columns(5)
    metrics[0].metric("상승 종목", f"{int(selected_summary['상승종목수'])}개")
    metrics[1].metric("부각 회차", f"{int(selected_summary['부각회차수'])}회")
    metrics[2].metric("반복 종목", f"{int(selected_summary['반복종목수'])}개")
    metrics[3].metric("평균 상승률", f"{selected_summary['평균상승률']:.2f}%")
    metrics[4].metric("대장주", selected_summary["대장주"])

    selected_events = issue_events[issue_events["이슈"] == selected_issue].copy()
    selected_events = selected_events.sort_values(["날짜", "상승률"], ascending=[False, False])
    if not selected_events.empty:
        evidence = selected_events[
            ["날짜", "회차번호", "종목명", "상승률", "상승이유", "원본테마"]
        ].head(100).copy()
        evidence["날짜"] = evidence["날짜"].apply(_format_date)
        evidence["상승이유"] = evidence["상승이유"].apply(_preview)
        st.dataframe(evidence, hide_index=True, width="stretch")

    if st.button(
        f"'{selected_issue}' 과거 이슈 상세 분석",
        key=f"open_hot_issue_{start_text}_{end_text}",
        type="primary",
    ):
        return selected_issue
    return None
