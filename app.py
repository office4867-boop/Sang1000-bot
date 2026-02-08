import streamlit as st
import pandas as pd
import os
from app_utils import (
    LIMIT_UP_THRESHOLD, MAX_SEARCH_RESULTS,
    clean_columns, convert_rise_rate, format_date, render_theme_badge,
    find_repo_file, load_data, load_company_overview, load_theme_data
)

# ---------------------------------------------------------
# 1. 페이지 설정
# ---------------------------------------------------------
st.set_page_config(page_title="주식 분석 봇", layout="wide")

# --- [비밀번호 보안 기능 시작] ---
MY_PASSWORD = "" 
login_pass = st.sidebar.text_input("🔑 비밀번호를 입력하세요", type="password")

if login_pass != MY_PASSWORD:
    st.error("비밀번호가 일치하지 않으면 내용을 볼 수 없습니다.")
    st.stop()
# --- [비밀번호 보안 기능 끝] ---

st.title("📈 주식 데이터 분석 챗봇 (하이브리드)")
st.markdown("---")

# ---------------------------------------------------------
# 2. 데이터 로드 로직
# ---------------------------------------------------------
with st.sidebar:
    st.header("📂 데이터 설정")
    
    # [1] 파일 업로더
    uploaded_file = st.file_uploader("새 엑셀 파일 업로드 (선택)", type=['xlsx'])
    
    # [2] 기본 파일 찾기
    repo_file = find_repo_file()

    if st.button("🔄 새로고침"):
        st.cache_data.clear()
        st.rerun()

# 로직 결정
final_file = None
source_msg = ""

if uploaded_file:
    final_file = uploaded_file
    source_msg = "📂 업로드된 파일을 분석 중입니다."
elif repo_file:
    final_file = repo_file
    source_msg = f"☁️ 서버(기본) 파일 사용 중: {repo_file}"
else:
    st.error("❌ 데이터를 찾을 수 없습니다. 깃허브에 엑셀 파일을 올리거나, 직접 업로드해주세요.")
    st.stop()

# 데이터 읽기
df_sangcheon, df_signal, err = load_data(final_file)

if err:
    st.error(f"오류 발생: {err}")
    st.stop()

# 보조 데이터 로드
df_company_overview = load_company_overview()
df_themes = load_theme_data()

st.success(f"✅ {source_msg}")

# ---------------------------------------------------------
# 3. 분석 화면 (검색 및 결과 표시)
# ---------------------------------------------------------
if '종목명' not in df_sangcheon.columns:
    st.error("데이터에서 '종목명' 컬럼을 찾을 수 없습니다.")
    st.stop()

# 종목명 리스트 추출
stock_list = df_sangcheon['종목명'].dropna().unique().tolist()
stock_list = sorted([str(s) for s in stock_list if pd.notna(s)])

# 세션 상태 초기화
if 'selected_stock_name' not in st.session_state:
    st.session_state.selected_stock_name = None
if 'current_query' not in st.session_state:
    st.session_state.current_query = None
if 'search_mode' not in st.session_state:
    st.session_state.search_mode = "종목명"

# 버튼 클릭으로 종목 선택된 경우 처리
if st.session_state.selected_stock_name:
    st.session_state.current_query = st.session_state.selected_stock_name
    st.session_state.selected_stock_name = None
    st.session_state.search_mode = "종목명"
    # 라디오 버튼 상태도 직접 업데이트 (Streamlit 위젯 상태)
    st.session_state.search_mode_radio = "종목명"

# 검색 모드 라디오 버튼
search_mode = st.radio(
    "검색 모드", 
    ["종목명", "테마"], 
    horizontal=True, 
    key="search_mode_radio", 
    index=0 if st.session_state.search_mode == "종목명" else 1
)
st.session_state.search_mode = search_mode

query = None
theme_results = None

