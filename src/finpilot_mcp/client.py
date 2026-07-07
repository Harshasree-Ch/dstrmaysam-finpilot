from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from io import BytesIO
from typing import Any
from urllib.parse import urljoin, urlparse, urlsplit, urlunsplit

import boto3
import requests

from finpilot.core.settings import Settings
from finpilot_mcp.data.yahoo_finance import YahooFinanceClient


class McpFinancialToolsClient:
    """MCP-over-SSE client for the central MCP-Tools FinPilot tools."""

    def __init__(self, settings: Settings, timeout: float = 20.0) -> None:
        if not settings.mcp_tool_url:
            raise ValueError("FINPILOT_MCP_TOOL_URL is not configured.")
        self.settings = settings
        self.tool_url = self._normalize_tool_url(settings.mcp_tool_url)
        self.timeout = timeout
        self._yahoo: YahooFinanceClient | None = None
        self._mcp_unavailable_reason: str | None = None

    @property
    def yahoo(self) -> YahooFinanceClient:
        if self._yahoo is None:
            self._yahoo = YahooFinanceClient(timeout=self.timeout)
        return self._yahoo

    def resolve_symbol(self, query: str, market: str | None = None) -> dict[str, Any]:
        try:
            return self.yahoo.resolve_symbol(query, market=market)
        except Exception:
            pass
        try:
            result = self._quote_lookup(query)
        except Exception:
            ticker = query.strip().upper()
            if market and market.lower() == "india" and not ticker.endswith((".NS", ".BO")):
                ticker = f"{ticker}.NS"
            return {
                "query": query,
                "ticker": ticker,
                "name": ticker,
                "exchange": self._exchange_for_ticker(ticker, market),
            }
        quote = result.get("quote", {})
        ticker = quote.get("ticker") or query.strip().upper()
        return {
            "query": query,
            "ticker": ticker,
            "name": quote.get("company_name") or ticker,
            "exchange": self._exchange_for_ticker(ticker, market),
        }

    def company_profile(self, ticker: str) -> dict[str, Any]:
        requested_symbol = ticker.upper()
        yahoo_profile: dict[str, Any] | None = None
        try:
            yahoo_profile = self.yahoo.company_profile(requested_symbol)
        except Exception:
            yahoo_profile = None

        try:
            result = self._quote_lookup(ticker)
        except Exception:
            result = {"quote": {}, "answer": None, "sources": []}
        quote = result.get("quote", {})
        symbol = self._best_symbol(requested_symbol, quote.get("ticker"))
        name = quote.get("company_name") or symbol
        market_cap = quote.get("market_cap")
        mcp_profile = {
            "ticker": symbol,
            "name": name,
            "sector": quote.get("sector") or "Unknown",
            "industry": quote.get("industry") or "Unknown",
            "market_cap": self._market_cap_bucket(market_cap),
            "market_cap_display": self._format_large_number(market_cap) or "N/A",
            "business_model": result.get("answer") or f"Live MCP quote data was returned for {name}.",
            "competitors": [],
            "metrics": {
                "market_cap": self._format_large_number(market_cap) or "N/A",
                "exchange": self._exchange_for_ticker(symbol),
            },
            "metric_sources": {"market_cap": "MCP-TOOLS"} if market_cap else {},
            "financials": self.company_financials(symbol),
            "quote": self._quote_to_snapshot(quote),
            "data_sources": result.get("sources") or ["MCP-TOOLS"],
            "provider_status": "MCP-TOOLS get_stock_quote response.",
        }
        if not yahoo_profile:
            return mcp_profile

        merged = dict(yahoo_profile)
        mcp_snapshot = self._quote_to_snapshot(quote, fallback_ticker=requested_symbol)
        if mcp_snapshot.get("price") is not None:
            merged["quote"] = mcp_snapshot
        merged["provider_status"] = (
            "Fundamentals, profile details, history, news, and earnings are enriched from Yahoo Finance/local "
            "Indian fallbacks. MCP-TOOLS is used only when its live quote contains usable price data."
        )
        merged["data_sources"] = list(dict.fromkeys([*(yahoo_profile.get("data_sources") or ["Yahoo Finance"]), "MCP-TOOLS"]))
        metrics = dict(yahoo_profile.get("metrics", {}))
        if market_cap:
            metrics["market_cap"] = self._format_large_number(market_cap) or metrics.get("market_cap", "N/A")
        merged["metrics"] = metrics
        return merged

    def company_financials(self, ticker: str) -> dict[str, Any]:
        try:
            return self.yahoo.financials(ticker)
        except Exception:
            pass
        return {
            "ticker": ticker.upper(),
            "revenue_growth": 0.0,
            "gross_margin": 0.0,
            "net_margin": 0.0,
            "source": "MCP-TOOLS get_stock_quote does not provide financial statements.",
        }

    def competitor_analysis(self, ticker: str) -> list[str]:
        try:
            return self.company_profile(ticker)["competitors"]
        except Exception:
            return []

    def latest_news(self, ticker: str) -> list[dict[str, Any]]:
        try:
            news = self.yahoo.latest_news(ticker)
            if news:
                return news
        except Exception:
            pass
        try:
            result = self._call("stock_research", {"question": f"latest market news and updates for {ticker}"})
        except Exception as exc:
            return [
                {
                    "title": f"{ticker.upper()} news unavailable",
                    "source": "MCP-TOOLS unavailable",
                    "summary": f"Recent news could not be retrieved from MCP-TOOLS: {exc}",
                    "url": None,
                }
            ]
        return [
            {
                "title": f"{ticker.upper()} MCP market update",
                "source": ", ".join(result.get("sources", [])) or "MCP-TOOLS",
                "summary": result.get("answer") or f"No recent MCP news summary was returned for {ticker.upper()}.",
                "url": None,
            }
        ]

    def latest_earnings(self, ticker: str) -> dict[str, Any]:
        try:
            return self.yahoo.latest_earnings(ticker)
        except Exception:
            pass
        try:
            result = self._call("stock_research", {"question": f"earnings, financials, and risks for {ticker}"})
        except Exception as exc:
            return {
                "quarter": "Latest earnings unavailable",
                "guidance": f"MCP-TOOLS earnings research could not be retrieved for {ticker.upper()}: {exc}",
                "risks": ["MCP-TOOLS is unavailable, so document-backed earnings evidence was skipped."],
            }
        return {
            "quarter": "Latest MCP stock research",
            "guidance": result.get("answer") or f"MCP-TOOLS did not return earnings details for {ticker.upper()}.",
            "risks": ["Dedicated earnings calendar data is not exposed by the deployed MCP-TOOLS server."],
        }

    def search_documents(self, query: str) -> list[Any]:
        try:
            body = self._call("finpilot_rag_search_documents", {"query": query, "limit": 5})
        except Exception:
            return self._search_s3_methodology_documents(query)
        if isinstance(body, str):
            body = json.loads(body)
        if not isinstance(body, dict):
            return self._search_s3_methodology_documents(query)
        if body.get("ok") is False:
            return self._search_s3_methodology_documents(query)
        evidence = body.get("evidence")
        if isinstance(evidence, list):
            return evidence or self._search_s3_methodology_documents(query)
        data = body.get("data") if isinstance(body.get("data"), dict) else {}
        documents = [
            {
                "source": match.get("source") or "FinPilot RAG",
                "title": match.get("title") or "Retrieved document chunk",
                "excerpt": match.get("excerpt") or "",
                "url": match.get("source"),
                "reliability": "high",
            }
            for match in data.get("matches", [])
            if isinstance(match, dict)
        ]
        return documents or self._search_s3_methodology_documents(query)

    def _search_s3_methodology_documents(self, query: str) -> list[dict[str, Any]]:
        if not self._looks_like_methodology_query(query):
            return []
        key = "finpilot_scoring_and_recommendation_rules.pdf"
        text = self._read_s3_pdf_text(key)
        if not text:
            return []
        excerpt = self._best_excerpt(text, query)
        return [
            {
                "source": f"s3://{self.settings.rag_s3_bucket}/{key}",
                "title": "FinPilot Scoring and Recommendation Rules",
                "excerpt": excerpt,
                "url": f"s3://{self.settings.rag_s3_bucket}/{key}",
                "reliability": "high",
            }
        ]

    def _read_s3_pdf_text(self, key: str) -> str:
        try:
            response = boto3.client("s3", region_name=self.settings.aws_region).get_object(
                Bucket=self.settings.rag_s3_bucket,
                Key=key,
            )
            payload = response["Body"].read()
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(payload))
            return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except Exception:
            return ""

    def _looks_like_methodology_query(self, query: str) -> bool:
        lowered = query.lower()
        return any(
            term in lowered
            for term in (
                "recommend",
                "recommendation",
                "score",
                "scoring",
                "signal",
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

    def _best_excerpt(self, text: str, query: str, max_chars: int = 900) -> str:
        terms = {term for term in query.lower().replace(",", " ").split() if len(term) > 3}
        paragraphs = [part.strip() for part in text.split("\n") if part.strip()]
        ranked = sorted(
            paragraphs,
            key=lambda paragraph: sum(1 for term in terms if term in paragraph.lower()),
            reverse=True,
        )
        excerpt = " ".join(ranked[:4] or paragraphs[:4])
        return excerpt[:max_chars].strip()

    def market_snapshot(self, ticker: str) -> dict[str, Any]:
        try:
            yahoo_snapshot = self.yahoo.quote(ticker)
        except Exception:
            yahoo_snapshot = None
        try:
            result = self._quote_lookup(ticker)
            mcp_snapshot = self._quote_to_snapshot(result.get("quote", {}), fallback_ticker=ticker.upper())
        except Exception:
            mcp_snapshot = None
        if mcp_snapshot and mcp_snapshot.get("price") is not None:
            return mcp_snapshot
        if yahoo_snapshot:
            return yahoo_snapshot
        return mcp_snapshot or self._quote_to_snapshot({}, fallback_ticker=ticker.upper())

    def price_history(self, ticker: str, horizon: str) -> dict[str, Any]:
        try:
            history = self.yahoo.price_history(ticker, horizon)
            history = dict(history)
            history["source"] = f"{history.get('source', 'Yahoo Finance')} (MCP-TOOLS quote endpoint has no candles)"
            return history
        except Exception:
            pass
        snapshot = self.market_snapshot(ticker)
        price = snapshot.get("price") or snapshot.get("previous_close") or 0.0
        previous_close = snapshot.get("previous_close") or price
        change = price - previous_close
        change_percent = change / previous_close if previous_close else 0.0
        today = datetime.now(UTC).date().isoformat()
        exchange = snapshot.get("exchange") or self._exchange_for_ticker(ticker)
        return {
            "ticker": snapshot.get("ticker") or ticker.upper(),
            "horizon": horizon,
            "currency": snapshot.get("currency") or "USD",
            "exchange": exchange,
            "start_date": today,
            "end_date": today,
            "start_price": previous_close,
            "end_price": price,
            "change": change,
            "change_percent": change_percent,
            "period_low": min(price, previous_close),
            "period_high": max(price, previous_close),
            "points": [
                {"date": today, "close": previous_close},
                {"date": today, "close": price},
            ],
            "source": "MCP-TOOLS get_stock_quote latest and previous close",
        }

    def market_status(self) -> dict[str, Any]:
        return {"is_open": True, "exchange": "MCP-TOOLS", "mode": self.settings.data_mode}

    def buying_power(self) -> float:
        return 25000.0

    def top_stocks(self, market: str, limit: int = 10) -> dict[str, Any]:
        symbols = self._top_stock_symbols(market)[:limit]
        rows = []
        for symbol in symbols:
            try:
                snapshot = self.market_snapshot(symbol)
                profile = self.company_profile(symbol)
                rows.append(
                    {
                        "ticker": snapshot.get("ticker") or symbol,
                        "company": profile.get("name") or symbol,
                        "price": snapshot.get("price"),
                        "previous_close": snapshot.get("previous_close"),
                        "change": snapshot.get("change"),
                        "change_percent": snapshot.get("change_percent"),
                        "currency": snapshot.get("currency") or ("INR" if market.lower() == "india" else "USD"),
                        "market_cap": profile.get("market_cap_display") or "N/A",
                        "sector": profile.get("sector") or "Unknown",
                        "industry": profile.get("industry") or "Unknown",
                        "exchange": snapshot.get("exchange") or "Unknown",
                        "source": snapshot.get("source") or "MCP-TOOLS",
                        "status": "Live",
                    }
                )
            except Exception as exc:
                rows.append(
                    {
                        "ticker": symbol,
                        "company": symbol,
                        "price": None,
                        "previous_close": None,
                        "change": None,
                        "change_percent": None,
                        "currency": "INR" if market.lower() == "india" else "USD",
                        "market_cap": "N/A",
                        "sector": "Unknown",
                        "industry": "Unknown",
                        "exchange": "Unknown",
                        "source": "MCP-TOOLS",
                        "status": f"Unavailable: {exc}",
                    }
                )
        return {"market": market, "timestamp": datetime.now(UTC).isoformat(), "rows": rows}

    def _quote_lookup(self, ticker_or_company: str) -> dict[str, Any]:
        return self._call("get_stock_quote", {"ticker_or_company": ticker_or_company})

    def _quote_to_snapshot(self, quote: dict[str, Any], fallback_ticker: str = "UNKNOWN") -> dict[str, Any]:
        ticker = self._best_symbol(fallback_ticker, quote.get("ticker"))
        price = self._as_float(quote.get("price"))
        previous_close = self._as_float(quote.get("previous_close"))
        change = price - previous_close if price is not None and previous_close is not None else None
        change_percent = change / previous_close if change is not None and previous_close else None
        return {
            "ticker": ticker,
            "price": price,
            "previous_close": previous_close,
            "change": change,
            "change_percent": change_percent,
            "day_high": None,
            "day_low": None,
            "volume": None,
            "currency": quote.get("currency") or "USD",
            "exchange": self._exchange_for_ticker(ticker),
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "MCP-TOOLS get_stock_quote",
        }

    def _call(self, tool: str, payload: dict[str, Any]) -> Any:
        if self._mcp_unavailable_reason:
            raise RuntimeError(self._mcp_unavailable_reason)
        try:
            with requests.Session() as session:
                with session.get(
                    self.tool_url,
                    headers={"Accept": "text/event-stream"},
                    stream=True,
                    timeout=self.timeout,
                ) as event_stream:
                    event_stream.raise_for_status()
                    events = self._iter_sse_events(event_stream)
                    messages_url = self._read_sse_endpoint(events)

                    request_id = 1
                    self._post_json_rpc(
                        session,
                        messages_url,
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "initialize",
                            "params": {
                                "protocolVersion": "2024-11-05",
                                "capabilities": {},
                                "clientInfo": {"name": "finpilot", "version": "1.0.0"},
                            },
                        },
                    )
                    self._read_json_rpc_result(events, request_id)

                    self._post_json_rpc(
                        session,
                        messages_url,
                        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
                    )

                    request_id += 1
                    self._post_json_rpc(
                        session,
                        messages_url,
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "method": "tools/call",
                            "params": {"name": tool, "arguments": payload},
                        },
                    )
                    result = self._read_json_rpc_result(events, request_id)
                    return self._extract_tool_result(tool, result)
        except requests.RequestException as exc:
            self._mcp_unavailable_reason = f"MCP-TOOLS unavailable at {self.tool_url}: {exc}"
            raise RuntimeError(self._mcp_unavailable_reason) from exc

    def _read_sse_endpoint(self, events: Iterator[dict[str, str]]) -> str:
        for event in events:
            if event.get("event") == "endpoint" and event.get("data"):
                return self._normalize_message_url(urljoin(self.tool_url, event["data"]))
        raise RuntimeError(f"MCP SSE endpoint was not announced by {self.tool_url}.")

    def _read_json_rpc_result(self, events: Iterator[dict[str, str]], request_id: int) -> Any:
        for event in events:
            if event.get("event") not in {"message", None} or not event.get("data"):
                continue
            message = json.loads(event["data"])
            if message.get("id") != request_id:
                continue
            if message.get("error"):
                error = message["error"]
                raise RuntimeError(error.get("message") or f"MCP request {request_id} failed.")
            return message.get("result")
        raise RuntimeError(f"MCP request {request_id} did not return a result.")

    def _iter_sse_events(self, response: requests.Response):
        event: dict[str, str] = {}
        data_lines: list[str] = []
        for raw_line in response.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue
            line = raw_line.strip()
            if not line:
                if event or data_lines:
                    if data_lines:
                        event["data"] = "\n".join(data_lines)
                    yield event
                    event = {}
                    data_lines = []
                continue
            if line.startswith(":"):
                continue
            field, _, value = line.partition(":")
            value = value.lstrip()
            if field == "event":
                event["event"] = value
            elif field == "data":
                data_lines.append(value)

    def _post_json_rpc(self, session: requests.Session, messages_url: str, body: dict[str, Any]) -> None:
        urls = [messages_url, *self._alternate_message_urls(messages_url)]
        last_error: requests.HTTPError | None = None
        for url in urls:
            response = session.post(url, json=body, timeout=self.timeout)
            try:
                response.raise_for_status()
                return
            except requests.HTTPError as exc:
                if response.status_code == 404 and url != urls[-1]:
                    last_error = exc
                    continue
                raise
        if last_error:
            raise last_error

    def _normalize_message_url(self, messages_url: str) -> str:
        parsed = urlsplit(messages_url)
        if parsed.path.endswith("/"):
            path = parsed.path.rstrip("/")
            if path:
                return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))
        return messages_url

    def _alternate_message_urls(self, messages_url: str) -> list[str]:
        parsed = urlsplit(messages_url)
        if not parsed.path.endswith("/"):
            return []
        path = parsed.path.rstrip("/")
        if not path:
            return []
        return [urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))]

    def _extract_tool_result(self, tool: str, result: Any) -> Any:
        if not isinstance(result, dict):
            return result
        if result.get("isError"):
            raise RuntimeError(f"MCP tool {tool} failed.")
        if "structuredContent" in result:
            return result["structuredContent"]
        if "data" in result:
            return result["data"]

        content = result.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and first.get("type") == "text":
                text = first.get("text", "")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
        return result

    def _normalize_tool_url(self, value: str) -> str:
        url = value.strip().rstrip("/")
        parsed = urlparse(url)
        if not parsed.path:
            return f"{url}/sse"
        return url

    def _exchange_for_ticker(self, ticker: str, market: str | None = None) -> str:
        symbol = ticker.upper()
        if symbol.endswith(".NS"):
            return "NSE"
        if symbol.endswith(".BO"):
            return "BSE"
        if market and market.lower() == "india":
            return "NSE/BSE"
        return "NASDAQ/NYSE"

    def _best_symbol(self, requested_symbol: str, mcp_symbol: Any) -> str:
        requested = requested_symbol.upper()
        candidate = str(mcp_symbol or "").strip().upper()
        if requested.endswith((".NS", ".BO")):
            return requested
        return candidate or requested

    def _market_cap_bucket(self, market_cap: Any) -> str:
        value = self._as_float(market_cap)
        if value is None:
            return "N/A"
        if value >= 200_000_000_000:
            return "Mega Cap"
        if value >= 10_000_000_000:
            return "Large Cap"
        if value >= 2_000_000_000:
            return "Mid Cap"
        return "Small Cap"

    def _format_large_number(self, value: Any) -> str | None:
        number = self._as_float(value)
        if number is None:
            return None
        for suffix, divisor in (("T", 1_000_000_000_000), ("B", 1_000_000_000), ("M", 1_000_000)):
            if abs(number) >= divisor:
                return f"{number / divisor:.2f}{suffix}"
        return f"{number:,.0f}"

    def _as_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _top_stock_symbols(self, market: str) -> list[str]:
        if market.lower() == "us":
            return ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA", "LLY", "JPM"]
        return [
            "RELIANCE.NS",
            "TCS.NS",
            "HDFCBANK.NS",
            "ICICIBANK.NS",
            "BHARTIARTL.NS",
            "SBIN.NS",
            "INFY.NS",
            "LICI.NS",
            "ITC.NS",
            "HINDUNILVR.NS",
        ]
