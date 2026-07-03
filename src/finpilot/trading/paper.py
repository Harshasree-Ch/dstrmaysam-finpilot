from __future__ import annotations

import requests

from finpilot.core.models import TradeIntent, TradeResult
from finpilot.core.runtime import add_workspace_venv_site_packages
from finpilot.core.settings import Settings


class PaperTradingService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def place_order(self, intent: TradeIntent) -> TradeResult:
        if not intent.user_confirmed:
            return TradeResult(accepted=False, status="rejected", message="User confirmation is required.")
        if intent.order_type == "limit" and not intent.limit_price:
            return TradeResult(accepted=False, status="rejected", message="Limit orders require a limit price.")
        if intent.market == "US":
            return self._place_alpaca_order(intent)
        return self._place_groww_order(intent)

    def _place_groww_order(self, intent: TradeIntent) -> TradeResult:
        if not self.settings.groww_api_key or not self.settings.groww_secret_key:
            return TradeResult(
                accepted=False,
                status="groww_not_configured",
                message="Please configure Groww API key and secret before placing an order.",
            )

        add_workspace_venv_site_packages()
        try:
            from growwapi import GrowwAPI
        except ModuleNotFoundError:
            return TradeResult(
                accepted=False,
                status="groww_sdk_missing",
                message=(
                    "The Groww SDK package is not installed in the Python environment running this app. "
                    "Install dependencies from requirements.txt and restart/redeploy Streamlit."
                ),
            )

        try:
            access_token = GrowwAPI.get_access_token(
                api_key=self.settings.groww_api_key,
                secret=self.settings.groww_secret_key,
            )
            groww = GrowwAPI(access_token)
            order_kwargs = {
                "trading_symbol": self._groww_trading_symbol(intent.ticker),
                "quantity": intent.quantity,
                "validity": groww.VALIDITY_DAY,
                "exchange": self._groww_exchange(groww, intent.ticker),
                "segment": groww.SEGMENT_CASH,
                "product": groww.PRODUCT_MIS,
                "order_type": self._groww_order_type(groww, intent.order_type),
                "transaction_type": self._groww_transaction_type(groww, intent.side),
            }
            if intent.order_type == "limit" and intent.limit_price is not None:
                order_kwargs["price"] = intent.limit_price
            data = groww.place_order(**order_kwargs)
        except Exception as exc:
            return TradeResult(
                accepted=False,
                status=self._groww_error_status(exc),
                message=self._groww_error_message(exc),
            )

        order_id = str(data.get("groww_order_id") or data.get("order_id") or data.get("id") or "")
        status = str(data.get("status") or "submitted")
        return TradeResult(
            accepted=True,
            status=status,
            message=f"Groww {intent.side} order submitted for {intent.quantity} share(s) of {intent.ticker.upper()}.",
            order_id=order_id or None,
        )

    def groww_order_status(self, groww_order_id: str) -> dict:
        groww_order_id = groww_order_id.strip()
        if not groww_order_id:
            raise ValueError("Groww order id is required.")
        groww = self._groww_client()
        return groww.get_order_status(segment=groww.SEGMENT_CASH, groww_order_id=groww_order_id)

    def groww_orders(self, page_size: int = 50) -> dict:
        groww = self._groww_client()
        return groww.get_order_list(page=0, page_size=page_size, segment=groww.SEGMENT_CASH, timeout=15)

    def _groww_client(self) -> object:
        if not self.settings.groww_api_key or not self.settings.groww_secret_key:
            raise RuntimeError("Please configure Groww API key and secret before checking order status.")
        try:
            from growwapi import GrowwAPI
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "The Groww SDK package is not installed in the Python environment running this app. "
                "Install dependencies from requirements.txt and restart/redeploy Streamlit."
            ) from exc
        access_token = GrowwAPI.get_access_token(
            api_key=self.settings.groww_api_key,
            secret=self.settings.groww_secret_key,
        )
        return GrowwAPI(access_token)

    def _groww_trading_symbol(self, ticker: str) -> str:
        symbol = ticker.upper().strip()
        for suffix in (".NS", ".BO"):
            if symbol.endswith(suffix):
                return symbol[: -len(suffix)]
        return symbol

    def _groww_exchange(self, groww: object, ticker: str) -> str:
        return groww.EXCHANGE_BSE if ticker.upper().strip().endswith(".BO") else groww.EXCHANGE_NSE

    def _groww_order_type(self, groww: object, order_type: str) -> str:
        if order_type == "limit":
            return groww.ORDER_TYPE_LIMIT
        return groww.ORDER_TYPE_MARKET

    def _groww_transaction_type(self, groww: object, side: str) -> str:
        if side == "sell":
            return groww.TRANSACTION_TYPE_SELL
        return groww.TRANSACTION_TYPE_BUY

    def _groww_error_status(self, exc: Exception) -> str:
        text = str(exc).lower()
        if "registered ip" in text or "register your ip" in text:
            return "groww_ip_not_registered"
        return "groww_rejected"

    def _groww_error_message(self, exc: Exception) -> str:
        text = str(exc)
        if "registered IP" in text or "registered ip" in text.lower() or "register your IP" in text:
            return (
                "Groww rejected the order because this app is running from an IP address that is not registered "
                "for your Groww API key. Register or allowlist the public IP of the machine/server running "
                "Streamlit in your Groww API settings, then try again."
            )
        return f"Groww order request failed: {exc}"

    def _place_alpaca_order(self, intent: TradeIntent) -> TradeResult:
        if not self.settings.alpaca_api_key or not self.settings.alpaca_secret_key:
            return TradeResult(
                accepted=False,
                status="alpaca_not_configured",
                message="Please configure Alpaca paper trading credentials before placing a US stock order.",
            )

        payload: dict[str, str | int | float] = {
            "symbol": intent.ticker.upper().strip(),
            "qty": intent.quantity,
            "side": intent.side,
            "type": intent.order_type,
            "time_in_force": "day",
        }
        if intent.order_type == "limit":
            payload["limit_price"] = intent.limit_price or 0

        base_url = self.settings.alpaca_paper_base_url.rstrip("/")
        try:
            response = requests.post(
                f"{base_url}/v2/orders",
                json=payload,
                headers={
                    "APCA-API-KEY-ID": self.settings.alpaca_api_key,
                    "APCA-API-SECRET-KEY": self.settings.alpaca_secret_key,
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            response.raise_for_status()
            data = response.json() if response.content else {}
        except Exception as exc:
            return TradeResult(
                accepted=False,
                status="alpaca_rejected",
                message=f"Alpaca paper order request failed: {exc}",
            )

        order_id = str(data.get("id") or data.get("client_order_id") or "")
        status = str(data.get("status") or "submitted")
        return TradeResult(
            accepted=True,
            status=status,
            message=f"Alpaca paper {intent.side} order submitted for {intent.quantity} share(s) of {intent.ticker.upper()}.",
            order_id=order_id or None,
        )

    def alpaca_orders(self, limit: int = 50) -> list[dict]:
        if not self.settings.alpaca_api_key or not self.settings.alpaca_secret_key:
            raise RuntimeError("Please configure Alpaca paper trading credentials before viewing Alpaca orders.")

        base_url = self.settings.alpaca_paper_base_url.rstrip("/")
        response = requests.get(
            f"{base_url}/v2/orders",
            params={"status": "all", "limit": limit, "direction": "desc", "nested": "true"},
            headers={
                "APCA-API-KEY-ID": self.settings.alpaca_api_key,
                "APCA-API-SECRET-KEY": self.settings.alpaca_secret_key,
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        response.raise_for_status()
        data = response.json() if response.content else []
        return data if isinstance(data, list) else []
