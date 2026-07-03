from __future__ import annotations

from finpilot.core.models import TradeIntent, TradeResult
from finpilot.trading.paper import PaperTradingService


class TradingAgent:
    """Guarded trading agent. It validates user intent but never decides autonomously."""

    def __init__(self, service: PaperTradingService) -> None:
        self.service = service

    def execute(self, intent: TradeIntent) -> TradeResult:
        if intent.ticker.strip() == "":
            return TradeResult(accepted=False, status="rejected", message="Ticker is required.")
        return self.service.place_order(intent)

    def groww_order_status(self, groww_order_id: str) -> dict:
        return self.service.groww_order_status(groww_order_id)

    def groww_orders(self, page_size: int = 50) -> dict:
        return self.service.groww_orders(page_size=page_size)

    def alpaca_orders(self, limit: int = 50) -> list[dict]:
        return self.service.alpaca_orders(limit=limit)
