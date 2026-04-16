"""
Restock pipeline — triggered when CIS warehouse stock falls below threshold.

Flow:
  1. Fetch live CIS pooled inventory.
  2. Identify products with quantityOnHand < LOW_STOCK_THRESHOLD.
  3. For each low-stock product, find vendors in AgNet that carry it.
  4. Place a restock order with the first available vendor for the required
     top-up quantity (up to what the vendor has available).
  5. Return a structured summary of all restock actions taken.
"""

import logging
import math

import requests

from src.agnet_client import AgNetError, get_vendors, place_restock_order
from src.cis_client import CISError, create_vendor_reservation
from src.config import Config

logger = logging.getLogger(__name__)

# Products whose quantityOnHand falls below this are restocked.
LOW_STOCK_THRESHOLD = 10

# How many units to order per restock: top up to this target level.
RESTOCK_TARGET = 50


def fetch_cis_inventory():
    """
    Fetch current CIS pooled inventory, retrying up to 10 times on 5xx/network errors.

    Returns list of items:
      [{"productId": str, "productName": str, "quantityOnHand": int/float, ...}]
    Raises RuntimeError if all attempts fail.
    """
    url = f"{Config.CIS_BASE_URL}/inventory/pooled"
    headers = {"X-API-Key": Config.CIS_API_KEY}
    last_err = None
    for attempt in range(10):
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            resp.raise_for_status()
            return resp.json().get("items", [])
        except requests.RequestException as e:
            last_err = e
            logger.warning("CIS inventory fetch attempt %d failed: %s", attempt + 1, e)
    raise RuntimeError(f"CIS inventory unavailable after 10 attempts: {last_err}")


