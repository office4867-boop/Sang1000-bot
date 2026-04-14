#!/usr/bin/env python3
"""
사명 변경 자동 감지 및 Excel 업데이트 스크립트
GitHub Actions에서 매주 월요일 자동 실행됩니다.

동작 방식:
  1. FDR(FinanceDataReader)로 현재 KRX 전체 종목 이름→코드 조회
  2. DART corpCode.xml로 코드→현재 공식 이름 조회
  3. Excel 파일의 종목명과 비교해 사명 변경 감지
  4. 변경된 종목명을 Excel 파일에 일괄 반영
  5. 변경 내역을 stock_code_map.json에 저장 (다음 실행 시 이전 사명도 추적 가능)
"""

import os
import json
import zipfile
import requests
import pandas as pd
import FinanceDataReader as fdr
from io import BytesIO
import xml.etree.ElementTree as ET
from datetime import datetime

# ── 설정 ──────────────────────────────────────────────────────
DART_API_KEY = os.environ.get('DART_API_KEY', '')

# 이름→코드 누적 매핑 파일 (구 사명도 계속 추적하기 위해 repo에 저장)
CODE_MAP_FILE = 'stock_code_map.json'

# 업데이트 대상 Excel 파일 목록
EXCEL_FILES = [
    '종목정리_종목순 정렬.xlsx',
    '시그널뷰_기업개요.xlsx',
    '시그널뷰_종목정리_핵심정리 및 테마.xlsx',
    '시그널뷰_테마별 기업개요.xlsx',
    '시그널뷰_관련테마.xlsx',
    'stock_combined.xlsx',
]

NAME_COL = '종목명'


# ── 데이터 수집 ────────────────────────────────────────────────

def get_fdr_name_to_code() -> dict:
    """FDR로 현재 KRX 전체 종목 이름→코드 딕셔너리 반환"""
    result = {}
    try:
        df = fdr.StockListing('KRX')
        for _, row in df.iterrows():
            code = str(row.get('Code', '')).zfill(6)
            name = str(row.get('Name', '')).strip()
            if code and name:
                result[name] = code
    except Exception as e:
        print(f"  [FDR] KRX 조회 실패: {e}")
    return result


def get_dart_code_to_name() -> dict:
    """DART corpCode.xml에서 종목코드→현재 회사명 딕셔너리 반환"""
    if not DART_API_KEY:
        print("  [DART] API 키 없음 — 스킵")
        return {}
    try:
        url = f"https://opendart.fss.or.kr/api/corpCode.xml?crtfc_key={DART_API_KEY}"
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()

        with zipfile.ZipFile(BytesIO(resp.content)) as z:
            with z.open('CORPCODE.xml') as f:
                root = ET.parse(f).getroot()

        result = {}
        for item in root.findall('list'):
            stock_code = (item.find('stock_code').text or '').strip()
            corp_name  = (item.find('corp_name').text  or '').strip()
            if stock_code:
                result[stock_code] = corp_name

        print(f"  [DART] {len(result)}개 법인 로드 완료")
        return result
    except Exception as e:
        print(f"  [DART] 오류: {e}")
        return {}


# ── 매핑 파일 관리 ─────────────────────────────────────────────

