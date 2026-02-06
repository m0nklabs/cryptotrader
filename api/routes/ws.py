"""WebSocket routes for live price updates."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.websocket.manager import get_price_ws_manager

router = APIRouter(tags=["websocket"])


@router.websocket("/ws/prices")
async def websocket_prices(websocket: WebSocket) -> None:
    manager = get_price_ws_manager()
    await websocket.accept()
    await manager.connect(websocket)

    try:
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                continue
            action = message.get("action") or message.get("type")
            if action == "subscribe":
                exchange = str(message.get("exchange", "bitfinex")).lower()
                symbols_raw = message.get("symbols", [])
                symbols = {str(sym).upper() for sym in symbols_raw if sym}
                await manager.update_subscription(websocket, exchange=exchange, symbols=symbols)
            elif action == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:
        await manager.disconnect(websocket)
