import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf
from pycoingecko import CoinGeckoAPI
from datetime import datetime, timedelta

st.set_page_config(page_title="Portfolio Dashboard", layout="wide")
st.title("🚀 My Crypto & Equity Portfolio Dashboard")

FINNHUB_API_KEY = st.secrets.get("FINNHUB_API_KEY")

st.sidebar.header("📋 Edit Your Holdings")

if 'holdings' not in st.session_state:
    st.session_state.holdings = pd.DataFrame({
        "Asset": ["BTC", "ETH", "AAPL", "TSLA"],
        "Type": ["Crypto", "Crypto", "Equity", "Equity"],
        "Quantity": [0.5, 10.0, 50.0, 20.0],
        "Avg Cost": [45000.0, 2500.0, 150.0, 200.0]
    })

# Editing UI
st.sidebar.subheader("Current Holdings")
st.sidebar.dataframe(st.session_state.holdings, use_container_width=True)

st.sidebar.subheader("Add New Holding")
new_asset = st.sidebar.text_input("Asset (e.g. SOL, MSFT)")
new_type = st.sidebar.selectbox("Type", ["Crypto", "Equity"])
new_qty = st.sidebar.number_input("Quantity", min_value=0.0, value=1.0, step=0.0001)
new_cost = st.sidebar.number_input("Avg Cost $", min_value=0.0, value=100.0, step=0.01)

if st.sidebar.button("➕ Add Holding"):
    if new_asset:
        new_row = pd.DataFrame([{"Asset": new_asset.upper(), "Type": new_type, "Quantity": new_qty, "Avg Cost": new_cost}])
        st.session_state.holdings = pd.concat([st.session_state.holdings, new_row], ignore_index=True)

delete_index = st.sidebar.number_input("Delete row number (0-based)", min_value=0, value=0, step=1)
if st.sidebar.button("🗑️ Delete Row"):
    if 0 <= delete_index < len(st.session_state.holdings):
        st.session_state.holdings = st.session_state.holdings.drop(delete_index).reset_index(drop=True)

if st.sidebar.button("🗑️ Clear All Holdings"):
    st.session_state.holdings = pd.DataFrame(columns=["Asset", "Type", "Quantity", "Avg Cost"])
    st.success("✅ All holdings cleared!")

# CSV Tools
st.sidebar.subheader("💾 CSV Tools")
col1, col2 = st.sidebar.columns(2)
if col1.button("📤 Export CSV"):
    csv = st.session_state.holdings.to_csv(index=False)
    st.download_button("Download portfolio_holdings.csv", csv, "portfolio_holdings.csv", "text/csv")

if uploaded_file := col2.file_uploader("📥 Import CSV", type=["csv"]):
    st.session_state.holdings = pd.read_csv(uploaded_file)
    st.success("✅ Portfolio imported!")

# Refresh Prices Button
if st.sidebar.button("🔄 Refresh Prices"):
    st.cache_data.clear()
    st.success("✅ Prices refreshed!")
    st.rerun()

# Price fetching
cg = CoinGeckoAPI()

@st.cache_data(ttl=300)
def get_price(symbol, asset_type):
    try:
        if asset_type == "Crypto":
            coin_map = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "ripple"}
            coin_id = coin_map.get(symbol.upper(), symbol.lower())
            data = cg.get_price(ids=coin_id, vs_currencies="usd")
            return data.get(coin_id, {}).get("usd")
        else:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            return hist['Close'].iloc[-1] if not hist.empty else None
    except:
        st.warning(f"Could not fetch {symbol}")
        return None

# Current Portfolio
portfolio = []
total_value = 0.0
for _, row in st.session_state.holdings.iterrows():
    price = get_price(row["Asset"], row["Type"])
    if price is not None:
        value = float(row["Quantity"]) * price
        gain_loss = (price - float(row["Avg Cost"])) * float(row["Quantity"])
        portfolio.append({
            "Asset": row["Asset"],
            "Type": row["Type"],
            "Quantity": row["Quantity"],
            "Avg Cost": row["Avg Cost"],
            "Current Price": price,
            "Market Value": value,
            "Gain/Loss $": gain_loss,
            "Gain/Loss %": ((price / float(row["Avg Cost"])) - 1) * 100 if float(row["Avg Cost"]) > 0 else 0
        })
        total_value += value

