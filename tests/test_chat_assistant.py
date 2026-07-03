from finpilot.chat import FinanceChatAssistant
from finpilot.chat.storage import InMemoryChatStore, RdsChatStore, build_chat_store
from finpilot.core.settings import Settings


class FakeServer:
    def market_snapshot(self, ticker):
        prices = {
            "TCS.NS": {"price": 3900.0, "currency": "INR", "change_percent": 0.012, "exchange": "NSE"},
            "INFY.NS": {"price": 1500.0, "currency": "INR", "change_percent": -0.004, "exchange": "NSE"},
            "AAPL": {"price": 200.0, "currency": "USD", "change_percent": 0.01, "exchange": "NASDAQ"},
        }
        return prices[ticker]

    def company_profile(self, ticker):
        profiles = {
            "TCS.NS": {
                "name": "Tata Consultancy Services",
                "sector": "Technology",
                "metrics": {"market_cap": "14.20T", "pe_ratio_ttm": "30.20", "roe": "49.00%"},
            },
            "INFY.NS": {
                "name": "Infosys",
                "sector": "Technology",
                "metrics": {"market_cap": "6.40T", "pe_ratio_ttm": "24.20", "roe": "31.00%"},
            },
            "AAPL": {
                "name": "Apple Inc.",
                "sector": "Technology",
                "metrics": {"market_cap": "Mega Cap", "pe_ratio_ttm": "31.00", "roe": "N/A"},
            },
        }
        return profiles[ticker]


class FakeTradingAgent:
    def groww_orders(self):
        return {
            "orders": [
                {"trading_symbol": "TCS", "transaction_type": "BUY", "quantity": 1, "order_status": "EXECUTED"},
                {"trading_symbol": "INFY", "transaction_type": "SELL", "quantity": 2, "order_status": "SUBMITTED"},
            ]
        }

    def alpaca_orders(self):
        return [{"symbol": "AAPL", "side": "buy", "qty": "3", "status": "filled"}]


def test_chat_answers_stock_price_question():
    assistant = FinanceChatAssistant(FakeServer(), FakeTradingAgent(), Settings())

    answer = assistant.answer("What is the current price of TCS?", market="India")

    assert "Tata Consultancy Services" in answer
    assert "INR 3,900.00" in answer
    assert "1.20%" in answer


def test_chat_compares_two_indian_stocks():
    assistant = FinanceChatAssistant(FakeServer(), FakeTradingAgent(), Settings())

    answer = assistant.answer("Compare TCS and Infosys", market="India")

    assert "Tata Consultancy Services" in answer
    assert "Infosys" in answer
    assert "P/E 30.20" in answer
    assert "P/E 24.20" in answer


def test_chat_summarizes_configured_portfolio_orders():
    settings = Settings(groww_api_key="groww-key", groww_secret_key="groww-secret")
    assistant = FinanceChatAssistant(FakeServer(), FakeTradingAgent(), settings)

    answer = assistant.answer("Show my Groww portfolio orders", market="India")

    assert "Groww: 2 order(s)" in answer
    assert "EXECUTED: 1" in answer
    assert "SUBMITTED: 1" in answer


def test_in_memory_chat_store_round_trip():
    store = InMemoryChatStore()

    store.append_message("session-1", "user", "hello")
    store.append_message("session-1", "assistant", "hi")

    messages = store.load_messages("session-1")
    assert [message.role for message in messages] == ["user", "assistant"]
    assert [message.content for message in messages] == ["hello", "hi"]

    store.clear_messages("session-1")
    assert store.load_messages("session-1") == []


def test_build_chat_store_uses_rds_when_database_url_is_set():
    store = build_chat_store("postgresql+psycopg://user:pass@example.com:5432/finpilot")

    assert isinstance(store, RdsChatStore)
