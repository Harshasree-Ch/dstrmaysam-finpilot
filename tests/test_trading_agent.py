import sys
import types

from finpilot.agents.trading import TradingAgent
from finpilot.core.models import TradeIntent
from finpilot.core.settings import Settings
from finpilot.trading.paper import PaperTradingService


def test_trading_requires_confirmation():
    agent = TradingAgent(PaperTradingService(Settings()))
    result = agent.execute(TradeIntent(ticker="RELIANCE.NS", side="buy", quantity=1))
    assert not result.accepted


def test_confirmed_mock_trade_is_accepted():
    agent = TradingAgent(PaperTradingService(Settings()))
    result = agent.execute(TradeIntent(ticker="RELIANCE.NS", side="buy", quantity=1, user_confirmed=True))
    assert not result.accepted
    assert result.status == "groww_not_configured"


def test_live_order_requires_groww_configuration():
    settings = Settings(data_mode="live")
    agent = TradingAgent(PaperTradingService(settings))
    result = agent.execute(TradeIntent(ticker="RELIANCE.NS", side="buy", quantity=1, user_confirmed=True))
    assert not result.accepted
    assert result.status == "groww_not_configured"
    assert "Groww API key and secret" in result.message


def test_configured_groww_order_uses_sdk(monkeypatch):
    captured = {}

    class FakeGrowwAPI:
        VALIDITY_DAY = "DAY"
        EXCHANGE_NSE = "NSE"
        EXCHANGE_BSE = "BSE"
        SEGMENT_CASH = "CASH"
        PRODUCT_MIS = "MIS"
        ORDER_TYPE_MARKET = "MARKET"
        ORDER_TYPE_LIMIT = "LIMIT"
        TRANSACTION_TYPE_BUY = "BUY"
        TRANSACTION_TYPE_SELL = "SELL"

        @staticmethod
        def get_access_token(api_key, secret):
            captured["api_key"] = api_key
            captured["secret"] = secret
            return "access-token"

        def __init__(self, access_token):
            captured["access_token"] = access_token

        def place_order(self, **kwargs):
            captured["order"] = kwargs
            return {"groww_order_id": "groww-123", "status": "submitted"}

    fake_module = types.SimpleNamespace(GrowwAPI=FakeGrowwAPI)
    monkeypatch.setitem(sys.modules, "growwapi", fake_module)
    settings = Settings(
        data_mode="live",
        groww_api_key="groww-key",
        groww_secret_key="groww-secret",
    )
    agent = TradingAgent(PaperTradingService(settings))

    result = agent.execute(
        TradeIntent(ticker="RELIANCE.NS", market="India", side="buy", quantity=2, user_confirmed=True)
    )

    assert result.accepted
    assert result.order_id == "groww-123"
    assert captured["api_key"] == "groww-key"
    assert captured["secret"] == "groww-secret"
    assert captured["access_token"] == "access-token"
    assert captured["order"] == {
        "trading_symbol": "RELIANCE",
        "quantity": 2,
        "validity": "DAY",
        "exchange": "NSE",
        "segment": "CASH",
        "product": "MIS",
        "order_type": "MARKET",
        "transaction_type": "BUY",
    }


def test_groww_ip_registration_error_is_actionable(monkeypatch):
    class FakeGrowwAPI:
        VALIDITY_DAY = "DAY"
        EXCHANGE_NSE = "NSE"
        EXCHANGE_BSE = "BSE"
        SEGMENT_CASH = "CASH"
        PRODUCT_MIS = "MIS"
        ORDER_TYPE_MARKET = "MARKET"
        ORDER_TYPE_LIMIT = "LIMIT"
        TRANSACTION_TYPE_BUY = "BUY"
        TRANSACTION_TYPE_SELL = "SELL"

        @staticmethod
        def get_access_token(api_key, secret):
            return "access-token"

        def __init__(self, access_token):
            pass

        def place_order(self, **kwargs):
            raise RuntimeError("No registered IPs found for this user. Please register your IPs first.")

    fake_module = types.SimpleNamespace(GrowwAPI=FakeGrowwAPI)
    monkeypatch.setitem(sys.modules, "growwapi", fake_module)
    settings = Settings(data_mode="live", groww_api_key="groww-key", groww_secret_key="groww-secret")
    agent = TradingAgent(PaperTradingService(settings))

    result = agent.execute(
        TradeIntent(ticker="RELIANCE.NS", market="India", side="buy", quantity=1, user_confirmed=True)
    )

    assert not result.accepted
    assert result.status == "groww_ip_not_registered"
    assert "public IP" in result.message
    assert "Groww API settings" in result.message


