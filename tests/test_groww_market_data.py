from finpilot.core.settings import Settings
from finpilot_mcp.server import FinancialIntelligenceServer


class FakeGrowwClient:
    EXCHANGE_NSE = "NSE"
    EXCHANGE_BSE = "BSE"
    SEGMENT_CASH = "CASH"

    def get_quote(self, trading_symbol, exchange, segment, timeout=None):
        return {
            "trading_symbol": trading_symbol,
            "ltp": 0.96,
            "open": 0.94,
            "high": 0.98,
            "low": 0.91,
            "volume": 12345,
            "exchange": exchange,
            "segment": segment,
        }

    def get_instrument_by_exchange_and_trading_symbol(self, exchange, trading_symbol):
        return {
            "trading_symbol": trading_symbol,
            "exchange": exchange,
            "groww_symbol": "BSE-PADAMCO",
            "isin": "INE000TEST01",
            "exchange_token": "531395",
        }


class QuoteOnlyGrowwClient(FakeGrowwClient):
    def get_instrument_by_exchange_and_trading_symbol(self, exchange, trading_symbol):
        raise RuntimeError("instrument not found")


class FailingGrowwClient(FakeGrowwClient):
    def get_quote(self, trading_symbol, exchange, segment, timeout=None):
        raise RuntimeError("quote failed")

    def get_instrument_by_exchange_and_trading_symbol(self, exchange, trading_symbol):
        raise RuntimeError("instrument failed")


def test_groww_enriches_sparse_indian_company_profile():
    server = FinancialIntelligenceServer(Settings(data_mode="live", groww_api_key="key", groww_secret_key="secret"))
    server._groww_client = FakeGrowwClient()

    profile = server._enrich_profile_with_groww(
        "PADAMCO.BO",
        {
            "ticker": "PADAMCO.BO",
            "name": "Padam Cotton Yarns Limited",
            "sector": "Unknown",
            "industry": "Unknown",
            "market_cap": "Unknown",
            "business_model": "Realtime quote data was returned for Padam Cotton Yarns Limited, but no company summary was available.",
            "metrics": {
                "market_cap": "N/A",
                "roe": "N/A",
                "pe_ratio_ttm": "N/A",
                "eps_ttm": "N/A",
            },
        },
    )

    assert profile["metrics"]["market_cap"] == "Unavailable from Groww/Yahoo"
    assert profile["metrics"]["exchange"] == "BSE"
    assert profile["metrics"]["trading_symbol"] == "PADAMCO"
    assert profile["metrics"]["ltp"] == "0.96"
    assert profile["metrics"]["isin"] == "INE000TEST01"
    assert profile["metrics"]["groww_symbol"] == "BSE-PADAMCO"
    assert profile["metrics"]["open"] == "0.94"
    assert profile["metrics"]["volume"] == "12,345.00"
    assert profile["provider_status"] == "Yahoo checked; Groww enrichment applied."
    assert "Yahoo and Groww were checked" in profile["business_model"]


def test_groww_quote_still_enriches_when_instrument_lookup_fails():
    server = FinancialIntelligenceServer(Settings(data_mode="live", groww_api_key="key", groww_secret_key="secret"))
    server._groww_client = QuoteOnlyGrowwClient()

    profile = server._enrich_profile_with_groww(
        "PADAMCO.BO",
        {
            "ticker": "PADAMCO.BO",
            "name": "Padam Cotton Yarns Limited",
            "sector": "Unknown",
            "industry": "Unknown",
            "market_cap": "Unknown",
            "business_model": "Realtime quote data was returned for Padam Cotton Yarns Limited, but no company summary was available.",
            "metrics": {"market_cap": "N/A"},
        },
    )

    assert profile["metrics"]["exchange"] == "BSE"
    assert profile["metrics"]["trading_symbol"] == "PADAMCO"
    assert profile["metrics"]["ltp"] == "0.96"
    assert "instrument lookup failed" in profile["groww"]["errors"][0]
    assert profile["provider_status"] == "Yahoo checked; Groww enrichment applied."


def test_provider_status_explains_when_groww_returns_no_data():
    server = FinancialIntelligenceServer(Settings(data_mode="live", groww_api_key="key", groww_secret_key="secret"))
    server._groww_client = FailingGrowwClient()

    profile = server._enrich_profile_with_groww(
        "PADAMCO.BO",
        {
            "ticker": "PADAMCO.BO",
            "name": "Padam Cotton Yarns Limited",
            "sector": "Unknown",
            "industry": "Unknown",
            "market_cap": "Unknown",
            "business_model": "Realtime quote data was returned for Padam Cotton Yarns Limited, but no company summary was available.",
            "metrics": {"market_cap": "N/A"},
        },
    )

    assert profile["metrics"]["exchange"] == "BSE"
    assert profile["metrics"]["trading_symbol"] == "PADAMCO"
    assert "Groww enrichment unavailable" in profile["provider_status"]
    assert "quote lookup failed" in profile["provider_status"]


def test_groww_enriches_market_snapshot_price():
    server = FinancialIntelligenceServer(Settings(data_mode="live", groww_api_key="key", groww_secret_key="secret"))
    server._groww_client = FakeGrowwClient()

    quote = server._enrich_quote_with_groww(
        "PADAMCO.BO",
        {
            "ticker": "PADAMCO.BO",
            "price": None,
            "day_high": None,
            "day_low": None,
            "volume": None,
            "source": "Yahoo Finance",
        },
    )

    assert quote["price"] == 0.96
    assert quote["day_high"] == 0.98
    assert quote["day_low"] == 0.91
    assert quote["volume"] == 12345.0
    assert quote["exchange"] == "BSE"
    assert quote["source"] == "Yahoo Finance + Groww API"
