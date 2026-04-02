import streamlit as st
import streamlit.components.v1 as components
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import requests
from bs4 import BeautifulSoup
import urllib.parse
import unicodedata
import urllib3
import re
from datetime import datetime, timedelta

# SSL 인증서 경고 강제 무시
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 📱 모바일 최적화 레이아웃
st.set_page_config(layout="centered", page_title="📱 JH 모바일 타격대")

# 📌 기본 관심 종목 리스트
KOSPI_STOCKS = {
    "[반도체] 삼성전자": "005930.KS", "[반도체] SK하이닉스": "000660.KS", "[반도체] 한미반도체": "042700.KS",
    "[방산] 한화에어로스페이스": "012450.KS", "[방산] 한국항공우주": "047810.KS", "[방산] LIG넥스원": "079550.KS", "[방산] 현대로템": "064350.KS",
    "[원전] 두산에너빌리티": "034020.KS", "[원전] 한전기술": "052690.KS", "[원전] 한전KPS": "051600.KS",
    "[바이오] 삼성바이오로직스": "207940.KS", "[바이오] 셀트리온": "068270.KS", "[바이오] 유한양행": "000100.KS",
    "[증권] 키움증권": "039490.KS", "[증권] 미래에셋증권": "006800.KS", "[증권] 한국금융지주": "071050.KS",
    "[친환경] 씨에스윈드": "112610.KS"
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
    tickers = {"NQ=F": "나스닥 선물", "EWY": "한국물 ETF", "NVDA": "엔비디아", "TSLA": "테슬라"}
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
        headers = {'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip, deflate'}
        response = requests.get("http://adrinfo.kr", headers=headers, timeout=5, verify=False)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text(separator=' ')
        matches = re.findall(r'(\d{2,3}\.\d{1,2})\s*%\s*\(', text)
        if len(matches) >= 2: return float(matches[0]), float(matches[1])
        return 100.0, 100.0
    except: return 100.0, 100.0

@st.cache_data(ttl=5)
def search_stock_ultimate(keyword):
    keyword = keyword.strip()
    if not keyword: return None, None, None, "검색어가 없습니다."
    
    # 1. 6자리 숫자 다이렉트 입력 
    if keyword.isdigit() and len(keyword) == 6:
        code = keyword
        if not yf.Ticker(f"{code}.KQ").history(period="1d").empty:
            return f"{code}.KQ", code, f"종목코드 {code}", "SUCCESS"
        if not yf.Ticker(f"{code}.KS").history(period="1d").empty:
            return f"{code}.KS", code, f"종목코드 {code}", "SUCCESS"
        return None, None, None, f"코드 '{code}' 의 차트 데이터가 존재하지 않습니다."

    # 2. 한글 검색 (네이버 메인 검색 우회 + 압축 해제 에러 방어)
    keyword = unicodedata.normalize('NFC', keyword)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
        'Accept-Encoding': 'gzip, deflate' 
    }
    
    try:
        url = f"https://search.naver.com/search.naver?query={urllib.parse.quote(keyword + ' 주가')}"
        res = requests.get(url, headers=headers, timeout=3, verify=False)
        match = re.search(r'code=(\d{6})', res.text)
        if match:
            code = match.group(1)
            suffix = ".KQ" if "코스닥" in res.text else ".KS"
            if yf.Ticker(f"{code}{suffix}").history(period="1d").empty:
                suffix = ".KS" if suffix == ".KQ" else ".KQ"
            return f"{code}{suffix}", code, keyword, "SUCCESS"
    except Exception as e:
        return None, None, None, f"검색 접근 실패: {str(e)}"

    return None, None, None, "종목을 찾지 못했습니다. 6자리 숫자를 입력해 주세요."

def auto_market_stage_impl(kpi_adr, kdq_adr):
    def get_stage(ticker, adr):
        df = yf.Ticker(ticker).history(period="3mo")
        if len(df) < 20: return "분석 불가"
        curr = float(df['Close'].iloc[-1]); ma5 = float(df['Close'].rolling(5).mean().iloc[-1]); ma20 = float(df['Close'].rolling(20).mean().iloc[-1])
        if curr > ma5 and ma5 > ma20 and adr >= 100: return "🟢 [Stage 2] 공격 (리턴/종베)"
        elif curr < ma20 or adr <= 75: return "🔴 [Stage 3] 수비 (변곡 대기)"
        else: return "🟡 [Stage 1] 순환매 (JH존)"
    kpi_t = get_stage("^KS11", kpi_adr); kdq_t = get_stage("^KQ11", kdq_adr)
    return kpi_t, kdq_t

