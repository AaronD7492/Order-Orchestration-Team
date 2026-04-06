import logging

logger = logging.getLogger(__name__)


def submit_delivery(f2f_order_id, shipping_id, destination, drop_off):
    """
    Stub: hand completed order off to the Delivery Execution team.

    The Delivery Execution team will consume this data and call
    POST /api/v1/orders on ODS with the following payload shape:

        {
            "warehouseOrderNumber": shipping_id,   # CIS shippingId used as WH order number
            "destination": {
                "addressLine1": str,
                "addressLine2": str,               # may be empty
                "city":         str,               # must be Waterloo | Kitchener | Cambridge
                "province":     str,               # ON
                "postalCode":   str
            },
            "specialRequirements": {
                "refrigeration": True,             # assumed True for food orders
                "dropOff":       bool              # True = leave at door, False = signature
            },
            "requestedAtUtc": "<ISO-8601 UTC>"
        }

    dropOff behaviour (ODS spec):
        True  — always succeeds at cycle completion
        False — 80% success rate per attempt; auto-retried until delivered

    TODO: Replace this stub with one of (pending Delivery Execution team discussion):
        - POST to Delivery Execution service REST API
        - Shared DB event record consumed by DE service
        - Message queue / event bus publish
    """
    logger.info(
        "STUB — Delivery Execution handoff | f2fOrderId=%s | shippingId=%s | city=%s | dropOff=%s",
        f2f_order_id,
        shipping_id,
        destination.get("city"),
        drop_off,
    )

    return {
        "status": "handoff_stubbed",
        "f2fOrderId": f2f_order_id,
        "shippingId": shipping_id,
        "note": "Delivery Execution integration pending — see ods_client.py TODO",
    }
