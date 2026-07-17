# 앱 비밀번호 설정

상천봇은 `st.secrets`의 `APP_PASSWORD`가 설정된 경우에만 로그인을 요구합니다.

1. `.streamlit/secrets.toml.example`을 참고해 로컬에 `.streamlit/secrets.toml`을 만듭니다.
2. 예시 값을 실제 비밀번호로 바꿉니다.
3. `python -m streamlit run app.py`로 실행합니다.

`APP_PASSWORD`가 없으면 개발 모드로 명시하고 로그인 없이 실행합니다. 실제 `secrets.toml`은 `.gitignore`에 포함되며 저장소에 추가하면 안 됩니다. 비밀번호 값은 화면 오류나 로그에 출력하지 않습니다.
