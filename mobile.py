import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime, timedelta

# 📱 모바일 최적화 레이아웃
st.set_page_config(layout="centered", page_title="📱 JH 모바일 타격대")

# 📌 종목 데이터베이스
KOSPI_STOCKS = {
    "[반도체] 삼성전자": "005930.KS", "[반도체] SK하이닉스": "000660.KS", "[반도체] 한미반도체": "042700.KS",
    "[방산] 한화에어로스페이스": "012450.KS", "[방산] 한국항공우주": "047810.KS", "[방산] LIG넥스원": "079550.KS", "[방산] 현대로템": "064350.KS",
    "[원전] 두산에너빌리티": "034020.KS", "[원전] 한전기술": "052690.KS", "[원전] 한전KPS": "051600.KS",
    "[바이오] 삼성바이오로직스": "207940.KS", "[바이오] 셀트리온": "068270.KS", "[바이오] 유한양행": "000100.KS",
    "[증권] 키움증권": "039490.KS", "[증권] 미래에셋증권": "006800.KS", "[증권] 한국금융지주": "071050.KS",
    "[친환경] 씨에스윈드": "112610.KS", "[친환경] 한화솔루션": "009830.KS", "[친환경] OCI홀딩스": "010060.KS", "[친환경] 두산퓨얼셀": "241560.KS"
}
KOSDAQ_STOCKS = {
    "[반도체] 리노공업": "058470.KQ", "[반도체] HPSP": "403870.KQ", "[반도체] 이오테크닉스": "039030.KQ",
    "[방산] 빅텍": "065450.KQ", "[방산] 스페코": "013810.KQ", "[방산] 제노코": "361390.KQ",
    "[원전] 일진파워": "094820.KQ", "[원전] 보성파워텍": "006910.KQ", "[원전] 서전기전": "189860.KQ",
    "[바이오] 알테오젠": "196170.KQ", "[바이오] HLB": "028300.KQ", "[바이오] 삼천당제약": "000250.KQ",
    "[이차전지] 에코프로비엠": "247540.KQ", "[이차전지] 에코프로": "086520.KQ"
}

@st.cache_data(ttl=300)
def get_main_data():
    all_tickers = list(KOSPI_STOCKS.values()) + list(KOSDAQ_STOCKS.values()) + ["^KS11", "^KQ11"]
    return yf.download(all_tickers, period="6mo")['Close']

@st.cache_data(ttl=60)
def get_briefing():
    tickers = {"NQ=F": "나스닥 선물", "EWY": "한국물 ETF", "NVDA": "엔비디아"}
    res = {}
    for t, n in tickers.items():
        try:
            h = yf.Ticker(t).history(period="5d")
            if len(h) >= 2:
                pct = ((h['Close'].iloc[-1] - h['Close'].iloc[-2]) / h['Close'].iloc[-2]) * 100
                res[n] = (h['Close'].iloc[-1], pct)
        except: pass
    return res

@st.cache_data(ttl=300)
def fetch_real_adr():
    try:
        url = "http://adrinfo.kr"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=5)
        response.encoding = 'utf-8'
        text = BeautifulSoup(response.text, 'html.parser').get_text(separator=' ')
        matches = re.findall(r'(\d{2,3}\.\d{1,2})\s*%\s*\(', text)
        if len(matches) >= 2: return float(matches[0]), float(matches[1])
        return 100.0, 100.0
    except: return 100.0, 100.0

@st.cache_data(ttl=60)
def auto_market_stage(kpi_adr, kdq_adr):
    def get_stage(ticker, adr):
        df = yf.Ticker(ticker).history(period="3mo")
        if len(df) < 20: return "분석 불가"
        curr = float(df['Close'].iloc[-1])
        ma5 = float(df['Close'].rolling(5).mean().iloc[-1])
        ma20 = float(df['Close'].rolling(20).mean().iloc[-1])
        if curr > ma5 and ma5 > ma20 and adr >= 100: return "🟢 [Stage 2] 공격 (리턴/종베)"
        elif curr < ma20 or adr <= 75: return "🔴 [Stage 3] 수비 (변곡 대기)"
        else: return "🟡 [Stage 1] 순환매 (JH존)"
    return get_stage("^KS11", kpi_adr), get_stage("^KQ11", kdq_adr)

@st.cache_data(ttl=2)
def fetch_realtime_naver(sym):
    try:
        code = sym.split('.')[0]
        url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{code}"
        data = requests.get(url, timeout=2).json()['result']['areas'][0]['datas'][0]
        return float(data['nv']), float(data['aq'])
    except: return None, None