def test_groww_order_status_uses_sdk(monkeypatch):
    captured = {}

    class FakeGrowwAPI:
        SEGMENT_CASH = "CASH"

        @staticmethod
        def get_access_token(api_key, secret):
            captured["api_key"] = api_key
            captured["secret"] = secret
            return "access-token"

        def __init__(self, access_token):
            captured["access_token"] = access_token

        def get_order_status(self, segment, groww_order_id):
            captured["segment"] = segment
            captured["groww_order_id"] = groww_order_id
            return {"order_status": "EXECUTED", "groww_order_id": groww_order_id}

    fake_module = types.SimpleNamespace(GrowwAPI=FakeGrowwAPI)
    monkeypatch.setitem(sys.modules, "growwapi", fake_module)
    settings = Settings(data_mode="live", groww_api_key="groww-key", groww_secret_key="groww-secret")
    agent = TradingAgent(PaperTradingService(settings))

    status = agent.groww_order_status("GMK260701172820RYDM3XF2ZUSG")

    assert status["order_status"] == "EXECUTED"
    assert captured["api_key"] == "groww-key"
    assert captured["secret"] == "groww-secret"
    assert captured["access_token"] == "access-token"
    assert captured["segment"] == "CASH"
    assert captured["groww_order_id"] == "GMK260701172820RYDM3XF2ZUSG"


def test_groww_orders_uses_sdk_order_list(monkeypatch):
    captured = {}

    class FakeGrowwAPI:
        SEGMENT_CASH = "CASH"

        @staticmethod
        def get_access_token(api_key, secret):
            captured["api_key"] = api_key
            captured["secret"] = secret
            return "access-token"

        def __init__(self, access_token):
            captured["access_token"] = access_token

        def get_order_list(self, page, page_size, segment, timeout):
            captured["page"] = page
            captured["page_size"] = page_size
            captured["segment"] = segment
            captured["timeout"] = timeout
            return {"orders": [{"groww_order_id": "groww-123", "order_status": "EXECUTED"}]}

    fake_module = types.SimpleNamespace(GrowwAPI=FakeGrowwAPI)
    monkeypatch.setitem(sys.modules, "growwapi", fake_module)
    settings = Settings(data_mode="live", groww_api_key="groww-key", groww_secret_key="groww-secret")
    agent = TradingAgent(PaperTradingService(settings))

    orders = agent.groww_orders(page_size=20)

    assert orders["orders"][0]["groww_order_id"] == "groww-123"
    assert captured["api_key"] == "groww-key"
    assert captured["secret"] == "groww-secret"
    assert captured["access_token"] == "access-token"
    assert captured["page"] == 0
    assert captured["page_size"] == 20
    assert captured["segment"] == "CASH"
    assert captured["timeout"] == 15


