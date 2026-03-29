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


def lock_inventory(items):
    """
    Call CIS POST /orders/request to lock inventory.
    items: list of {"product_id": str, "quantity": int}
    Returns the CIS response JSON on success.
    Raises InsufficientStockError (409) or CISError on failure.
    """
    url = f"{Config.CIS_BASE_URL}/orders/request"
    try:
        response = requests.post(url, json={"items": items}, timeout=10)
    except requests.exceptions.RequestException as e:
        raise CISError(f"CIS unreachable: {e}", 503)

    if response.status_code == 409:
        raise InsufficientStockError(
            response.json().get("message", "Insufficient stock"),
            409
        )
    if not response.ok:
        raise CISError(
            response.json().get("message", "CIS error"),
            response.status_code
        )

    return response.json()


def ship_order(order_id):
    """
    Call CIS POST /orders/ship to finalize a locked order.
    order_id: the lock/order ID returned by lock_inventory.
    Returns the CIS response JSON on success.
    Raises LockExpiredError (410) or CISError on failure.
    """
    url = f"{Config.CIS_BASE_URL}/orders/ship"
    try:
        response = requests.post(url, json={"order_id": order_id}, timeout=10)
    except requests.exceptions.RequestException as e:
        raise CISError(f"CIS unreachable: {e}", 503)

    if response.status_code == 410:
        raise LockExpiredError(
            response.json().get("message", "Lock expired"),
            410
        )
    if response.status_code == 409:
        raise InsufficientStockError(
            response.json().get("message", "Insufficient stock"),
            409
        )
    if not response.ok:
        raise CISError(
            response.json().get("message", "CIS error"),
            response.status_code
        )

    return response.json()


# ---------------------------------------------------------------------------
# Checkout-flow functions — matched to the real CIS API spec
# ---------------------------------------------------------------------------

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

    if response.status_code == 409:
        raise InsufficientStockError(
            response.json().get("message", "Insufficient stock for one or more items"),
            409,
        )
    if not response.ok:
        raise CISError(
            response.json().get("message", "CIS error"),
            response.status_code,
        )
    return response.json()


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

    if response.status_code == 409:
        data = response.json()
        if data.get("status") == "ship-lock-expired":
            raise LockExpiredError(
                data.get("message", "Lock expired after 60 seconds"),
                409,
            )
        raise InsufficientStockError(data.get("message", "Insufficient stock"), 409)
    if not response.ok:
        raise CISError(
            response.json().get("message", "CIS error"),
            response.status_code,
        )
    return response.json()
