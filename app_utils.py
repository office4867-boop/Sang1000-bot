import pandas as pd
import glob
import os
import pickle
import streamlit as st

# ---------------------------------------------------------
# 상수 설정
# ---------------------------------------------------------
LIMIT_UP_THRESHOLD = 29.5  # 상한가 기준 (%)
CACHE_TTL = 3600           # 캐시 유효 시간 (초)
MAX_SEARCH_RESULTS = 100   # 검색 결과 최대 표시 수
CACHE_DIR = ".cache"       # 캐시 파일 저장 폴더

# ---------------------------------------------------------
# 캐시 관리 함수
# ---------------------------------------------------------
def ensure_cache_dir():
    """캐시 디렉토리가 없으면 생성"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)

def get_file_mtime(file_path):
    """파일의 수정 시간 반환"""
    try:
        return os.path.getmtime(file_path)
    except:
        return 0

def get_cache_path(original_path, suffix=""):
    """원본 파일 경로에 대응하는 캐시 파일 경로 생성"""
    ensure_cache_dir()
    # 파일명에서 확장자 제거하고 .pkl 확장자 추가
    base_name = os.path.basename(original_path).replace(".xlsx", "").replace(".csv", "")
    return os.path.join(CACHE_DIR, f"{base_name}{suffix}.pkl")

def load_from_cache(cache_path, original_path):
    """캐시에서 데이터 로드 (원본 파일이 변경되지 않았을 때만)"""
    if not os.path.exists(cache_path):
        return None
    
    try:
        # 캐시 파일이 원본 파일보다 최신인지 확인
        cache_mtime = get_file_mtime(cache_path)
        original_mtime = get_file_mtime(original_path)
        
        if cache_mtime > original_mtime:
            with open(cache_path, 'rb') as f:
                return pickle.load(f)
    except Exception as e:
        pass
    
    return None

def save_to_cache(cache_path, data):
    """데이터를 캐시에 저장"""
    try:
        ensure_cache_dir()
        with open(cache_path, 'wb') as f:
            pickle.dump(data, f)
    except Exception as e:
        pass

# ---------------------------------------------------------
# 유틸리티 함수
# ---------------------------------------------------------
def clean_columns(df):
    """컬럼명 표준화 및 공백 제거"""
    df.columns = df.columns.str.replace(" ", "").str.strip()
    rename_map = {
        '종목이름': '종목명', '종목': '종목명',
        '주요상승이유': '상승이유', '주요상승이유및관련이슈': '상승이유', '이슈': '상승이유',
        '관련테마': '테마', '등락률': '상승률', '일자': '날짜',
        '관련테마_전체': '테마_전체', '관련테마전체': '테마_전체'
    }
    df.rename(columns=rename_map, inplace=True)
    return df

def convert_rise_rate(rise_rate_origin):
    """상승률을 % 형식으로 변환 (소수점 형태도 처리)"""
    if pd.isna(rise_rate_origin) or rise_rate_origin == '-':
        return None, '-'
    
    try:
        rise_rate_str = str(rise_rate_origin).replace('%', '').strip()
        rise_rate_val = float(rise_rate_str)
        
        if rise_rate_val < 1:
            rise_rate_val = rise_rate_val * 100
        
        rise_rate_display = f"{rise_rate_val:.2f}%"
        return rise_rate_val, rise_rate_display
    except (ValueError, TypeError):
        return None, str(rise_rate_origin)

def format_date(date_val):
    """날짜를 YYYY-MM-DD 형식 문자열로 변환"""
    if pd.isna(date_val):
        return '-'
    try:
        if isinstance(date_val, pd.Timestamp):
            return date_val.strftime('%Y-%m-%d')
        return str(date_val)[:10] if len(str(date_val)) > 10 else str(date_val)
    except:
        return str(date_val)

def render_theme_badge(theme_text):
    """테마 텍스트를 배지 형태로 렌더링"""
    if not theme_text or theme_text == '-' or pd.isna(theme_text):
        return ""
        
    theme_formatted = str(theme_text).replace('#', ' #').strip()
    if theme_formatted.startswith(' '):
        theme_formatted = theme_formatted[1:]
    
    return f"""
    <div style='background-color: #f0f2f6; padding: 12px 15px; border-radius: 5px; margin: 5px 0;'>
        <p style='color: #000000; font-size: 17px; margin: 0; line-height: 1.6;'>
            🏷️ <span style='color: #000000;'>{theme_formatted}</span>
        </p>
    </div>
    """

def find_repo_file():
    """기본 엑셀 파일을 재귀적으로 검색하여 찾음"""
    # [1] 명시적인 새 파일명 우선 (순서 변경: 종목정리_종목순 정렬.xlsx 우선)
    exact_pattern = "**/종목정리_종목순 정렬.xlsx"
    exact_files = glob.glob(exact_pattern, recursive=True)
    if exact_files:
        return exact_files[0]
        
    # [2] 기존 주력 파일명 (순서 변경: 시그널뷰_... 후순위)
    exact_pattern_old = "**/시그널뷰_종목정리_핵심정리 및 테마.xlsx"
    exact_files_old = glob.glob(exact_pattern_old, recursive=True)
    if exact_files_old:
        return exact_files_old[0]
    
    # [3] 기타 패턴
    pattern_files = glob.glob("**/*종목정리*.xlsx", recursive=True)
    if pattern_files:
        return pattern_files[0]
        
    all_files = glob.glob("**/*종목*.xlsx", recursive=True)
    if all_files:
        return all_files[0]
        
    return None

# ---------------------------------------------------------
# 데이터 로드 함수 (Pickle 캐싱 적용)
# ---------------------------------------------------------
@st.cache_data(show_spinner=True, ttl=CACHE_TTL)
def load_data(file_input):
    """파일 경로(문자열) 또는 업로드된 파일 객체를 받아서 데이터 로드 (캐싱 적용)"""
    try:
        # 업로드된 파일인 경우 캐싱 불가 (매번 새로 읽기)
        if hasattr(file_input, 'read'):
            import io
            file_input.seek(0)
            file_buffer = io.BytesIO(file_input.read())
            xl = pd.ExcelFile(file_buffer, engine='openpyxl')
            return _parse_excel(xl)
        
        # 파일 경로인 경우 캐시 확인
        cache_path = get_cache_path(file_input, "_main")
        cached_data = load_from_cache(cache_path, file_input)
        
        if cached_data is not None:
            return cached_data
        
        # 캐시가 없거나 오래됨 -> 엑셀에서 읽기
        xl = pd.ExcelFile(file_input, engine='openpyxl')
        result = _parse_excel(xl)
        
        # 캐시에 저장
        save_to_cache(cache_path, result)
        
        return result

    except Exception as e:
        return None, None, str(e)

def _parse_excel(xl):
    """ExcelFile 객체에서 데이터를 파싱"""
    sangcheon_list = []
    signal_df = None
    
    for sheet in xl.sheet_names:
        if "상천" in sheet:
            df = xl.parse(sheet)
            df = clean_columns(df)
            sangcheon_list.append(df)
        elif "시그널" in sheet:
            df = xl.parse(sheet)
            df = clean_columns(df)
            signal_df = df
    
    final_sangcheon = pd.DataFrame()
    if sangcheon_list:
        final_sangcheon = pd.concat(sangcheon_list, ignore_index=True)
        if '날짜' in final_sangcheon.columns:
            final_sangcheon['날짜'] = pd.to_datetime(final_sangcheon['날짜'], errors='coerce')
            final_sangcheon = final_sangcheon.sort_values('날짜', ascending=False)
    
    return final_sangcheon, signal_df, None

@st.cache_data(show_spinner=True, ttl=CACHE_TTL)
def load_company_overview():
    """시그널뷰_기업개요.xlsx 또는 .csv 파일을 로드 (캐싱 적용)"""
    try:
        xlsx_path = "시그널뷰_기업개요.xlsx"
        csv_path = "시그널뷰_기업개요.csv"
        
        # xlsx 파일 확인
        if os.path.exists(xlsx_path):
            cache_path = get_cache_path(xlsx_path)
            cached = load_from_cache(cache_path, xlsx_path)
            if cached is not None:
                return cached
            
            df = pd.read_excel(xlsx_path, engine='openpyxl')
            df = clean_columns(df)
            save_to_cache(cache_path, df)
            return df
        
        # csv 파일 확인
        if os.path.exists(csv_path):
            cache_path = get_cache_path(csv_path)
            cached = load_from_cache(cache_path, csv_path)
            if cached is not None:
                return cached
            
            df = pd.read_csv(csv_path, encoding='utf-8-sig')
            df = clean_columns(df)
            save_to_cache(cache_path, df)
            return df
        
        return None
    except Exception as e:
        return None

@st.cache_data(show_spinner=True, ttl=CACHE_TTL)
def load_theme_data():
    """시그널뷰_종목정리_핵심정리 및 테마.xlsx 파일을 로드 (캐싱 적용)"""
    try:
        theme_path = "시그널뷰_종목정리_핵심정리 및 테마.xlsx"
        if not os.path.exists(theme_path):
            # 폴백: 기존 파일 시도
            theme_path = "시그널뷰_관련테마.xlsx"
            if not os.path.exists(theme_path):
                return None
        
        # 캐시 확인
        cache_path = get_cache_path(theme_path)
        cached = load_from_cache(cache_path, theme_path)
        if cached is not None:
            return cached
            
        df = pd.read_excel(theme_path, engine='openpyxl')
        df = clean_columns(df)
        
        # 종목명 컬럼 확인
        if '종목명' not in df.columns:
            df.rename(columns={df.columns[0]: '종목명'}, inplace=True)
        
        # 테마_전체 컬럼 확인 (새 파일에서는 '테마' 또는 '관련테마'로 되어 있을 수 있음)
        if '테마_전체' not in df.columns:
            theme_col = next((c for c in df.columns if any(k in c for k in ['관련테마', '테마'])), None)
            if theme_col:
                df.rename(columns={theme_col: '테마_전체'}, inplace=True)
        
        # 핵심요약 컬럼 확인
        summary_col = next((c for c in df.columns if '핵심요약' in c), None)
        if summary_col and summary_col != '핵심요약':
            df.rename(columns={summary_col: '핵심요약'}, inplace=True)
        
        # 필요한 컬럼만 선택 및 정리
        cols_to_keep = ['종목명', '테마_전체']
        if '핵심요약' in df.columns:
            cols_to_keep.append('핵심요약')
            
        if '종목명' in df.columns and '테마_전체' in df.columns:
            df = df.dropna(subset=['종목명'])
            df['종목명'] = df['종목명'].astype(str).str.strip()
            df = df.drop_duplicates(subset=['종목명'], keep='first')
            result = df[cols_to_keep]
            
            # 캐시에 저장
            save_to_cache(cache_path, result)
            return result
            
        return None
    except Exception as e:
        return None

@st.cache_data(show_spinner=True, ttl=CACHE_TTL)
def load_analysis_data():
    """시그널뷰_테마별 기업개요.xlsx 파일을 로드 (캐싱 적용)"""
    try:
        path = "시그널뷰_테마별 기업개요.xlsx"
        if not os.path.exists(path):
            return None
        
        cache_path = get_cache_path(path)
        cached = load_from_cache(cache_path, path)
        if cached is not None:
            return cached
            
        df = pd.read_excel(path, engine='openpyxl')
        df = clean_columns(df)
        
        # 표준화
        if '종목명' not in df.columns:
            df.rename(columns={df.columns[0]: '종목명'}, inplace=True)
        if '테마명' not in df.columns:
            theme_col = next((c for c in df.columns if '테마' in c), None)
            if theme_col: df.rename(columns={theme_col: '테마명'}, inplace=True)
        if '분석결과' not in df.columns:
            res_col = next((c for c in df.columns if '분석' in c or '내용' in c), None)
            if res_col: df.rename(columns={res_col: '분석결과'}, inplace=True)
            
        # 캐시에 저장
        save_to_cache(cache_path, df)
        return df
    except Exception as e:
        return None
