import streamlit as st
import pandas as pd
import os
from app_utils import (
    LIMIT_UP_THRESHOLD, MAX_SEARCH_RESULTS,
    clean_columns, convert_rise_rate, format_date, render_theme_badge,
    find_repo_file, load_data, load_company_overview, load_theme_data, load_analysis_data,
    load_name_aliases, load_stock_code_map, normalize_stock_code, clear_disk_cache
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
        clear_disk_cache()
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
df_analysis = load_analysis_data()
name_aliases = load_name_aliases()  # {구 사명: 현재 사명}
stock_code_map = load_stock_code_map()  # {종목명/구 사명: 종목코드}

st.success(f"✅ {source_msg}")

# ---------------------------------------------------------
# 3. 분석 화면 (검색 및 결과 표시)
# ---------------------------------------------------------
if '종목명' not in df_sangcheon.columns:
    st.error("데이터에서 '종목명' 컬럼을 찾을 수 없습니다.")
    st.stop()

df_sangcheon['종목명'] = df_sangcheon['종목명'].astype(str).str.strip()
if '종목코드' not in df_sangcheon.columns:
    df_sangcheon['종목코드'] = ""
else:
    df_sangcheon['종목코드'] = df_sangcheon['종목코드'].apply(normalize_stock_code)

def clean_name(value):
    if pd.isna(value):
        return ""
    return str(value).strip()

def resolve_alias_name(name):
    """A→B→C처럼 여러 번 바뀐 사명을 최종 사명으로 정리"""
    current = clean_name(name)
    seen = set()
    while current in name_aliases and current not in seen:
        seen.add(current)
        next_name = clean_name(name_aliases[current])
        if not next_name or next_name == current:
            break
        current = next_name
    return current

def resolve_code_by_name(name):
    """종목명/구 사명으로 누적 코드 매핑에서 종목코드 찾기"""
    current = clean_name(name)
    seen = set()

    while current and current not in seen:
        code = normalize_stock_code(stock_code_map.get(current, ""))
        if code:
            return code

        seen.add(current)
        next_name = clean_name(name_aliases.get(current, ""))
        if not next_name or next_name == current:
            break
        current = next_name

    return ""

def fill_missing_stock_codes(df):
    """엑셀에 빈 종목코드가 남아 있으면 stock_code_map.json으로 화면 로딩 시 보정"""
    if df is None or df.empty or '종목명' not in df.columns:
        return df

    df['종목명'] = df['종목명'].astype(str).str.strip()
    if '종목코드' not in df.columns:
        df['종목코드'] = ""
    else:
        df['종목코드'] = df['종목코드'].apply(normalize_stock_code)

    missing_mask = ~df['종목코드'].astype(bool)
    if missing_mask.any():
        df.loc[missing_mask, '종목코드'] = df.loc[missing_mask, '종목명'].apply(resolve_code_by_name)

    return df

df_sangcheon = fill_missing_stock_codes(df_sangcheon)
df_company_overview = fill_missing_stock_codes(df_company_overview)
df_themes = fill_missing_stock_codes(df_themes)
df_analysis = fill_missing_stock_codes(df_analysis)

use_stock_code = df_sangcheon['종목코드'].astype(bool).any()
if not use_stock_code:
    st.warning("종목코드 컬럼이 없어 종목명 기준으로 검색합니다. 사명 변경 추적 정확도를 높이려면 엑셀에 종목코드를 유지해주세요.")

def make_stock_key(code, name):
    code = normalize_stock_code(code)
    if use_stock_code and code:
        return code
    return clean_name(name)

def assign_stock_keys(df):
    """각 데이터프레임에 빠른 조회용 종목 키를 붙임"""
    if df is None or df.empty or '종목명' not in df.columns:
        return df

    df['종목명'] = df['종목명'].astype(str).str.strip()
    if '종목코드' in df.columns:
        df['종목코드'] = df['종목코드'].apply(normalize_stock_code)

    if use_stock_code and '종목코드' in df.columns:
        df['__stock_key'] = df['종목코드'].where(df['종목코드'].astype(bool), df['종목명'])
    else:
        df['__stock_key'] = df['종목명']

    df['__stock_key'] = df['__stock_key'].astype(str).str.strip()
    return df

df_sangcheon = assign_stock_keys(df_sangcheon)
df_company_overview = assign_stock_keys(df_company_overview)
df_themes = assign_stock_keys(df_themes)
df_analysis = assign_stock_keys(df_analysis)

names_by_key = {}
name_to_keys = {}
latest_name_by_key = {}

stock_pairs = df_sangcheon[['__stock_key', '종목명']].dropna().drop_duplicates()
stock_pairs = stock_pairs[
    stock_pairs['__stock_key'].astype(str).str.strip().astype(bool)
    & stock_pairs['종목명'].astype(str).str.strip().astype(bool)
]

for stock_key, stock_name in stock_pairs.itertuples(index=False, name=None):
    names_by_key.setdefault(stock_key, set()).add(stock_name)
    name_to_keys.setdefault(stock_name, set()).add(stock_key)

latest_pairs = stock_pairs.drop_duplicates('__stock_key', keep='first')
latest_name_by_key = dict(latest_pairs[['__stock_key', '종목명']].itertuples(index=False, name=None))

for extra_df in [df_company_overview, df_themes, df_analysis]:
    if extra_df is None or extra_df.empty or '종목명' not in extra_df.columns or '__stock_key' not in extra_df.columns:
        continue
    extra_pairs = extra_df[['__stock_key', '종목명']].dropna().drop_duplicates()
    for extra_key, extra_name in extra_pairs.itertuples(index=False, name=None):
        if extra_name and extra_key in names_by_key:
            names_by_key.setdefault(extra_key, set()).add(extra_name)
            name_to_keys.setdefault(extra_name, set()).add(extra_key)

resolved_aliases = {}
for old_name, new_name in name_aliases.items():
    old_name = clean_name(old_name)
    new_name = resolve_alias_name(new_name)
    if old_name and new_name and old_name != new_name:
        resolved_aliases[old_name] = new_name

preferred_name_by_key = {}
for old_name, new_name in resolved_aliases.items():
    alias_keys = set()
    alias_keys.update(name_to_keys.get(new_name, set()))
    alias_keys.update(name_to_keys.get(old_name, set()))

    for stock_key in alias_keys:
        names_by_key.setdefault(stock_key, set()).update([old_name, new_name])
        name_to_keys.setdefault(old_name, set()).add(stock_key)
        name_to_keys.setdefault(new_name, set()).add(stock_key)
        preferred_name_by_key[stock_key] = new_name

stock_keys = sorted(
    names_by_key.keys(),
    key=lambda key: (preferred_name_by_key.get(key) or latest_name_by_key.get(key) or key).lower()
)

def get_display_name(stock_key):
    return preferred_name_by_key.get(stock_key) or latest_name_by_key.get(stock_key) or stock_key

def get_alias_names(stock_key):
    display_name = get_display_name(stock_key)
    return sorted(name for name in names_by_key.get(stock_key, set()) if name and name != display_name)

def format_stock_option(stock_key):
    display_name = get_display_name(stock_key)
    code_text = f", {stock_key}" if use_stock_code else ""
    aliases = get_alias_names(stock_key)
    if aliases:
        alias_text = ", ".join(aliases[:3])
        if len(aliases) > 3:
            alias_text += f" 외 {len(aliases) - 3}개"
        return f"{display_name} ({alias_text}{code_text})"
    return f"{display_name} ({stock_key})" if use_stock_code else display_name

def matches_stock(stock_key, search_text):
    if not search_text:
        return True
    search_lower = search_text.lower().strip()
    haystack = [stock_key, get_display_name(stock_key), *names_by_key.get(stock_key, set())]
    return any(search_lower in str(item).lower() for item in haystack if item)

def get_auto_selected_stock_key(search_text, options):
    """정확히 하나로 좁혀지거나 정확히 일치하면 바로 상세로 진입"""
    if not search_text:
        return None

    search_text = search_text.strip()
    search_lower = search_text.lower()
    normalized_code = normalize_stock_code(search_text)

    for stock_key in options:
        candidates = [stock_key, get_display_name(stock_key), *names_by_key.get(stock_key, set())]
        if normalized_code and stock_key == normalized_code:
            return stock_key
        if any(search_lower == str(item).lower() for item in candidates if item):
            return stock_key

    if len(options) == 1:
        return options[0]

    return None

def resolve_stock_key_by_name(stock_name):
    keys = sorted(name_to_keys.get(clean_name(stock_name), set()))
    return keys[0] if keys else None

def filter_stock_rows(df, stock_key, stock_name=None):
    if df is None or df.empty:
        return pd.DataFrame()

    if '__stock_key' in df.columns:
        rows = df[df['__stock_key'] == stock_key]
        if not rows.empty:
            return rows

    if use_stock_code and stock_key and '종목코드' in df.columns:
        rows = df[df['종목코드'] == stock_key]
        if not rows.empty:
            return rows

    if '종목명' in df.columns:
        candidate_names = set(names_by_key.get(stock_key, set()))
        if stock_name:
            candidate_names.add(clean_name(stock_name))
        candidate_names.add(get_display_name(stock_key))
        candidate_names = {name for name in candidate_names if name}
        if candidate_names:
            return df[df['종목명'].astype(str).str.strip().isin(candidate_names)]

    return pd.DataFrame()

def get_row_stock_key(row):
    row_key = clean_name(row.get('__stock_key'))
    if row_key:
        return row_key
    return make_stock_key(row.get('종목코드'), row.get('종목명'))

# 세션 상태 초기화
if 'selected_stock_code' not in st.session_state:
    st.session_state.selected_stock_code = None
if 'selected_stock_name' not in st.session_state:
    st.session_state.selected_stock_name = None
if 'current_query' not in st.session_state:
    st.session_state.current_query = None
if 'search_mode' not in st.session_state:
    st.session_state.search_mode = "종목명"

# 버튼 클릭으로 종목 선택된 경우 처리
if st.session_state.selected_stock_code:
    st.session_state.current_query = st.session_state.selected_stock_code
    st.session_state.selected_stock_code = None
    st.session_state.search_mode = "종목명"
    st.session_state.search_mode_radio = "종목명"

if st.session_state.selected_stock_name:
    resolved_key = resolve_stock_key_by_name(st.session_state.selected_stock_name)
    st.session_state.current_query = resolved_key or st.session_state.selected_stock_name
    st.session_state.selected_stock_name = None
    st.session_state.search_mode = "종목명"
    st.session_state.search_mode_radio = "종목명"

# 검색 모드 변경 시 초기화 콜백
def reset_search_state():
    st.session_state.current_query = None

# 검색 모드 라디오 버튼
search_mode = st.radio(
    "검색 모드", 
    ["종목명", "테마"], 
    horizontal=True, 
    key="search_mode_radio", 
    index=0 if st.session_state.search_mode == "종목명" else 1,
    on_change=reset_search_state
)
st.session_state.search_mode = search_mode

query = None
theme_results = None

if search_mode == "종목명":
    # 현재 선택된 종목이 있으면 표시
    if st.session_state.current_query:
        current_stock_name = get_display_name(st.session_state.current_query)
        st.info(f"📌 현재 분석 중: **{current_stock_name}**")
        col1, col2 = st.columns([3, 1])
        with col1:
            query = st.session_state.current_query
        with col2:
            if st.button("🔄 새 검색", use_container_width=True):
                st.session_state.current_query = None
                st.session_state.stock_search = ""
                st.rerun()
    else:
        # 검색어 입력
        search_query = st.text_input("🔍 종목명/구 사명/종목코드 검색", placeholder="예: 삼성전자, 005930...", key="stock_search")
        
        all_options = [stock_key for stock_key in stock_keys if matches_stock(stock_key, search_query)]
        if len(all_options) > MAX_SEARCH_RESULTS:
            all_options = all_options[:MAX_SEARCH_RESULTS]
            st.info(f"💡 검색 결과가 많아 {MAX_SEARCH_RESULTS}개만 표시됩니다.")

        auto_selected_stock = get_auto_selected_stock_key(search_query, all_options)
        if auto_selected_stock:
            st.session_state.current_query = auto_selected_stock
            st.rerun()

        # 종목 선택
        if all_options and not auto_selected_stock:
            selected_stock = st.selectbox(
                "📋 종목 선택",
                options=[""] + all_options,
                format_func=lambda x: "종목을 선택하세요..." if x == "" else format_stock_option(x),
                key="stock_select"
            )

            if selected_stock:
                st.session_state.current_query = selected_stock
                query = selected_stock
                st.rerun()
        else:
            if search_query:
                st.warning(f"'{search_query}'와 일치하는 종목이 없습니다.")

else:  # 테마 검색
    theme_query = st.text_input("🔍 테마 검색", placeholder="예: 반도체, AI...", key="theme_search")
    
    if theme_query and df_themes is not None:
        # 벡터화된 검색 (빠름!)
        mask = df_themes['테마_전체'].str.lower().str.contains(theme_query.lower(), na=False)
        if '__stock_key' in df_themes.columns:
            matched_keys = df_themes.loc[mask, '__stock_key'].dropna().astype(str).str.strip().unique().tolist()
            matched_keys = [key for key in matched_keys if key]
        else:
            matched_keys = []
            seen_keys = set()
            for _, matched_row in df_themes.loc[mask].iterrows():
                stock_key = get_row_stock_key(matched_row)
                if not stock_key:
                    stock_key = resolve_stock_key_by_name(matched_row.get('종목명'))
                if stock_key and stock_key not in seen_keys:
                    matched_keys.append(stock_key)
                    seen_keys.add(stock_key)
        
        if matched_keys:
            # 테마 이슈 상승률 기준으로 정렬
            theme_keyword = theme_query.lower()
            scored_results = []
            
            for stock_key in matched_keys:
                stock_name = get_display_name(stock_key)
                stock_data = filter_stock_rows(df_sangcheon, stock_key, stock_name)
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
                    '종목코드': stock_key,
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
                stock_key = stock_info.get('종목코드')
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
                    
                    if st.button(label, key=f"theme_{theme_query}_{stock_key}", use_container_width=True):
                        st.session_state.selected_stock_code = stock_key
                        st.rerun()
                    
                    # 상승률 표시
                    if theme_rise > 0:
                        st.caption(f"테마상승 {theme_rise:.1f}%")
                    elif max_rise > 0:
                        st.caption(f"최고 {max_rise:.1f}%")
    else:
        for idx, stock_info in enumerate(theme_results, 1):
            stock_key = stock_info.get('종목코드')
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
                
                if st.button(label, key=f"themelist_{theme_query}_{stock_key}", use_container_width=True):
                    st.session_state.selected_stock_code = stock_key
                    st.rerun()
            with col2:
                if theme_rise > 0:
                    st.caption(f"{theme_rise:.1f}%")
                elif max_rise > 0:
                    st.caption(f"{max_rise:.1f}%")

# 종목 상세 분석 표시
if query:
    stock_name = get_display_name(query)
    res = filter_stock_rows(df_sangcheon, query, stock_name).copy()
    
    if res.empty:
        st.warning(f"'{stock_name}' 종목의 데이터를 찾을 수 없습니다.")
    else:
        if '날짜' in res.columns:
            res = res.sort_values('날짜', ascending=False)
        
        row = res.iloc[0]
        
        st.markdown("---")
        st.subheader(f"📊 {stock_name} 종목 분석")
        alias_names = get_alias_names(query)
        meta_parts = []
        if use_stock_code:
            meta_parts.append(f"종목코드: {query}")
        if alias_names:
            meta_parts.append(f"구/별칭: {', '.join(alias_names[:5])}")
        if meta_parts:
            st.caption(" | ".join(meta_parts))
        
        # 1. 기업개요
        summary_text = None
        if df_company_overview is not None and '종목명' in df_company_overview.columns:
            overview_row = filter_stock_rows(df_company_overview, query, stock_name)
            if not overview_row.empty:
                # 핵심요약 컬럼 찾기
                summary_col = next((c for c in df_company_overview.columns if any(k in c for k in ['핵심요약', '3줄정리'])), None)
                if summary_col:
                    val = overview_row.iloc[0][summary_col]
                    if pd.notna(val):
                        summary_text = str(val)
        
        if summary_text is None and df_themes is not None and '종목명' in df_themes.columns:
            theme_sum_row = filter_stock_rows(df_themes, query, stock_name)
            if not theme_sum_row.empty and '핵심요약' in df_themes.columns:
                val = theme_sum_row.iloc[0]['핵심요약']
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
            theme_row = filter_stock_rows(df_themes, query, stock_name)
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
            
        # 5. 테마별 상세 분석 (뉴스 대체)
        st.markdown("---")
        st.subheader("📝 테마별 상세 분석")
        
        found_analysis = False
        if df_analysis is not None and '종목명' in df_analysis.columns:
            analysis_rows = filter_stock_rows(df_analysis, query, stock_name)
            if not analysis_rows.empty:
                found_analysis = True
                for _, r in analysis_rows.iterrows():
                    theme_name = r.get('테마명', '-')
                    content = r.get('분석결과', '-')
                    with st.expander(f"📌 {theme_name}", expanded=True):
                        st.write(content)
        
        if not found_analysis:
            st.caption("해당 종목의 상세 분석 데이터가 없습니다.")
            
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
                    other_key = get_row_stock_key(theme_row)
                    if not other_key:
                        other_key = resolve_stock_key_by_name(theme_row.get('종목명'))
                    other_name = get_display_name(other_key) if other_key else clean_name(theme_row.get('종목명'))
                    themes_str = theme_row.get('테마_전체', '')
                    
                    # 자기 자신 제외
                    if other_key == query:
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
                        stock_data = filter_stock_rows(df_sangcheon, other_key, other_name)
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
                            '종목코드': other_key,
                            '종목명': other_name,
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
                sims_df = df_sangcheon[df_sangcheon['테마'] == row_theme].copy()
                sims_df = sims_df[sims_df['__stock_key'] != query]
                sims_df = sims_df.drop_duplicates('__stock_key')
                
                # 2순위도 상승률 기준 정렬
                fallback_scores = []
                for other_key in sims_df['__stock_key'].dropna().unique():
                    other_name = get_display_name(other_key)
                    stock_data = filter_stock_rows(df_sangcheon, other_key, other_name)
                    max_rise = 0
                    if not stock_data.empty and '상승률' in stock_data.columns:
                        for _, sr in stock_data.iterrows():
                            rise_val, _ = convert_rise_rate(sr.get('상승률'))
                            if rise_val is not None:
                                max_rise = max(max_rise, rise_val)
                    fallback_scores.append({'종목코드': other_key, '종목명': other_name, '최고상승률': max_rise, '혼합점수': max_rise})
                
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
                stock_key = stock_info.get('종목코드')
                stock_name = stock_info['종목명']
                max_rise = stock_info.get('최고상승률', 0)
                
                with cols[i]:
                    # 버튼 라벨에 최고 상승률 표시
                    label = f"{stock_name}"
                    if max_rise >= LIMIT_UP_THRESHOLD:
                        label = f"🔥 {stock_name}"
                    
                    if st.button(label, key=f"sim_{query}_{stock_key}", use_container_width=True):
                        st.session_state.selected_stock_code = stock_key
                        st.rerun()
                    
                    # 상승률 표시 (테마 매칭 상승률 우선, 없으면 최고 상승률)
                    theme_rise = stock_info.get('테마상승률', 0)
                    if theme_rise > 0:
                        st.caption(f"🎯 테마상승 {theme_rise:.1f}%")
                    elif max_rise > 0:
                        st.caption(f"최고 {max_rise:.1f}%")
        else:
            st.caption("유사 종목을 찾을 수 없습니다.")
