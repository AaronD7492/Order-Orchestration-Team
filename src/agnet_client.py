"""
AgNet client — supplier network (vendor catalog + purchase orders).

Used by Order Orchestration for:
  - Homepage: building the product catalog from vendor manifests
  - Restocking: POST /orders when CIS inventory runs low (S&N flow, future)
"""

import logging

import requests

from src.config import Config

logger = logging.getLogger(__name__)

_HEADERS = {"X-API-Key": Config.AGNET_API_KEY}


class AgNetError(Exception):
    def __init__(self, message, status_code=500):
        super().__init__(message)
        self.status_code = status_code


def get_vendors():
    """
    Fetch all vendors and their available product manifests from AgNet.

    Returns list of vendor dicts:
      [{
        vendorId, vendorName, vendorType (Farm|Butcher|Dairy),
        regState, lastOrder,
        availableManifest: [{productId, productName, hierarchy, unit, quantityAvailable}]
      }]
    """
    url = f"{Config.AGNET_BASE_URL}/api/v1/vendors"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json().get("items", [])
    except requests.RequestException as e:
        logger.error("AgNet GET /vendors failed: %s", e)
        raise AgNetError(f"AgNet unavailable: {e}")


def get_product_catalog():
    """
    Build a deduplicated product catalog from all vendor manifests.

    Products with the same productId across multiple vendors are merged —
    quantityAvailable is summed across all vendors.

    Returns dict keyed by productId:
      {
        "PROD-CARROTS": {
          productId, productName, hierarchy, unit,
          quantityAvailable,           # sum across all vendors
          vendors: [vendorName, ...]
        }
      }
    """
    vendors = get_vendors()
    catalog = {}
    for vendor in vendors:
        for product in vendor.get("availableManifest", []):
            pid = product["productId"]
            if pid not in catalog:
                catalog[pid] = {
                    "productId": pid,
                    "productName": product["productName"],
                    "hierarchy": product["hierarchy"],
                    "unit": product["unit"],
                    "quantityAvailable": 0,
                    "vendors": [],
                }
            catalog[pid]["quantityAvailable"] += product["quantityAvailable"]
            catalog[pid]["vendors"].append(vendor["vendorName"])
    return catalog
