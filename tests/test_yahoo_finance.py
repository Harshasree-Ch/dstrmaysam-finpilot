import requests

from finpilot_mcp.data.yahoo_finance import YahooFinanceClient


def test_company_fallback_enriches_sparse_indian_profile(monkeypatch):
    client = YahooFinanceClient()

    monkeypatch.setattr(client, "_quote_result", lambda ticker: {"longName": "Reliance Industries Limited"})
    monkeypatch.setattr(client, "_quote_summary", lambda ticker, modules=None: {})
    monkeypatch.setattr(client, "_stockanalysis_profile", lambda ticker: {})
    monkeypatch.setattr(client, "_screener_profile", lambda ticker: {})
    monkeypatch.setattr(
        client,
        "quote",
        lambda ticker: {
            "ticker": ticker,
            "price": 1293.9,
            "currency": "INR",
            "change": None,
            "change_percent": None,
        },
    )

    profile = client.company_profile("RELIANCE.NS")

    assert profile["sector"] == "Energy"
    assert profile["industry"] == "Oil & Gas Refining and Marketing"
    assert profile["market_cap"] == "Large Cap"
    assert profile["metrics"]["market_cap"] == "19.50T"
    assert profile["metrics"]["debt_to_equity"] == "0.38"
    assert "oil-to-chemicals" in profile["business_model"]


def test_company_fallback_enriches_sparse_indian_bank_profile(monkeypatch):
    client = YahooFinanceClient()

    monkeypatch.setattr(client, "_quote_result", lambda ticker: {"longName": "State Bank of India"})
    monkeypatch.setattr(client, "_quote_summary", lambda ticker, modules=None: {})
    monkeypatch.setattr(client, "_stockanalysis_profile", lambda ticker: {})
    monkeypatch.setattr(client, "_screener_profile", lambda ticker: {})
    monkeypatch.setattr(
        client,
        "quote",
        lambda ticker: {
            "ticker": ticker,
            "price": 820.0,
            "currency": "INR",
            "change": None,
            "change_percent": None,
        },
    )

    profile = client.company_profile("SBIN.NS")

    assert profile["sector"] == "Financial Services"
    assert profile["industry"] == "Banks - Regional"
    assert profile["metrics"]["market_cap"] == "7.20T"
    assert profile["metrics"]["roe"] == "17.00%"
    assert profile["metrics"]["pe_ratio_ttm"] == "9.50"
    assert profile["metrics"]["pb_ratio"] == "1.55"


def test_company_fallback_includes_employee_count_for_tcs(monkeypatch):
    client = YahooFinanceClient()

    monkeypatch.setattr(client, "_quote_result", lambda ticker: {"longName": "Tata Consultancy Services Limited"})
    monkeypatch.setattr(client, "_quote_summary", lambda ticker, modules=None: {})
    monkeypatch.setattr(client, "_stockanalysis_profile", lambda ticker: {})
    monkeypatch.setattr(client, "_screener_profile", lambda ticker: {})
    monkeypatch.setattr(
        client,
        "quote",
        lambda ticker: {
            "ticker": ticker,
            "price": 3900.0,
            "currency": "INR",
            "change": None,
            "change_percent": None,
        },
    )

    profile = client.company_profile("TCS.NS")

    assert profile["employees"] == "607,979"
    assert profile["metrics"]["market_cap"] == "14.20T"


def test_indian_screener_profile_fills_sparse_fundamentals(monkeypatch):
    client = YahooFinanceClient()
    html = """
    <ul id="top-ratios">
      <li class="flex flex-space-between" data-source="default">
        <span class="name">Market Cap</span>
        <span class="nowrap value">₹ <span class="number">1,07,985</span> Cr.</span>
      </li>
      <li class="flex flex-space-between" data-source="default">
        <span class="name">Stock P/E</span>
        <span class="nowrap value"><span class="number">6.23</span></span>
      </li>
      <li class="flex flex-space-between" data-source="default">
        <span class="name">Book Value</span>
        <span class="nowrap value">₹ <span class="number">127</span></span>
      </li>
      <li class="flex flex-space-between" data-source="default">
        <span class="name">Dividend Yield</span>
        <span class="nowrap value"><span class="number">15.8</span> %</span>
      </li>
      <li class="flex flex-space-between" data-source="default">
        <span class="name">ROE</span>
        <span class="nowrap value"><span class="number">38.2</span> %</span>
      </li>
      <li class="flex flex-space-between" data-source="default">
        <span class="name">Face Value</span>
        <span class="nowrap value">₹ <span class="number">1.00</span></span>
      </li>
    </ul>
    """

    monkeypatch.setattr(client, "_get_text", lambda url: html)

    profile = client._screener_profile("VEDL.NS")

    assert profile["metrics"]["market_cap"] == "1,07,985 Cr"
    assert profile["metrics"]["pe_ratio_ttm"] == "6.23"
    assert profile["metrics"]["book_value"] == "127"
    assert profile["metrics"]["dividend_yield"] == "15.8%"
    assert profile["metrics"]["roe"] == "38.2%"
    assert profile["metrics"]["face_value"] == "1.00"


