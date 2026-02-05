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
MY_PASSWORD = "" 

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

def convert_rise_rate(상승률_원본):
    """상승률을 % 형식으로 변환 (소수점 형태도 처리)"""
    if pd.isna(상승률_원본) or 상승률_원본 == '-':
        return None, '-'
    
    try:
        상승률_str = str(상승률_원본).replace('%', '').strip()
        상승률_값 = float(상승률_str)
        
        # 소수점 형태인 경우 (예: 0.0436 = 4.36%)
        if 상승률_값 < 1:
            상승률_값 = 상승률_값 * 100
        
        상승률_표시 = f"{상승률_값:.2f}%"
        return 상승률_값, 상승률_표시
    except (ValueError, TypeError):
        return None, str(상승률_원본)

@st.cache_data(show_spinner=True, ttl=3600)
def load_data(file_input):
    """파일 경로(문자열) 또는 업로드된 파일 객체를 받아서 데이터 로드"""
    try:
        # 파일 객체인 경우 BytesIO로 읽기
        if hasattr(file_input, 'read'):
            import io
            file_buffer = io.BytesIO(file_input.read())
            xl = pd.ExcelFile(file_buffer, engine='openpyxl')
        else:
            xl = pd.ExcelFile(file_input, engine='openpyxl')
        
        sangcheon_list = []
        signal_df = None
        
        for sheet in xl.sheet_names:
            if "상천" in sheet:
                if hasattr(file_input, 'read'):
                    df = pd.read_excel(file_buffer, sheet_name=sheet, engine='openpyxl')
                else:
                    df = pd.read_excel(file_input, sheet_name=sheet, engine='openpyxl')
                df = clean_columns(df)
                sangcheon_list.append(df)
            elif "시그널" in sheet:
                if hasattr(file_input, 'read'):
                    df = pd.read_excel(file_buffer, sheet_name=sheet, engine='openpyxl')
                else:
                    df = pd.read_excel(file_input, sheet_name=sheet, engine='openpyxl')
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

@st.cache_data(show_spinner=True, ttl=3600)
def load_company_overview():
    """시그널뷰_기업개요.xlsx 또는 .csv 파일을 로드"""
    try:
        # 먼저 xlsx 파일 시도
        xlsx_path = "시그널뷰_기업개요.xlsx"
        if os.path.exists(xlsx_path):
            df = pd.read_excel(xlsx_path, engine='openpyxl')
            # 컬럼명 공백 제거
            df.columns = df.columns.str.replace(" ", "").str.strip()
            return df
        
        # xlsx가 없으면 csv 파일 시도
        csv_path = "시그널뷰_기업개요.csv"
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            # 컬럼명 공백 제거
            df.columns = df.columns.str.replace(" ", "").str.strip()
            return df
        
        return None
    except Exception as e:
        return None

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

# 시그널뷰 기업개요 데이터 로드
df_company_overview = load_company_overview()

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

# 세션 상태 초기화
if 'selected_stock_name' not in st.session_state:
    st.session_state.selected_stock_name = None
if 'force_stock_search' not in st.session_state:
    st.session_state.force_stock_search = False

# 검색 모드 선택 (항상 표시)
# 버튼 클릭으로 종목이 선택된 경우, 자동으로 종목명 검색 모드로 전환
if st.session_state.selected_stock_name or st.session_state.force_stock_search:
    # selected_stock_name이 있거나 force_stock_search가 True면 종목명 검색 모드로 설정
    # radio 위젯의 기본값을 종목명 검색(index=0)으로 설정
    if 'search_mode' not in st.session_state or st.session_state.search_mode != "종목명 검색":
        st.session_state.search_mode = "종목명 검색"
    search_mode = st.radio("검색 모드", ["종목명 검색", "키워드 검색"], horizontal=True, key="search_mode", index=0)
    st.session_state.force_stock_search = False  # 사용 후 초기화
else:
    # 검색 모드 선택
    search_mode = st.radio("검색 모드", ["종목명 검색", "키워드 검색"], horizontal=True, key="search_mode")

