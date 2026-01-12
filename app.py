import streamlit as st
import pandas as pd
import glob
import os

# ---------------------------------------------------------
# 1. 페이지 설정
# ---------------------------------------------------------
st.set_page_config(page_title="주식 분석 봇", layout="wide")
# --- [비밀번호 보안 기능 시작] ---
# 친구들과 공유할 비밀번호를 여기에 적으세요
MY_PASSWORD = "wang10ri" 

login_pass = st.sidebar.text_input("🔑 비밀번호를 입력하세요", type="password")

if login_pass != MY_PASSWORD:
    st.error("비밀번호가 일치하지 않으면 내용을 볼 수 없습니다.")
    st.stop()  # 여기서 코드 실행을 멈춤 (아래 내용 안 보임)
# --- [비밀번호 보안 기능 끝] ---
st.title("📈 주식 데이터 분석 챗봇 (하이브리드)")
st.markdown("---")

# ---------------------------------------------------------
# 2. 유틸리티 함수
# ---------------------------------------------------------
def clean_columns(df):
    """컬럼명 표준화"""
    df.columns = df.columns.str.replace(" ", "").str.strip()
    rename_map = {
        '종목이름': '종목명', '종목': '종목명',
        '주요상승이유': '상승이유', '주요상승이유및관련이슈': '상승이유', '이슈': '상승이유',
        '관련테마': '테마', '등락률': '상승률', '일자': '날짜'
    }
    df.rename(columns=rename_map, inplace=True)
    return df

@st.cache_data(show_spinner=False)
def load_data(file_input):
    """파일 경로(문자열) 또는 업로드된 파일 객체를 받아서 데이터 로드"""
    try:
        xl = pd.ExcelFile(file_input)
        sangcheon_list = []
        signal_df = None
        
        for sheet in xl.sheet_names:
            if "상천" in sheet:
                df = pd.read_excel(file_input, sheet_name=sheet)
                df = clean_columns(df)
                sangcheon_list.append(df)
            elif "시그널" in sheet:
                df = pd.read_excel(file_input, sheet_name=sheet)
                df = clean_columns(df)
                signal_df = df
        
        final_sangcheon = pd.DataFrame()
        if sangcheon_list:
            final_sangcheon = pd.concat(sangcheon_list, ignore_index=True)
            if '날짜' in final_sangcheon.columns:
                final_sangcheon['날짜'] = pd.to_datetime(final_sangcheon['날짜'], errors='coerce')
                final_sangcheon = final_sangcheon.sort_values('날짜', ascending=False)
        
        return final_sangcheon, signal_df, None

    except Exception as e:
        return None, None, str(e)

# ---------------------------------------------------------
# 3. 데이터 로드 로직 (핵심 수정 부분)
# ---------------------------------------------------------
with st.sidebar:
    st.header("📂 데이터 설정")
    
    # [1] 파일 업로더 (우선순위 1등)
    uploaded_file = st.file_uploader("새 엑셀 파일 업로드 (선택)", type=['xlsx'])
    
    # [2] 기본 파일 찾기 (우선순위 2등)
    # 하위 폴더까지 재귀적으로 검색
    repo_file = None
    
    # 정확한 파일명으로 먼저 찾기
    exact_pattern = "**/종목정리_종목순 정렬.xlsx"
    exact_files = glob.glob(exact_pattern, recursive=True)
    if exact_files:
        repo_file = exact_files[0]
    else:
        # 패턴으로 찾기: 종목정리가 포함된 파일
        pattern_files = glob.glob("**/*종목정리*.xlsx", recursive=True)
        if pattern_files:
            repo_file = pattern_files[0]
        else:
            # 마지막으로 종목이 포함된 파일 찾기
            all_files = glob.glob("**/*종목*.xlsx", recursive=True)
            if all_files:
                repo_file = all_files[0]

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

st.success(f"✅ {source_msg}")

# ---------------------------------------------------------
# 4. 분석 화면 (자동완성 기능 추가)
# ---------------------------------------------------------
if '종목명' not in df_sangcheon.columns:
    st.error("데이터에서 '종목명' 컬럼을 찾을 수 없습니다.")
    st.stop()

