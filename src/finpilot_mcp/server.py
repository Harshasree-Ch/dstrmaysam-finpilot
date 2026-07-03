from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from finpilot.core.runtime import add_workspace_venv_site_packages
from finpilot.core.settings import Settings
from finpilot_mcp.data.yahoo_finance import YahooFinanceClient


class FinancialIntelligenceServer:
    """Centralized facade for every external financial interaction."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._yahoo: YahooFinanceClient | None = None
        self._groww_client: Any | None = None

    @property
    def yahoo(self) -> YahooFinanceClient:
        if self._yahoo is None:
            self._yahoo = YahooFinanceClient()
        return self._yahoo

    @property
    def groww_client(self) -> Any:
        if self._groww_client is None:
            if not self.settings.groww_api_key or not self.settings.groww_secret_key:
                raise RuntimeError("Groww API key and secret are not configured.")
            add_workspace_venv_site_packages()
            from growwapi import GrowwAPI

            access_token = GrowwAPI.get_access_token(
                api_key=self.settings.groww_api_key,
                secret=self.settings.groww_secret_key,
            )
            self._groww_client = GrowwAPI(access_token)
        return self._groww_client

    def resolve_symbol(self, query: str, market: str | None = None) -> dict:
        return self.yahoo.resolve_symbol(query, market=market)

    def company_profile(self, ticker: str) -> dict:
        profile = self.yahoo.company_profile(ticker)
        return self._enrich_profile_with_groww(ticker, profile)

    def company_financials(self, ticker: str) -> dict:
        return self.yahoo.financials(ticker)

    def competitor_analysis(self, ticker: str) -> list[str]:
        return self.company_profile(ticker)["competitors"]

    def latest_news(self, ticker: str) -> list[dict]:
        return self.yahoo.latest_news(ticker)

    def latest_earnings(self, ticker: str) -> dict:
        return self.yahoo.latest_earnings(ticker)

    def search_documents(self, query: str) -> list[dict[str, Any]]:
        return []

    def market_snapshot(self, ticker: str) -> dict:
        quote = self.yahoo.quote(ticker)
        return self._enrich_quote_with_groww(ticker, quote)

    def top_stocks(self, market: str, limit: int = 10) -> dict:
        symbols = self._top_stock_symbols(market)[:limit]
        rows = []
        for symbol in symbols:
            try:
                snapshot = self.market_snapshot(symbol)
                profile = self.company_profile(symbol)
                metrics = profile.get("metrics", {})
                rows.append(
                    {
                        "ticker": symbol,
                        "company": profile.get("name") or symbol,
                        "price": snapshot.get("price"),
                        "previous_close": snapshot.get("previous_close"),
                        "change": snapshot.get("change"),
                        "change_percent": snapshot.get("change_percent"),
                        "currency": snapshot.get("currency") or ("INR" if market.lower() == "india" else "USD"),
                        "market_cap": metrics.get("market_cap") or profile.get("market_cap_display") or "N/A",
                        "sector": profile.get("sector") or "Unknown",
                        "industry": profile.get("industry") or "Unknown",
                        "exchange": snapshot.get("exchange") or metrics.get("exchange") or "Unknown",
                        "source": snapshot.get("source") or "Yahoo Finance",
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
                        "source": "Unavailable",
                        "status": f"Unavailable: {exc}",
                    }
                )
        return {
            "market": market,
            "timestamp": datetime.now(UTC).isoformat(),
            "rows": rows,
        }

    def price_history(self, ticker: str, horizon: str) -> dict:
        return self.yahoo.price_history(ticker, horizon)

    def market_status(self) -> dict:
        return {"is_open": True, "exchange": "NSE/BSE", "mode": self.settings.data_mode}

    def buying_power(self) -> float:
        return 25000.0

    def _enrich_profile_with_groww(self, ticker: str, profile: dict) -> dict:
        enriched = dict(profile)
        metrics = dict(enriched.get("metrics", {}))
        metric_sources = dict(enriched.get("metric_sources", {}))
        for key, value in metrics.items():
            if not self._metric_is_missing(value):
                metric_sources.setdefault(key, "Yahoo Finance")
        if not ticker.upper().endswith((".NS", ".BO")):
            enriched["metrics"] = metrics
            enriched["metric_sources"] = metric_sources
            enriched["provider_status"] = "Yahoo checked. Groww enrichment applies only to NSE/BSE tickers."
            enriched["data_sources"] = ["Yahoo Finance"]
            return enriched

        exchange = self._groww_exchange_name(ticker)
        trading_symbol = self._groww_trading_symbol(ticker)

        self._set_metric_if_empty(metrics, "market_cap", "Unavailable from Groww/Yahoo", metric_sources, "Provider status")
        self._set_metric_if_empty(metrics, "exchange", exchange, metric_sources, "Ticker")
        self._set_metric_if_empty(metrics, "trading_symbol", trading_symbol, metric_sources, "Ticker")

        instrument: dict[str, Any] = {}
        quote: dict[str, Any] = {}
        groww_errors = []
        if not self._can_use_groww_market_data(ticker):
            groww_errors.append("Groww API key/secret not configured")
        else:
            try:
                instrument = self._groww_instrument(ticker)
            except Exception as exc:
                groww_errors.append(f"instrument lookup failed: {exc}")
            try:
                quote = self._groww_quote(ticker)
            except Exception as exc:
                groww_errors.append(f"quote lookup failed: {exc}")

        if instrument:
            display_name = self._first_present(
                instrument,
                "company_name",
                "companyName",
                "name",
                "display_name",
                "displayName",
                "groww_name",
                "groww_symbol",
                "trading_symbol",
            )
            if display_name and (not enriched.get("name") or enriched["name"] == enriched.get("ticker")):
                enriched["name"] = display_name

            sector = self._first_present(instrument, "sector", "industry_sector", "macro_sector")
            industry = self._first_present(instrument, "industry", "sub_sector", "micro_sector", "sector")
            if sector and enriched.get("sector") in {None, "", "Unknown"}:
                enriched["sector"] = sector
            if industry and enriched.get("industry") in {None, "", "Unknown"}:
                enriched["industry"] = industry

            self._set_metric_if_empty(
                metrics,
                "groww_symbol",
                self._first_present(instrument, "groww_symbol", "growwSymbol"),
                metric_sources,
                "Groww API",
            )
            self._set_metric_if_empty(
                metrics,
                "isin",
                self._first_present(instrument, "isin", "isin_code", "isinCode"),
                metric_sources,
                "Groww API",
            )
            self._set_metric_if_empty(
                metrics,
                "exchange_token",
                self._first_present(instrument, "exchange_token", "exchangeToken"),
                metric_sources,
                "Groww API",
            )

        if quote:
            self._set_metric_if_empty(
                metrics,
                "ltp",
                self._format_metric_number(self._value_from(quote, "ltp", "last_price", "lastPrice", "close")),
                metric_sources,
                "Groww API",
            )
            self._set_metric_if_empty(
                metrics,
                "open",
                self._format_metric_number(self._value_from(quote, "open", "open_price", "day_open")),
                metric_sources,
                "Groww API",
            )
            self._set_metric_if_empty(
                metrics,
                "high",
                self._format_metric_number(self._value_from(quote, "high", "day_high", "high_price")),
                metric_sources,
                "Groww API",
            )
            self._set_metric_if_empty(
                metrics,
                "low",
                self._format_metric_number(self._value_from(quote, "low", "day_low", "low_price")),
                metric_sources,
                "Groww API",
            )
            self._set_metric_if_empty(
                metrics,
                "volume",
                self._format_metric_number(self._value_from(quote, "volume", "day_volume", "total_volume")),
                metric_sources,
                "Groww API",
            )

        if "Realtime quote data was returned" in enriched.get("business_model", ""):
            enriched["business_model"] = (
                f"Yahoo and Groww were checked for {trading_symbol} on {exchange}. "
                "Deep fundamentals such as ROE, P/E, EPS, book value, and dividend yield were not returned "
                "by the current realtime providers."
            )

        enriched["metrics"] = metrics
        enriched["metric_sources"] = metric_sources
        enriched["data_sources"] = ["Yahoo Finance"] + (["Groww API"] if self.settings.groww_api_key and self.settings.groww_secret_key else [])
        if instrument or quote:
            enriched["provider_status"] = "Yahoo checked; Groww enrichment applied."
        elif groww_errors:
            enriched["provider_status"] = "Yahoo checked; Groww enrichment unavailable: " + "; ".join(groww_errors)
        else:
            enriched["provider_status"] = "Yahoo checked; Groww did not return additional fields."
        enriched["groww"] = {
            "source": "Groww API",
            "instrument": instrument,
            "quote": quote,
            "errors": groww_errors,
        }
        return enriched

    def _enrich_quote_with_groww(self, ticker: str, quote: dict) -> dict:
        if not ticker.upper().endswith((".NS", ".BO")):
            return quote
        try:
            groww_quote = self._groww_quote(ticker)
        except Exception:
            enriched = dict(quote)
            enriched["source"] = f"{quote.get('source', 'Yahoo Finance')} (Groww quote unavailable)"
            return enriched

        enriched = dict(quote)
        enriched["source"] = "Yahoo Finance + Groww API"
        enriched["exchange"] = self._groww_exchange_name(ticker)
        enriched["price"] = self._first_number(
            self._value_from(groww_quote, "ltp", "last_price", "lastPrice", "close"),
            enriched.get("price"),
        )
        enriched["day_high"] = self._first_number(self._value_from(groww_quote, "high", "day_high"), enriched.get("day_high"))
        enriched["day_low"] = self._first_number(self._value_from(groww_quote, "low", "day_low"), enriched.get("day_low"))
        enriched["volume"] = self._first_number(self._value_from(groww_quote, "volume", "day_volume"), enriched.get("volume"))
        return enriched

    def _can_use_groww_market_data(self, ticker: str) -> bool:
        return ticker.upper().endswith((".NS", ".BO")) and bool(self.settings.groww_api_key and self.settings.groww_secret_key)

    def _groww_quote(self, ticker: str) -> dict:
        groww = self.groww_client
        return groww.get_quote(
            trading_symbol=self._groww_trading_symbol(ticker),
            exchange=self._groww_exchange_value(groww, ticker),
            segment=groww.SEGMENT_CASH,
            timeout=8,
        )

    def _groww_instrument(self, ticker: str) -> dict:
        groww = self.groww_client
        return groww.get_instrument_by_exchange_and_trading_symbol(
            exchange=self._groww_exchange_value(groww, ticker),
            trading_symbol=self._groww_trading_symbol(ticker),
        )

    def _groww_trading_symbol(self, ticker: str) -> str:
        symbol = ticker.upper().strip()
        for suffix in (".NS", ".BO"):
            if symbol.endswith(suffix):
                return symbol[: -len(suffix)]
        return symbol

    def _groww_exchange_value(self, groww: Any, ticker: str) -> str:
        return groww.EXCHANGE_BSE if ticker.upper().strip().endswith(".BO") else groww.EXCHANGE_NSE

    def _groww_exchange_name(self, ticker: str) -> str:
        return "BSE" if ticker.upper().strip().endswith(".BO") else "NSE"

    def _first_present(self, data: dict, *keys: str) -> str | None:
        for key in keys:
            value = data.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    def _value_from(self, data: dict, *keys: str) -> Any:
        for key in keys:
            value = data.get(key)
            if value is not None:
                return value
        return None

    def _set_metric_if_empty(
        self,
        metrics: dict,
        key: str,
        value: Any,
        metric_sources: dict | None = None,
        source: str | None = None,
    ) -> None:
        if value is None or value == "":
            return
        if self._metric_is_missing(metrics.get(key)):
            metrics[key] = str(value)
            if metric_sources is not None and source:
                metric_sources[key] = source

    def _metric_is_missing(self, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            return value.strip() in {"", "N/A", "Unknown", "Unavailable from Groww/Yahoo"}
        return False

    def _format_metric_number(self, value: Any) -> str | None:
        number = self._first_number(value)
        if number is None:
            return None
        return f"{number:,.2f}"

    def _first_number(self, *values: Any) -> float | None:
        for value in values:
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
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