def run_restock_pipeline():
    """
    Main entry point — scan CIS inventory and restock any low items via AgNet.

    Returns a summary dict:
    {
        "checked": int,           # total products checked
        "low_stock": int,         # products below threshold
        "restocked": int,         # successful restock orders placed
        "skipped": int,           # low-stock items with no supplier found
        "failed": int,            # supplier orders that errored
        "actions": [              # one entry per low-stock product
            {
                "productId": str,
                "productName": str,
                "quantityOnHand": float,
                "status": "restocked" | "no_supplier" | "failed",
                "vendorId": str | None,
                "vendorName": str | None,
                "quantityOrdered": int | None,
                "agnetOrderId": str | None,
                "error": str | None,
            }
        ]
    }
    """
    # Step 1: Fetch CIS inventory
    try:
        cis_items = fetch_cis_inventory()
    except RuntimeError as e:
        logger.error("Restock pipeline aborted — CIS unavailable: %s", e)
        return {
            "checked": 0,
            "low_stock": 0,
            "restocked": 0,
            "skipped": 0,
            "failed": 0,
            "error": str(e),
            "actions": [],
        }

    # Step 2: Find low-stock items (keep full CIS item metadata for later reservation)
    low_stock_items = [
        item for item in cis_items
        if item.get("quantityOnHand", 0) < LOW_STOCK_THRESHOLD
    ]
    # Index full CIS item metadata by productId for reservation payloads
    cis_meta = {item["productId"]: item for item in cis_items}

    if not low_stock_items:
        logger.info("Restock pipeline: all products adequately stocked.")
        return {
            "checked": len(cis_items),
            "low_stock": 0,
            "restocked": 0,
            "skipped": 0,
            "failed": 0,
            "actions": [],
        }

    logger.info(
        "Restock pipeline: %d / %d products are below threshold (%d)",
        len(low_stock_items),
        len(cis_items),
        LOW_STOCK_THRESHOLD,
    )

    # Step 3: Build a vendor lookup keyed by productId
    #   {productId: [{"vendorId": str, "vendorName": str, "quantityAvailable": int}]}
    try:
        vendors = get_vendors()
    except AgNetError as e:
        logger.error("Restock pipeline aborted — AgNet unavailable: %s", e)
        return {
            "checked": len(cis_items),
            "low_stock": len(low_stock_items),
            "restocked": 0,
            "skipped": len(low_stock_items),
            "failed": 0,
            "error": str(e),
            "actions": [
                {
                    "productId": item.get("productId"),
                    "productName": item.get("productName", ""),
                    "quantityOnHand": item.get("quantityOnHand", 0),
                    "status": "no_supplier",
                    "vendorId": None,
                    "vendorName": None,
                    "quantityOrdered": None,
                    "agnetOrderId": None,
                    "error": "AgNet unavailable",
                }
                for item in low_stock_items
            ],
        }

    # Index vendors by productId AND by normalized productName.
    # Inactive vendors are skipped — AgNet rejects orders from them.
    # Name-based index handles CIS/AgNet productId mismatches (e.g. WF-CARROTS vs PROD-CARROTS).
    vendor_by_product = {}   # keyed by AgNet productId
    vendor_by_name = {}      # keyed by lowercase productName

    for vendor in vendors:
        if vendor.get("regState") == "Inactive":
            logger.info("Restock: skipping inactive vendor %s", vendor["vendorId"])
            continue
        for product in vendor.get("availableManifest", []):
            pid = product["productId"]
            name_key = product["productName"].lower().strip()
            entry = {
                "vendorId": vendor["vendorId"],
                "vendorName": vendor["vendorName"],
                "agnetProductId": pid,
                "quantityAvailable": product.get("quantityAvailable", 0),
            }
            vendor_by_product.setdefault(pid, []).append(entry)
            vendor_by_name.setdefault(name_key, []).append(entry)

    for key in list(vendor_by_product) + list(vendor_by_name):
        for d in (vendor_by_product, vendor_by_name):
            if key in d:
                d[key].sort(key=lambda v: v["quantityAvailable"], reverse=True)

    # Step 4: Place restock orders
    restocked = 0
    skipped = 0
    failed = 0
    actions = []

    for item in low_stock_items:
        product_id = item.get("productId")
        product_name = item.get("productName", product_id or "unknown")
        qty_on_hand = item.get("quantityOnHand", 0)

        action = {
            "productId": product_id,
            "productName": product_name,
            "quantityOnHand": qty_on_hand,
            "status": None,
            "vendorId": None,
            "vendorName": None,
            "quantityOrdered": None,
            "agnetOrderId": None,
            "error": None,
        }

        # Try productId match first, fall back to name match for CIS/AgNet ID mismatches
        suppliers = vendor_by_product.get(product_id) or \
                    vendor_by_name.get(product_name.lower().strip(), [])
        if not suppliers:
            logger.warning(
                "Restock: no AgNet supplier found for %s (%s)", product_id, product_name
            )
            action["status"] = "no_supplier"
            skipped += 1
            actions.append(action)
            continue

        # Pick the best supplier (most stock available)
        supplier = suppliers[0]
        qty_needed = max(1, math.ceil(RESTOCK_TARGET - qty_on_hand))
        # Don't order more than the vendor has
        qty_to_order = min(qty_needed, supplier["quantityAvailable"])

        if qty_to_order <= 0:
            logger.warning(
                "Restock: supplier %s has 0 available for %s",
                supplier["vendorName"],
                product_id,
            )
            action["status"] = "no_supplier"
            action["vendorId"] = supplier["vendorId"]
            action["vendorName"] = supplier["vendorName"]
            action["error"] = "Supplier has no available stock"
            skipped += 1
            actions.append(action)
            continue

        action["vendorId"] = supplier["vendorId"]
        action["vendorName"] = supplier["vendorName"]
        action["quantityOrdered"] = qty_to_order

        try:
            agnet_product_id = supplier.get("agnetProductId", product_id)
            result = place_restock_order(
                vendor_id=supplier["vendorId"],
                items=[{"productId": agnet_product_id, "quantity": qty_to_order}],
            )
            action["agnetOrderId"] = result.get("orderId")
            logger.info(
                "Restock: ordered %d units of %s from %s (AgNet orderId=%s)",
                qty_to_order, product_id, supplier["vendorName"], result.get("orderId"),
            )

            # Notify CIS that stock is incoming so warehouse levels update
            meta = cis_meta.get(product_id, {})
            try:
                create_vendor_reservation(
                    vendor_id=supplier["vendorId"],
                    items=[{
                        "productId": product_id,
                        "hierarchy": meta.get("hierarchy", ["General", "General", "General"]),
                        "productName": meta.get("productName", product_name),
                        "quantity": qty_to_order,
                        "unit": meta.get("unit", "kg"),
                    }],
                )
                action["status"] = "restocked"
                logger.info("Restock: CIS reservation created for %s (+%d)", product_id, qty_to_order)
            except CISError as ce:
                # AgNet order succeeded but CIS reservation failed — mark partial
                action["status"] = "restocked_pending_cis"
                action["cisError"] = str(ce)
                logger.warning("Restock: AgNet OK but CIS reservation failed for %s: %s", product_id, ce)

            restocked += 1

        except AgNetError as e:
            action["status"] = "failed"
            action["error"] = str(e)
            failed += 1
            logger.error(
                "Restock: AgNet order failed for %s from %s: %s",
                product_id, supplier["vendorName"], e,
            )

        actions.append(action)

    return {
        "checked": len(cis_items),
        "low_stock": len(low_stock_items),
        "restocked": restocked,
        "skipped": skipped,
        "failed": failed,
        "actions": actions,
    }