if search_mode == "종목명":
    # 현재 선택된 종목이 있으면 표시
    if st.session_state.current_query:
        st.info(f"📌 현재 분석 중: **{st.session_state.current_query}**")
        col1, col2 = st.columns([3, 1])
        with col1:
            query = st.session_state.current_query
        with col2:
            if st.button("🔄 새 검색", use_container_width=True):
                st.session_state.current_query = None
                st.rerun()
    else:
        # 검색어 입력
        search_query = st.text_input("🔍 종목명 검색 (자동완성)", placeholder="예: 삼성전자...", key="stock_search")
        
        # 필터링
        filtered_stocks = stock_list
        if search_query:
            search_lower = search_query.lower()
            filtered_stocks = [s for s in stock_list if search_lower in s.lower()]
        
        if len(filtered_stocks) > MAX_SEARCH_RESULTS:
            filtered_stocks = filtered_stocks[:MAX_SEARCH_RESULTS]
            st.info(f"💡 검색 결과가 많아 {MAX_SEARCH_RESULTS}개만 표시됩니다.")
        
        # 종목 선택
        if filtered_stocks:
            selected_stock = st.selectbox(
                "📋 종목 선택",
                options=[""] + filtered_stocks,
                format_func=lambda x: "종목을 선택하세요..." if x == "" else x,
                key="stock_select"
            )
            
            if selected_stock:
                st.session_state.current_query = selected_stock
                query = selected_stock
            elif search_query and search_query in stock_list:
                st.session_state.current_query = search_query
                query = search_query
        else:
            if search_query:
                st.warning(f"'{search_query}'와 일치하는 종목이 없습니다.")

else:  # 테마 검색
    theme_query = st.text_input("🔍 테마 검색", placeholder="예: 반도체, AI...", key="theme_search")
    
    if theme_query and df_themes is not None:
        # 벡터화된 검색 (빠름!)
        mask = df_themes['테마_전체'].str.lower().str.contains(theme_query.lower(), na=False)
        matched_stocks = df_themes.loc[mask, '종목명'].unique().tolist()
        
        if matched_stocks:
            # 테마 이슈 상승률 기준으로 정렬
            theme_keyword = theme_query.lower()
            scored_results = []
            
            for stock_name in matched_stocks:
                stock_data = df_sangcheon[df_sangcheon['종목명'] == stock_name]
                theme_matched_rise = 0
                theme_matched_count = 0
                max_rise = 0
                
                if not stock_data.empty and '상승률' in stock_data.columns:
                    for _, sr in stock_data.iterrows():
                        rise_val, _ = convert_rise_rate(sr.get('상승률'))
                        reason = sr.get('상승이유', '')
                        
                        if rise_val is not None:
                            max_rise = max(max_rise, rise_val)
                            
                            # 상승이유에 검색 테마 키워드가 포함되어 있는지 확인
                            if pd.notna(reason) and theme_keyword in str(reason).lower():
                                theme_matched_rise = max(theme_matched_rise, rise_val)
                                theme_matched_count += 1
                
                # 점수 계산: 테마 상승률 우선, 그 다음 최고 상승률
                score = (theme_matched_rise * 2) + (theme_matched_count * 5) + (max_rise * 0.5)
                
                scored_results.append({
                    '종목명': stock_name,
                    '테마상승률': theme_matched_rise,
                    '테마상승횟수': theme_matched_count,
                    '최고상승률': max_rise,
                    '점수': score
                })
            
            # 점수 순으로 정렬
            scored_results.sort(key=lambda x: x['점수'], reverse=True)
            theme_results = scored_results
        else:
            st.warning(f"'{theme_query}' 테마가 포함된 종목을 찾을 수 없습니다.")
    elif theme_query and df_themes is None:
        st.warning("테마 데이터를 불러올 수 없습니다.")

