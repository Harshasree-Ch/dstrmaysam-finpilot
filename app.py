from __future__ import annotations

import atexit
import os
import subprocess
import time
from dataclasses import fields
from datetime import datetime
import sys
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
for site_packages in [
    ROOT / ".venv" / "Lib" / "site-packages",
    *sorted((ROOT / ".venv" / "lib").glob("python*/site-packages")),
]:
    if site_packages.exists() and str(site_packages) not in sys.path:
        sys.path.insert(0, str(site_packages))

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from finpilot.core.runtime import add_workspace_venv_site_packages

add_workspace_venv_site_packages(ROOT)

from finpilot.chat import build_chat_store
from finpilot.core.models import InvestmentReport
from finpilot.core.settings import Settings


REQUIRED_BACKEND_VERSION = 3


st.set_page_config(page_title="FinPilot", page_icon=":chart_with_upwards_trend:", layout="wide")


def is_local_api_url(api_url: str) -> bool:
    parsed = urlparse(api_url)
    return parsed.hostname in {"localhost", "127.0.0.1", "::1"}


def api_health(api_url: str, timeout: float = 1.0) -> dict | None:
    try:
        response = requests.get(f"{api_url.rstrip('/')}/health", timeout=timeout)
        if not response.ok:
            return None
        return response.json()
    except Exception:
        return None


def api_health_ok(api_url: str, timeout: float = 1.0) -> bool:
    body = api_health(api_url, timeout=timeout)
    return bool(body and body.get("ok") is True)


def backend_is_current(api_url: str, timeout: float = 1.0) -> bool:
    body = api_health(api_url, timeout=timeout)
    return bool(body and body.get("ok") is True and body.get("backend_version") == REQUIRED_BACKEND_VERSION)


def backend_python_executable() -> str:
    windows_venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    posix_venv_python = ROOT / ".venv" / "bin" / "python"
    if windows_venv_python.exists():
        return str(windows_venv_python)
    if posix_venv_python.exists():
        return str(posix_venv_python)
    return sys.executable


@st.cache_resource(show_spinner=False)
def ensure_local_fastapi_backend(api_url: str, required_backend_version: int) -> dict:
    if not is_local_api_url(api_url):
        return {"api_url": api_url, "managed": False, "status": "external"}
    if backend_is_current(api_url):
        return {"api_url": api_url, "managed": False, "status": "already_running"}

    parsed = urlparse(api_url)
    host = "127.0.0.1"
    port = parsed.port or 8600
    start_port = port if not api_health_ok(api_url) else port + 1
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{SRC}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
    log_path = ROOT / ".finpilot-api-startup.log"
    selected_api_url = api_url
    process = None
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform.startswith("win") else 0
    log_file = log_path.open("a", encoding="utf-8")

    for candidate_port in range(start_port, start_port + 20):
        selected_api_url = f"{parsed.scheme or 'http'}://{host}:{candidate_port}"
        if api_health_ok(selected_api_url):
            continue
        command = [
            backend_python_executable(),
            "-m",
            "uvicorn",
            "finpilot.api:app",
            "--app-dir",
            str(SRC),
            "--host",
            host,
            "--port",
            str(candidate_port),
        ]
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )
        break

    if process is None:
        log_file.close()
        return {"api_url": api_url, "managed": False, "status": "no_free_port", "log_path": str(log_path)}

    atexit.register(log_file.close)
    atexit.register(lambda: process.poll() is None and process.terminate())

    for _ in range(60):
        if backend_is_current(selected_api_url, timeout=0.5):
            return {
                "api_url": selected_api_url,
                "managed": True,
                "status": "started",
                "pid": process.pid,
                "log_path": str(log_path),
            }
        if process.poll() is not None:
            log_file.flush()
            return {
                "api_url": selected_api_url,
                "managed": True,
                "status": "failed",
                "pid": process.pid,
                "log_path": str(log_path),
            }
        time.sleep(0.25)
    log_file.flush()
    return {"api_url": selected_api_url, "managed": True, "status": "timeout", "pid": process.pid, "log_path": str(log_path)}


base_settings = Settings.from_env()
if "groww_api_key" not in st.session_state:
    st.session_state.groww_api_key = base_settings.groww_api_key or ""