def test_company_fallback_enriches_sparse_us_profile(monkeypatch):
    client = YahooFinanceClient()

    monkeypatch.setattr(client, "_quote_result", lambda ticker: {"longName": "Apple Inc."})
    monkeypatch.setattr(client, "_quote_summary", lambda ticker, modules=None: {})
    monkeypatch.setattr(client, "_stockanalysis_profile", lambda ticker: {})
    monkeypatch.setattr(
        client,
        "quote",
        lambda ticker: {
            "ticker": ticker,
            "price": 289.36,
            "currency": "USD",
            "change": None,
            "change_percent": None,
        },
    )

    profile = client.company_profile("AAPL")

    assert profile["sector"] == "Technology"
    assert profile["industry"] == "Consumer Electronics"
    assert profile["market_cap"] == "Mega Cap"
    assert profile["metrics"]["market_cap"] == "Mega Cap"
    assert profile["metrics"]["pe_ratio_ttm"] == "30.00"
    assert profile["metrics"]["dividend_yield"] == "0.50%"
    assert profile["metrics"]["debt_to_equity"] == "1.20"
    assert "smartphones" in profile["business_model"]


def test_walmart_resolves_and_uses_us_fallback(monkeypatch):
    client = YahooFinanceClient()
    monkeypatch.setattr(client, "_quote_result", lambda ticker: {})

    resolved = client.resolve_symbol("walmart", market="US")
    profile = client.company_profile(resolved["ticker"])

    assert resolved["ticker"] == "WMT"
    assert profile["name"] == "Walmart Inc."
    assert profile["sector"] == "Consumer Defensive"
    assert profile["industry"] == "Discount Stores"
    assert profile["metrics"]["market_cap"] == "Mega Cap"
    assert profile["metrics"]["dividend_yield"] == "0.90%"


def test_us_market_resolves_plain_ticker_without_india_suffix(monkeypatch):
    client = YahooFinanceClient()

    def fake_quote(ticker):
        if ticker == "META":
            return {"symbol": "META", "longName": "Meta Platforms, Inc.", "exchange": "NMS"}
        return {}

    monkeypatch.setattr(client, "_safe_quote_result", fake_quote)

    resolved = client.resolve_symbol("META", market="US")

    assert resolved["ticker"] == "META"


def test_us_market_resolves_known_ticker_from_fallback_when_yahoo_unavailable(monkeypatch):
    client = YahooFinanceClient()
    monkeypatch.setattr(client, "_safe_quote_result", lambda ticker: {})
    monkeypatch.setattr(client, "_search_quote", lambda query: None)

    resolved = client.resolve_symbol("AAPL", market="US")

    assert resolved["ticker"] == "AAPL"
    assert resolved["name"] == "Apple Inc."


def test_india_market_resolves_plain_ticker_to_nse_suffix(monkeypatch):
    client = YahooFinanceClient()

    def fake_quote(ticker):
        if ticker == "TCS.NS":
            return {"symbol": "TCS.NS", "longName": "Tata Consultancy Services Limited", "exchange": "NSI"}
        return {}

    monkeypatch.setattr(client, "_safe_quote_result", fake_quote)

    resolved = client.resolve_symbol("TCS", market="India")

    assert resolved["ticker"] == "TCS.NS"


def test_known_stock_uses_local_fallback_when_yahoo_is_unavailable(monkeypatch):
    client = YahooFinanceClient()

    def blocked_network(*args, **kwargs):
        raise requests.ConnectionError("network blocked")

    monkeypatch.setattr(client.session, "get", blocked_network)

    quote = client.quote("TCS.NS")
    history = client.price_history("TCS.NS", "3 months")
    profile = client.company_profile("TCS.NS")

    assert quote["source"] == "Local fallback profile"
    assert quote["price"] is not None
    assert history["source"] == "Local fallback profile"
    assert len(history["points"]) > 1
    assert profile["name"] == "Tata Consultancy Services Limited"
    assert profile["metrics"]["pe_ratio_ttm"] == "30.20"


def test_indian_news_falls_back_to_google_news_when_yahoo_is_empty(monkeypatch):
    client = YahooFinanceClient()
    captured = []

    class FakeResponse:
        def __init__(self, url):
            self.url = url
            self.content = b"ok"
            self.text = """
                <rss>
                  <channel>
                    <item>
                      <title>SBI shares rise after quarterly update - Economic Times</title>
                      <link>https://example.com/sbi-news</link>
                      <description>State Bank of India stock moved higher after recent market updates.</description>
                      <pubDate>Wed, 01 Jul 2026 10:30:00 GMT</pubDate>
                      <source>The Economic Times</source>
                    </item>
                  </channel>
                </rss>
            """

        def raise_for_status(self):
            return None

        def json(self):
            return {"news": []}

    def fake_get(url, params=None, timeout=None):
        captured.append({"url": url, "params": params, "timeout": timeout})
        return FakeResponse(url)

    monkeypatch.setattr(
        client,
        "company_profile",
        lambda ticker: {"name": "State Bank of India"},
    )
    monkeypatch.setattr(client.session, "get", fake_get)

    news = client.latest_news("SBIN.NS")

    assert news[0]["title"].startswith("SBI shares rise")
    assert news[0]["source"] == "The Economic Times"
    assert news[0]["published_at"] == "Wed, 01 Jul 2026 10:30:00 GMT"
    assert any(call["url"] == "https://news.google.com/rss/search" for call in captured)
    google_call = next(call for call in captured if call["url"] == "https://news.google.com/rss/search")
    assert "SBI" in google_call["params"]["q"]
