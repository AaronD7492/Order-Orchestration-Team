"""
Local JSON-backed order store.
Persists full order details (F2F ID, shipping ID, items, address) per client.
Used for order history since the shared DB schema can't store these fields.
"""
import json
import os
import threading
from datetime import datetime, timezone

_STORE_PATH = os.path.join(os.path.dirname(__file__), "..", "order_history.json")
_lock = threading.Lock()


def _load():
    if not os.path.exists(_STORE_PATH):
        return {}
    try:
        with open(_STORE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(data):
    with open(_STORE_PATH, "w") as f:
        json.dump(data, f, indent=2)


def record_order(client_id, f2f_order_id, shipping_id, items, address, drop_off):
    """Append a completed order to the store for the given client."""
    entry = {
        "f2f_order_id": f2f_order_id,
        "shipping_id": shipping_id,
        "order_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "products": [
            {
                "productId": i.get("productId", ""),
                "productName": i.get("productName", i.get("productId", "Unknown")),
                "quantity": i.get("quantity", 0),
                "unit": i.get("unit", ""),
            }
            for i in items
        ],
        "address": address,
        "delivery_type": "Drop Off" if drop_off else "Signature Required",
        "status": "Processing",
    }
    with _lock:
        data = _load()
        data.setdefault(client_id, [])
        data[client_id].insert(0, entry)  # newest first
        _save(data)


def get_orders(client_id):
    """Return all orders for a client, newest first."""
    with _lock:
        data = _load()
        return data.get(client_id, [])
