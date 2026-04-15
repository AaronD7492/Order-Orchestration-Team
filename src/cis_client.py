import requests
from src.config import Config


class CISError(Exception):
    def __init__(self, message, status_code):
        super().__init__(message)
        self.status_code = status_code


class InsufficientStockError(CISError):
    pass


class LockExpiredError(CISError):
    pass


def request_order_lock(f2f_order_id, shipping_address, manifest):
    """
    Call CIS POST /orders/request to soft-lock inventory (60-second TTL).

    f2f_order_id:     unique F2F order ID, e.g. "F2F-20260328-A1B2C3D4"
    shipping_address: formatted string, e.g. "123 King St W, Waterloo, ON N2L 3G1"
    manifest:         list of {"productId": str, "quantity": float, "unit": str}

    Returns on success:
        {"status": "request-locked", "lockOrderId": ..., "lockToken": ..., "expiresAt": ...}
    Raises:
        InsufficientStockError (409) — not enough stock for one or more items
        CISError                     — any other CIS or network failure
    """
    url = f"{Config.CIS_BASE_URL}/orders/request"
    headers = {"X-API-Key": Config.CIS_API_KEY}
    payload = {
        "f2fOrderId": f2f_order_id,
        "shippingAddress": shipping_address,
        "manifest": manifest,
    }
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
    except requests.exceptions.RequestException as e:
        raise CISError(f"CIS unreachable: {e}", 503)

    try:
        data = response.json()
    except Exception:
        data = {}

    if response.status_code == 409:
        raise InsufficientStockError(
            data.get("message", "Insufficient stock for one or more items"),
            409,
        )
    if not response.ok:
        raise CISError(
            data.get("message", f"CIS error {response.status_code}"),
            response.status_code,
        )
    return data


def ship_locked_order(lock_order_id, lock_token):
    """
    Call CIS POST /orders/ship to finalise a previously locked order.

    lock_order_id: the lockOrderId returned by request_order_lock
    lock_token:    the lockToken returned by request_order_lock

    Returns on success:
        {"status": "ready", "shippingId": ..., "f2fOrderId": ...}
    Raises:
        LockExpiredError (409 ship-lock-expired) — lock TTL elapsed
        CISError                                  — any other failure
    """
    url = f"{Config.CIS_BASE_URL}/orders/ship"
    headers = {"X-API-Key": Config.CIS_API_KEY}
    try:
        response = requests.post(
            url,
            json={"lockOrderId": lock_order_id, "lockToken": lock_token},
            headers=headers,
            timeout=10,
        )
    except requests.exceptions.RequestException as e:
        raise CISError(f"CIS unreachable: {e}", 503)

    try:
        data = response.json()
    except Exception:
        data = {}

    if response.status_code == 409:
        if data.get("status") == "ship-lock-expired":
            raise LockExpiredError(
                data.get("message", "Lock expired after 60 seconds"),
                409,
            )
        raise InsufficientStockError(data.get("message", "Insufficient stock"), 409)
    if not response.ok:
        raise CISError(
            data.get("message", f"CIS error {response.status_code}"),
            response.status_code,
        )
    return data

def get_pooled_inventory(page: int = 1, page_size: int = 100):
    """
    Call CIS GET /inventory/pooled to read current stock levels.

    page:      page number (1-based, minimum 1)
    page_size: items per page (default 100, max 500)

    Returns on success:
        {
            "page": int,
            "pageSize": int,
            "total": int,
            "hasNext": bool,
            "items": [
                {
                    "productId": str,
                    "productName": str,
                    "hierarchy": [str],
                    "quantityOnHand": float,
                    "unit": str
                },
                ...
            ]
        }

    Raises:
        CISError — any CIS or network failure
    """
    url = f"{Config.CIS_BASE_URL}/inventory/pooled"
    headers = {"X-API-Key": Config.CIS_API_KEY}
    params = {"page": page, "pageSize": page_size}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
    except requests.exceptions.RequestException as e:
        raise CISError(f"CIS unreachable: {e}", 503)

    try:
        data = response.json()
    except Exception:
        data = {}

    if response.status_code == 422:
        raise CISError(
            data.get("detail", "Invalid pagination parameters"),
            422,
        )

    if not response.ok:
        raise CISError(
            data.get("message", f"CIS error {response.status_code}"),
            response.status_code,
        )

    return data