if "groww_secret_key" not in st.session_state:
    st.session_state.groww_secret_key = base_settings.groww_secret_key or ""
if "alpaca_api_key" not in st.session_state:
    st.session_state.alpaca_api_key = base_settings.alpaca_api_key or ""
if "alpaca_secret_key" not in st.session_state:
    st.session_state.alpaca_secret_key = base_settings.alpaca_secret_key or ""
if "alpaca_paper_base_url" not in st.session_state:
    st.session_state.alpaca_paper_base_url = base_settings.alpaca_paper_base_url

settings_payload = {
    "data_mode": "live",
    "aws_region": base_settings.aws_region,
    "bedrock_model_id": base_settings.bedrock_model_id,
    "use_bedrock": base_settings.use_bedrock,
    "opensearch_endpoint": base_settings.opensearch_endpoint,
    "groww_api_key": st.session_state.groww_api_key or None,
    "groww_secret_key": st.session_state.groww_secret_key or None,
    "alpaca_api_key": st.session_state.alpaca_api_key or None,
    "alpaca_secret_key": st.session_state.alpaca_secret_key or None,
    "alpaca_paper_base_url": st.session_state.alpaca_paper_base_url,
    "finnhub_api_key": base_settings.finnhub_api_key,
    "rds_database_url": base_settings.rds_database_url,
    "mcp_tool_url": base_settings.mcp_tool_url,
    "finpilot_api_url": getattr(base_settings, "finpilot_api_url", os.getenv("FINPILOT_API_URL") or None),
}
settings_fields = {field.name for field in fields(Settings)}
settings = Settings(**{key: value for key, value in settings_payload.items() if key in settings_fields})
requested_finpilot_api_url = settings_payload["finpilot_api_url"] or "http://localhost:8600"
backend_status = ensure_local_fastapi_backend(requested_finpilot_api_url, REQUIRED_BACKEND_VERSION)
finpilot_api_url = backend_status.get("api_url", requested_finpilot_api_url)

st.title("FinPilot")
st.caption("AI-powered market research and guided investing copilot")
if backend_status["status"] in {"failed", "timeout"}:
    log_hint = f" Startup log: `{backend_status.get('log_path')}`." if backend_status.get("log_path") else ""
    st.error(
        "FinPilot FastAPI backend could not be started automatically. "
        "Stop Streamlit and run `streamlit run app.py` again."
        + log_hint
    )

with st.sidebar:
    st.header("Research Setup")
    selected_market = st.selectbox("Market", ["India", "US"])
    search_query = st.text_input("Ticker or company name", value="").strip()
    horizon = st.selectbox("Investment horizon", ["3 months", "6 months", "12 months", "3 years"])
    risk_profile = "Balanced"
    run = st.button("Run Research", type="primary", use_container_width=True)

if "chat_session_id" not in st.session_state:
    st.session_state.chat_session_id = str(uuid4())
if "chat_memory_messages" not in st.session_state:
    st.session_state.chat_memory_messages = {}
chat_store = build_chat_store(settings.rds_database_url, st.session_state.chat_memory_messages)

tabs = st.tabs(["Research", "Evidence", "Invest", "Portfolio", "Market Today", "Chat"])


def format_money(value: float | None, currency: str) -> str:
    if value is None:
        return "N/A"
    symbol = "$" if currency == "USD" else "INR "
    return f"{symbol}{value:,.2f}" if currency == "USD" else f"{symbol}{value:,.2f}"


def format_percent(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2%}"


def first_value(data: dict, *keys: str) -> object:
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return value
    return None


def backend_credentials_payload() -> dict:
    return {
        "groww_api_key": st.session_state.groww_api_key or None,
        "groww_secret_key": st.session_state.groww_secret_key or None,
        "alpaca_api_key": st.session_state.alpaca_api_key or None,
        "alpaca_secret_key": st.session_state.alpaca_secret_key or None,
        "alpaca_paper_base_url": st.session_state.alpaca_paper_base_url,
    }


def raise_for_backend_error(response: requests.Response) -> None:
    if response.ok:
        return
    try:
        body = response.json()
    except ValueError:
        response.raise_for_status()
    detail = body.get("detail") or body.get("error") or response.text
    raise RuntimeError(str(detail))