@st.cache_data(ttl=2)
def auto_stock_filter(ticker):
    stock = yf.Ticker(ticker)
    h_d = stock.history(period="5d")
    h_15m = stock.history(period="1mo", interval="15m") 
    if h_d.empty: return False, 0, False, 0, 0, 0, 0, 0, 0
    
    real_p, real_v = fetch_realtime_naver(ticker)
    curr_p = real_p if real_p else float(h_d['Close'].iloc[-1])
    curr_v = real_v if real_v else float(h_d['Volume'].iloc[-1])
    high_p = max(float(h_d['High'].max()), curr_p)
    low_p = min(float(h_d['Low'].min()), curr_p)
    ma5_d = float(h_d['Close'].rolling(5).mean().iloc[-1])
    
    val_100m = (curr_p * curr_v) / 100000000
    is_v_ok = bool(val_100m >= 2000)
    
    is_a = False
    m60 = 0.0
    m120 = 0.0
    if not h_15m.empty:
        v15 = h_15m['Close'].dropna()
        if len(v15) >= 120:
            m60 = float(v15.rolling(60).mean().iloc[-1])
            m120 = float(v15.rolling(120).mean().iloc[-1])
            is_a = bool((curr_p > m60) and (m60 > m120))
    return is_v_ok, val_100m, is_a, curr_p, high_p, low_p, ma5_d, m60, m120

# --- 📱 모바일 UI 구성 ---
st.title("🦅 JH 모바일 타격대")

with st.expander("🕒 장전 탑다운 시황 및 비중", expanded=False):
    brief = get_briefing()
    for n, (p, pct) in brief.items():
        st.metric(n, f"{p:,.2f}", f"{pct:.2f}%")

data = get_main_data()
k_adr, q_adr = fetch_real_adr()
k_st, q_st = auto_market_stage(k_adr, q_adr)

t1, t2 = st.tabs(["📊 시장 & RS", "⚔️ AI 타점 계산기"])

with t1:
    st.subheader("1. Market Stage")
    st.info(f"🔵 **KOSPI:** {k_adr}% | {k_st}")
    st.warning(f"🟡 **KOSDAQ:** {q_adr}% | {q_st}")
    
    st.subheader("2. 실시간 ADR 차트")
    components.iframe("http://adrinfo.kr/chart", height=280, scrolling=True)

    st.subheader("3. 주도주 RS 판독")
    target_rs = st.selectbox("시장 선택", ["KOSPI 주도주", "KOSDAQ 주도주"])
    if target_rs == "KOSPI 주도주":
        sel_k = st.multiselect("종목", list(KOSPI_STOCKS.keys()), default=["[방산] 한화에어로스페이스", "[반도체] SK하이닉스"])
        fig_k = go.Figure()
        fig_k.add_hline(y=100, line_dash="dash", line_color="white")
        if "^KS11" in data.columns:
            for name in sel_k:
                if KOSPI_STOCKS[name] in data.columns:
                    try:
                        base_sym = data[KOSPI_STOCKS[name]].dropna().iloc[0]
                        base_idx = data["^KS11"].dropna().iloc[0]
                        rs = (data[KOSPI_STOCKS[name]] / data["^KS11"]) / (base_sym / base_idx) * 100
                        fig_k.add_trace(go.Scatter(x=data.index, y=rs, name=name))
                    except: pass
        fig_k.update_layout(height=350, template="plotly_dark", margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig_k, use_container_width=True)
    else:
        sel_q = st.multiselect("종목", list(KOSDAQ_STOCKS.keys()), default=["[방산] 빅텍", "[바이오] 알테오젠"])
        fig_q = go.Figure()
        fig_q.add_hline(y=100, line_dash="dash", line_color="#fcd34d")
        if "^KQ11" in data.columns:
            for name in sel_q:
                if KOSDAQ_STOCKS[name] in data.columns:
                    try:
                        base_sym = data[KOSDAQ_STOCKS[name]].dropna().iloc[0]
                        base_idx = data["^KQ11"].dropna().iloc[0]
                        rs = (data[KOSDAQ_STOCKS[name]] / data["^KQ11"]) / (base_sym / base_idx) * 100
                        fig_q.add_trace(go.Scatter(x=data.index, y=rs, name=name))
                    except: pass
        fig_q.update_layout(height=350, template="plotly_dark", margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig_q, use_container_width=True)

with t2:
    st.subheader("🤖 타점 계산기 (HTS 연동)")
    all_s = {**KOSPI_STOCKS, **KOSDAQ_STOCKS}
    t_name = st.selectbox("종목 선택", list(all_s.keys()))
    t_sym = all_s[t_name]
    
    is_v, val, is_a, curr, hi, lo, ma5, m60, m120 = auto_stock_filter(t_sym)
    
    st.metric("현재가", f"{curr:,.0f}원", f"고점: {hi:,.0f} / 저점: {lo:,.0f}")
    
    v_col, a_col = st.columns(2)
    v_col.metric("대금", f"{val:,.0f}억", "PASS" if is_v else "FAIL")
    if m120 == 0: a_col.metric("정배열", "데이터 부족")
    else: a_col.metric("정배열", "✅ 통과" if is_a else "❌ 깨짐")
    
    st.divider()
    st.info(f"**🛡️ 수비 (JH존)**\n- 1차(-4%): {hi*0.96:,.0f}원\n- 2차(-6%): {hi*0.94:,.0f}원\n- 3차(-8%): {hi*0.92:,.0f}원")
    st.success(f"**⚔️ 공격 (리턴)**\n- 60선: {m60:,.0f}원")
    st.error(f"**💣 필살 (변곡)**\n- 피보 0.5: {hi-((hi-lo)*0.5):,.0f}원")
    
    st.caption(f"📊 {t_name} 현재 차트 상태:\n현재({curr:,.0f}) | 60선({m60:,.0f}) | 120선({m120:,.0f})")

