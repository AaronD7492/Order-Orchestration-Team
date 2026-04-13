"""
CFP client — customer profile data.

Delegates to the Customer & Subscription (C&S) team's internal API,
which owns the customer data and CFP sync responsibility.
OO does not connect to CFP directly — C&S owns that integration.

C&S endpoint used: GET /api/v1/customers
Returns paginated customer objects with client_id, mobile, produce, meat,
dairy, delivery_count. Address data is sourced from CFP by the C&S service.
"""

import logging

import requests

from src.config import Config

logger = logging.getLogger(__name__)


class CFPError(Exception):
    def __init__(self, message, status_code=500):
        super().__init__(message)
        self.status_code = status_code


def get_client(client_id):
    """
    Fetch a single customer record from the C&S service by client_id.

    The C&S team owns CFP sync and customer data — we call their
    GET /api/v1/customers endpoint and find the matching record.

    Args:
        client_id: e.g. "S297"

    Returns:
        Customer dict with at least {"client_id": str, "address": str}
        or None if the client is not found or the C&S service is unavailable.
    """
    url = f"{Config.CS_BASE_URL}/api/v1/customers"
    try:
        response = requests.get(url, timeout=8)
    except requests.exceptions.RequestException as e:
        logger.warning("C&S GET /customers unreachable: %s", e)
        return None

    if not response.ok:
        logger.warning("C&S GET /customers returned %s", response.status_code)
        return None

    try:
        data = response.json()
    except Exception as e:
        logger.warning("C&S GET /customers invalid JSON: %s", e)
        return None

    items = data.get("data", {}).get("items", [])
    for customer in items:
        if customer.get("client_id") == client_id:
            return customer

    logger.info("CFP: client '%s' not found in C&S customer list", client_id)
    return None