def load_code_map() -> dict:
    """저장된 이름→코드 누적 매핑 로드"""
    if os.path.exists(CODE_MAP_FILE):
        with open(CODE_MAP_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {}


def save_code_map(mapping: dict):
    """이름→코드 누적 매핑 저장"""
    with open(CODE_MAP_FILE, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)


# ── Excel 처리 ─────────────────────────────────────────────────

def get_all_stock_names() -> set:
    """모든 Excel 파일에서 종목명 수집"""
    names = set()
    for path in EXCEL_FILES:
        if not os.path.exists(path):
            continue
        try:
            df = pd.read_excel(path, engine='openpyxl')
            df.columns = df.columns.str.replace(' ', '').str.strip()
            if NAME_COL in df.columns:
                found = df[NAME_COL].dropna().astype(str).str.strip().unique()
                names.update(found)
        except Exception as e:
            print(f"  [Excel] {path} 읽기 실패: {e}")
    return names


def apply_name_changes(name_changes: dict) -> int:
    """모든 Excel 파일에 {구 사명: 신 사명} 일괄 치환. 수정된 행 수 반환."""
    total = 0
    for path in EXCEL_FILES:
        if not os.path.exists(path):
            continue
        try:
            xl = pd.ExcelFile(path, engine='openpyxl')
            sheets = {}
            file_changed = False

            for sheet in xl.sheet_names:
                df = xl.parse(sheet)
                df.columns = df.columns.str.replace(' ', '').str.strip()

                if NAME_COL in df.columns:
                    for old, new in name_changes.items():
                        mask = df[NAME_COL] == old
                        if mask.any():
                            df.loc[mask, NAME_COL] = new
                            cnt = int(mask.sum())
                            print(f"    [{path}] '{sheet}' 시트: {old} → {new} ({cnt}행)")
                            total += cnt
                            file_changed = True

                sheets[sheet] = df

            if file_changed:
                with pd.ExcelWriter(path, engine='openpyxl') as w:
                    for sheet, df in sheets.items():
                        df.to_excel(w, sheet_name=sheet, index=False)

        except Exception as e:
            print(f"  [Excel] {path} 업데이트 실패: {e}")

    return total


# ── 메인 ───────────────────────────────────────────────────────

def main():
    print(f"\n{'='*55}")
    print(f"  사명 변경 자동 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*55}\n")

    # 1) 현재 KRX 이름→코드 조회 (FDR)
    print("[1] FDR KRX 종목 조회...")
    fdr_map = get_fdr_name_to_code()
    print(f"    {len(fdr_map)}개 종목 로드\n")

    # 2) DART 코드→현재 이름 조회
    print("[2] DART 법인 정보 조회...")
    dart_map = get_dart_code_to_name()
    print()

    # 3) 누적 매핑 로드 후 FDR 현재 종목으로 보강
    #    (구 사명 → 코드 기록이 누적되어 있어 이름 변경 후에도 추적 가능)
    print("[3] 코드 매핑 로드...")
    code_map = load_code_map()
    prev_count = len(code_map)
    code_map.update(fdr_map)   # FDR 현재 이름으로 갱신 (신규 상장 포함)
    print(f"    이전 {prev_count}개 → 현재 {len(code_map)}개\n")

    # 4) Excel 전체 종목명 수집
    print("[4] Excel 종목명 수집...")
    excel_names = get_all_stock_names()
    print(f"    {len(excel_names)}개 종목 발견\n")

    # 5) 사명 변경 감지
    print("[5] 사명 변경 감지...")
    name_changes = {}
    unmapped = []

    for old_name in sorted(excel_names):
        code = code_map.get(old_name)
        if not code:
            unmapped.append(old_name)
            continue

        current_name = dart_map.get(code)
        if current_name and current_name != old_name:
            name_changes[old_name] = current_name
            print(f"    변경 감지: {old_name} → {current_name}  (코드: {code})")
            # 매핑을 신 사명으로 갱신
            code_map[current_name] = code

    if not name_changes:
        print("    변경 없음")

    if unmapped:
        print(f"\n    코드 미매핑 종목 {len(unmapped)}개 (처음 실행 시 정상):")
        for n in unmapped[:10]:
            print(f"      - {n}")
        if len(unmapped) > 10:
            print(f"      ... 외 {len(unmapped)-10}개")
    print()

    # 6) Excel 업데이트
    print("[6] Excel 업데이트...")
    if name_changes:
        total = apply_name_changes(name_changes)
        print(f"    총 {total}행 수정 완료\n")
    else:
        print("    업데이트 없음\n")

    # 7) 매핑 파일 저장
    save_code_map(code_map)
    print(f"[7] 매핑 저장 완료: {len(code_map)}개 종목")
    print(f"\n{'='*55}  완료\n")


if __name__ == '__main__':
    main()