# 테마 검색 결과 표시
if theme_results:
    st.markdown("---")
    st.subheader(f"🔍 테마 '{theme_query}' 검색 결과 ({len(theme_results)}개)")
    st.caption("📌 해당 테마 이슈 상승률 순으로 정렬됨")
    
    if len(theme_results) > 10:
        cols_per_row = 3
        for i in range(0, len(theme_results), cols_per_row):
            cols = st.columns(cols_per_row)
            for j, stock_info in enumerate(theme_results[i:i+cols_per_row]):
                stock_name = stock_info['종목명'] if isinstance(stock_info, dict) else stock_info
                theme_rise = stock_info.get('테마상승률', 0) if isinstance(stock_info, dict) else 0
                max_rise = stock_info.get('최고상승률', 0) if isinstance(stock_info, dict) else 0
                
                with cols[j]:
                    # 버튼 라벨
                    label = stock_name
                    if theme_rise >= LIMIT_UP_THRESHOLD:
                        label = f"🔥 {stock_name}"
                    elif theme_rise > 0:
                        label = f"🎯 {stock_name}"
                    
                    if st.button(label, key=f"theme_{theme_query}_{stock_name}", use_container_width=True):
                        st.session_state.selected_stock_name = stock_name
                        st.rerun()
                    
                    # 상승률 표시
                    if theme_rise > 0:
                        st.caption(f"테마상승 {theme_rise:.1f}%")
                    elif max_rise > 0:
                        st.caption(f"최고 {max_rise:.1f}%")
    else:
        for idx, stock_info in enumerate(theme_results, 1):
            stock_name = stock_info['종목명'] if isinstance(stock_info, dict) else stock_info
            theme_rise = stock_info.get('테마상승률', 0) if isinstance(stock_info, dict) else 0
            max_rise = stock_info.get('최고상승률', 0) if isinstance(stock_info, dict) else 0
            
            col1, col2 = st.columns([4, 1])
            with col1:
                label = f"{idx}. {stock_name}"
                if theme_rise >= LIMIT_UP_THRESHOLD:
                    label = f"{idx}. 🔥 {stock_name}"
                elif theme_rise > 0:
                    label = f"{idx}. 🎯 {stock_name}"
                
                if st.button(label, key=f"themelist_{theme_query}_{stock_name}", use_container_width=True):
                    st.session_state.selected_stock_name = stock_name
                    st.rerun()
            with col2:
                if theme_rise > 0:
                    st.caption(f"{theme_rise:.1f}%")
                elif max_rise > 0:
                    st.caption(f"{max_rise:.1f}%")