# 종목명 리스트 추출 (중복 제거, 최신순으로 정렬)
stock_list = df_sangcheon['종목명'].dropna().unique().tolist()
stock_list = sorted([str(s) for s in stock_list if pd.notna(s)])

# 검색어 입력
search_query = st.text_input("🔍 종목명 검색 (자동완성)", placeholder="예: 삼성전자, SK하이닉스...", key="stock_search")

# 검색어에 따라 필터링된 종목 리스트 생성
filtered_stocks = stock_list
if search_query:
    search_lower = search_query.lower()
    filtered_stocks = [s for s in stock_list if search_lower in s.lower()]

# 필터링된 종목이 너무 많으면 제한
if len(filtered_stocks) > 100:
    filtered_stocks = filtered_stocks[:100]
    st.info(f"💡 검색 결과가 많습니다. 처음 100개만 표시됩니다. 검색어를 더 구체적으로 입력해주세요.")

# 종목 선택 (자동완성)
if filtered_stocks:
    selected_stock = st.selectbox(
        "📋 종목 선택 (또는 위 검색창에서 입력)",
        options=[""] + filtered_stocks,
        format_func=lambda x: "종목을 선택하세요..." if x == "" else x,
        key="stock_select"
    )
else:
    selected_stock = None
    if search_query:
        st.warning(f"'{search_query}'와 일치하는 종목을 찾을 수 없습니다.")

# 검색 실행: selectbox에서 선택했거나, 검색어가 정확히 일치하는 경우
query = None
if selected_stock and selected_stock != "":
    query = selected_stock
elif search_query and search_query in stock_list:
    query = search_query