# 변수 초기화
query = None
keyword_query = None
keyword_results = None

if search_mode == "종목명 검색":
    # 버튼 클릭으로 선택된 종목이 있으면 우선 사용
    if st.session_state.selected_stock_name:
        query = st.session_state.selected_stock_name
        st.session_state.selected_stock_name = None  # 사용 후 초기화
    
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
        # query가 이미 설정되어 있으면 해당 종목을 기본값으로
        default_index = 0
        if query and query in filtered_stocks:
            default_index = filtered_stocks.index(query) + 1
        
        selected_stock = st.selectbox(
            "📋 종목 선택 (또는 위 검색창에서 입력)",
            options=[""] + filtered_stocks,
            format_func=lambda x: "종목을 선택하세요..." if x == "" else x,
            key="stock_select",
            index=default_index
        )
    else:
        selected_stock = None
        if search_query:
            st.warning(f"'{search_query}'와 일치하는 종목을 찾을 수 없습니다.")
    
    # 검색 실행: query가 이미 설정되어 있으면 그대로 사용, 아니면 selectbox나 검색어 확인
    if not query:
        if selected_stock and selected_stock != "":
            query = selected_stock
        elif search_query and search_query in stock_list:
            query = search_query

else:  # 키워드 검색
    keyword_query = st.text_input("🔍 키워드 검색", placeholder="예: 반도체, AI, 배터리...", key="keyword_search")
    
    if keyword_query:
        # 키워드가 포함된 종목 찾기 (상승이유 컬럼에서 검색)
        keyword_lower = keyword_query.lower()
        
        # 각 종목별로 키워드가 나타나는 횟수 계산
        stock_keyword_count = {}
        
        for _, row in df_sangcheon.iterrows():
            종목명 = row.get('종목명', '')
            상승이유 = row.get('상승이유', '')
            
            if pd.notna(종목명) and pd.notna(상승이유):
                종목명_str = str(종목명)
                상승이유_str = str(상승이유).lower()
                
                # 키워드가 상승이유에 포함되어 있는지 확인
                if keyword_lower in 상승이유_str:
                    if 종목명_str not in stock_keyword_count:
                        stock_keyword_count[종목명_str] = 0
                    stock_keyword_count[종목명_str] += 1
        
        # 반복횟수 기준으로 정렬
        if stock_keyword_count:
            sorted_stocks = sorted(stock_keyword_count.items(), key=lambda x: x[1], reverse=True)
            keyword_results = sorted_stocks[:10]  # 최대 10개
        else:
            st.warning(f"'{keyword_query}' 키워드가 포함된 종목을 찾을 수 없습니다.")

