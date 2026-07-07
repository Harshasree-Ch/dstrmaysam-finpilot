from __future__ import annotations

import re
from typing import Any

from finpilot.agents.trading import TradingAgent
from finpilot.core.settings import Settings
from finpilot.financial_tools import FinancialTools


class FinanceChatAssistant:
    def __init__(
        self,
        server: FinancialTools,
        trading_agent: TradingAgent,
        settings: Settings,
    ) -> None:
        self.server = server
        self.trading_agent = trading_agent
        self.settings = settings

    def answer(self, question: str, market: str = "India") -> str:
        text = question.strip()
        if not text:
            return "Ask me about your portfolio, current stock prices, or comparing companies."

        lowered = text.lower()
        if any(word in lowered for word in ("portfolio", "order", "orders", "holding", "holdings", "account")):
            return self._portfolio_answer(lowered)
        if self._is_rag_methodology_question(lowered):
            return self._rag_methodology_answer(text)
        if any(word in lowered for word in ("compare", "comparison", "versus", " vs ", "better than")):
            return self._comparison_answer(text, market)
        if any(word in lowered for word in ("price", "quote", "current", "ltp", "trading at")):
            return self._price_answer(text, market)
        return (
            "I can help with portfolio/order history, live stock prices, and stock comparisons. "
            "Try: 'What is the current price of TCS?', 'Compare SBI and HDFC Bank', or "
            "'Show my Groww orders.'"
        )

    def _is_rag_methodology_question(self, lowered_question: str) -> bool:
        methodology_terms = (
            "recommend",
            "recommendation",
            "recommended",
            "score",
            "scoring",
            "signal",
            "method",
            "methodology",
            "confidence",
            "allocation",
            "why",
            "how",
            "watch",
            "hold",
            "buy",
            "sell",
            "accumulate",
            "reduce",
        )
        return any(term in lowered_question for term in methodology_terms) and any(
            target in lowered_question
            for target in (
                "recommend",
                "score",
                "signal",
                "method",
                "methodology",
                "confidence",
                "allocation",
                "watch",
                "hold",
                "buy",
                "sell",
                "accumulate",
                "reduce",
            )
        )

    def _rag_methodology_answer(self, question: str) -> str:
        evidence = self.server.search_documents(question)
        if not evidence:
            return (
                "I tried to answer this from the RAG methodology documents, but no matching document chunks were "
                "returned. Check that the scoring/recommendation PDF has been ingested into the vector index and "
                "that the MCP RAG tool is reachable."
            )

        excerpts = []
        citations = []
        for item in evidence[:4]:
            if isinstance(item, dict):
                title = item.get("title") or item.get("source") or "Retrieved RAG document"
                excerpt = item.get("excerpt") or item.get("text") or item.get("summary") or ""
                source = item.get("source") or item.get("url") or title
            else:
                title = getattr(item, "title", None) or getattr(item, "source", None) or "Retrieved RAG document"
                excerpt = getattr(item, "excerpt", None) or getattr(item, "text", None) or ""
                source = getattr(item, "source", None) or getattr(item, "url", None) or title
            if excerpt:
                excerpts.append(str(excerpt).strip())
            citations.append(str(source))

        context = " ".join(excerpts)
        answer = (
            "The recommendation signal is based on FinPilot's document-backed scoring methodology. "
            "The RAG evidence says the system blends market performance, fundamentals, earnings/news context, "
            "risk signals, and document evidence into a weighted score. Watch/Hold-style recommendations mean the "
            "total evidence is mixed or moderate rather than strongly positive or strongly negative."
        )
        if context:
            answer += f"\n\nRelevant retrieved evidence: {context[:900]}"
        if citations:
            answer += "\n\nSources: " + "; ".join(dict.fromkeys(citations[:4]))
        answer += "\n\nThis is educational research, not financial advice."
        return answer

    def _portfolio_answer(self, lowered_question: str) -> str:
        brokers = []
        if "groww" in lowered_question:
            brokers = ["Groww"]
        elif "alpaca" in lowered_question:
            brokers = ["Alpaca paper"]
        else:
            if self.settings.groww_api_key and self.settings.groww_secret_key:
                brokers.append("Groww")
            if self.settings.alpaca_api_key and self.settings.alpaca_secret_key:
                brokers.append("Alpaca paper")

        if not brokers:
            return "No broker credentials are configured yet. Add Groww or Alpaca credentials in the Invest tab first."

        sections = []
        for broker in brokers:
            try:
                raw_orders = self.trading_agent.groww_orders() if broker == "Groww" else self.trading_agent.alpaca_orders()
                rows = self._normalize_order_rows(broker, raw_orders)
            except Exception as exc:
                sections.append(f"{broker}: I could not fetch orders: {exc}")
                continue

            if not rows:
                sections.append(f"{broker}: no orders were returned by the broker account.")
                continue
            status_counts: dict[str, int] = {}
            tickers = []
            for row in rows:
                status = str(row.get("status") or "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1
                ticker = str(row.get("ticker") or "")
                if ticker and ticker != "N/A" and ticker not in tickers:
                    tickers.append(ticker)
            status_text = ", ".join(f"{status}: {count}" for status, count in sorted(status_counts.items()))
            recent = rows[:3]
            recent_text = "; ".join(
                f"{row['side']} {row['quantity']} {row['ticker']} ({row['status']})" for row in recent
            )
            sections.append(
                f"{broker}: {len(rows)} order(s). Status mix: {status_text}. "
                f"Tickers seen: {', '.join(tickers[:8]) or 'N/A'}. Recent: {recent_text}."
            )
        return "\n\n".join(sections)

    def _price_answer(self, question: str, market: str) -> str:
        symbols = self._extract_symbols(question, market)
        if not symbols:
            return "Which stock should I check? Use a ticker or company name, for example TCS, SBI, AAPL, or MSFT."

        lines = []
        for symbol in symbols[:5]:
            try:
                snapshot = self.server.market_snapshot(symbol)
                profile = self.server.company_profile(symbol)
            except Exception as exc:
                lines.append(f"{symbol}: price data unavailable ({exc}).")
                continue
            price = snapshot.get("price")
            currency = snapshot.get("currency") or ("INR" if symbol.endswith((".NS", ".BO")) else "USD")
            change_percent = snapshot.get("change_percent")
            price_text = "N/A" if price is None else self._format_money(float(price), currency)
            change_text = "N/A" if change_percent is None else f"{float(change_percent):.2%}"
            lines.append(
                f"{profile.get('name', symbol)} ({symbol}) is at {price_text}; today's change is {change_text}. "
                f"Exchange: {snapshot.get('exchange', 'Unknown')}."
            )
        return "\n\n".join(lines)

    def _comparison_answer(self, question: str, market: str) -> str:
        symbols = self._extract_symbols(question, market)
        if len(symbols) < 2:
            return "Tell me at least two stocks to compare, for example 'Compare TCS and Infosys' or 'Compare AAPL vs MSFT'."

        rows = []
        for symbol in symbols[:4]:
            try:
                snapshot = self.server.market_snapshot(symbol)
                profile = self.server.company_profile(symbol)
            except Exception as exc:
                rows.append({"ticker": symbol, "error": str(exc)})
                continue
            metrics = profile.get("metrics", {})
            rows.append(
                {
                    "ticker": symbol,
                    "name": profile.get("name", symbol),
                    "price": snapshot.get("price"),
                    "currency": snapshot.get("currency") or ("INR" if symbol.endswith((".NS", ".BO")) else "USD"),
                    "change_percent": snapshot.get("change_percent"),
                    "market_cap": metrics.get("market_cap", "N/A"),
                    "pe": metrics.get("pe_ratio_ttm", "N/A"),
                    "roe": metrics.get("roe", "N/A"),
                    "sector": profile.get("sector", "Unknown"),
                }
            )

        lines = ["Here is a quick comparison:"]
        for row in rows:
            if "error" in row:
                lines.append(f"- {row['ticker']}: unavailable ({row['error']}).")
                continue
            price_text = "N/A" if row["price"] is None else self._format_money(float(row["price"]), str(row["currency"]))
            change_text = "N/A" if row["change_percent"] is None else f"{float(row['change_percent']):.2%}"
            lines.append(
                f"- {row['name']} ({row['ticker']}): price {price_text}, today {change_text}, "
                f"market cap {row['market_cap']}, P/E {row['pe']}, ROE {row['roe']}, sector {row['sector']}."
            )
        return "\n".join(lines)

    def _extract_symbols(self, question: str, market: str) -> list[str]:
        lowered = question.lower()
        symbols = []
        aliases = {
            "sbi": "SBIN.NS",
            "state bank of india": "SBIN.NS",
            "tcs": "TCS.NS",
            "tata consultancy services": "TCS.NS",
            "infosys": "INFY.NS",
            "infy": "INFY.NS",
            "reliance": "RELIANCE.NS",
            "hdfc bank": "HDFCBANK.NS",
            "icici bank": "ICICIBANK.NS",
            "apple": "AAPL",
            "microsoft": "MSFT",
            "nvidia": "NVDA",
            "amazon": "AMZN",
            "google": "GOOGL",
            "alphabet": "GOOGL",
            "meta": "META",
            "tesla": "TSLA",
        }
        for alias, symbol in aliases.items():
            if re.search(rf"\b{re.escape(alias)}\b", lowered) and symbol not in symbols:
                symbols.append(symbol)

        ignore = {
            "WHAT",
            "WHATS",
            "PRICE",
            "CURRENT",
            "COMPARE",
            "SHOW",
            "ORDERS",
            "PORTFOLIO",
            "AND",
            "THE",
            "FOR",
            "WITH",
            "TODAY",
            "LIVE",
        }
        for token in re.findall(r"\b[A-Z0-9]{2,12}(?:\.(?:NS|BO))?\b", question):
            if token in ignore or token in symbols:
                continue
            if "." not in token and market == "India":
                candidate = f"{token}.NS"
            else:
                candidate = token
            if candidate not in symbols:
                symbols.append(candidate)
        return symbols

    def _normalize_order_rows(self, broker: str, raw_orders: object) -> list[dict[str, Any]]:
        orders = self._flatten_groww_orders(raw_orders) if broker == "Groww" else raw_orders
        if not isinstance(orders, list):
            return []
        rows = []
        for order in orders:
            if not isinstance(order, dict):
                continue
            rows.append(
                {
                    "ticker": self._first_value(order, "symbol", "trading_symbol", "tradingSymbol", "ticker") or "N/A",
                    "side": str(
                        self._first_value(order, "side", "transaction_type", "transactionType") or "N/A"
                    ).lower(),
                    "quantity": self._first_value(order, "qty", "quantity", "filled_qty", "filledQuantity") or "N/A",
                    "status": self._first_value(order, "status", "order_status", "orderStatus") or "N/A",
                }
            )
        return rows

    def _flatten_groww_orders(self, raw_orders: object) -> list[dict]:
        if isinstance(raw_orders, list):
            return raw_orders
        if not isinstance(raw_orders, dict):
            return []
        for key in ("orders", "order_list", "orderList", "data", "results"):
            value = raw_orders.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = self._flatten_groww_orders(value)
                if nested:
                    return nested
        return []

    def _first_value(self, data: dict, *keys: str) -> object:
        for key in keys:
            value = data.get(key)
            if value is not None and value != "":
                return value
        return None

    def _format_money(self, value: float, currency: str) -> str:
        if currency == "USD":
            return f"${value:,.2f}"
        return f"{currency} {value:,.2f}"