if query:
    # 해당 종목의 모든 데이터 찾기 (날짜 기준)
    res = df_sangcheon[df_sangcheon['종목명'] == query].copy()
    
    if res.empty:
        st.warning(f"'{query}' 종목의 데이터를 찾을 수 없습니다.")
    else:
        # 날짜가 있으면 최신순으로 정렬
        if '날짜' in res.columns:
            res = res.sort_values('날짜', ascending=False)
        
        # 가장 최신 데이터
        row = res.iloc[0]
        
        st.divider()
        c1, c2, c3 = st.columns(3)
        with c1: 
            date_str = str(row.get('날짜','-'))
            if date_str != '-':
                try:
                    date_str = date_str[:10] if len(date_str) > 10 else date_str
                except:
                    pass
            st.metric("최근 날짜", date_str)
        with c2: st.metric("상승률", str(row.get('상승률','-')))
        with c3: st.metric("테마", str(row.get('테마','-')))
        
        st.markdown("---")
        
        # 최근 3회 상승 이슈 표시
        st.subheader("📊 최근 상승 이슈 (최근 3회)")
        
        # 상승률 컬럼 확인 및 상한가 판단
        상승률_col = '상승률'
        상한가_기준 = 29.5  # 상승률 29.5% 이상이면 상한가로 간주
        
        # 최근 3회 데이터 추출
        recent_3 = res.head(3)
        
        if not recent_3.empty:
            for idx, (_, r) in enumerate(recent_3.iterrows(), 1):
                날짜 = r.get('날짜', '-')
                if pd.notna(날짜):
                    try:
                        날짜_str = str(날짜)[:10] if len(str(날짜)) > 10 else str(날짜)
                    except:
                        날짜_str = str(날짜)
                else:
                    날짜_str = '-'
                
                상승률 = r.get(상승률_col, '-')
                상승이유 = r.get('상승이유', '-')
                
                # 상승률이 숫자인지 확인
                is_limit_up = False
                if pd.notna(상승률):
                    try:
                        상승률_값 = float(str(상승률).replace('%', ''))
                        if 상승률_값 >= 상한가_기준:
                            is_limit_up = True
                    except:
                        pass
                
                # 상한가 표시
                limit_up_badge = " 🔥 상한가" if is_limit_up else ""
                
                with st.container():
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        st.write(f"**{idx}.** {날짜_str}{limit_up_badge}")
                    with col2:
                        if 상승이유 != '-' and pd.notna(상승이유):
                            st.write(f"상승률: {상승률} | {상승이유}")
                        else:
                            st.write(f"상승률: {상승률}")
                    st.divider()
        else:
            st.caption("상승 이슈 데이터가 없습니다.")
        
        # 과거 상한가 이력 표시
        st.markdown("---")
        st.subheader("🔥 과거 상한가 이력")
        
        # 상한가 이력 찾기 (최근 3회에 포함되지 않은 것들)
        limit_up_history = []
        
        for _, r in res.iterrows():
            상승률 = r.get(상승률_col, '-')
            날짜 = r.get('날짜', '-')
            상승이유 = r.get('상승이유', '-')
            
            if pd.notna(상승률):
                try:
                    상승률_값 = float(str(상승률).replace('%', ''))
                    if 상승률_값 >= 상한가_기준:
                        if pd.notna(날짜):
                            try:
                                날짜_str = str(날짜)[:10] if len(str(날짜)) > 10 else str(날짜)
                            except:
                                날짜_str = str(날짜)
                        else:
                            날짜_str = '-'
                        
                        limit_up_history.append({
                            '날짜': 날짜_str,
                            '상승률': 상승률,
                            '상승이유': 상승이유 if pd.notna(상승이유) else '-'
                        })
                except:
                    pass
        
        # 최근 3회에 포함된 상한가는 제외 (중복 방지)
        recent_3_dates = set()
        for _, r in recent_3.iterrows():
            날짜 = r.get('날짜', '-')
            if pd.notna(날짜):
                try:
                    날짜_str = str(날짜)[:10] if len(str(날짜)) > 10 else str(날짜)
                    recent_3_dates.add(날짜_str)
                except:
                    pass
        
        # 최근 3회에 포함되지 않은 상한가만 표시
        past_limit_up = [h for h in limit_up_history if h['날짜'] not in recent_3_dates]
        
        if past_limit_up:
            # 날짜순으로 정렬 (최신순)
            past_limit_up = sorted(past_limit_up, key=lambda x: x['날짜'], reverse=True)
            
            for idx, history in enumerate(past_limit_up, 1):
                with st.container():
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        st.write(f"**{idx}.** {history['날짜']} 🔥")
                    with col2:
                        if history['상승이유'] != '-':
                            st.write(f"상승률: {history['상승률']} | {history['상승이유']}")
                        else:
                            st.write(f"상승률: {history['상승률']}")
                    st.divider()
        else:
            st.caption("과거 상한가 이력이 없습니다.")

        st.markdown("---")
        st.subheader("📰 뉴스")
        if df_signal is not None and '종목명' in df_signal.columns:
            news_col = next((c for c in ['주요뉴스','뉴스','내용'] if c in df_signal.columns), None)
            if news_col:
                news = df_signal[df_signal['종목명'] == query]
                if not news.empty:
                    for _, r in news.iterrows():
                        st.write(f"• {r[news_col]}")
                else:
                    st.caption("관련 뉴스가 없습니다.")
            else:
                st.caption("뉴스 데이터 없음")
        else:
            st.caption("뉴스 데이터 없음")
        
        # 유사 종목
        st.markdown("---")
        st.subheader("🔗 유사 종목")
        theme = row.get('테마')
        if theme and pd.notna(theme):
            sims = df_sangcheon[(df_sangcheon['테마']==theme) & (df_sangcheon['종목명']!=query)]
            sims = sims.drop_duplicates('종목명')
            # 날짜 기준으로 정렬
            if '날짜' in sims.columns:
                sims = sims.sort_values('날짜', ascending=False)
            sims = sims.head(5)
            
            if not sims.empty:
                cols = st.columns(len(sims))
                for i, (_, r) in enumerate(sims.iterrows()):
                    with cols[i]: 
                        if st.button(r['종목명'], key=f"sim_{i}", use_container_width=True):
                            # 버튼 클릭 시 해당 종목으로 검색
                            st.session_state.stock_search = r['종목명']
                            st.rerun()
            else:
                st.caption("같은 테마의 다른 종목이 없습니다.")
        else:
            st.caption("테마 정보가 없어 유사 종목을 찾을 수 없습니다.")