# 키워드 검색 결과 표시
if keyword_results:
    st.markdown("---")
    st.subheader(f"🔍 키워드 '{keyword_query}' 검색 결과 (반복횟수 순)")
    
    for idx, (종목명, 반복횟수) in enumerate(keyword_results, 1):
        col1, col2 = st.columns([3, 1])
        with col1:
            if st.button(f"{idx}. {종목명} (반복횟수: {반복횟수}회)", key=f"kw_{idx}", use_container_width=True):
                # 버튼 클릭 시 해당 종목으로 검색
                st.session_state.selected_stock_name = 종목명
                st.session_state.force_stock_search = True  # 종목명 검색 모드로 강제 전환
                st.rerun()
        with col2:
            st.caption(f"{반복횟수}회")

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
        
        # 종목명 표시
        st.markdown("---")
        st.subheader(f"📊 {query} 종목 분석")
        st.markdown("")
        
        c1, c2, c3 = st.columns(3)
        with c1: 
            date_str = str(row.get('날짜','-'))
            if date_str != '-':
                try:
                    date_str = date_str[:10] if len(date_str) > 10 else date_str
                except:
                    pass
            st.metric("최근 날짜", date_str)
        # 상승률을 % 형식으로 변환
        _, 상승률_표시 = convert_rise_rate(row.get('상승률', '-'))
        with c2: st.metric("상승률", 상승률_표시)
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
                
                # 상승률을 % 형식으로 변환
                상승률_값, 상승률_표시 = convert_rise_rate(상승률)
                is_limit_up = False
                if 상승률_값 is not None:
                    if 상승률_값 >= 상한가_기준:
                        is_limit_up = True
                
                # 상한가 표시
                limit_up_badge = " 🔥 상한가" if is_limit_up else ""
                
                with st.container():
                    col1, col2 = st.columns([1, 4])
                    with col1:
                        st.write(f"**{idx}.** {날짜_str}{limit_up_badge}")
                    with col2:
                        if 상승이유 != '-' and pd.notna(상승이유):
                            st.write(f"상승률: {상승률_표시} | {상승이유}")
                        else:
                            st.write(f"상승률: {상승률_표시}")
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
            
            # 상승률 변환 및 상한가 확인
            상승률_값, 상승률_표시 = convert_rise_rate(상승률)
            
            if 상승률_값 is not None and 상승률_값 >= 상한가_기준:
                # 날짜 처리
                if pd.notna(날짜):
                    try:
                        if isinstance(날짜, pd.Timestamp):
                            날짜_str = 날짜.strftime('%Y-%m-%d')
                        else:
                            날짜_str = str(날짜)[:10] if len(str(날짜)) > 10 else str(날짜)
                    except:
                        날짜_str = str(날짜)
                else:
                    날짜_str = '-'
                
                limit_up_history.append({
                    '날짜': 날짜_str,
                    '상승률': 상승률_표시,
                    '상승이유': 상승이유 if pd.notna(상승이유) else '-',
                    '원본_날짜': 날짜  # 정렬을 위해 원본 날짜도 저장
                })
        
        # 최근 3회에 포함된 상한가는 제외 (중복 방지)
        recent_3_dates = set()
        for _, r in recent_3.iterrows():
            날짜 = r.get('날짜', '-')
            if pd.notna(날짜):
                try:
                    if isinstance(날짜, pd.Timestamp):
                        날짜_str = 날짜.strftime('%Y-%m-%d')
                    else:
                        날짜_str = str(날짜)[:10] if len(str(날짜)) > 10 else str(날짜)
                    recent_3_dates.add(날짜_str)
                except:
                    pass
        
        # 최근 3회에 포함되지 않은 상한가만 표시
        past_limit_up = [h for h in limit_up_history if h['날짜'] not in recent_3_dates]
        
        if past_limit_up:
            # 날짜순으로 정렬 (최신순) - 원본 날짜를 사용하여 정확한 정렬
            try:
                past_limit_up = sorted(past_limit_up, 
                                     key=lambda x: x['원본_날짜'] if pd.notna(x.get('원본_날짜')) else pd.Timestamp.min, 
                                     reverse=True)
            except:
                # 정렬 실패 시 날짜 문자열로 정렬
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
        st.subheader("📝 종목 설명")
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
        
        # 시그널뷰 기업개요
        if df_company_overview is not None and '종목명' in df_company_overview.columns:
            overview_row = df_company_overview[df_company_overview['종목명'] == query]
            if not overview_row.empty:
                # '핵심 요약 (3줄 정리)' 컬럼 찾기 (공백 제거된 컬럼명으로)
                summary_col = next((c for c in df_company_overview.columns if '핵심요약' in c or '3줄정리' in c or '핵심요약(3줄정리)' in c), None)
                if summary_col:
                    summary_text = overview_row.iloc[0][summary_col]
                    if pd.notna(summary_text) and str(summary_text).strip():
                        st.markdown("---")
                        st.subheader("📝 시그널뷰 기업개요")
                        st.info(str(summary_text))
        
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
                            st.session_state.selected_stock_name = r['종목명']
                            st.session_state.force_stock_search = True  # 종목명 검색 모드로 강제 전환
                            st.rerun()
            else:
                st.caption("같은 테마의 다른 종목이 없습니다.")
        else:
            st.caption("테마 정보가 없어 유사 종목을 찾을 수 없습니다.")