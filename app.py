"""Точка входа: русская навигация."""

import streamlit as st

st.set_page_config(
    page_title="Предиктивная аналитика продаж",
    page_icon="📈",
    layout="wide",
)

overview = st.Page("pages/0_Обзор.py", title="Обзор", default=True)
upload = st.Page("pages/1_Загрузка.py", title="Загрузка")
analytics = st.Page("pages/2_Аналитика.py", title="Аналитика")
forecast = st.Page("pages/3_Прогноз.py", title="Прогноз")
scenarios = st.Page("pages/4_Сценарии.py", title="Сценарии")
insights = st.Page("pages/5_Рекомендации.py", title="Рекомендации")

st.navigation([overview, upload, analytics, forecast, scenarios, insights]).run()
