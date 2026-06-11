import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import yfinance as yf
from pycoingecko import CoinGeckoAPI
from datetime import datetime, timedelta
import supabase
import json
import os

st.set_page_config(page_title="Portfolio Dashboard", layout="wide")

# Supabase — cached so the client is only created once across reruns
SUPABASE_URL = "https://zbbnslbahdkpfwdbnifp.supabase.co"
SUPABASE_ANON_KEY = "sb_publishable_tH7XB5PpnisfKWYa9RgeiQ_yY0MYXTk"

@st.cache_resource
def get_supabase_client():
    return supabase.create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

supa = get_supabase_client()

# Local backup
DATA_FILE = "portfolio_data.json"

if "user" not in st.session_state:
    st.session_state.user = None
if "login_error" not in st.session_state:
    st.session_state.login_error = None

# ================== LOGIN SCREEN ==================
if st.session_state.user is None:
    st.title("🚀 Portfolio Dashboard")
    col1, col_center, col3 = st.columns([1, 2, 1])
    with col_center:
        st.subheader("Sign in to access your personal portfolio")
        tab1, tab2 = st.tabs(["🔑 Login", "📝 Register"])

        with tab1:
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_pass")

            if st.button("Login", use_container_width=True, key="login_btn"):
                if not email or not password:
                    st.session_state.login_error = "Please enter email and password"
                else:
                    st.session_state.login_error = None
                    try:
                        res = supa.auth.sign_in_with_password({"email": email, "password": password})
                        if res.user:
                            st.session_state.user = res.user
                            st.session_state.login_error = None
                            st.rerun()
                        else:
                            st.session_state.login_error = "Login failed — no user returned. Check credentials."
                    except Exception as e:
                        err = str(e).lower()
                        if "invalid" in err or "credentials" in err or "password" in err:
                            st.session_state.login_error = "Invalid email or password"
                        else:
                            st.session_state.login_error = f"Login error: {e}"

            if st.session_state.login_error:
                st.error(st.session_state.login_error)

        with tab2:
            email = st.text_input("Email", key="reg_email")
            password = st.text_input("Password (min 6 chars)", type="password", key="reg_pass")
            if st.button("Create Account", use_container_width=True):
                try:
                    res = supa.auth.sign_up({"email": email, "password": password})
                    st.success("✅ Account created! Check your email.")
                except Exception as e:
                    st.error(str(e))
    st.stop()

# ================== MAIN DASHBOARD ==================
user = st.session_state.user
st.title(f"🚀 {user.email.split('@')[0]}'s Portfolio")

st.sidebar.success(f"✅ Logged in as {user.email}")

if st.sidebar.button("Logout"):
    supa.auth.sign_out()
    st.session_state.clear()
    st.rerun()

user_id = user.id

def save_to_supabase(holdings_df):
    try:
        supa.table("portfolios").upsert({
            "user_id": user_id,
            "holdings": holdings_df.to_dict('records')
        }).execute()
        return True
    except:
        return False

def load_from_supabase():
    try:
        response = supa.table("portfolios").select("holdings").eq("user_id", user_id).execute()
        if response.data and len(response.data) > 0 and response.data[0].get("holdings"):
            return pd.DataFrame(response.data[0]["holdings"])
    except:
        pass
    return None

# Load holdings (Supabase first, then local file, then default)
if 'holdings' not in st.session_state:
    holdings = load_from_supabase()
    if holdings is not None and len(holdings) > 0:
        st.session_state.holdings = holdings
        st.success("✅ Portfolio loaded from cloud")
    elif os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                st.session_state.holdings = pd.DataFrame(data)
        except:
            pass
    if 'holdings' not in st.session_state or len(st.session_state.holdings) == 0:
        st.session_state.holdings = pd.DataFrame({
            "Asset": ["BTC", "ETH", "AAPL", "TSLA"],
            "Type": ["Crypto", "Crypto", "Equity", "Equity"],
            "Quantity": [0.5, 10.0, 50.0, 20.0],
            "Avg Cost": [45000.0, 2500.0, 150.0, 200.0]
        })
        save_to_supabase(st.session_state.holdings)