df_portfolio = pd.DataFrame(portfolio)

col1, col2, col3 = st.columns(3)
col1.metric("💰 Total Value", f"${total_value:,.2f}")
col2.metric("📈 Total P&L", f"${df_portfolio['Gain/Loss $'].sum():,.2f}" if not df_portfolio.empty else "$0.00")
col3.metric("Assets", len(df_portfolio))

st.subheader("📊 Holdings")
if not df_portfolio.empty:
    st.dataframe(df_portfolio.style.format({
        "Current Price": "${:,.2f}", "Market Value": "${:,.2f}",
        "Gain/Loss $": "${:,.2f}", "Gain/Loss %": "{:,.1f}%"
    }), use_container_width=True)

c1, c2 = st.columns(2)
with c1:
    if not df_portfolio.empty:
        st.plotly_chart(px.pie(df_portfolio, values="Market Value", names="Asset", title="Allocation"), use_container_width=True)
with c2:
    if not df_portfolio.empty:
        st.plotly_chart(px.bar(df_portfolio, x="Asset", y="Gain/Loss %", color="Type", title="Performance"), use_container_width=True)

# Historical Charts - Cleaner Layout
st.subheader("📈 Historical Portfolio Value (Last 30 Days)")
chart_type = st.radio("Chart Type", ["Line", "Candlestick", "Combined"], horizontal=True)

if st.button("Load Real Historical Trend"):
    with st.spinner("Fetching real historical prices..."):
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        hist_data = []
        for single_date in pd.date_range(start_date, end_date):
            daily_value = 0.0
            for _, row in st.session_state.holdings.iterrows():
                try:
                    ticker = yf.Ticker(row["Asset"] if row["Type"] == "Equity" else row["Asset"] + "-USD")
                    hist = ticker.history(start=single_date, end=single_date + timedelta(days=1))
                    if not hist.empty:
                        daily_value += float(row["Quantity"]) * hist['Close'].iloc[-1]
                except:
                    pass
            hist_data.append({"Date": single_date.date(), "Value": daily_value})

        hist_df = pd.DataFrame(hist_data).dropna()

        if not hist_df.empty:
            if chart_type == "Line":
                st.line_chart(hist_df.set_index("Date")["Value"], use_container_width=True)
            elif chart_type == "Candlestick":
                hist_df['Open'] = hist_df['Value'].shift(1).fillna(hist_df['Value'])
                hist_df['Close'] = hist_df['Value']
                hist_df['High'] = hist_df['Value'] * 1.008
                hist_df['Low'] = hist_df['Value'] * 0.992
                fig = go.Figure(data=[go.Candlestick(
                    x=hist_df["Date"],
                    open=hist_df["Open"],
                    high=hist_df["High"],
                    low=hist_df["Low"],
                    close=hist_df["Close"],
                    increasing_line_color='limegreen',
                    decreasing_line_color='red'
                )])
                fig.update_layout(title="Portfolio Value Candlestick", xaxis_title="Date", yaxis_title="Value ($)")
                st.plotly_chart(fig, use_container_width=True)
            else:  # Combined
                # Candlestick
                hist_df['Open'] = hist_df['Value'].shift(1).fillna(hist_df['Value'])
                hist_df['Close'] = hist_df['Value']
                hist_df['High'] = hist_df['Value'] * 1.008
                hist_df['Low'] = hist_df['Value'] * 0.992
                fig_c = go.Figure(data=[go.Candlestick(
                    x=hist_df["Date"], open=hist_df["Open"], high=hist_df["High"],
                    low=hist_df["Low"], close=hist_df["Close"],
                    increasing_line_color='limegreen', decreasing_line_color='red'
                )])
                fig_c.update_layout(title="Candlestick View", xaxis_title="Date", yaxis_title="Value ($)")
                st.plotly_chart(fig_c, use_container_width=True)
                
                # Line below
                st.line_chart(hist_df.set_index("Date")["Value"], use_container_width=True)
        else:
            st.warning("Could not fetch historical data.")

st.caption("💡 Full editing + CSV tools in sidebar")
