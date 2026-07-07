from finpilot.chat import FinanceChatAssistant
from finpilot.chat.storage import InMemoryChatStore, RdsChatStore, build_chat_store
from finpilot.core.settings import Settings


class FakeServer:
    def __init__(self):
        self.document_queries = []

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

    def search_documents(self, query):
        self.document_queries.append(query)
        return [
            {
                "title": "FinPilot Scoring and Recommendation Rules",
                "source": "s3://finpilot-rag/raw/scoring/finpilot_scoring_and_recommendation_rules.pdf",
                "excerpt": (
                    "Recommendation Mapping: scores from 55 to 74 map to Hold when evidence is mixed. "
                    "Confidence Calculation uses data coverage, source agreement, signal strength, and penalties."
                ),
            }
        ]


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


def test_chat_routes_recommendation_rationale_to_rag():
    server = FakeServer()
    assistant = FinanceChatAssistant(server, FakeTradingAgent(), Settings())

    answer = assistant.answer("how are you recommending hold for sbi?", market="India")

    assert server.document_queries == ["how are you recommending hold for sbi?"]
    assert "document-backed scoring methodology" in answer
    assert "scores from 55 to 74 map to Hold" in answer
    assert "Sources:" in answer


def test_chat_routes_recommendation_signal_wording_to_rag():
    server = FakeServer()
    assistant = FinanceChatAssistant(server, FakeTradingAgent(), Settings())

    answer = assistant.answer("how are calculating score to predict recommendation signal", market="India")

    assert server.document_queries == ["how are calculating score to predict recommendation signal"]
    assert "recommendation signal" in answer
    assert "RAG evidence" in answer


def test_chat_routes_watch_hold_signal_wording_to_rag():
    server = FakeServer()
    assistant = FinanceChatAssistant(server, FakeTradingAgent(), Settings())

    answer = assistant.answer("how are recommending research signal as watch,hold", market="India")

    assert server.document_queries == ["how are recommending research signal as watch,hold"]
    assert "Watch/Hold-style" in answer
    assert "Sources:" in answer


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
