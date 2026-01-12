import streamlit as st
import pandas as pd
import glob
import os

# ---------------------------------------------------------
# 1. 기본 설정
# ---------------------------------------------------------
st.set_page_config(page_title="주식 테마 분석 봇", page_icon="📈", layout="wide")
# --- [비밀번호 보안 기능 시작] ---
# 친구들과 공유할 비밀번호를 여기에 적으세요
MY_PASSWORD = "wang10ri" 

login_pass = st.sidebar.text_input("🔑 비밀번호를 입력하세요", type="password")

if login_pass != MY_PASSWORD:
    st.error("비밀번호가 일치하지 않으면 내용을 볼 수 없습니다.")
    st.stop()  # 여기서 코드 실행을 멈춤 (아래 내용 안 보임)
# --- [비밀번호 보안 기능 끝] ---
st.title("📈 주식 데이터 분석 챗봇 (통합 버전)")
st.markdown("---")

# ---------------------------------------------------------
# 2. 데이터 처리 함수 (에러 방지용)
# ---------------------------------------------------------
def normalize_cols(df):
    """컬럼명의 공백을 제거하고 표준 이름으로 변경"""
    df.columns = df.columns.str.replace(" ", "").str.strip()
    
    # 우리가 코드에서 쓸 이름으로 통일 (엑셀 헤더가 달라도 인식되게)
    rename_map = {
        '종목이름': '종목명', '종목': '종목명',
        '주요상승이유': '상승이유', '주요상승이유및관련이슈': '상승이유', '이슈': '상승이유',
        '관련테마': '테마',
        '등락률': '상승률',
        '일자': '날짜'
    }
    df.rename(columns=rename_map, inplace=True)
    return df

@st.cache_data(ttl=600)
def load_excel_data(file_source):
    """파일을 받아서 상천정리와 시그널리포트로 분리"""
    try:
        xl = pd.ExcelFile(file_source)
        sangcheon_list = []
        signal_df = None
        
        for sheet in xl.sheet_names:
            clean_sheet = sheet.replace(" ", "")
            
            # A. 상천정리 시트 (연도가 포함된 시트)
            if "상천" in clean_sheet:
                df = pd.read_excel(file_source, sheet_name=sheet)
                df = normalize_cols(df)
                sangcheon_list.append(df)
                
            # B. 시그널리포트 시트
            elif "시그널" in clean_sheet:
                df = pd.read_excel(file_source, sheet_name=sheet)
                df = normalize_cols(df)
                signal_df = df
        
        # 상천정리 합치기
        final_sangcheon = pd.DataFrame()
        if sangcheon_list:
            final_sangcheon = pd.concat(sangcheon_list, ignore_index=True)
            if '날짜' in final_sangcheon.columns:
                final_sangcheon['날짜'] = pd.to_datetime(final_sangcheon['날짜'], errors='coerce')
                final_sangcheon = final_sangcheon.sort_values('날짜', ascending=False)
                
        return final_sangcheon, signal_df, None # 에러 없음

    except Exception as e:
        return None, None, str(e)

# ---------------------------------------------------------
# 3. 사이드바 (파일 로딩)
# ---------------------------------------------------------
with st.sidebar:
    st.header("📂 데이터 연결")
    
    # 1. 자동 검색 시도
    auto_files = glob.glob("*.xlsx")
    target_file = None
    for f in auto_files:
        if "종목" in f: # '종목' 글자가 들어간 엑셀 우선 선택
            target_file = f
            break
            
    # 2. 수동 업로드 (자동 검색 실패 시 비상용)
    uploaded_file = st.file_uploader("엑셀 파일 직접 업로드", type=['xlsx'])
    
    if st.button("🔄 데이터 새로고침"):
        st.cache_data.clear()
        st.rerun()

# ---------------------------------------------------------
# 4. 데이터 로드 실행
# ---------------------------------------------------------
df_sangcheon = pd.DataFrame()
df_signal = pd.DataFrame()
err = None

if uploaded_file:
    df_sangcheon, df_signal, err = load_excel_data(uploaded_file)
    st.success(f"업로드된 파일 사용 중")
elif target_file:
    df_sangcheon, df_signal, err = load_excel_data(target_file)
    st.sidebar.success(f"로컬 파일 연결됨: {target_file}")
else:
    st.warning("⚠️ 폴더에 엑셀 파일이 없습니다. 사이드바에서 파일을 직접 업로드해주세요.")
    st.stop()

if err:
    st.error(f"파일 읽기 오류: {err}")
    st.stop()

# ---------------------------------------------------------
# 5. 메인 기능 (검색)
# ---------------------------------------------------------
query = st.text_input("🔍 종목명 검색", placeholder="예: 삼성전자, 알테오젠...")

if query:
    # 데이터 있는지 확인
    if '종목명' not in df_sangcheon.columns:
        st.error("엑셀 파일에서 '종목명' 컬럼을 찾을 수 없습니다.")
        st.stop()

    # 검색
    res = df_sangcheon[df_sangcheon['종목명'] == query]
    
    if res.empty:
        st.warning(f"'{query}'에 대한 상천정리 기록이 없습니다.")
    else:
        # 최신 데이터 1건
        row = res.iloc[0]
        
        st.subheader(f"📌 {query} 분석")
        c1, c2, c3 = st.columns(3)
        with c1: st.metric("최근 포착일", str(row['날짜'])[:10] if '날짜' in row and pd.notnull(row['날짜']) else "-")
        with c2: st.metric("상승률", str(row['상승률']) if '상승률' in row else "-")
        with c3: st.metric("테마", row['테마'] if '테마' in row else "-")
        
        reason = row['상승이유'] if '상승이유' in row else "내용 없음"
        st.info(f"**💡 상승 이유:** {reason}")

        # 뉴스 매칭
        st.markdown("---")
        st.subheader("📰 관련 뉴스")
        if df_signal is not None and '종목명' in df_signal.columns:
            news_rows = df_signal[df_signal['종목명'] == query]
            if not news_rows.empty:
                # 주요뉴스 컬럼 찾기
                news_col = next((c for c in ['주요뉴스', '뉴스', '내용'] if c in df_signal.columns), None)
                if news_col:
                    for i, r in news_rows.iterrows():
                        st.write(f"• {r[news_col]}")
            else:
                st.caption("관련 뉴스 없음")

        # 유사 종목
        st.markdown("---")
        st.subheader("🔗 유사 테마 종목")
        if '테마' in row and pd.notnull(row['테마']):
            theme = row['테마']
            sims = df_sangcheon[
                (df_sangcheon['테마'] == theme) & 
                (df_sangcheon['종목명'] != query)
            ].drop_duplicates('종목명').head(5)
            
            if not sims.empty:
                cols = st.columns(len(sims))
                for i, (idx, r) in enumerate(sims.iterrows()):
                    with cols[i]:
                        st.button(r['종목명'], key=f"btn_{i}")
            else:
                st.caption("유사 종목 없음")