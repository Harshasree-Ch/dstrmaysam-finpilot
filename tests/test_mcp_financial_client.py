from finpilot.core.settings import Settings
from finpilot_mcp.client import McpFinancialToolsClient


class FakeEventStream:
    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def raise_for_status(self):
        return None

    def iter_lines(self, decode_unicode=True):
        return iter(self.lines)


class FakePostResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError("http error")
        return None


class FakeSession:
    def __init__(self, calls, lines, post_statuses=None):
        self.calls = calls
        self.lines = lines
        self.post_statuses = list(post_statuses or [])

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def get(self, url, headers, stream, timeout):
        self.calls.append({"method": "GET", "url": url, "headers": headers, "stream": stream, "timeout": timeout})
        return FakeEventStream(self.lines)

    def post(self, url, json, timeout):
        self.calls.append({"method": "POST", "url": url, "json": json, "timeout": timeout})
        status_code = self.post_statuses.pop(0) if self.post_statuses else 200
        return FakePostResponse(status_code=status_code)


class FailingYahoo:
    def resolve_symbol(self, query, market=None):
        raise RuntimeError("offline")

    def company_profile(self, ticker):
        raise RuntimeError("offline")

    def financials(self, ticker):
        raise RuntimeError("offline")

    def price_history(self, ticker, horizon):
        raise RuntimeError("offline")

    def latest_news(self, ticker):
        raise RuntimeError("offline")

    def latest_earnings(self, ticker):
        raise RuntimeError("offline")


def test_mcp_client_calls_remote_sse_tool(monkeypatch):
    calls = []
    lines = [
        "event: endpoint",
        "data: /messages/?session_id=abc",
        "",
        'event: message',
        'data: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}',
        "",
        'event: message',
        'data: {"jsonrpc":"2.0","id":2,"result":{"structuredContent":{"quote":{"ticker":"AAPL","price":200.0,"previous_close":190.0,"currency":"USD"}}}}',
        "",
    ]

    monkeypatch.setattr("finpilot_mcp.client.requests.Session", lambda: FakeSession(calls, lines))

    client = McpFinancialToolsClient(Settings(mcp_tool_url="http://localhost:8000/sse"))
    client._yahoo = FailingYahoo()
    snapshot = client.market_snapshot("AAPL")

    assert snapshot["price"] == 200.0
    assert calls[0]["method"] == "GET"
    assert calls[0]["url"] == "http://localhost:8000/sse"
    assert calls[1]["json"]["method"] == "initialize"
    assert calls[2]["json"]["method"] == "notifications/initialized"
    assert calls[3]["url"] == "http://localhost:8000/messages?session_id=abc"
    assert calls[3]["json"] == {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "get_stock_quote", "arguments": {"ticker_or_company": "AAPL"}},
    }


def test_mcp_client_normalizes_messages_url_without_trailing_slash(monkeypatch):
    calls = []
    lines = [
        "event: endpoint",
        "data: /messages/?session_id=abc",
        "",
        'event: message',
        'data: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}',
        "",
        'event: message',
        'data: {"jsonrpc":"2.0","id":2,"result":{"structuredContent":{"quote":{"ticker":"WMT","company_name":"Walmart Inc."}}}}',
        "",
    ]

    monkeypatch.setattr(
        "finpilot_mcp.client.requests.Session",
        lambda: FakeSession(calls, lines),
    )

    client = McpFinancialToolsClient(Settings(mcp_tool_url="http://localhost:8000/sse"))
    client._yahoo = FailingYahoo()
    result = client.resolve_symbol("walmart", market="US")

    assert result["ticker"] == "WMT"
    assert calls[1]["url"] == "http://localhost:8000/messages?session_id=abc"


def test_mcp_client_search_documents_uses_mcp_rag_tool(monkeypatch):
    calls = []

    client = McpFinancialToolsClient(Settings(mcp_tool_url="http://localhost:8000/sse"))
    client._yahoo = FailingYahoo()
    monkeypatch.setattr(
        client,
        "_call",
        lambda tool, payload: calls.append({"tool": tool, "payload": payload})
        or {
            "ok": True,
            "evidence": [
                {
                    "source": "s3://dstrmaysam-finpilot/documents/TCS.NS/report.pdf",
                    "title": "report.pdf",
                    "excerpt": "Reliance research summary",
                    "url": "s3://dstrmaysam-finpilot/documents/TCS.NS/report.pdf",
                    "reliability": "high",
                }
            ],
        },
    )
    documents = client.search_documents("RELIANCE.NS earnings management guidance")

    assert documents[0]["excerpt"] == "Reliance research summary"
    assert calls == [
        {
            "tool": "finpilot_rag_search_documents",
            "payload": {"query": "RELIANCE.NS earnings management guidance", "limit": 5},
        }
    ]


