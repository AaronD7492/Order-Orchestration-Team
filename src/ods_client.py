import logging
from datetime import datetime, timezone

import requests

from src.config import Config

logger = logging.getLogger(__name__)

ODS_ORDERS_URL = f"{Config.ODS_BASE_URL}/orders"


def _utc_now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def submit_delivery(f2f_order_id, shipping_id, destination, drop_off):
    """
    Submit a completed order to ODS (Order Distribution System).

    Uses the CIS shippingId as the warehouseOrderNumber.
    All food orders are flagged refrigeration=True.
    drop_off=True  — leave at door (always succeeds)
    drop_off=False — signature required (80% success, auto-retried by ODS)
    """
    payload = {
        "warehouseOrderNumber": shipping_id,
        "destination": {
            "addressLine1": destination["addressLine1"],
            "city": destination["city"],
            "province": destination["province"],
            "postalCode": destination.get("postalCode", ""),
        },
        "specialRequirements": {
            "refrigeration": True,
            "dropOff": bool(drop_off),
        },
        "requestedAtUtc": _utc_now_iso(),
    }

    if destination.get("addressLine2"):
        payload["destination"]["addressLine2"] = destination["addressLine2"]

    headers = {
        "X-API-Key": Config.ODS_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(ODS_ORDERS_URL, json=payload, headers=headers, timeout=10)
    except requests.RequestException as e:
        logger.error("ODS unreachable | f2fOrderId=%s | error=%s", f2f_order_id, e)
        return {"status": "ods_unreachable", "f2fOrderId": f2f_order_id, "error": str(e)}

    try:
        data = resp.json()
    except Exception:
        data = {"rawResponse": resp.text}

    if resp.status_code == 202:
        logger.info(
            "ODS accepted | f2fOrderId=%s | shippingId=%s | orderId=%s",
            f2f_order_id,
            shipping_id,
            data.get("orderId"),
        )
        return {"status": "accepted", "f2fOrderId": f2f_order_id, "odsResponse": data}

    logger.error(
        "ODS rejected | f2fOrderId=%s | status=%s | body=%s",
        f2f_order_id,
        resp.status_code,
        data,
    )
    return {
        "status": "ods_error",
        "f2fOrderId": f2f_order_id,
        "odsStatus": resp.status_code,
        "odsResponse": data,
    }
