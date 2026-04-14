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


def _post_with_retry(url, headers, payload, retries=3):
    """POST to CIS, retrying on 5xx up to `retries` times."""
    last_exc = None
    for _ in range(retries):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            if response.status_code < 500:
                return response
            last_exc = CISError(f"CIS error {response.status_code}", response.status_code)
        except requests.exceptions.RequestException as e:
            last_exc = CISError(f"CIS unreachable: {e}", 503)
    raise last_exc


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
    Retries up to 3 times on 5xx responses.

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

    response = _post_with_retry(url, headers, payload, retries=5)

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
    Retries up to 3 times on 5xx responses.

    CIS is occasionally flaky — it can return 500 while the ship actually
    succeeds server-side.  On retry we detect ALREADY_SHIPPED (409) and
    treat it as a success, using the lockOrderId as the shippingId fallback.

    Returns on success:
        {"status": "ready", "shippingId": ..., "f2fOrderId": ...}
    Raises:
        LockExpiredError  — lock TTL elapsed
        CISError          — any other failure
    """
    url = f"{Config.CIS_BASE_URL}/orders/ship"
    headers = {"X-API-Key": Config.CIS_API_KEY}
    payload = {"lockOrderId": lock_order_id, "lockToken": lock_token}

    response = _post_with_retry(url, headers, payload, retries=5)

    try:
        data = response.json()
    except Exception:
        data = {}

    if response.status_code == 409:
        error_code = data.get("error", {}).get("code", "") if isinstance(data.get("error"), dict) else ""
        # CIS processed the ship but returned 5xx, then ALREADY_SHIPPED on retry — treat as success
        if error_code == "ALREADY_SHIPPED":
            return {"status": "ready", "shippingId": lock_order_id, "f2fOrderId": None}
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