def flatten_groww_orders(raw_orders: object) -> list[dict]:
    if isinstance(raw_orders, list):
        return raw_orders
    if not isinstance(raw_orders, dict):
        return []
    for key in ("orders", "order_list", "orderList", "data", "results"):
        value = raw_orders.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = flatten_groww_orders(value)
            if nested:
                return nested
    return []


def normalize_order_rows(broker: str, raw_orders: object) -> list[dict]:
    orders = flatten_groww_orders(raw_orders) if broker == "Groww" else raw_orders
    if not isinstance(orders, list):
        return []

    rows = []
    for order in orders:
        if not isinstance(order, dict):
            continue
        symbol = first_value(order, "symbol", "trading_symbol", "tradingSymbol", "ticker")
        side = first_value(order, "side", "transaction_type", "transactionType")
        quantity = first_value(order, "qty", "quantity", "filled_qty", "filledQuantity")
        order_type = first_value(order, "type", "order_type", "orderType")
        status = first_value(order, "status", "order_status", "orderStatus")
        submitted_at = first_value(order, "submitted_at", "created_at", "createdAt", "order_timestamp", "orderTimestamp")
        order_id = first_value(order, "id", "order_id", "orderId", "groww_order_id", "growwOrderId")
        price = first_value(order, "limit_price", "price", "average_price", "averagePrice", "filled_avg_price", "filledAvgPrice")
        rows.append(
            {
                "Broker": broker,
                "Order ID": order_id or "N/A",
                "Ticker": symbol or "N/A",
                "Side": str(side or "N/A").lower(),
                "Quantity": quantity or "N/A",
                "Order Type": str(order_type or "N/A").lower(),
                "Price": price or "N/A",
                "Status": status or "N/A",
                "Submitted": submitted_at or "N/A",
            }
        )
    return rows