@st.cache_data(ttl=2)
def fetch_realtime_naver(ticker):
    try:
        code = ticker.split('.')[0]
        url = f"https://polling.finance.naver.com/api/realtime?query=SERVICE_ITEM:{code}"
        headers = {'User-Agent': 'Mozilla/5.0', 'Accept-Encoding': 'gzip, deflate'}
        res = requests.get(url, headers=headers, timeout=2, verify=False).json()
        data = res['result']['areas'][0]['datas'][0]
        curr = abs(float(data['nv']))
        vol = float(data['aq'])
        high = abs(float(data['hv']))
        low = abs(float(data['lv']))
        return curr, vol, high, low
    except: return None, None, None, None

@st.cache_data(ttl=2)
def auto_stock_filter(ticker):
    n_cur, n_vol, n_hi, n_lo = fetch_realtime_naver(ticker)
    try:
        stock = yf.Ticker(ticker)
        h_d = stock.history(period="5d")
        h_15m = stock.history(period="1mo", interval="15m")
    except:
        h_d, h_15m = pd.DataFrame(), pd.DataFrame()
        
    curr_p = n_cur if n_cur is not None else (float(h_d['Close'].iloc[-1]) if not h_d.empty else 0)
    curr_v = n_vol if n_vol is not None else (float(h_d['Volume'].iloc[-1]) if not h_d.empty else 0)
    
    if curr_p == 0: return False, 0, False, 0, 0, 0, 0, 0, 0
        
    yh_high = float(h_d['High'].max()) if not h_d.empty else 0
    yh_low = float(h_d['Low'].min()) if not h_d.empty else float('inf')
    
    high_p = max(n_hi if n_hi is not None else 0, yh_high, curr_p)
    low_p = min(n_lo if n_lo is not None else float('inf'), yh_low, curr_p)
    if low_p == float('inf'): low_p = curr_p
    
    ma5_d = float(h_d['Close'].rolling(5).mean().iloc[-1]) if not h_d.empty and len(h_d)>=5 else curr_p
    val_100m = (curr_p * curr_v) / 100000000
    is_v_ok = bool(val_100m >= 2000)
    
    is_a = False; m60 = 0.0; m120 = 0.0
    if not h_15m.empty and len(h_15m) >= 120:
        v15 = h_15m['Close'].dropna()
        m60 = float(v15.rolling(60).mean().iloc[-1]); m120 = float(v15.rolling(120).mean().iloc[-1])
        is_a = bool((curr_p > m60) and (m60 > m120))
            
    return is_v_ok, val_100m, is_a, curr_p, high_p, low_p, ma5_d, m60, m120

# --- 📱 모바일 UI 구성 ---
st.title("🦅 JH 모바일 타격대")

with st.expander("🕒 장전 탑다운 시황 및 비중", expanded=False):
    brief = get_briefing()
    if not brief:
        st.warning("🔄 데이터를 불러오고 있습니다.")
    else:
        for n, (p, pct) in brief.items():
            st.metric(n, f"{p:,.2f}", f"{pct:.2f}%")

data = get_main_data()
k_adr, q_adr = fetch_real_adr()
k_st, q_st = auto_market_stage_impl(k_adr, q_adr)

t1, t2 = st.tabs(["📊 시장 & RS", "⚔️ 타점 & 검색"])