# 종목 상세 분석 표시
if query:
    res = df_sangcheon[df_sangcheon['종목명'] == query].copy()
    
    if res.empty:
        st.warning(f"'{query}' 종목의 데이터를 찾을 수 없습니다.")
    else:
        if '날짜' in res.columns:
            res = res.sort_values('날짜', ascending=False)
        
        row = res.iloc[0]
        
        st.markdown("---")
        st.subheader(f"📊 {query} 종목 분석")
        
        # 1. 기업개요
        summary_text = None
        if df_company_overview is not None and '종목명' in df_company_overview.columns:
            overview_row = df_company_overview[df_company_overview['종목명'] == query]
            if not overview_row.empty:
                # 핵심요약 컬럼 찾기
                summary_col = next((c for c in df_company_overview.columns if any(k in c for k in ['핵심요약', '3줄정리'])), None)
                if summary_col:
                    val = overview_row.iloc[0][summary_col]
                    if pd.notna(val):
                        summary_text = str(val)
        
        if summary_text:
            st.markdown(summary_text)
        else:
            st.caption("기업개요 정보가 없습니다.")
        
        st.markdown("---")
        
        # 2. 테마 정보
        theme_text = row.get('테마', '-')
        # df_themes에서 더 정확한 정보가 있으면 덮어쓰기
        if df_themes is not None:
            theme_row = df_themes[df_themes['종목명'] == query]
            if not theme_row.empty:
                theme_text = theme_row.iloc[0]['테마_전체']
        
        st.markdown(render_theme_badge(theme_text), unsafe_allow_html=True)
        st.markdown("---")
        
        # 3. 최근 상승 이슈 (최근 3회)
        st.subheader("📊 최근 상승 이슈 (최근 3회)")
        
        recent_3 = res.head(3)
        recent_dates = set()
        
        if not recent_3.empty:
            for idx, (_, r) in enumerate(recent_3.iterrows(), 1):
                date_str = format_date(r.get('날짜'))
                recent_dates.add(date_str)
                
                rise_val, rise_disp = convert_rise_rate(r.get('상승률'))
                is_limit_up = (rise_val is not None and rise_val >= LIMIT_UP_THRESHOLD)
                limit_badge = " 🔥 상한가" if is_limit_up else ""
                
                reason = r.get('상승이유', '-')
                if pd.isna(reason): reason = '-'
                
                with st.container():
                    c1, c2 = st.columns([1, 4])
                    c1.write(f"**{idx}.** {date_str}{limit_badge}")
                    c2.write(f"상승률: {rise_disp} | {reason}" if reason != '-' else f"상승률: {rise_disp}")
                    st.divider()
        else:
            st.caption("상승 이슈 데이터가 없습니다.")
            
        # 4. 과거 상한가 이력
        st.markdown("---")
        st.subheader("🔥 과거 상한가 이력")
        
        limit_up_history = []
        for _, r in res.iterrows():
            rise_val, rise_disp = convert_rise_rate(r.get('상승률'))
            if rise_val is not None and rise_val >= LIMIT_UP_THRESHOLD:
                date_str = format_date(r.get('날짜'))
                
                # 최근 3회에 이미 나온 날짜면 제외
                if date_str in recent_dates:
                    continue
                    
                limit_up_history.append({
                    '날짜': date_str,
                    '상승률': rise_disp,
                    '상승이유': r.get('상승이유', '-'),
                    '원본_날짜': r.get('날짜', pd.Timestamp.min)
                })
        
        if limit_up_history:
            # 날짜순 정렬
            limit_up_history.sort(key=lambda x: x['원본_날짜'], reverse=True)
            
            for idx, h in enumerate(limit_up_history, 1):
                with st.container():
                    c1, c2 = st.columns([1, 4])
                    c1.write(f"**{idx}.** {h['날짜']} 🔥")
                    reason = h['상승이유']
                    c2.write(f"상승률: {h['상승률']} | {reason}" if reason != '-' else f"상승률: {h['상승률']}")
                    st.divider()
        else:
            st.caption("과거 상한가 이력이 없습니다.")
            
        # 5. 뉴스 및 유사 종목
        st.markdown("---")
        st.subheader("📝 종목 설명 & 뉴스")
        if df_signal is not None and '종목명' in df_signal.columns:
            news_col = next((c for c in ['주요뉴스','뉴스','내용'] if c in df_signal.columns), None)
            if news_col:
                news_df = df_signal[df_signal['종목명'] == query]
                if not news_df.empty:
                    for _, r in news_df.iterrows():
                        st.write(f"• {r[news_col]}")
                else:
                    st.caption("관련 뉴스가 없습니다.")
            else:
                st.caption("뉴스 컬럼을 찾을 수 없습니다.")
        else:
            st.caption("뉴스 데이터가 없습니다.")
            
        st.markdown("---")
        st.subheader("🔗 유사 종목 (같은 테마)")
        
        similar_stocks = []
        search_method = None
        
        # ========================================
        # 1순위: 해시태그 매칭 + 상승률 혼합 점수
        # ========================================
        if df_themes is not None and theme_text and theme_text != '-' and not pd.isna(theme_text):
            # 현재 종목의 해시태그들 추출
            current_hashtags = set()
            for tag in str(theme_text).split('#'):
                tag = tag.strip()
                if tag:
                    current_hashtags.add(tag.lower())
            
            if current_hashtags:
                # 다른 종목들과 공통 해시태그 개수 및 상승률 계산
                similarity_scores = []
                
                for _, theme_row in df_themes.iterrows():
                    stock_name = theme_row.get('종목명', '')
                    themes_str = theme_row.get('테마_전체', '')
                    
                    # 자기 자신 제외
                    if stock_name == query:
                        continue
                    
                    if pd.isna(themes_str):
                        continue
                    
                    # 해당 종목의 해시태그 추출
                    other_hashtags = set()
                    for tag in str(themes_str).split('#'):
                        tag = tag.strip()
                        if tag:
                            other_hashtags.add(tag.lower())
                    
                    # 공통 해시태그 개수 계산
                    common_count = len(current_hashtags & other_hashtags)
                    
                    if common_count > 0:
                        # 해당 종목의 상승 데이터 분석 (종목정리 파일에서)
                        stock_data = df_sangcheon[df_sangcheon['종목명'] == stock_name]
                        max_rise = 0
                        theme_matched_rise = 0  # 공통 테마 이슈로 상승한 최고 상승률
                        theme_matched_count = 0  # 공통 테마 이슈로 상승한 횟수
                        
                        # 공통 해시태그 (검색용 키워드)
                        common_hashtags = current_hashtags & other_hashtags
                        
                        if not stock_data.empty and '상승률' in stock_data.columns:
                            for _, sr in stock_data.iterrows():
                                rise_val, _ = convert_rise_rate(sr.get('상승률'))
                                reason = sr.get('상승이유', '')
                                
                                if rise_val is not None:
                                    max_rise = max(max_rise, rise_val)
                                    
                                    # 상승이유에 공통 테마 키워드가 포함되어 있는지 확인
                                    if pd.notna(reason):
                                        reason_lower = str(reason).lower()
                                        for tag in common_hashtags:
                                            # 해시태그에서 키워드 추출 (예: "양자암호" -> "양자", "암호")
                                            keywords = [tag]
                                            # 복합어 분리도 시도 (간단한 방식)
                                            if len(tag) > 2:
                                                keywords.append(tag[:2])  # 앞 2글자
                                            
                                            for kw in keywords:
                                                if kw in reason_lower:
                                                    theme_matched_rise = max(theme_matched_rise, rise_val)
                                                    theme_matched_count += 1
                                                    break
                        
                        # 개선된 혼합 점수 계산:
                        # - 공통 테마 개수 × 10 (기본 관련성)
                        # - 테마 매칭 상승률 × 2 (해당 테마 이슈로 오른 경우 가중치)
                        # - 테마 매칭 횟수 × 5 (해당 테마로 여러 번 오른 경우 보너스)
                        # - 최고 상승률 × 0.5 (전체 상승률은 보조적으로만)
                        hybrid_score = (common_count * 10) + (theme_matched_rise * 2) + (theme_matched_count * 5) + (max_rise * 0.5)
                        
                        similarity_scores.append({
                            '종목명': stock_name,
                            '공통개수': common_count,
                            '최고상승률': max_rise,
                            '테마상승률': theme_matched_rise,
                            '테마상승횟수': theme_matched_count,
                            '혼합점수': hybrid_score
                        })
                
                # 혼합 점수 순으로 정렬
                similarity_scores.sort(key=lambda x: x['혼합점수'], reverse=True)
                similar_stocks = similarity_scores[:5]
                
                if similar_stocks:
                    search_method = "hashtag"
        
        # ========================================
        # 2순위: 종목정리_종목순 정렬.xlsx에서 테마 일치 (폴백)
        # ========================================
        if not similar_stocks:
            row_theme = row.get('테마')
            if row_theme and pd.notna(row_theme):
                sims_df = df_sangcheon[(df_sangcheon['테마'] == row_theme) & (df_sangcheon['종목명'] != query)]
                sims_df = sims_df.drop_duplicates('종목명')
                
                # 2순위도 상승률 기준 정렬
                fallback_scores = []
                for stock_name in sims_df['종목명'].unique():
                    stock_data = df_sangcheon[df_sangcheon['종목명'] == stock_name]
                    max_rise = 0
                    if not stock_data.empty and '상승률' in stock_data.columns:
                        for _, sr in stock_data.iterrows():
                            rise_val, _ = convert_rise_rate(sr.get('상승률'))
                            if rise_val is not None:
                                max_rise = max(max_rise, rise_val)
                    fallback_scores.append({'종목명': stock_name, '최고상승률': max_rise, '혼합점수': max_rise})
                
                fallback_scores.sort(key=lambda x: x['최고상승률'], reverse=True)
                similar_stocks = fallback_scores[:5]
                
                if similar_stocks:
                    search_method = "theme"
        
        # ========================================
        # 결과 표시
        # ========================================
        if similar_stocks:
            if search_method == "hashtag":
                st.caption("📌 관련테마 + 상승률 기반 추천")
            else:
                st.caption("📌 동일 테마 + 상승률 기반 추천")
            
            cols = st.columns(len(similar_stocks))
            for i, stock_info in enumerate(similar_stocks):
                stock_name = stock_info['종목명']
                max_rise = stock_info.get('최고상승률', 0)
                
                with cols[i]:
                    # 버튼 라벨에 최고 상승률 표시
                    label = f"{stock_name}"
                    if max_rise >= LIMIT_UP_THRESHOLD:
                        label = f"🔥 {stock_name}"
                    
                    if st.button(label, key=f"sim_{query}_{stock_name}", use_container_width=True):
                        st.session_state.selected_stock_name = stock_name
                        st.rerun()
                    
                    # 상승률 표시 (테마 매칭 상승률 우선, 없으면 최고 상승률)
                    theme_rise = stock_info.get('테마상승률', 0)
                    if theme_rise > 0:
                        st.caption(f"🎯 테마상승 {theme_rise:.1f}%")
                    elif max_rise > 0:
                        st.caption(f"최고 {max_rise:.1f}%")
        else:
            st.caption("유사 종목을 찾을 수 없습니다.")