from pathlib import Path

import pandas as pd
import pytest

from app_utils import (
    _parse_excel,
    load_analysis_data,
    load_company_overview,
    load_name_aliases,
    load_stock_code_map,
    load_theme_data,
)
from search_engine import build_search_index, load_keyword_aliases, search_documents


@pytest.fixture(scope="module")
def real_search_index():
    main_path = Path("종목정리_종목순 정렬.xlsx")
    assert main_path.exists()
    sangcheon, signal, error = _parse_excel(pd.ExcelFile(main_path, engine="openpyxl"))
    assert error is None
    return build_search_index(
        sangcheon,
        signal,
        load_theme_data(),
        load_company_overview(),
        load_analysis_data(),
        load_name_aliases(),
        load_stock_code_map(),
    )


@pytest.mark.parametrize("query", ["HBM", "유리기판", "CXL", "원전", "헬륨", "반도체"])
def test_real_keywords_return_documents(real_search_index, query):
    result, _ = search_documents(real_search_index, query, aliases=load_keyword_aliases())
    assert not result.empty, query
    assert result["종목키"].astype(str).str.strip().all()