with t1:
    st.subheader("1. Market Stage")
    st.info(f"🔵 **KOSPI:** {k_adr}% | {k_st}")
    st.warning(f"🟡 **KOSDAQ:** {q_adr}% | {q_st}")
    
    st.subheader("2. 실시간 ADR 차트")
    components.iframe("http://adrinfo.kr/chart", height=280, scrolling=True)

    st.subheader("3. 주도주 RS 판독")
    target_rs = st.selectbox("시장 선택", ["KOSPI 주도주", "KOSDAQ 주도주"])
    if "KOSPI" in target_rs:
        sel_k = st.multiselect("종목", list(KOSPI_STOCKS.keys()), default=list(KOSPI_STOCKS.keys())[:2])
        fig_k = go.Figure(); fig_k.add_hline(y=100, line_dash="dash", line_color="white")
        for name in sel_k:
            if KOSPI_STOCKS[name] in data.columns:
                try:
                    rs = (data[KOSPI_STOCKS[name]]/data["^KS11"])/(data[KOSPI_STOCKS[name]].dropna().iloc[0]/data["^KS11"].dropna().iloc[0])*100
                    fig_k.add_trace(go.Scatter(x=data.index, y=rs, name=name))
                except: pass
        fig_k.update_layout(height=350, template="plotly_dark", margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig_k, use_container_width=True)
    else:
        sel_q = st.multiselect("종목", list(KOSDAQ_STOCKS.keys()), default=list(KOSDAQ_STOCKS.keys())[:2])
        fig_q = go.Figure(); fig_q.add_hline(y=100, line_dash="dash", line_color="#fcd34d")
        for name in sel_q:
            if KOSDAQ_STOCKS[name] in data.columns:
                try:
                    rs = (data[KOSDAQ_STOCKS[name]]/data["^KQ11"])/(data[KOSDAQ_STOCKS[name]].dropna().iloc[0]/data["^KQ11"].dropna().iloc[0])*100
                    fig_q.add_trace(go.Scatter(x=data.index, y=rs, name=name))
                except: pass
        fig_q.update_layout(height=350, template="plotly_dark", margin=dict(l=0, r=0, t=20, b=0), legend=dict(orientation="h", y=-0.2))
        st.plotly_chart(fig_q, use_container_width=True)

with t2:
    st.subheader("🤖 종목 검색 및 AI 타점")
    
    search_mode = st.radio("검색 방식", ["리스트에서 고르기", "이름/숫자 직접 입력"], horizontal=True)
    
    if search_mode == "리스트에서 고르기":
        all_s = {**KOSPI_STOCKS, **KOSDAQ_STOCKS}
        target_name = st.selectbox("종목 선택", list(all_s.keys()))
        target_ticker = all_s[target_name]
    else:
        user_keyword = st.text_input("종목명 또는 숫자 6자리 [엔터]", placeholder="예: 흥구석유, 024060")
        if user_keyword:
            t_sym, raw_code, found_name, err_msg = search_stock_ultimate(user_keyword)
            if not t_sym:
                st.error(f"검색 실패: {err_msg}")
                st.stop()
            target_ticker = t_sym
            target_name = f"[검색] {found_name} ({raw_code})"
        else:
            st.info("💡 종목의 한글 이름이나 6자리 숫자를 입력하세요.")
            st.stop()
            
    v_ok, val, a_ok, cur, hi, lo, m5, m60, m120 = auto_stock_filter(target_ticker)
    
    if cur == 0:
        st.error("데이터를 가져올 수 없습니다.")
        st.stop()

    st.metric(f"{target_name} 정규장 종가", f"{cur:,.0f}원", f"고가: {hi:,.0f} / 저가: {lo:,.0f}")
    
    v_col, a_col = st.columns(2)
    v_col.metric("대금", f"{val:,.0f}억", "PASS" if v_ok else "FAIL")
    align_str = f"{cur:,.0f} > {m60:,.0f} > {m120:,.0f}" if a_ok else f"{cur:,.0f} | {m60:,.0f} | {m120:,.0f}"
    a_col.metric("정배열", "✅ 통과" if a_ok else "❌ 깨짐", align_str if m120 > 0 else "데이터 부족")
    
    st.divider()
    
    st.caption("💡 NXT 저녁 8시 마감가를 입력하면 타점이 보정됩니다.")
    nxt_price = st.number_input(f"🌙 NXT 최종 체결가 입력", value=int(cur), step=50)
    
    base_price = nxt_price if nxt_price > 0 else cur
    actual_high = max(hi, base_price) 
    
    nxt_gap = ((base_price - cur) / cur) * 100 if cur > 0 else 0
    if nxt_gap != 0:
        st.caption(f"※ KRX 정규장 대비 NXT 프리미엄: **{nxt_gap:+.2f}%** 반영 완료")
    
    c1, c2 = st.columns(2)
    with c1:
        st.info(f"🛡️ **JH존(수비)**\n\n- 1차(-4%): **{actual_high*0.96:,.0f}원**\n- 2차(-6%): **{actual_high*0.94:,.0f}원**\n- 3차(-8%): **{actual_high*0.92:,.0f}원**")
        st.warning(f"🗡️ **5이탈 매매**\n\n5일선: **{m5:,.0f}원**")
    with c2:
        st.success(f"⚔️ **리턴(공격)**\n\n60선: **{m60:,.0f}원**")
        fibo_05 = actual_high - ((actual_high - lo) * 0.5)
        st.error(f"💣 **변곡(필살)**\n\n피보 0.5: **{fibo_05:,.0f}원**")
