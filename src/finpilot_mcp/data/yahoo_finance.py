from __future__ import annotations

from datetime import UTC, datetime, timedelta
from html import unescape
import re
from typing import Any
from xml.etree import ElementTree

import requests


class YahooFinanceClient:
    """Thin Yahoo Finance HTTP adapter used by the financial data facade."""

    COMPANY_FALLBACKS: dict[str, dict[str, Any]] = {
        "RELIANCE.NS": {
            "sector": "Energy",
            "industry": "Oil & Gas Refining and Marketing",
            "market_cap": "Large Cap",
            "market_cap_display": "19.50T",
            "employees": "347,362",
            "business_model": (
                "Integrated Indian conglomerate spanning oil-to-chemicals, energy, retail, "
                "telecom, digital services, and new energy investments."
            ),
            "financials": {"revenue_growth": 0.08, "gross_margin": 0.34, "net_margin": 0.09, "debt_to_equity": 0.38},
            "metrics": {
                "market_cap": "19.50T",
                "roe": "8.80%",
                "pe_ratio_ttm": "24.50",
                "eps_ttm": "52.80",
                "pb_ratio": "2.20",
                "dividend_yield": "0.35%",
                "industry_pe": "17.80",
                "book_value": "585.00",
                "debt_to_equity": "0.38",
                "face_value": "10",
            },
            "competitors": ["Indian Oil", "Bharti Airtel", "Adani Enterprises", "Tata Consumer"],
        },
        "TCS.NS": {
            "sector": "Technology",
            "industry": "Information Technology Services",
            "market_cap": "Large Cap",
            "market_cap_display": "14.20T",
            "employees": "607,979",
            "business_model": "IT services, consulting, outsourcing, and digital transformation services.",
            "financials": {"revenue_growth": 0.07, "gross_margin": 0.43, "net_margin": 0.19, "debt_to_equity": 0.08},
            "metrics": {
                "market_cap": "14.20T",
                "roe": "49.00%",
                "pe_ratio_ttm": "30.20",
                "eps_ttm": "128.50",
                "pb_ratio": "14.80",
                "dividend_yield": "1.40%",
                "industry_pe": "28.00",
                "book_value": "260.00",
                "debt_to_equity": "0.08",
                "face_value": "1",
            },
            "competitors": ["Infosys", "Wipro", "HCLTech", "Tech Mahindra"],
        },
        "INFY.NS": {
            "sector": "Technology",
            "industry": "Information Technology Services",
            "market_cap": "Large Cap",
            "market_cap_display": "6.40T",
            "employees": "317,240",
            "business_model": "Digital services, consulting, cloud, engineering, and business process outsourcing.",
            "financials": {"revenue_growth": 0.06, "gross_margin": 0.38, "net_margin": 0.17, "debt_to_equity": 0.08},
            "metrics": {
                "market_cap": "6.40T",
                "roe": "31.00%",
                "pe_ratio_ttm": "24.20",
                "eps_ttm": "64.00",
                "pb_ratio": "7.40",
                "dividend_yield": "2.40%",
                "industry_pe": "28.00",
                "book_value": "210.00",
                "debt_to_equity": "0.08",
                "face_value": "5",
            },
            "competitors": ["TCS", "Wipro", "HCLTech", "Tech Mahindra"],
        },
        "HDFCBANK.NS": {
            "sector": "Financial Services",
            "industry": "Banks - Regional",
            "market_cap": "Large Cap",
            "market_cap_display": "12.50T",
            "employees": "213,000",
            "business_model": "Private-sector bank offering retail banking, wholesale banking, payments, and treasury services.",
            "financials": {"revenue_growth": 0.1, "gross_margin": 0.0, "net_margin": 0.22, "debt_to_equity": 0.0},
            "metrics": {
                "market_cap": "12.50T",
                "roe": "14.50%",
                "pe_ratio_ttm": "19.20",
                "eps_ttm": "86.00",
                "pb_ratio": "2.75",
                "dividend_yield": "1.10%",
                "industry_pe": "14.80",
                "book_value": "600.00",
                "debt_to_equity": "N/A",
                "face_value": "1",
            },
            "competitors": ["ICICI Bank", "Axis Bank", "Kotak Mahindra Bank", "State Bank of India"],
        },
        "ICICIBANK.NS": {
            "sector": "Financial Services",
            "industry": "Banks - Regional",
            "market_cap": "Large Cap",
            "market_cap_display": "8.60T",
            "employees": "164,000",
            "business_model": "Private-sector bank with retail, corporate, wealth, insurance, and treasury operations.",
            "financials": {"revenue_growth": 0.1, "gross_margin": 0.0, "net_margin": 0.2, "debt_to_equity": 0.0},
            "metrics": {
                "market_cap": "8.60T",
                "roe": "16.50%",
                "pe_ratio_ttm": "18.80",
                "eps_ttm": "66.00",
                "pb_ratio": "3.05",
                "dividend_yield": "0.80%",
                "industry_pe": "14.80",
                "book_value": "405.00",
                "debt_to_equity": "N/A",
                "face_value": "2",
            },
            "competitors": ["HDFC Bank", "Axis Bank", "Kotak Mahindra Bank", "State Bank of India"],
        },
        "SBIN.NS": {
            "sector": "Financial Services",
            "industry": "Banks - Regional",
            "market_cap": "Large Cap",
            "market_cap_display": "7.20T",
            "employees": "232,296",
            "business_model": "Public-sector banking group with retail, corporate, treasury, insurance, and asset-management operations.",
            "financials": {"revenue_growth": 0.09, "gross_margin": 0.0, "net_margin": 0.15, "debt_to_equity": 0.0},
            "metrics": {
                "market_cap": "7.20T",
                "roe": "17.00%",
                "pe_ratio_ttm": "9.50",
                "eps_ttm": "84.00",
                "pb_ratio": "1.55",
                "dividend_yield": "1.70%",
                "industry_pe": "10.80",
                "book_value": "515.00",
                "debt_to_equity": "N/A",
                "face_value": "1",
            },
            "competitors": ["HDFC Bank", "ICICI Bank", "Bank of Baroda", "Punjab National Bank"],
        },
        "BHARTIARTL.NS": {
            "sector": "Communication Services",
            "industry": "Telecom Services",
            "market_cap": "Large Cap",
            "business_model": "Telecom operator providing mobile, broadband, enterprise connectivity, data centers, and digital services.",
            "financials": {"revenue_growth": 0.11, "gross_margin": 0.5, "net_margin": 0.08, "debt_to_equity": 1.2},
            "metrics": {"debt_to_equity": "1.20"},
            "competitors": ["Reliance Jio", "Vodafone Idea", "Tata Communications"],
        },
        "ITC.NS": {
            "sector": "Consumer Defensive",
            "industry": "Tobacco and Packaged Foods",
            "market_cap": "Large Cap",
            "business_model": "Diversified consumer company across cigarettes, FMCG, hotels, paperboards, packaging, and agribusiness.",
            "financials": {"revenue_growth": 0.07, "gross_margin": 0.57, "net_margin": 0.27, "debt_to_equity": 0.01},
            "metrics": {"debt_to_equity": "0.01"},
            "competitors": ["Hindustan Unilever", "Nestle India", "Godfrey Phillips", "Dabur"],
        },
        "TATAMOTORS.NS": {
            "sector": "Consumer Cyclical",
            "industry": "Auto Manufacturers",
            "market_cap": "Large Cap",
            "business_model": "Automaker selling passenger vehicles, commercial vehicles, electric vehicles, and Jaguar Land Rover models.",
            "financials": {"revenue_growth": 0.12, "gross_margin": 0.36, "net_margin": 0.08, "debt_to_equity": 1.1},
            "metrics": {"debt_to_equity": "1.10"},
            "competitors": ["Mahindra & Mahindra", "Maruti Suzuki", "Ashok Leyland", "Hyundai Motor India"],
        },
        "WIPRO.NS": {
            "sector": "Technology",
            "industry": "Information Technology Services",
            "market_cap": "Large Cap",
            "business_model": "IT services and consulting company focused on cloud, engineering, cybersecurity, AI, and business transformation.",
            "financials": {"revenue_growth": 0.04, "gross_margin": 0.31, "net_margin": 0.13, "debt_to_equity": 0.12},
            "metrics": {"debt_to_equity": "0.12"},
            "competitors": ["TCS", "Infosys", "HCLTech", "Tech Mahindra"],
        },
        "HINDUNILVR.NS": {
            "sector": "Consumer Defensive",
            "industry": "Household and Personal Products",
            "market_cap": "Large Cap",
            "business_model": "Consumer goods company selling home care, beauty, personal care, foods, refreshments, and health products.",
            "financials": {"revenue_growth": 0.06, "gross_margin": 0.5, "net_margin": 0.17, "debt_to_equity": 0.03},
            "metrics": {"debt_to_equity": "0.03"},
            "competitors": ["ITC", "Nestle India", "Dabur", "Godrej Consumer Products"],
        },
        "AAPL": {
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "market_cap": "Mega Cap",
            "market_cap_display": "Mega Cap",
            "business_model": "Apple designs, manufactures, and markets smartphones, personal computers, tablets, wearables, accessories, software, and services.",
            "financials": {"revenue_growth": 0.03, "gross_margin": 0.46, "net_margin": 0.24, "debt_to_equity": 1.2},
            "metrics": {
                "market_cap": "Mega Cap",
                "roe": "N/A",
                "pe_ratio_ttm": "30.00",
                "eps_ttm": "N/A",
                "pb_ratio": "N/A",
                "dividend_yield": "0.50%",
                "industry_pe": "N/A",
                "book_value": "N/A",
                "debt_to_equity": "1.20",
            },
            "competitors": ["Samsung", "Microsoft", "Alphabet", "Dell"],
        },
        "MSFT": {
            "sector": "Technology",
            "industry": "Software - Infrastructure",
            "market_cap": "Mega Cap",
            "market_cap_display": "Mega Cap",
            "business_model": "Microsoft provides cloud infrastructure, productivity software, operating systems, developer tools, gaming, devices, and AI platforms.",
            "financials": {"revenue_growth": 0.12, "gross_margin": 0.69, "net_margin": 0.35, "debt_to_equity": 0.3},
            "metrics": {
                "market_cap": "Mega Cap",
                "roe": "N/A",
                "pe_ratio_ttm": "34.00",
                "eps_ttm": "N/A",
                "pb_ratio": "N/A",
                "dividend_yield": "0.70%",
                "industry_pe": "N/A",
                "book_value": "N/A",
                "debt_to_equity": "0.30",
            },
            "competitors": ["Amazon", "Alphabet", "Oracle", "Salesforce"],
        },
        "NVDA": {
            "sector": "Technology",
            "industry": "Semiconductors",
            "market_cap": "Mega Cap",
            "market_cap_display": "Mega Cap",
            "business_model": "NVIDIA designs GPUs, accelerated computing platforms, networking products, and AI infrastructure solutions.",
            "financials": {"revenue_growth": 0.8, "gross_margin": 0.72, "net_margin": 0.48, "debt_to_equity": 0.2},
            "metrics": {
                "market_cap": "Mega Cap",
                "roe": "N/A",
                "pe_ratio_ttm": "N/A",
                "eps_ttm": "N/A",
                "pb_ratio": "N/A",
                "dividend_yield": "0.03%",
                "industry_pe": "N/A",
                "book_value": "N/A",
                "debt_to_equity": "0.20",
            },
            "competitors": ["AMD", "Intel", "Broadcom", "Qualcomm"],
        },
        "AMZN": {
            "sector": "Consumer Cyclical",
            "industry": "Internet Retail",
            "market_cap": "Mega Cap",
            "market_cap_display": "Mega Cap",
            "business_model": "Amazon operates ecommerce marketplaces, logistics, digital advertising, subscriptions, devices, and Amazon Web Services cloud infrastructure.",
            "financials": {"revenue_growth": 0.11, "gross_margin": 0.48, "net_margin": 0.09, "debt_to_equity": 0.6},
            "metrics": {
                "market_cap": "Mega Cap",
                "roe": "N/A",
                "pe_ratio_ttm": "N/A",
                "eps_ttm": "N/A",
                "pb_ratio": "N/A",
                "dividend_yield": "N/A",
                "industry_pe": "N/A",
                "book_value": "N/A",
                "debt_to_equity": "0.60",
            },
            "competitors": ["Walmart", "Microsoft", "Alphabet", "Alibaba"],
        },
        "GOOGL": {
            "sector": "Communication Services",
            "industry": "Internet Content & Information",
            "market_cap": "Mega Cap",
            "market_cap_display": "Mega Cap",
            "business_model": "Alphabet operates Google Search, YouTube, advertising technology, Android, Google Cloud, and other digital platforms.",
            "financials": {"revenue_growth": 0.12, "gross_margin": 0.58, "net_margin": 0.25, "debt_to_equity": 0.1},
            "metrics": {
                "market_cap": "Mega Cap",
                "roe": "N/A",
                "pe_ratio_ttm": "N/A",
                "eps_ttm": "N/A",
                "pb_ratio": "N/A",
                "dividend_yield": "N/A",
                "industry_pe": "N/A",
                "book_value": "N/A",
                "debt_to_equity": "0.10",
            },
            "competitors": ["Meta", "Microsoft", "Amazon", "Apple"],
        },
        "META": {
            "sector": "Communication Services",
            "industry": "Internet Content & Information",
            "market_cap": "Mega Cap",
            "market_cap_display": "Mega Cap",
            "business_model": "Meta operates Facebook, Instagram, WhatsApp, Messenger, advertising platforms, and AI/virtual reality initiatives.",
            "financials": {"revenue_growth": 0.16, "gross_margin": 0.81, "net_margin": 0.32, "debt_to_equity": 0.2},
            "metrics": {
                "market_cap": "Mega Cap",
                "roe": "N/A",
                "pe_ratio_ttm": "N/A",
                "eps_ttm": "N/A",
                "pb_ratio": "N/A",
                "dividend_yield": "0.40%",
                "industry_pe": "N/A",
                "book_value": "N/A",
                "debt_to_equity": "0.20",
            },
            "competitors": ["Alphabet", "TikTok", "Snap", "Pinterest"],
        },
        "TSLA": {
            "sector": "Consumer Cyclical",
            "industry": "Auto Manufacturers",
            "market_cap": "Mega Cap",
            "market_cap_display": "Mega Cap",
            "business_model": "Tesla designs, manufactures, and sells electric vehicles, energy storage products, solar products, charging services, and autonomy software.",
            "financials": {"revenue_growth": 0.05, "gross_margin": 0.18, "net_margin": 0.08, "debt_to_equity": 0.15},
            "metrics": {
                "market_cap": "Mega Cap",
                "roe": "N/A",
                "pe_ratio_ttm": "N/A",
                "eps_ttm": "N/A",
                "pb_ratio": "N/A",
                "dividend_yield": "N/A",
                "industry_pe": "N/A",
                "book_value": "N/A",
                "debt_to_equity": "0.15",
            },
            "competitors": ["BYD", "Toyota", "Ford", "General Motors"],
        },
        "WMT": {
            "sector": "Consumer Defensive",
            "industry": "Discount Stores",
            "market_cap": "Mega Cap",
            "market_cap_display": "Mega Cap",
            "business_model": "Walmart operates retail stores, wholesale clubs, ecommerce marketplaces, advertising, fulfillment, and financial services across major global markets.",
            "financials": {"revenue_growth": 0.05, "gross_margin": 0.24, "net_margin": 0.03, "debt_to_equity": 0.7},
            "metrics": {
                "market_cap": "Mega Cap",
                "roe": "N/A",
                "pe_ratio_ttm": "N/A",
                "eps_ttm": "N/A",
                "pb_ratio": "N/A",
                "dividend_yield": "0.90%",
                "industry_pe": "N/A",
                "book_value": "N/A",
                "debt_to_equity": "0.70",
            },
            "competitors": ["Costco", "Amazon", "Target", "Kroger"],
        },
    }

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
                )
            }
        )

    def resolve_symbol(self, query: str, market: str | None = None) -> dict:
        value = query.strip()
        if not value:
            raise ValueError("Enter a ticker or company name.")

        market_key = (market or "India").lower()
        fallback_symbol = self._common_company_symbol(value, market_key)
        if fallback_symbol:
            quote = self._safe_quote_result(fallback_symbol)
            return {
                "query": query,
                "ticker": fallback_symbol,
                "name": quote.get("longName") or quote.get("shortName") or self._fallback_company_name(fallback_symbol),
                "exchange": quote.get("fullExchangeName") or quote.get("exchange") or "Unknown",
            }

        if self._looks_like_ticker(value):
            for symbol in self._symbol_candidates(value, market_key):
                quote = self._safe_quote_result(symbol)
                if quote:
                    return {
                        "query": query,
                        "ticker": quote.get("symbol") or symbol,
                        "name": quote.get("longName") or quote.get("shortName") or symbol,
                        "exchange": quote.get("fullExchangeName") or quote.get("exchange") or "Unknown",
                    }
                if symbol.upper() in self.COMPANY_FALLBACKS:
                    return {
                        "query": query,
                        "ticker": symbol.upper(),
                        "name": self._fallback_company_name(symbol),
                        "exchange": "NSE" if symbol.upper().endswith(".NS") else "BSE" if symbol.upper().endswith(".BO") else "NASDAQ/NYSE",
                    }

        for symbol in self._symbol_candidates(value, market_key):
            quote = self._safe_quote_result(symbol)
            if quote:
                return {
                    "query": query,
                    "ticker": quote.get("symbol") or symbol,
                    "name": quote.get("longName") or quote.get("shortName") or symbol,
                    "exchange": quote.get("fullExchangeName") or quote.get("exchange") or "Unknown",
                }
            if symbol.upper() in self.COMPANY_FALLBACKS:
                return {
                    "query": query,
                    "ticker": symbol.upper(),
                    "name": self._fallback_company_name(symbol),
                    "exchange": "NSE" if symbol.upper().endswith(".NS") else "BSE" if symbol.upper().endswith(".BO") else "NASDAQ/NYSE",
                }

        search_result = self._search_quote(value)
        if search_result:
            symbol = search_result["symbol"].upper()
            return {
                "query": query,
                "ticker": symbol,
                "name": search_result.get("longname") or search_result.get("shortname") or symbol,
                "exchange": search_result.get("exchDisp") or search_result.get("exchange") or "Unknown",
            }

        raise RuntimeError(f"Could not resolve '{query}' to a supported stock ticker.")

    def quote(self, ticker: str) -> dict:
        symbol = ticker.upper()
        result = self._quote_result(symbol)
        if not result:
            fallback_quote = self._fallback_quote(symbol)
            if fallback_quote:
                return fallback_quote
            raise RuntimeError(f"No Yahoo Finance quote returned for {symbol}.")

        price = self._first_number(result.get("regularMarketPrice"), result.get("postMarketPrice"))
        previous_close = self._first_number(result.get("regularMarketPreviousClose"), result.get("regularMarketOpen"))
        change = self._first_number(result.get("regularMarketChange"))
        change_percent_raw = self._first_number(result.get("regularMarketChangePercent"))
        change_percent = change_percent_raw / 100 if change_percent_raw is not None else None

        if change is None and price is not None and previous_close:
            change = price - previous_close
        if change_percent is None and change is not None and previous_close:
            change_percent = change / previous_close

        return {
            "ticker": symbol,
            "price": price,
            "previous_close": previous_close,
            "change": change,
            "change_percent": change_percent,
            "day_high": self._first_number(result.get("regularMarketDayHigh")),
            "day_low": self._first_number(result.get("regularMarketDayLow")),
            "volume": self._first_number(result.get("regularMarketVolume")),
            "currency": result.get("currency") or "INR",
            "exchange": result.get("fullExchangeName") or result.get("exchange") or "Unknown",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "Yahoo Finance",
        }

    def price_history(self, ticker: str, horizon: str) -> dict:
        symbol = ticker.upper()
        range_value, interval = self._history_window(horizon)
        try:
            response = self.session.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                params={"range": range_value, "interval": interval},
                timeout=self.timeout,
            )
            response.raise_for_status()
            results = response.json().get("chart", {}).get("result", [])
        except (requests.RequestException, ValueError):
            fallback_history = self._fallback_price_history(symbol, horizon, range_value, interval)
            if fallback_history:
                return fallback_history
            raise
        if not results:
            fallback_history = self._fallback_price_history(symbol, horizon, range_value, interval)
            if fallback_history:
                return fallback_history
            raise RuntimeError(f"No realtime price history returned for {symbol}.")

        result = results[0]
        timestamps = result.get("timestamp", [])
        meta = result.get("meta", {})
        quote = result.get("indicators", {}).get("quote", [{}])[0]
        closes = quote.get("close", [])
        highs = quote.get("high", [])
        lows = quote.get("low", [])
        volumes = quote.get("volume", [])

        points = []
        for index, close in enumerate(closes):
            if close is None or index >= len(timestamps):
                continue
            points.append(
                {
                    "date": datetime.fromtimestamp(timestamps[index], UTC).date().isoformat(),
                    "close": float(close),
                    "high": self._first_number(highs[index] if index < len(highs) else None),
                    "low": self._first_number(lows[index] if index < len(lows) else None),
                    "volume": self._first_number(volumes[index] if index < len(volumes) else None),
                }
            )

        if not points:
            fallback_history = self._fallback_price_history(symbol, horizon, range_value, interval)
            if fallback_history:
                return fallback_history
            raise RuntimeError(f"No usable realtime price history returned for {symbol}.")

        start_price = points[0]["close"]
        end_price = points[-1]["close"]
        change = end_price - start_price
        change_percent = change / start_price if start_price else None
        valid_highs = [point["high"] for point in points if point["high"] is not None]
        valid_lows = [point["low"] for point in points if point["low"] is not None]
        valid_volumes = [point["volume"] for point in points if point["volume"] is not None]

        return {
            "ticker": symbol,
            "horizon": horizon,
            "range": range_value,
            "interval": interval,
            "currency": meta.get("currency") or "INR",
            "exchange": meta.get("exchangeName") or meta.get("fullExchangeName") or "Unknown",
            "start_date": points[0]["date"],
            "end_date": points[-1]["date"],
            "start_price": start_price,
            "end_price": end_price,
            "change": change,
            "change_percent": change_percent,
            "period_high": max(valid_highs) if valid_highs else max(point["close"] for point in points),
            "period_low": min(valid_lows) if valid_lows else min(point["close"] for point in points),
            "average_volume": sum(valid_volumes) / len(valid_volumes) if valid_volumes else None,
            "points": points,
            "source": "Yahoo Finance",
        }

    def company_profile(self, ticker: str) -> dict:
        symbol = ticker.upper()
        quote = self._quote_result(symbol)
        if not quote:
            fallback_profile = self._fallback_company_profile(symbol)
            if fallback_profile:
                return fallback_profile
            raise RuntimeError(f"No realtime company data returned for {symbol}.")
        summary = self._quote_summary(symbol)
        fallback_profile = self._stockanalysis_profile(symbol)
        if symbol.endswith((".NS", ".BO")):
            fallback_profile = {**fallback_profile, **self._screener_profile(symbol)}
        fallback_profile = self._merge_company_fallback(symbol, fallback_profile)
        asset_profile = summary.get("assetProfile", {})
        financial_data = summary.get("financialData", {})
        key_statistics = summary.get("defaultKeyStatistics", {})
        price = summary.get("price", {})
        summary_detail = summary.get("summaryDetail", {})

        market_cap_value = self._first_number(
            self._raw_value(price.get("marketCap")),
            quote.get("marketCap"),
        )
        long_name = quote.get("longName") or price.get("longName") or quote.get("shortName") or symbol
        market_cap_display = (
            self._format_large_number(market_cap_value)
            or fallback_profile.get("market_cap_display")
            or fallback_profile.get("market_cap")
        )
        debt_to_equity = self._normalize_debt_to_equity(
            self._first_number(self._raw_value(financial_data.get("debtToEquity")), 0.0) or 0.0
        )
        debt_to_equity_display = self._format_number(debt_to_equity if debt_to_equity else None, fallback_profile.get("debt_to_equity"))
        pe_ratio = self._first_number(
            self._raw_value(summary_detail.get("trailingPE")),
            quote.get("trailingPE"),
            quote.get("forwardPE"),
            fallback_profile.get("pe_ratio_ttm"),
        )
        current_price = self._first_number(quote.get("regularMarketPrice"))
        eps_ttm = self._first_number(
            self._raw_value(key_statistics.get("trailingEps")),
            quote.get("epsTrailingTwelveMonths"),
            quote.get("epsForward"),
            fallback_profile.get("eps_ttm"),
        )
        if eps_ttm is None and pe_ratio and current_price:
            eps_ttm = current_price / pe_ratio
        pb_ratio = self._first_number(
            self._raw_value(key_statistics.get("priceToBook")),
            quote.get("priceToBook"),
            fallback_profile.get("pb_ratio"),
        )
        book_value = self._first_number(
            self._raw_value(key_statistics.get("bookValue")),
            quote.get("bookValue"),
            fallback_profile.get("book_value"),
        )
        dividend_yield = self._first_number(
            self._raw_value(summary_detail.get("dividendYield")),
            quote.get("trailingAnnualDividendYield"),
            quote.get("dividendYield"),
            fallback_profile.get("dividend_yield"),
        )
        fallback_financials = fallback_profile.get("financials", {})
        fallback_metrics = fallback_profile.get("metrics", {})
        profile = {
            "ticker": symbol,
            "name": long_name,
            "sector": asset_profile.get("sector") or fallback_profile.get("sector") or "Unknown",
            "industry": asset_profile.get("industry") or fallback_profile.get("industry") or "Unknown",
            "market_cap": self._market_cap_bucket(market_cap_value) if market_cap_value else fallback_profile.get("market_cap", "Unknown"),
            "market_cap_display": market_cap_display or "Unknown",
            "market_cap_value": market_cap_value,
            "business_model": asset_profile.get("longBusinessSummary")
            or fallback_profile.get("description")
            or fallback_profile.get("business_model")
            or f"Realtime quote data was returned for {long_name}, but no company summary was available.",
            "financials": {
                "revenue_growth": self._first_number(
                    self._raw_value(financial_data.get("revenueGrowth")),
                    fallback_financials.get("revenue_growth"),
                    0.0,
                )
                or 0.0,
                "gross_margin": self._first_number(
                    self._raw_value(financial_data.get("grossMargins")),
                    fallback_financials.get("gross_margin"),
                    0.0,
                )
                or 0.0,
                "net_margin": self._first_number(
                    self._raw_value(financial_data.get("profitMargins")),
                    fallback_financials.get("net_margin"),
                    0.0,
                )
                or 0.0,
                "debt_to_equity": debt_to_equity or self._first_number(fallback_financials.get("debt_to_equity"), 0.0) or 0.0,
            },
            "metrics": {
                "market_cap": market_cap_display or "N/A",
                "roe": self._format_percent(self._raw_value(financial_data.get("returnOnEquity")), fallback_profile.get("roe")),
                "pe_ratio_ttm": self._format_number(pe_ratio, fallback_profile.get("pe_ratio_ttm")),
                "eps_ttm": self._format_number(eps_ttm, fallback_profile.get("eps_ttm")),
                "pb_ratio": self._format_number(pb_ratio, fallback_profile.get("pb_ratio")),
                "dividend_yield": self._format_percent(
                    self._normalize_yield(dividend_yield),
                    fallback_profile.get("dividend_yield"),
                ),
                "industry_pe": fallback_profile.get("industry_pe") or "N/A",
                "book_value": self._format_number(book_value, fallback_profile.get("book_value")),
                "debt_to_equity": debt_to_equity_display,
                "face_value": "N/A",
            },
            "competitors": fallback_profile.get("competitors") or ["Peer data unavailable in live Yahoo Finance response"],
            "quote": self.quote(symbol),
            "dividend_yield": self._normalize_yield(dividend_yield),
            "revenue_ttm": fallback_profile.get("revenue_ttm"),
            "net_income_ttm": fallback_profile.get("net_income_ttm"),
            "employees": self._format_integer(asset_profile.get("fullTimeEmployees")) or fallback_profile.get("employees"),
        }
        if profile["metrics"]["market_cap"] == "N/A" and profile["market_cap"] != "Unknown":
            profile["metrics"]["market_cap"] = market_cap_display or profile["market_cap"]
        for metric_key, fallback_value in fallback_metrics.items():
            if profile["metrics"].get(metric_key) == "N/A" and fallback_value:
                profile["metrics"][metric_key] = fallback_value
        return profile

    def financials(self, ticker: str) -> dict:
        return self.company_profile(ticker)["financials"]

    def latest_earnings(self, ticker: str) -> dict:
        symbol = ticker.upper()
        summary = self._quote_summary(symbol, modules="calendarEvents,earnings")
        fallback_profile = self._stockanalysis_profile(symbol)
        fallback_profile = self._merge_company_fallback(symbol, fallback_profile)
        calendar = summary.get("calendarEvents", {})
        earnings = summary.get("earnings", {})
        earnings_date = calendar.get("earnings", {}).get("earningsDate", [])
        date_text = "next earnings date unavailable"
        if earnings_date:
            raw_date = self._raw_value(earnings_date[0])
            if raw_date:
                date_text = datetime.fromtimestamp(int(raw_date), UTC).date().isoformat()
        yearly = earnings.get("financialsChart", {}).get("yearly", [])
        latest_year = yearly[-1] if yearly else {}
        revenue = self._raw_value(latest_year.get("revenue"))
        earnings_value = self._raw_value(latest_year.get("earnings"))
        details = []
        if revenue is not None:
            details.append(f"latest annual revenue reported by Yahoo Finance: {revenue:,.0f}")
        if earnings_value is not None:
            details.append(f"latest annual earnings reported by Yahoo Finance: {earnings_value:,.0f}")
        guidance = f"Yahoo Finance realtime earnings calendar shows {date_text} for {symbol}."
        if details:
            guidance = f"{guidance} " + "; ".join(details) + "."
        elif fallback_profile:
            fallback_details = []
            if fallback_profile.get("revenue_ttm"):
                fallback_details.append(f"revenue (ttm): {fallback_profile['revenue_ttm']}")
            if fallback_profile.get("net_income_ttm"):
                fallback_details.append(f"net income (ttm): {fallback_profile['net_income_ttm']}")
            if fallback_profile.get("market_cap"):
                fallback_details.append(f"market cap: {fallback_profile['market_cap']}")
            if fallback_details:
                guidance = f"Live financial snapshot for {symbol}: " + "; ".join(fallback_details) + "."
        return {
            "quarter": "Realtime earnings snapshot",
            "guidance": guidance,
            "risks": ["Earnings transcript guidance is not available from the current realtime providers"],
        }

    def latest_news(self, ticker: str, limit: int = 5) -> list[dict]:
        profile = self.company_profile(ticker)
        company_name = profile["name"]
        search_terms = self._news_terms(ticker, company_name)
        try:
            response = self.session.get(
                "https://query1.finance.yahoo.com/v1/finance/search",
                params={"q": f"{ticker.upper()} {company_name}", "newsCount": limit * 5, "quotesCount": 0},
                timeout=self.timeout,
            )
            response.raise_for_status()
            items = response.json().get("news", [])
        except (requests.RequestException, ValueError):
            items = []
        filtered: list[dict] = []
        seen_urls = set()
        for item in items:
            title = item.get("title") or "Untitled market update"
            summary = item.get("summary") or title
            url = item.get("link")
            text = f"{title} {summary}".lower()
            if not any(term in text for term in search_terms):
                continue
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            filtered.append(
                {
                    "title": title,
                    "source": item.get("publisher") or "Yahoo Finance",
                    "summary": summary,
                    "url": url,
                }
            )
            if len(filtered) >= limit:
                break
        if filtered:
            return filtered
        if ticker.upper().endswith((".NS", ".BO")):
            indian_news = self._google_news(ticker, company_name, search_terms, limit)
            if indian_news:
                return indian_news
        return self._finviz_news(ticker, search_terms, limit)

    def _news_terms(self, ticker: str, company_name: str) -> list[str]:
        symbol = ticker.upper()
        base_symbol = symbol.split(".")[0].lower()
        terms = {ticker.lower(), base_symbol, company_name.lower()}
        cleaned_name = re.sub(r"\b(inc|inc\.|corporation|corp|corp\.|company|co|co\.|plc|ltd|limited|class|common|stock)\b", "", company_name.lower())
        cleaned_name = " ".join(cleaned_name.replace(",", " ").split())
        if cleaned_name:
            terms.add(cleaned_name)
        for alias in self._indian_news_aliases(symbol):
            terms.add(alias.lower())
        first_word = cleaned_name.split()[0] if cleaned_name.split() else ""
        if len(first_word) >= 4 and first_word not in {"state", "bank"}:
            terms.add(first_word)
        return sorted(terms, key=len, reverse=True)

    def _google_news(self, ticker: str, company_name: str, search_terms: list[str], limit: int) -> list[dict]:
        query_terms = self._news_query_terms(ticker, company_name, search_terms)
        if not query_terms:
            return []
        quoted_terms = [f'"{term}"' if " " in term else term for term in query_terms]
        query = f"({' OR '.join(quoted_terms)}) stock OR shares"
        try:
            response = self.session.get(
                "https://news.google.com/rss/search",
                params={"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            root = ElementTree.fromstring(response.text)
        except (requests.RequestException, ElementTree.ParseError):
            return []

        news = []
        seen_urls = set()
        required_terms = [term.lower() for term in query_terms if len(term) >= 3]
        for item in root.findall(".//item"):
            title = self._clean_html(item.findtext("title") or "Untitled market update")
            summary = self._clean_html(item.findtext("description") or title)
            url = item.findtext("link")
            source_node = item.find("source")
            source = self._clean_html(source_node.text) if source_node is not None and source_node.text else "Google News"
            published_at = item.findtext("pubDate")
            text = f"{title} {summary} {source}".lower()
            if required_terms and not any(term in text for term in required_terms):
                continue
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            news.append(
                {
                    "title": title,
                    "source": source,
                    "summary": summary,
                    "url": url,
                    "published_at": published_at,
                }
            )
            if len(news) >= limit:
                break
        return news

    def _news_query_terms(self, ticker: str, company_name: str, search_terms: list[str]) -> list[str]:
        symbol = ticker.upper()
        base_symbol = symbol.split(".")[0]
        preferred = [company_name, base_symbol, *self._indian_news_aliases(symbol)]
        terms = []
        for term in preferred + search_terms:
            normalized = " ".join(str(term).replace("&amp;", "&").split())
            if not normalized or normalized.lower() in {"state", "bank", "limited", "ltd"}:
                continue
            if normalized.lower() not in {item.lower() for item in terms}:
                terms.append(normalized)
        return terms[:5]

    def _indian_news_aliases(self, ticker: str) -> list[str]:
        aliases = {
            "SBIN.NS": ["SBI", "State Bank of India"],
            "SBIN.BO": ["SBI", "State Bank of India"],
            "INFY.NS": ["Infosys"],
            "INFY.BO": ["Infosys"],
            "RELIANCE.NS": ["Reliance Industries", "RIL"],
            "RELIANCE.BO": ["Reliance Industries", "RIL"],
            "TCS.NS": ["TCS", "Tata Consultancy Services"],
            "TCS.BO": ["TCS", "Tata Consultancy Services"],
            "HDFCBANK.NS": ["HDFC Bank"],
            "HDFCBANK.BO": ["HDFC Bank"],
            "ICICIBANK.NS": ["ICICI Bank"],
            "ICICIBANK.BO": ["ICICI Bank"],
        }
        return aliases.get(ticker.upper(), [])

    def _finviz_news(self, ticker: str, search_terms: list[str], limit: int) -> list[dict]:
        try:
            response = self.session.get(
                "https://finviz.com/quote.ashx",
                params={"t": ticker.upper()},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException:
            return []

        links = re.findall(
            r'<a[^>]*class="tab-link-news"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            response.text,
            flags=re.DOTALL,
        )
        news = []
        seen_urls = set()
        for url, raw_title in links:
            title = self._clean_html(raw_title)
            if not title or url in seen_urls:
                continue
            if not any(term in title.lower() for term in search_terms):
                continue
            seen_urls.add(url)
            news.append(
                {
                    "title": title,
                    "source": "Finviz",
                    "summary": title,
                    "url": url,
                }
            )
            if len(news) >= limit:
                break
        return news

    def _fallback_quote(self, ticker: str) -> dict:
        symbol = ticker.upper()
        fallback = self.COMPANY_FALLBACKS.get(symbol)
        if not fallback:
            return {}
        price = self._first_number(fallback.get("fallback_price"), fallback.get("metrics", {}).get("book_value"), 100.0)
        previous_close = price * 0.995 if price is not None else None
        change = price - previous_close if price is not None and previous_close is not None else None
        change_percent = change / previous_close if change is not None and previous_close else None
        return {
            "ticker": symbol,
            "price": price,
            "previous_close": previous_close,
            "change": change,
            "change_percent": change_percent,
            "day_high": price * 1.01 if price is not None else None,
            "day_low": price * 0.99 if price is not None else None,
            "volume": None,
            "currency": "INR" if symbol.endswith((".NS", ".BO")) else "USD",
            "exchange": "NSE" if symbol.endswith(".NS") else "BSE" if symbol.endswith(".BO") else "NASDAQ/NYSE",
            "timestamp": datetime.now(UTC).isoformat(),
            "source": "Local fallback profile",
        }

    def _fallback_price_history(self, ticker: str, horizon: str, range_value: str, interval: str) -> dict:
        quote = self._fallback_quote(ticker)
        if not quote:
            return {}
        end_price = quote["price"] or 100.0
        start_price = end_price * 0.94
        points = []
        steps = 12
        end_date = datetime.now(UTC).date()
        spacing_days = max(1, self._fallback_history_days(horizon) // (steps - 1))
        for index in range(steps):
            progress = index / (steps - 1)
            close = start_price + ((end_price - start_price) * progress)
            point_date = end_date - timedelta(days=spacing_days * (steps - index - 1))
            points.append(
                {
                    "date": point_date.isoformat(),
                    "close": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "volume": None,
                }
            )
        change = end_price - start_price
        change_percent = change / start_price if start_price else None
        return {
            "ticker": ticker.upper(),
            "horizon": horizon,
            "range": range_value,
            "interval": interval,
            "currency": quote["currency"],
            "exchange": quote["exchange"],
            "start_date": points[0]["date"],
            "end_date": points[-1]["date"],
            "start_price": start_price,
            "end_price": end_price,
            "change": change,
            "change_percent": change_percent,
            "period_high": max(point["high"] for point in points),
            "period_low": min(point["low"] for point in points),
            "average_volume": None,
            "points": points,
            "source": "Local fallback profile",
        }

    def _fallback_company_profile(self, ticker: str) -> dict:
        symbol = ticker.upper()
        fallback = self.COMPANY_FALLBACKS.get(symbol)
        if not fallback:
            return {}
        metrics = {
            "market_cap": fallback.get("market_cap_display") or fallback.get("market_cap") or "N/A",
            "roe": "N/A",
            "pe_ratio_ttm": "N/A",
            "eps_ttm": "N/A",
            "pb_ratio": "N/A",
            "dividend_yield": "N/A",
            "industry_pe": "N/A",
            "book_value": "N/A",
            "debt_to_equity": "N/A",
            "face_value": "N/A",
            **fallback.get("metrics", {}),
        }
        return {
            "ticker": symbol,
            "name": self._fallback_company_name(symbol),
            "sector": fallback.get("sector") or "Unknown",
            "industry": fallback.get("industry") or "Unknown",
            "market_cap": fallback.get("market_cap") or "Unknown",
            "market_cap_display": fallback.get("market_cap_display") or fallback.get("market_cap") or "Unknown",
            "market_cap_value": None,
            "business_model": fallback.get("business_model") or f"Company profile fallback for {symbol}.",
            "financials": {
                "revenue_growth": 0.0,
                "gross_margin": 0.0,
                "net_margin": 0.0,
                "debt_to_equity": 0.0,
                **fallback.get("financials", {}),
            },
            "metrics": metrics,
            "competitors": fallback.get("competitors") or ["Peer data unavailable"],
            "quote": self._fallback_quote(symbol),
            "dividend_yield": None,
            "revenue_ttm": fallback.get("revenue_ttm"),
            "net_income_ttm": fallback.get("net_income_ttm"),
            "employees": fallback.get("employees"),
        }

    def _fallback_company_name(self, ticker: str) -> str:
        names = {
            "RELIANCE.NS": "Reliance Industries Limited",
            "TCS.NS": "Tata Consultancy Services Limited",
            "INFY.NS": "Infosys Limited",
            "HDFCBANK.NS": "HDFC Bank Limited",
            "ICICIBANK.NS": "ICICI Bank Limited",
            "SBIN.NS": "State Bank of India",
            "BHARTIARTL.NS": "Bharti Airtel Limited",
            "ITC.NS": "ITC Limited",
            "TATAMOTORS.NS": "Tata Motors Limited",
            "WIPRO.NS": "Wipro Limited",
            "HINDUNILVR.NS": "Hindustan Unilever Limited",
            "AAPL": "Apple Inc.",
            "MSFT": "Microsoft Corporation",
            "NVDA": "NVIDIA Corporation",
            "AMZN": "Amazon.com, Inc.",
            "GOOGL": "Alphabet Inc.",
            "META": "Meta Platforms, Inc.",
            "TSLA": "Tesla, Inc.",
            "WMT": "Walmart Inc.",
        }
        return names.get(ticker.upper(), ticker.upper())

    def _fallback_history_days(self, horizon: str) -> int:
        normalized = horizon.lower().strip()
        if normalized == "6 months":
            return 180
        if normalized == "12 months":
            return 365
        if normalized == "3 years":
            return 365 * 3
        return 90

    def _quote_result(self, ticker: str) -> dict:
        symbol = ticker.upper()
        try:
            response = self.session.get(
                "https://query1.finance.yahoo.com/v7/finance/quote",
                params={"symbols": symbol},
                timeout=self.timeout,
            )
            response.raise_for_status()
            results = response.json().get("quoteResponse", {}).get("result", [])
            if results:
                return results[0]
        except requests.RequestException:
            pass
        try:
            return self._chart_quote_result(symbol)
        except (requests.RequestException, ValueError):
            return {}

    def _safe_quote_result(self, ticker: str) -> dict:
        try:
            return self._quote_result(ticker)
        except (requests.RequestException, ValueError):
            return {}

    def _chart_quote_result(self, ticker: str) -> dict:
        response = self.session.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker.upper()}",
            params={"range": "1d", "interval": "1m"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        results = response.json().get("chart", {}).get("result", [])
        if not results:
            return {}
        result = results[0]
        meta = result.get("meta", {})
        indicators = result.get("indicators", {}).get("quote", [{}])[0]
        closes = [value for value in indicators.get("close", []) if value is not None]
        highs = [value for value in indicators.get("high", []) if value is not None]
        lows = [value for value in indicators.get("low", []) if value is not None]
        volumes = [value for value in indicators.get("volume", []) if value is not None]
        price = self._first_number(meta.get("regularMarketPrice"), closes[-1] if closes else None)
        previous_close = self._first_number(meta.get("chartPreviousClose"), meta.get("previousClose"))
        change = price - previous_close if price is not None and previous_close else None
        change_percent = (change / previous_close) * 100 if change is not None and previous_close else None
        return {
            "symbol": ticker.upper(),
            "shortName": meta.get("shortName") or ticker.upper(),
            "longName": meta.get("longName") or meta.get("shortName") or ticker.upper(),
            "regularMarketPrice": price,
            "regularMarketPreviousClose": previous_close,
            "regularMarketChange": change,
            "regularMarketChangePercent": change_percent,
            "regularMarketDayHigh": max(highs) if highs else None,
            "regularMarketDayLow": min(lows) if lows else None,
            "regularMarketVolume": volumes[-1] if volumes else None,
            "currency": meta.get("currency") or "INR",
            "exchange": meta.get("exchangeName") or meta.get("exchangeTimezoneName") or "Unknown",
            "fullExchangeName": meta.get("fullExchangeName") or meta.get("exchangeName") or "Unknown",
        }

    def _quote_summary(
        self,
        ticker: str,
        modules: str = "assetProfile,price,summaryDetail,financialData,defaultKeyStatistics",
    ) -> dict:
        try:
            response = self.session.get(
                f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{ticker.upper()}",
                params={"modules": modules},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException:
            return {}
        results = response.json().get("quoteSummary", {}).get("result", [])
        return results[0] if results else {}

    def _search_quote(self, query: str) -> dict | None:
        try:
            response = self.session.get(
                "https://query1.finance.yahoo.com/v1/finance/search",
                params={"q": query, "quotesCount": 8, "newsCount": 0},
                timeout=self.timeout,
            )
            response.raise_for_status()
            quotes = response.json().get("quotes", [])
        except (requests.RequestException, ValueError):
            quotes = []

        indian_quotes = [
            quote for quote in quotes if str(quote.get("symbol", "")).upper().endswith((".NS", ".BO"))
        ]
        for quote in indian_quotes:
            quote_type = str(quote.get("quoteType", "")).upper()
            if quote_type in {"EQUITY", "ETF"} and quote.get("symbol"):
                return quote
        for quote in quotes:
            quote_type = str(quote.get("quoteType", "")).upper()
            symbol = str(quote.get("symbol", ""))
            if quote_type in {"EQUITY", "ETF"} and symbol and "." not in symbol:
                return quote
        for quote in quotes:
            if quote.get("symbol"):
                return quote
        return None

    def _stockanalysis_profile(self, ticker: str) -> dict:
        symbol = ticker.lower()
        profile: dict[str, str | None] = {}
        try:
            company_html = self._get_text(f"https://stockanalysis.com/stocks/{symbol}/company/")
            profile["description"] = self._first_paragraph(company_html)
            profile["industry"] = self._table_value(company_html, "Industry")
            profile["sector"] = self._table_value(company_html, "Sector")
            profile["employees"] = self._table_value(company_html, "Employees")
        except requests.RequestException:
            pass

        try:
            quote_html = self._get_text(f"https://stockanalysis.com/stocks/{symbol}/")
            profile["market_cap"] = self._stat_value(quote_html, "Market Cap")
            profile["revenue_ttm"] = self._stat_value(quote_html, "Revenue (ttm)")
            profile["net_income_ttm"] = self._stat_value(quote_html, "Net Income (ttm)")
            profile["pe_ratio_ttm"] = self._table_value(quote_html, "PE Ratio")
        except requests.RequestException:
            pass

        try:
            stats_html = self._get_text(f"https://stockanalysis.com/stocks/{symbol}/statistics/")
            profile["pb_ratio"] = self._table_value(stats_html, "PB Ratio")
            profile["book_value"] = self._table_value(stats_html, "Book Value Per Share")
            profile["roe"] = self._paragraph_percent(stats_html, "Return on equity")
            profile["debt_to_equity"] = self._paragraph_number(stats_html, "Debt / Equity ratio")
            profile["dividend_yield"] = self._paragraph_percent(stats_html, "dividend yield")
        except requests.RequestException:
            pass

        return {key: value for key, value in profile.items() if value}

    def _screener_profile(self, ticker: str) -> dict:
        symbol = ticker.upper().replace(".NS", "").replace(".BO", "")
        html = ""
        for suffix in ("/consolidated/", "/"):
            try:
                html = self._get_text(f"https://www.screener.in/company/{symbol}{suffix}")
            except requests.RequestException:
                continue
            if "Page Not Found" not in html and "id=\"top-ratios\"" in html:
                break
        if not html or "id=\"top-ratios\"" not in html:
            return {}

        ratios = self._screener_ratios(html)
        profile: dict[str, Any] = {}
        metrics: dict[str, str] = {}
        if ratios.get("Market Cap"):
            profile["market_cap_display"] = ratios["Market Cap"]
            profile["market_cap"] = "Large Cap"
            metrics["market_cap"] = ratios["Market Cap"]
        if ratios.get("Stock P/E"):
            metrics["pe_ratio_ttm"] = ratios["Stock P/E"]
        if ratios.get("Book Value"):
            metrics["book_value"] = ratios["Book Value"]
        if ratios.get("Dividend Yield"):
            metrics["dividend_yield"] = ratios["Dividend Yield"]
        if ratios.get("ROE"):
            metrics["roe"] = ratios["ROE"]
        if ratios.get("Face Value"):
            metrics["face_value"] = ratios["Face Value"]
        if metrics:
            profile["metrics"] = metrics
        return profile

    def _screener_ratios(self, html: str) -> dict[str, str]:
        ratios: dict[str, str] = {}
        for row in re.findall(r"<li[^>]*data-source=\"default\"[^>]*>(.*?)</li>", html, flags=re.DOTALL):
            name_match = re.search(r"<span class=\"name\">(.*?)</span>", row, flags=re.DOTALL)
            number_match = re.search(r"<span class=\"number\">(.*?)</span>", row, flags=re.DOTALL)
            if not name_match or not number_match:
                continue
            name = self._clean_html(name_match.group(1))
            number = self._clean_html(number_match.group(1))
            value_text = self._clean_html(row)
            if "Cr." in value_text:
                value = f"{number} Cr"
            elif "%" in value_text:
                value = f"{number}%"
            else:
                value = number
            ratios[name] = value
        return ratios

    def _merge_company_fallback(self, ticker: str, profile: dict) -> dict:
        fallback = self.COMPANY_FALLBACKS.get(ticker.upper())
        if not fallback:
            return profile

        merged = dict(fallback)
        merged.update(profile)
        merged["financials"] = {
            **fallback.get("financials", {}),
            **profile.get("financials", {}),
        }
        merged["metrics"] = {
            **fallback.get("metrics", {}),
            **profile.get("metrics", {}),
        }
        return merged

    def _get_text(self, url: str) -> str:
        response = self.session.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=self.timeout)
        response.raise_for_status()
        return response.text

    def _first_paragraph(self, html: str) -> str | None:
        matches = re.findall(r"<p>(.*?)</p>", html, flags=re.DOTALL)
        for match in matches:
            text = self._clean_html(match)
            if len(text) > 80:
                return text
        return None

    def _table_value(self, html: str, label: str) -> str | None:
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.DOTALL):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.DOTALL)
            if len(cells) < 2:
                continue
            if self._clean_html(cells[0]).lower() == label.lower():
                return self._clean_html(cells[1])
        return None

    def _stat_value(self, html: str, label: str) -> str | None:
        value = self._table_value(html, label)
        if not value:
            return None
        return value.split()[0]

    def _paragraph_percent(self, html: str, label: str) -> str | None:
        pattern = rf"{re.escape(label)}[^.]*?([0-9]+(?:\.[0-9]+)?%)"
        match = re.search(pattern, self._clean_html(html), flags=re.IGNORECASE)
        return match.group(1) if match else None

    def _paragraph_number(self, html: str, label: str) -> str | None:
        pattern = rf"{re.escape(label)}[^.]*?([0-9]+(?:\.[0-9]+)?)"
        match = re.search(pattern, self._clean_html(html), flags=re.IGNORECASE)
        return match.group(1) if match else None

    def _clean_html(self, value: str) -> str:
        text = re.sub(r"<!--.*?-->", " ", value, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        return " ".join(text.split())

    def _looks_like_ticker(self, value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9]{1,12}(?:\.(?:NS|BO))?", value.strip(), flags=re.IGNORECASE))

    def _symbol_candidates(self, value: str, market: str = "india") -> list[str]:
        symbol = value.upper().strip()
        if "." in symbol:
            return [symbol]
        if market == "us":
            return [symbol]
        return [f"{symbol}.NS", f"{symbol}.BO", symbol]

    def _common_company_symbol(self, query: str, market: str = "india") -> str | None:
        normalized = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
        indian_aliases = {
            "reliance": "RELIANCE.NS",
            "reliance industries": "RELIANCE.NS",
            "tcs": "TCS.NS",
            "tata consultancy services": "TCS.NS",
            "infosys": "INFY.NS",
            "infy": "INFY.NS",
            "hdfc bank": "HDFCBANK.NS",
            "hdfcbank": "HDFCBANK.NS",
            "icici bank": "ICICIBANK.NS",
            "icicibank": "ICICIBANK.NS",
            "sbi": "SBIN.NS",
            "state bank of india": "SBIN.NS",
            "bharti airtel": "BHARTIARTL.NS",
            "airtel": "BHARTIARTL.NS",
            "itc": "ITC.NS",
            "tata motors": "TATAMOTORS.NS",
            "wipro": "WIPRO.NS",
            "hindustan unilever": "HINDUNILVR.NS",
            "hul": "HINDUNILVR.NS",
        }
        us_aliases = {
            "apple": "AAPL",
            "apple inc": "AAPL",
            "microsoft": "MSFT",
            "microsoft corporation": "MSFT",
            "nvidia": "NVDA",
            "amazon": "AMZN",
            "amazon com": "AMZN",
            "alphabet": "GOOGL",
            "google": "GOOGL",
            "meta": "META",
            "meta platforms": "META",
            "facebook": "META",
            "tesla": "TSLA",
            "walmart": "WMT",
            "wal mart": "WMT",
            "walmart inc": "WMT",
            "wmt": "WMT",
        }
        aliases = us_aliases if market == "us" else indian_aliases
        return aliases.get(normalized)

    def _history_window(self, horizon: str) -> tuple[str, str]:
        normalized = horizon.lower().strip()
        if normalized == "3 months":
            return "3mo", "1d"
        if normalized == "6 months":
            return "6mo", "1d"
        if normalized == "12 months":
            return "1y", "1d"
        if normalized == "3 years":
            return "3y", "1wk"
        return "3mo", "1d"

    def _raw_value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return value.get("raw")
        return value

    def _first_number(self, *values: Any) -> float | None:
        for value in values:
            if value is None:
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    def _normalize_debt_to_equity(self, value: float) -> float:
        return value / 100 if value > 10 else value

    def _normalize_yield(self, value: float | None) -> float | None:
        if value is None:
            return None
        return value / 100 if value > 1 else value

    def _market_cap_bucket(self, market_cap: float | None) -> str:
        if not market_cap:
            return "Unknown"
        if market_cap >= 200_000_000_000:
            return "Mega Cap"
        if market_cap >= 10_000_000_000:
            return "Large Cap"
        if market_cap >= 2_000_000_000:
            return "Mid Cap"
        return "Small Cap"

    def _format_large_number(self, value: float | None) -> str | None:
        if value is None:
            return None
        if value >= 1_000_000_000_000:
            return f"{value / 1_000_000_000_000:.2f}T"
        if value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f}B"
        if value >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"
        return f"{value:,.0f}"

    def _format_number(self, value: Any, fallback: str | None = None) -> str:
        number = self._first_number(value)
        if number is None:
            return fallback or "N/A"
        return f"{number:,.2f}"

    def _format_integer(self, value: Any) -> str | None:
        number = self._first_number(value)
        if number is None:
            return None
        return f"{number:,.0f}"

    def _format_percent(self, value: Any, fallback: str | None = None) -> str:
        number = self._first_number(value)
        if number is None:
            return fallback or "N/A"
        return f"{number:.2%}"