def test_missing_groww_sdk_is_actionable(monkeypatch):
    monkeypatch.delitem(sys.modules, "growwapi", raising=False)

    original_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "growwapi":
            raise ModuleNotFoundError("No module named 'growwapi'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    settings = Settings(data_mode="live", groww_api_key="groww-key", groww_secret_key="groww-secret")
    agent = TradingAgent(PaperTradingService(settings))

    result = agent.execute(
        TradeIntent(ticker="RELIANCE.NS", market="India", side="buy", quantity=1, user_confirmed=True)
    )

    assert not result.accepted
    assert result.status == "groww_sdk_missing"
    assert "requirements.txt" in result.message
    assert "restart/redeploy Streamlit" in result.message


def test_us_order_requires_alpaca_configuration():
    agent = TradingAgent(PaperTradingService(Settings(data_mode="live")))
    result = agent.execute(TradeIntent(ticker="AAPL", market="US", side="buy", quantity=1, user_confirmed=True))
    assert not result.accepted
    assert result.status == "alpaca_not_configured"
    assert "configure Alpaca" in result.message


def test_configured_alpaca_order_posts_payload(monkeypatch):
    captured = {}

    class FakeResponse:
        content = b'{"id": "alpaca-123", "status": "accepted"}'

        def raise_for_status(self):
            return None

        def json(self):
            return {"id": "alpaca-123", "status": "accepted"}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("finpilot.trading.paper.requests.post", fake_post)
    settings = Settings(
        data_mode="live",
        alpaca_api_key="alpaca-key",
        alpaca_secret_key="alpaca-secret",
        alpaca_paper_base_url="https://paper-api.example",
    )
    agent = TradingAgent(PaperTradingService(settings))

    result = agent.execute(
        TradeIntent(
            ticker="AAPL",
            market="US",
            side="buy",
            quantity=3,
            order_type="limit",
            limit_price=190.5,
            user_confirmed=True,
        )
    )

    assert result.accepted
    assert result.order_id == "alpaca-123"
    assert captured["url"] == "https://paper-api.example/v2/orders"
    assert captured["json"] == {
        "symbol": "AAPL",
        "qty": 3,
        "side": "buy",
        "type": "limit",
        "time_in_force": "day",
        "limit_price": 190.5,
    }
    assert captured["headers"]["APCA-API-KEY-ID"] == "alpaca-key"
    assert captured["headers"]["APCA-API-SECRET-KEY"] == "alpaca-secret"


def test_configured_alpaca_orders_gets_order_history(monkeypatch):
    captured = {}

    class FakeResponse:
        content = b'[{"id": "alpaca-123", "symbol": "AAPL", "status": "filled"}]'

        def raise_for_status(self):
            return None

        def json(self):
            return [{"id": "alpaca-123", "symbol": "AAPL", "status": "filled"}]

    def fake_get(url, params, headers, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("finpilot.trading.paper.requests.get", fake_get)
    settings = Settings(
        data_mode="live",
        alpaca_api_key="alpaca-key",
        alpaca_secret_key="alpaca-secret",
        alpaca_paper_base_url="https://paper-api.example",
    )
    agent = TradingAgent(PaperTradingService(settings))

    orders = agent.alpaca_orders(limit=25)

    assert orders[0]["id"] == "alpaca-123"
    assert captured["url"] == "https://paper-api.example/v2/orders"
    assert captured["params"] == {"status": "all", "limit": 25, "direction": "desc", "nested": "true"}
    assert captured["headers"]["APCA-API-KEY-ID"] == "alpaca-key"
    assert captured["headers"]["APCA-API-SECRET-KEY"] == "alpaca-secret"
    assert captured["timeout"] == 15


def test_limit_trade_requires_limit_price():
    agent = TradingAgent(PaperTradingService(Settings(data_mode="live")))
    result = agent.execute(
        TradeIntent(ticker="RELIANCE.NS", side="buy", quantity=1, order_type="limit", user_confirmed=True)
    )
    assert not result.accepted
    assert "Limit orders" in result.message


def test_trading_rejects_blank_ticker():
    agent = TradingAgent(PaperTradingService(Settings(data_mode="live")))
    result = agent.execute(TradeIntent(ticker=" ", side="buy", quantity=1, user_confirmed=True))
    assert not result.accepted
    assert "Ticker" in result.message