def save_holdings():
    save_to_supabase(st.session_state.holdings)
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(st.session_state.holdings.to_dict('records'), f)
    except:
        pass

# ================== EDITING UI ==================
# Add New Holding
st.sidebar.subheader("🚀 Add Holding")
new_asset = st.sidebar.text_input("Asset (e.g. SOL, MSFT)", key="new_asset")
new_type = st.sidebar.selectbox("Type", ["Crypto", "Equity"], key="new_type")
new_qty = st.sidebar.number_input("Quantity", min_value=0.0, value=1.0, step=0.0001, key="new_qty_unique", format="%.6f")
new_cost = st.sidebar.number_input("Avg Cost $", min_value=0.0, value=100.0, step=0.01, key="new_cost_unique", format="%.4f")

if st.sidebar.button("➕ Add Holding", key="add_btn"):
    if new_asset:
        new_row = pd.DataFrame([{"Asset": new_asset.upper(), "Type": new_type, "Quantity": new_qty, "Avg Cost": new_cost}])
        st.session_state.holdings = pd.concat([st.session_state.holdings, new_row], ignore_index=True)
        save_holdings()
        st.success("✅ Added!")

# ================== IMPROVED EDIT HOLDING ==================
st.sidebar.subheader("✏️ Edit Holding")

if not st.session_state.holdings.empty:
    asset_options = [""] + st.session_state.holdings["Asset"].tolist()
    selected_asset = st.sidebar.selectbox("Select Asset to Edit", asset_options, key="edit_asset_select")

    if selected_asset:
        edit_index = st.session_state.holdings[st.session_state.holdings["Asset"] == selected_asset].index[0]
        row = st.session_state.holdings.iloc[edit_index]
        
        edit_asset = st.sidebar.text_input("Asset", value=row["Asset"], key=f"edit_asset_{edit_index}")
        edit_type = st.sidebar.selectbox("Type", ["Crypto", "Equity"], 
                                        index=0 if row["Type"] == "Crypto" else 1, 
                                        key=f"edit_type_{edit_index}")
        edit_qty = st.sidebar.number_input("Quantity", value=float(row["Quantity"]), step=0.000001, 
                                          key=f"edit_qty_{edit_index}", format="%.8f")
        edit_cost = st.sidebar.number_input("Avg Cost $", value=float(row["Avg Cost"]), step=0.01, 
                                           key=f"edit_cost_{edit_index}", format="%.4f")

        if st.sidebar.button("💾 Save Edit", key=f"save_edit_{edit_index}"):
            st.session_state.holdings.at[edit_index, "Asset"] = edit_asset.upper()
            st.session_state.holdings.at[edit_index, "Type"] = edit_type
            st.session_state.holdings.at[edit_index, "Quantity"] = edit_qty
            st.session_state.holdings.at[edit_index, "Avg Cost"] = edit_cost
            save_holdings()
            st.success("✅ Holding updated!")
            st.rerun()

# ================== DELETE HOLDING ==================
st.sidebar.subheader("🗑️ Delete Holding")
if not st.session_state.holdings.empty:
    delete_options = [""] + st.session_state.holdings["Asset"].tolist()
    selected_to_delete = st.sidebar.selectbox("Select Asset to Delete", delete_options, key="delete_select")

    if selected_to_delete and st.sidebar.button("🗑️ Confirm Delete", key="confirm_delete"):
        delete_index = st.session_state.holdings[st.session_state.holdings["Asset"] == selected_to_delete].index[0]
        st.session_state.holdings = st.session_state.holdings.drop(delete_index).reset_index(drop=True)
        save_holdings()
        st.success(f"✅ {selected_to_delete} deleted!")
        st.rerun()

