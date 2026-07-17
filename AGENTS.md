# 상천봇 작업 지침

- 앱 실행: `python -m streamlit run app.py`
- 테스트: `python -m pytest -q`
- 컴파일 점검: `python -m py_compile app.py app_utils.py search_engine.py issue_analysis.py ui_components.py`
- 저장소의 엑셀 원본은 수정하거나 삭제하지 않는다. 중복 의심 파일도 임의로 삭제하지 않는다.
- 종목 연결과 조회의 기본 식별키는 정규화한 종목코드(`__stock_key`)다.
- Streamlit과 한국어 UI를 유지한다.
- 작업 완료 전 전체 테스트, Python 컴파일, 변경 diff를 검토한다.