def render_portfolio_tab() -> None:
    with tabs[3]:
        st.subheader("Portfolio")
        controls = st.columns([2, 1, 4])
        broker = controls[0].selectbox("Account", ["Groww", "Alpaca paper"], key="portfolio_broker")
        refresh_clicked = controls[1].button("Refresh", use_container_width=True, key="portfolio_refresh")
        cache_key = f"portfolio_orders_{broker.lower().replace(' ', '_')}"

        has_groww_config = bool(settings.groww_api_key and settings.groww_secret_key)
        has_alpaca_config = bool(settings.alpaca_api_key and settings.alpaca_secret_key)
        if broker == "Groww" and not has_groww_config:
            st.warning("Configure Groww API key and secret in the Invest tab before viewing Groww orders.")
            return
        if broker == "Alpaca paper" and not has_alpaca_config:
            st.warning("Configure Alpaca paper trading credentials in the Invest tab before viewing Alpaca orders.")
            return

        if refresh_clicked or cache_key not in st.session_state:
            with st.spinner(f"Fetching {broker} orders..."):
                try:
                    response = requests.post(
                        f"{finpilot_api_url.rstrip('/')}/portfolio/orders",
                        json={"broker": broker, "credentials": backend_credentials_payload()},
                        timeout=60,
                    )
                    raise_for_backend_error(response)
                    raw_orders = response.json()["data"]
                    st.session_state[cache_key] = {
                        "orders": normalize_order_rows(broker, raw_orders),
                        "raw": raw_orders,
                        "error": None,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                except Exception as exc:
                    st.session_state[cache_key] = {
                        "orders": [],
                        "raw": None,
                        "error": str(exc),
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }

        portfolio_data = st.session_state[cache_key]
        st.caption(f"Last refreshed: {portfolio_data['timestamp']}")
        if portfolio_data["error"]:
            st.error(f"Could not fetch {broker} orders: {portfolio_data['error']}")
            return
        if not portfolio_data["orders"]:
            st.info(f"No orders returned by {broker}.")
            with st.expander("Raw broker response", expanded=False):
                st.json(portfolio_data["raw"])
            return
        st.dataframe(pd.DataFrame(portfolio_data["orders"]), use_container_width=True, hide_index=True)
        with st.expander("Raw broker response", expanded=False):
            st.json(portfolio_data["raw"])


def render_market_today_tab() -> None:
    with tabs[4]:
        st.subheader("Market Today")
        controls = st.columns([2, 1, 4])
        market_today = controls[0].selectbox("Market", ["India", "US"], key="market_today_market")
        refresh_clicked = controls[1].button("Refresh", use_container_width=True, key="market_today_refresh")
        cache_key = f"market_today_{market_today.lower()}"

        if refresh_clicked or cache_key not in st.session_state:
            with st.spinner(f"Fetching live top 10 stocks for {market_today}..."):
                try:
                    response = requests.post(
                        f"{finpilot_api_url.rstrip('/')}/market/today",
                        json={"market": market_today, "limit": 10, "credentials": backend_credentials_payload()},
                        timeout=60,
                    )
                    raise_for_backend_error(response)
                    body = response.json()
                    st.session_state[cache_key] = {"data": body["data"], "error": None}
                except Exception as exc:
                    st.session_state[cache_key] = {"data": None, "error": str(exc)}

        cached_market = st.session_state[cache_key]
        if "data" not in cached_market and "rows" in cached_market:
            cached_market = {"data": cached_market, "error": None}
        if cached_market.get("error"):
            st.error(f"Market Today data could not be fetched: {cached_market['error']}")
            return

        market_data = cached_market["data"]
        timestamp = market_data.get("timestamp")
        if timestamp:
            refreshed_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S")
            st.caption(f"Last refreshed: {refreshed_at}")

        rows = []
        for item in market_data["rows"]:
            currency = item.get("currency") or ("INR" if market_today == "India" else "USD")
            rows.append(
                {
                    "Ticker": item["ticker"],
                    "Company": item["company"],
                    "Price": format_money(item.get("price"), currency),
                    "Previous Close": format_money(item.get("previous_close"), currency),
                    "Change %": format_percent(item.get("change_percent")),
                    "Currency": currency,
                    "Market Cap": item.get("market_cap") or "N/A",
                    "Sector": item.get("sector") or "Unknown",
                    "Industry": item.get("industry") or "Unknown",
                    "Exchange": item.get("exchange") or "Unknown",
                    "Source": item.get("source") or "Unknown",
                    "Status": item.get("status") or "Live",
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_chat_tab() -> None:
    with tabs[5]:
        st.subheader("Chat")
        st.caption("Ask about portfolio orders, live stock prices, or comparisons between companies.")
        storage_label = "AWS RDS" if settings.rds_database_url else "session memory"
        st.caption(f"Chat storage: {storage_label}")

        if st.button("Clear Chat", key="clear_finance_chat"):
            try:
                chat_store.clear_messages(st.session_state.chat_session_id)
                st.rerun()
            except Exception as exc:
                st.error(f"Could not clear chat: {exc}")

        try:
            messages = chat_store.load_messages(st.session_state.chat_session_id)
        except Exception as exc:
            st.error(f"Could not load chat history: {exc}")
            return

        if not messages:
            st.info("Try asking: 'What is the current price of SBI?', 'Compare TCS and Infosys', or 'Show my Groww orders.'")

        for message in messages:
            with st.chat_message(message.role):
                st.markdown(message.content)

        prompt = st.chat_input("Ask FinPilot", key="finance_chat_input")
        if prompt:
            try:
                chat_store.append_message(st.session_state.chat_session_id, "user", prompt)
                response = requests.post(
                    f"{finpilot_api_url.rstrip('/')}/chat/answer",
                    json={
                        "question": prompt,
                        "market": selected_market,
                        "credentials": backend_credentials_payload(),
                    },
                    timeout=60,
                )
                raise_for_backend_error(response)
                answer = response.json()["answer"]
                chat_store.append_message(st.session_state.chat_session_id, "assistant", answer)
                st.rerun()
            except Exception as exc:
                st.error(f"Could not answer chat question: {exc}")


render_portfolio_tab()
render_market_today_tab()
render_chat_tab()

if not search_query:
    with tabs[0]:
        st.info("Select a market and enter a ticker or company name to run research.")
    with tabs[2]:
        st.info("Select a market and enter a ticker or company name in Research Setup to preview an investment order.")
    st.stop()

report_request = {
    "query": search_query,
    "market": selected_market,
    "horizon": horizon,
    "risk_profile": risk_profile,
    "data_mode": settings.data_mode,
}

if run or "research_payload" not in st.session_state or st.session_state.get("report_request") != report_request:
    with st.spinner("Running backend research workflow..."):
        try:
            response = requests.post(
                f"{finpilot_api_url.rstrip('/')}/research/run",
                json={**report_request, "credentials": backend_credentials_payload()},
                timeout=120,
            )
            raise_for_backend_error(response)
            payload = response.json()
            if not payload.get("ok"):
                raise RuntimeError(payload.get("error") or "FinPilot backend research failed.")
            st.session_state.research_payload = payload
            st.session_state.report_error = None
            st.session_state.report_request = report_request
        except Exception as exc:
            st.session_state.research_payload = None
            st.session_state.report_error = str(exc)
            st.session_state.report_request = report_request

research_payload = st.session_state.get("research_payload")
if not research_payload:
    st.error(st.session_state.get("report_error") or "Realtime data could not be fetched for this ticker.")
    st.stop()

resolved_symbol = research_payload["resolved_symbol"]
report = InvestmentReport.model_validate(research_payload["report"])
snapshot = research_payload["snapshot"]
history = research_payload["history"]
profile = research_payload["profile"]
earnings = research_payload["earnings"]
news_items = research_payload["news_items"]

with tabs[0]:
    st.subheader(f"{profile['name']} ({report.ticker}) Realtime Research")
    if resolved_symbol["query"].strip().upper() != report.ticker:
        st.caption(
            f"Resolved '{resolved_symbol['query']}' to {report.ticker}"
            f" ({resolved_symbol['name']})"
        )
    st.caption(
        f"{history['horizon']} price window: {history['start_date']} to {history['end_date']} | "
        f"Source: {history['source']} | Exchange: {history['exchange']}"
    )

    price = snapshot["price"]
    daily_delta = None
    if snapshot["change"] is not None and snapshot["change_percent"] is not None:
        daily_delta = f"{snapshot['change']:,.2f} ({snapshot['change_percent']:.2%}) today"
    period_delta = f"{history['change']:,.2f} ({history['change_percent']:.2%})"

    metric_cols = st.columns(4)
    metric_cols[0].metric(
        "Current Price",
        "N/A" if price is None else f"{snapshot['currency']} {price:,.2f}",
        delta=daily_delta,
    )
    metric_cols[1].metric(f"{horizon} Change", period_delta)
    metric_cols[2].metric("Period Low", f"{history['currency']} {history['period_low']:,.2f}")
    metric_cols[3].metric("Period High", f"{history['currency']} {history['period_high']:,.2f}")

    history_df = pd.DataFrame(history["points"])
    fig = px.line(history_df, x="date", y="close", title=f"{report.ticker} Price Trend Over {horizon}")
    fig.update_layout(xaxis_title=None, yaxis_title=f"Close ({history['currency']})", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    overview_col, signal_col = st.columns([2, 1])
    with overview_col:
        st.markdown("#### Company Overview")
        detail_cols = st.columns(3)
        with detail_cols[0]:
            st.caption("Sector")
            st.markdown(f"**{profile['sector']}**")
        with detail_cols[1]:
            st.caption("Industry")
            st.markdown(f"**{profile['industry']}**")
        with detail_cols[2]:
            st.caption("Employees")
            st.markdown(f"**{profile.get('employees') or 'N/A'}**")
        if profile.get("provider_status"):
            st.info(profile["provider_status"])
        st.write(profile["business_model"])

        st.markdown("#### Fundamentals Snapshot")
        metrics = profile.get("metrics", {})
        fundamental_rows = [
            [("Mkt Cap", "market_cap", metrics.get("market_cap", "N/A")), ("ROE", "roe", metrics.get("roe", "N/A"))],
            [("P/E Ratio (TTM)", "pe_ratio_ttm", metrics.get("pe_ratio_ttm", "N/A")), ("EPS (TTM)", "eps_ttm", metrics.get("eps_ttm", "N/A"))],
            [("P/B Ratio", "pb_ratio", metrics.get("pb_ratio", "N/A")), ("Div Yield", "dividend_yield", metrics.get("dividend_yield", "N/A"))],
            [("Industry P/E", "industry_pe", metrics.get("industry_pe", "N/A")), ("Book Value", "book_value", metrics.get("book_value", "N/A"))],
            [("Debt to Equity", "debt_to_equity", metrics.get("debt_to_equity", "N/A")), ("Face Value", "face_value", metrics.get("face_value", "N/A"))],
        ]
        for row in fundamental_rows:
            row_cols = st.columns(2)
            for col, (label, metric_key, value) in zip(row_cols, row):
                with col:
                    st.caption(label)
                    st.markdown(f"**{value}**")

        st.markdown("#### Recent News")
        if news_items:
            for item in news_items[:5]:
                title = item["title"]
                source_line = item.get("source") or "Realtime provider"
                if item.get("published_at"):
                    source_line = f"{source_line} - {item['published_at']}"
                st.caption(source_line)
                if item.get("url"):
                    st.markdown(f"[{title}]({item['url']})")
                else:
                    st.markdown(title)
                if item.get("summary") and item["summary"] != title:
                    st.write(item["summary"])
                st.divider()
        else:
            st.write("No recent news returned by the realtime provider.")

    with signal_col:
        st.markdown("#### Research Signal")
        st.metric("Recommendation", report.recommendation)
        st.metric("Confidence", f"{report.confidence_score:.0%}")
        st.metric("Suggested Allocation", f"{report.suggested_allocation:.1%}")
        st.write(report.investment_summary)

with tabs[1]:
    st.subheader("Supporting Evidence")
    evidence_df = pd.DataFrame([e.model_dump() for e in report.evidence])
    st.dataframe(evidence_df, use_container_width=True, hide_index=True)

    st.subheader("Agent Findings")
    for finding in report.agent_findings:
        with st.expander(f"{finding.agent_name}: {finding.headline}", expanded=False):
            st.write(finding.summary)
            if finding.evidence:
                st.write("Evidence")
                for item in finding.evidence:
                    st.write(f"- {item.title} ({item.source})")

with tabs[2]:
    st.subheader("Invest")
    if selected_market == "India":
        st.warning("Orders are sent to Groww only when Groww account details are configured and the order is confirmed.")
        has_groww_config = bool(settings.groww_api_key and settings.groww_secret_key)
        with st.expander("Groww Account", expanded=not has_groww_config):
            if has_groww_config:
                st.success("Groww account details are configured for this session.")
            else:
                st.info("Generate a Groww API key and secret, then paste both here before placing an order.")
            st.caption("Groww also requires the public IP of this Streamlit server to be registered for your API key.")
            st.markdown("[Open Groww API](https://groww.in/trade-api)")
            with st.form("groww_credentials_form"):
                groww_api_key = st.text_input(
                    "Groww API key",
                    value=st.session_state.groww_api_key,
                    type="password",
                )
                groww_secret_key = st.text_input(
                    "Groww secret key",
                    value=st.session_state.groww_secret_key,
                    type="password",
                )
                save_groww = st.form_submit_button("Save Groww Configuration", type="primary")
            if save_groww:
                st.session_state.groww_api_key = groww_api_key.strip()
                st.session_state.groww_secret_key = groww_secret_key.strip()
                st.rerun()
    else:
        st.warning("US orders are sent to Alpaca paper trading only after credentials are configured and the order is confirmed.")
        has_alpaca_config = bool(settings.alpaca_api_key and settings.alpaca_secret_key)
        with st.expander("Alpaca Paper Trading Account", expanded=not has_alpaca_config):
            if has_alpaca_config:
                st.success("Alpaca paper trading credentials are configured for this session.")
            else:
                st.info("Create or use an Alpaca paper trading account, then paste the API key and secret here.")
            st.markdown("[Open Alpaca Paper Trading](https://app.alpaca.markets/paper/dashboard/overview)")
            with st.form("alpaca_credentials_form"):
                alpaca_api_key = st.text_input(
                    "Alpaca API key",
                    value=st.session_state.alpaca_api_key,
                    type="password",
                )
                alpaca_secret_key = st.text_input(
                    "Alpaca secret key",
                    value=st.session_state.alpaca_secret_key,
                    type="password",
                )
                alpaca_paper_base_url = st.text_input(
                    "Alpaca paper base URL",
                    value=st.session_state.alpaca_paper_base_url,
                )
                save_alpaca = st.form_submit_button("Save Alpaca Configuration", type="primary")
            if save_alpaca:
                st.session_state.alpaca_api_key = alpaca_api_key.strip()
                st.session_state.alpaca_secret_key = alpaca_secret_key.strip()
                st.session_state.alpaca_paper_base_url = alpaca_paper_base_url.strip() or Settings.alpaca_paper_base_url
                st.rerun()

    invest_snapshot = None
    try:
        invest_ticker = report.ticker
        response = requests.post(
            f"{finpilot_api_url.rstrip('/')}/market/snapshot",
            json={"ticker": invest_ticker, "credentials": backend_credentials_payload()},
            timeout=60,
        )
        raise_for_backend_error(response)
        invest_snapshot = response.json()["data"]
    except Exception as exc:
        st.error(f"Investment data could not be fetched: {exc}")
        invest_ticker = report.ticker

    current_price = invest_snapshot["price"] if invest_snapshot else None
    currency = invest_snapshot["currency"] if invest_snapshot else ("INR" if selected_market == "India" else "USD")
    order_cols = st.columns(3)
    side = order_cols[0].selectbox("Side", ["buy", "sell"])
    order_type = order_cols[1].selectbox("Order type", ["market", "limit"])
    quantity = order_cols[2].number_input("Quantity", min_value=1, value=1, step=1)
    limit_price = None
    if order_type == "limit":
        limit_price = st.number_input(f"Limit price ({currency})", min_value=0.0, value=0.0, step=1.0)
    estimated_cost = current_price * quantity if current_price is not None else None

    price_cols = st.columns(3)
    price_cols[0].metric("Selected Stock", invest_ticker)
    price_cols[1].metric("Current Price", "N/A" if current_price is None else f"{currency} {current_price:,.2f}")
    price_cols[2].metric("Estimated Cost", "N/A" if estimated_cost is None else f"{currency} {estimated_cost:,.2f}")

    broker_name = "Groww" if selected_market == "India" else "Alpaca paper trading"
    confirm = st.checkbox(f"I confirm I want to place this order through {broker_name}.")
    if st.button("Place Order", disabled=not confirm or current_price is None):
        try:
            response = requests.post(
                f"{finpilot_api_url.rstrip('/')}/trade/execute",
                json={
                    "ticker": invest_ticker,
                    "market": selected_market,
                    "side": side,
                    "quantity": int(quantity),
                    "order_type": order_type,
                    "limit_price": limit_price if order_type == "limit" else None,
                    "user_confirmed": confirm,
                    "credentials": backend_credentials_payload(),
                },
                timeout=60,
            )
            raise_for_backend_error(response)
            result = response.json()["data"]
            if result["accepted"]:
                st.success(result["message"])
                if result.get("order_id"):
                    st.session_state.last_order = {
                        "broker": broker_name,
                        "market": selected_market,
                        "ticker": invest_ticker,
                        "order_id": result["order_id"],
                    }
            else:
                st.error(result["message"])
            st.json(result)
        except Exception as exc:
            st.error(f"Could not place order: {exc}")

    last_order = st.session_state.get("last_order")
    if selected_market == "India" and last_order and last_order.get("broker") == "Groww":
        st.markdown("#### Last Order")
        st.caption(f"{last_order['ticker']} | Groww order id: {last_order['order_id']}")
        if st.button("Check Last Order Status"):
            try:
                response = requests.post(
                    f"{finpilot_api_url.rstrip('/')}/trade/groww-order-status",
                    json={"order_id": last_order["order_id"], "credentials": backend_credentials_payload()},
                    timeout=60,
                )
                raise_for_backend_error(response)
                order_status = response.json()["data"]
                st.success("Groww returned the latest order status.")
                st.json(order_status)
            except Exception as exc:
                st.error(f"Could not fetch Groww order status: {exc}")