def test_mcp_client_search_documents_falls_back_to_s3_methodology_pdf(monkeypatch):
    client = McpFinancialToolsClient(Settings(mcp_tool_url="http://localhost:8000/sse", rag_s3_bucket="dstrmaysam-finpilot"))
    monkeypatch.setattr(client, "_call", lambda tool, payload: {"ok": True, "evidence": []})
    monkeypatch.setattr(
        client,
        "_read_s3_pdf_text",
        lambda key: (
            "Recommendation Mapping: scores from 55 to 74 map to Hold. "
            "Watch is used when the score is lower but evidence is not negative. "
            "Confidence Calculation uses data coverage, source agreement, signal strength, and penalties."
        ),
    )

    documents = client.search_documents("how are calculating score to predict recommendation signal")

    assert documents == [
        {
            "source": "s3://dstrmaysam-finpilot/finpilot_scoring_and_recommendation_rules.pdf",
            "title": "FinPilot Scoring and Recommendation Rules",
            "excerpt": (
                "Recommendation Mapping: scores from 55 to 74 map to Hold. Watch is used when the score is lower "
                "but evidence is not negative. Confidence Calculation uses data coverage, source agreement, signal "
                "strength, and penalties."
            ),
            "url": "s3://dstrmaysam-finpilot/finpilot_scoring_and_recommendation_rules.pdf",
            "reliability": "high",
        }
    ]


def test_mcp_client_price_history_includes_ui_fields(monkeypatch):
    calls = []
    lines = [
        "event: endpoint",
        "data: /messages/?session_id=abc",
        "",
        'event: message',
        'data: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}',
        "",
        'event: message',
        'data: {"jsonrpc":"2.0","id":2,"result":{"structuredContent":{"quote":{"ticker":"AAPL","price":200.0,"previous_close":190.0,"currency":"USD"}}}}',
        "",
    ]

    monkeypatch.setattr("finpilot_mcp.client.requests.Session", lambda: FakeSession(calls, lines))

    client = McpFinancialToolsClient(Settings(mcp_tool_url="http://localhost:8000/sse"))
    client._yahoo = FailingYahoo()
    history = client.price_history("AAPL", "3 months")

    assert history["exchange"] == "NASDAQ/NYSE"
    assert history["source"] == "MCP-TOOLS get_stock_quote latest and previous close"
    assert history["points"] == [
        {"date": history["start_date"], "close": 190.0},
        {"date": history["end_date"], "close": 200.0},
    ]


def test_mcp_client_uses_yahoo_price_history_when_available():
    class FakeYahoo(FailingYahoo):
        def price_history(self, ticker, horizon):
            return {
                "ticker": ticker,
                "horizon": horizon,
                "currency": "USD",
                "exchange": "NASDAQ",
                "start_date": "2026-04-01",
                "end_date": "2026-07-02",
                "start_price": 100.0,
                "end_price": 125.0,
                "change": 25.0,
                "change_percent": 0.25,
                "period_low": 95.0,
                "period_high": 130.0,
                "points": [{"date": "2026-04-01", "close": 100.0}, {"date": "2026-07-02", "close": 125.0}],
                "source": "Yahoo Finance",
            }

    client = McpFinancialToolsClient(Settings(mcp_tool_url="http://localhost:8000/sse"))
    client._yahoo = FakeYahoo()

    history = client.price_history("AAPL", "3 months")

    assert len(history["points"]) == 2
    assert history["exchange"] == "NASDAQ"
    assert history["source"] == "Yahoo Finance (MCP-TOOLS quote endpoint has no candles)"


def test_mcp_client_preserves_indian_suffix_and_yahoo_fundamentals(monkeypatch):
    class FakeYahoo(FailingYahoo):
        def company_profile(self, ticker):
            assert ticker == "SBIN.NS"
            return {
                "ticker": "SBIN.NS",
                "name": "State Bank of India",
                "sector": "Financial Services",
                "industry": "Banks - Regional",
                "market_cap": "Large Cap",
                "market_cap_display": "7.20T",
                "business_model": "State Bank of India is a public sector bank.",
                "competitors": ["HDFC Bank"],
                "metrics": {"market_cap": "7.20T", "roe": "17.00%", "dividend_yield": "1.60%"},
                "financials": {"revenue_growth": 0.08, "gross_margin": 0.0, "net_margin": 0.18},
                "data_sources": ["Yahoo Finance"],
            }

    calls = []
    lines = [
        "event: endpoint",
        "data: /messages/?session_id=abc",
        "",
        'event: message',
        'data: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05"}}',
        "",
        'event: message',
        'data: {"jsonrpc":"2.0","id":2,"result":{"structuredContent":{"quote":{"ticker":"SBIN","company_name":null,"price":null,"previous_close":null}}}}',
        "",
    ]

    monkeypatch.setattr("finpilot_mcp.client.requests.Session", lambda: FakeSession(calls, lines))

    client = McpFinancialToolsClient(Settings(mcp_tool_url="http://localhost:8000/sse"))
    client._yahoo = FakeYahoo()
    profile = client.company_profile("SBIN.NS")

    assert profile["ticker"] == "SBIN.NS"
    assert profile["sector"] == "Financial Services"
    assert profile["metrics"]["market_cap"] == "7.20T"
    assert profile["metrics"]["dividend_yield"] == "1.60%"
    assert profile["provider_status"].startswith("Fundamentals")


def test_mcp_client_normalizes_base_url_to_sse_endpoint():
    client = McpFinancialToolsClient(Settings(mcp_tool_url="http://18.134.14.0:8000/"))

    assert client.tool_url == "http://18.134.14.0:8000/sse"


def test_mcp_client_raises_tool_errors():
    client = McpFinancialToolsClient(Settings(mcp_tool_url="http://localhost:8000/sse"))

    try:
        client._extract_tool_result("finpilot_company_profile", {"isError": True})
    except RuntimeError as exc:
        assert "MCP tool finpilot_company_profile failed" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")