# Clear All Holdings
if st.sidebar.button("🗑️ Clear All Holdings"):
    st.session_state.holdings = pd.DataFrame(columns=["Asset", "Type", "Quantity", "Avg Cost"])
    save_holdings()
    st.success("✅ All holdings cleared!")

# CSV Tools + Refresh
st.sidebar.subheader("💾 CSV Tools")
col1, col2 = st.sidebar.columns(2)
if col1.button("📤 Export CSV"):
    csv = st.session_state.holdings.to_csv(index=False)
    st.download_button("Download portfolio_holdings.csv", csv, "portfolio_holdings.csv", "text/csv")

if uploaded_file := col2.file_uploader("📥 Import CSV", type=["csv"]):
    st.session_state.holdings = pd.read_csv(uploaded_file)
    save_holdings()
    st.success("✅ Portfolio imported!")

if st.sidebar.button("🔄 Refresh Prices"):
    st.cache_data.clear()
    st.success("✅ Prices refreshed!")
    st.rerun()

# Price fetching
cg = CoinGeckoAPI()

# Price fetching
cg = CoinGeckoAPI()

@st.cache_data(ttl=300)
def get_price(symbol, asset_type):
    try:
        if asset_type == "Crypto":
            # Expanded coin map for your portfolio
            coin_map = {
                "BTC": "bitcoin",
                "ETH": "ethereum",
                "SOL": "solana",
                "XRP": "ripple",
                "RENDER": "render-token",
                "GRASS": "grass",
                "FET": "fetch-ai",
                "ASI": "artificial-superintelligence-alliance",
                "TRAC": "origintrail",
                "AKT": "akash-network",
                "TIA": "celestia",
                "HYPE": "hyperliquid",           # adjust if needed
                "TAO": "bittensor",
                "ADA": "cardano",
                "DOGE": "dogecoin",
                "AVAX": "avalanche-2",
                "LINK": "chainlink",
                "DOT": "polkadot",
                "TON": "the-open-network",
                "SHIB": "shiba-inu",
                "HBAR": "hedera-hashgraph",
                "TRX": "tron",
                "LTC": "litecoin",
                "USDT": "tether",
                "USDC": "usd-coin"
            }
            coin_id = coin_map.get(symbol.upper(), symbol.lower())
            data = cg.get_price(ids=coin_id, vs_currencies="usd")
            return data.get(coin_id, {}).get("usd")
        else:
            # Equities via yfinance
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d")
            return hist['Close'].iloc[-1] if not hist.empty else None
    except:
        st.warning(f"Could not fetch {symbol}")
        return None

# Current Portfolio Calculation
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

# ================== PORTFOLIO SUMMARY ==================
st.subheader("📊 Portfolio Summary")

total_cost = sum(
    float(row["Quantity"]) * float(row["Avg Cost"]) 
    for _, row in st.session_state.holdings.iterrows()
)

total_pnl = df_portfolio["Gain/Loss $"].sum() if not df_portfolio.empty else 0.0
overall_return = ((total_value / total_cost) - 1) * 100 if total_cost > 0 else 0
crypto_value = df_portfolio[df_portfolio["Type"] == "Crypto"]["Market Value"].sum() if not df_portfolio.empty else 0.0
crypto_pct = (crypto_value / total_value * 100) if total_value > 0 else 0

col1, col2, col3, col4 = st.columns(4)
col1.metric("💰 Total Value", f"${total_value:,.2f}")
col2.metric("📈 Total P&L", f"${total_pnl:,.2f}", f"{overall_return:.1f}%")
col3.metric("Crypto %", f"{crypto_pct:.1f}%")

if not df_portfolio.empty:
    top_asset = df_portfolio.loc[df_portfolio["Market Value"].idxmax(), "Asset"]
    col4.metric("Top Holding", top_asset)
else:
    col4.metric("Top Holding", "-")

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

# Historical Charts
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
            else:
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
                st.line_chart(hist_df.set_index("Date")["Value"], use_container_width=True)

st.caption("💡 Changes are automatically saved to your account")
