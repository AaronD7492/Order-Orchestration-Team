import logging
import uuid
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, redirect, request, session

from src.cis_client import (
    CISError,
    InsufficientStockError,
    LockExpiredError,
    get_pooled_inventory,
    request_order_lock,
    ship_locked_order,
)
from src.config import Config
from src.db import get_team_secret
from src.ods_client import submit_delivery


def create_app():
    app = Flask(__name__)
    app.secret_key = Config.SECRET_KEY

    # ------------------------------------------------------------------
    # Health / baseline
    # ------------------------------------------------------------------

    @app.route("/secret", methods=["GET"])
    def secret():
        secret_value = get_team_secret()
        return jsonify({"secret": secret_value}), 200

    @app.route("/inventory/pooled", methods=["GET"])
    def inventory_pooled():
        """
        Proxy to CIS GET /inventory/pooled with pagination.
        Used by the checkout UI to validate cart stock before submitting.

        Query params:
            page     (int, default 1, minimum 1)
            pageSize (int, default 100, maximum 500)
        """
        try:
            page = int(request.args.get("page", 1))
            page_size = int(request.args.get("pageSize", 100))
        except ValueError:
            return jsonify({"error": "page and pageSize must be integers"}), 400

        if page < 1:
            return jsonify({"error": "page must be >= 1"}), 400
        if not (1 <= page_size <= 500):
            return jsonify({"error": "pageSize must be between 1 and 500"}), 400

        try:
            result = get_pooled_inventory(page, page_size)
            return jsonify(result), 200
        except CISError as e:
            return jsonify({"error": "cis_error", "message": str(e)}), e.status_code
    # ------------------------------------------------------------------
    # Checkout — initiate (called by Supply & Network homepage)
    # ------------------------------------------------------------------

    @app.route("/checkout/initiate", methods=["POST"])
    def checkout_initiate():
        """
        Called by the Supply & Network team when the user clicks Go to Checkout.

        Expected JSON body:
        {
            "items": [
                {
                    "productId":   str,
                    "productName": str,
                    "quantity":    float,
                    "unit":        str   ("kg" | "l")
                },
                ...
            ],
            "userToken": str   (C&S session token, passed through as-is)
        }

        Stores the cart and token in the Flask session, then returns a redirect
        URL for the caller to navigate the user to the checkout page.
        No CIS lock is created here — the lock fires at Place Order time so
        that the real shipping address is available and lock + ship are
        back-to-back with no risk of TTL expiry.
        """
        body = request.get_json(silent=True)
        if not body or "items" not in body:
            return jsonify({"error": "Missing required field: items"}), 400

        items = body["items"]
        if not isinstance(items, list) or len(items) == 0:
            return jsonify({"error": "items must be a non-empty list"}), 400

        session["cart_items"] = items
        session["user_token"] = body.get("userToken")

        # Fallback: allow direct client_id for automated flows (e.g. C&S subscriptions)
        if not body.get("userToken") and body.get("client_id"):
            session["client_id"] = body.get("client_id")

        return jsonify({"redirect_url": "/checkout"}), 200

    # ------------------------------------------------------------------
    # Checkout — page render (stubbed — UI is owned by the UI team)
    # ------------------------------------------------------------------

    @app.route("/checkout", methods=["GET"])
    def checkout():
        """
        Stub endpoint. Returns cart state and prefill data as JSON.

        Previously rendered a Jinja2 template; templates have been moved to
        the shared UI branch. The UI team's frontend should call
        POST /checkout/initiate to set the session, then read this endpoint
        to hydrate the checkout page client-side.

        SAGA NOTE: Arriving here after a failed or abandoned submit means the
        user has navigated back. Any pending CIS lock stored in the session is
        released by _release_pending_lock() — this is the compensating
        transaction for a lock that was created but never shipped. The lock
        also expires naturally after 60s, but releasing it immediately frees
        the stock for other customers.

        Returns 400 if no cart is present in session.
        """
        _release_pending_lock()

        cart_items = session.get("cart_items")
        if not cart_items:
            return (
                jsonify({"error": "No cart found. Please start from the store."}),
                400,
            )

        prefill = {}
        user_token = session.get("user_token")
        if user_token:
            try:
                import jwt as pyjwt
                from src.cfp_client import get_client
                decoded = pyjwt.decode(
                    user_token, Config.CS_JWT_PASS, algorithms=["HS256"]
                )
                client = get_client(decoded.get("client_id", ""))
                if client and client.get("address"):
                    addr = client["address"]
                    parts = [p.strip() for p in addr.split(",")]
                    if len(parts) >= 3:
                        prov_postal = parts[-1].strip().split()
                        prefill = {
                            "addressLine1": parts[0],
                            "city": parts[-2].strip(),
                            "province": prov_postal[0] if prov_postal else "ON",
                            "postalCode": prov_postal[1] if len(prov_postal) > 1 else "",
                        }
            except Exception as e:
                logging.getLogger(__name__).warning("Address prefill failed: %s", e)

        return jsonify({"cart_items": cart_items, "prefill": prefill}), 200

    # ------------------------------------------------------------------
    # Dev-only demo route
    # ------------------------------------------------------------------

    @app.route("/checkout/demo", methods=["GET"])
    def checkout_demo():
        """Pre-fills session with sample cart data for local development/demo."""
        session["cart_items"] = [
            {"productId": "PROD-CARROTS", "productName": "Carrots",
             "quantity": 2.5, "unit": "kg", "category": "Produce"},
            {"productId": "PROD-ONIONS", "productName": "Onions",
             "quantity": 1.0, "unit": "kg", "category": "Produce"},
            {"productId": "PROD-MILK", "productName": "Whole Milk",
             "quantity": 2.0, "unit": "l", "category": "Dairy"},
        ]
        session["user_token"] = "demo-token"
        return redirect("/checkout")

    # ------------------------------------------------------------------
    # SAGA — compensating transaction endpoint
    # ------------------------------------------------------------------

    @app.route("/checkout/cancel", methods=["GET", "POST"])
    def checkout_cancel():
        """
        SAGA compensating transaction — explicit cancel/rollback.

        Called when the UI navigates the user away from the checkout page
        (e.g. "Go back to shop" button). Releases any pending CIS inventory
        lock immediately so stock is freed for other customers rather than
        waiting for the 60s TTL to expire.

        Also triggered internally by _release_pending_lock() on GET /checkout
        to handle the browser back-button case.

        After releasing the lock the session cart is cleared and the user
        is redirected to the shop root. The UI team should point their
        "Go back to shop" href at /checkout/cancel instead of /.
        """
        _release_pending_lock()
        session.pop("cart_items", None)
        session.pop("user_token", None)
        return redirect("/")

    # ------------------------------------------------------------------
    # Checkout — submit (full order flow)
    # ------------------------------------------------------------------

    @app.route("/checkout/submit", methods=["POST"])
    def checkout_submit():
        """
        Process a checkout form submission.

        Expected JSON body:
        {
            "addressLine1": str,
            "addressLine2": str,   (optional)
            "city":         str,   (Waterloo | Kitchener | Cambridge)
            "province":     str,   ("ON")
            "postalCode":   str,
            "dropOff":      bool,
            "items":        list   (optional — falls back to session cart)
        }

        SAGA flow:
          T1. Lock inventory in CIS (60s TTL)
              → lock details written to session immediately after success
              → compensating action: _release_pending_lock() releases the lock
                if user navigates back before T3 completes
          T2. Mock payment — always succeeds (real payment deferred to Sprint 3)
              → no compensating action needed
          T3. Ship locked order in CIS — consumes the lock on success or failure
              → lock is gone after this point regardless of outcome, so T1
                compensating action is no longer applicable
          T4. Stub handoff to Delivery Execution team (ODS)
          T5. Notify C&S to increment delivery category counts
        """
        _log = logging.getLogger(__name__)

        body = request.get_json(silent=True)
        if not body:
            return jsonify({"error": "Invalid request body"}), 400

        for field in ("addressLine1", "city", "province"):
            if not body.get(field):
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Detect re-submission: a pending lock in the session means the user
        # submitted, got an error, and is trying again without going back first.
        # Release the stale lock before creating a new one.
        if session.get("pending_lock_order_id"):
            _log.warning(
                "Re-submission detected — releasing stale lock %s before new attempt",
                session["pending_lock_order_id"],
            )
            _release_pending_lock()

        cart_items = body.get("items") or session.get("cart_items")
        if not cart_items:
            return (
                jsonify({"error": "No cart found. Please start from the store."}),
                400,
            )

        drop_off = body.get("dropOff", True)

        manifest = [
            {
                "productId": item["productId"],
                "quantity": item["quantity"],
                "unit": item["unit"],
            }
            for item in cart_items
        ]

        parts = [body["addressLine1"]]
        if body.get("addressLine2"):
            parts.append(body["addressLine2"])
        postal = body.get("postalCode", "").strip()
        city_line = f"{body['city']}, {body['province']}"
        if postal:
            city_line += f" {postal}"
        parts.append(city_line)
        shipping_address = ", ".join(parts)

        f2f_order_id = (
            f"F2F-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
            f"-{uuid.uuid4().hex[:8].upper()}"
        )

        # T1: Lock inventory in CIS
        # Write lock details to session immediately so _release_pending_lock()
        # can clean up if the user navigates back before T3 completes.
        try:
            lock_result = request_order_lock(f2f_order_id, shipping_address, manifest)
        except InsufficientStockError as e:
            return jsonify({"error": "out_of_stock", "message": str(e)}), 409
        except CISError as e:
            return jsonify({"error": "cis_error", "message": str(e)}), 503

        lock_order_id = lock_result["lockOrderId"]
        lock_token = lock_result["lockToken"]

        session["pending_lock_order_id"] = lock_order_id
        session["pending_lock_token"] = lock_token
        session["pending_f2f_order_id"] = f2f_order_id
        session.modified = True

        # T2: Mock payment (real payment processor deferred to Sprint 3)

        # T3: Ship — immediately after lock, well within 60s TTL.
        # Lock is consumed by CIS at this point regardless of outcome,
        # so clear the pending lock from session before returning.
        ship_result = None
        max_ship_retries = 3
        last_ship_error = None
        for attempt in range(max_ship_retries):
            try:
                ship_result = ship_locked_order(lock_order_id, lock_token)
                break  # success
            except LockExpiredError:
                session.pop("pending_lock_order_id", None)
                session.pop("pending_lock_token", None)
                session.pop("pending_f2f_order_id", None)
                return (
                    jsonify(
                        {
                            "error": "lock_expired",
                            "message": "Order could not be finalised. Please try again.",
                        }
                    ),
                    409,
                )
            except CISError as e:
                last_ship_error = e
                logging.getLogger(__name__).warning(
                    "CIS ship attempt %d/%d failed: %s", attempt + 1, max_ship_retries, e
                )
                continue

        if ship_result is None:
            session.pop("pending_lock_order_id", None)
            session.pop("pending_lock_token", None)
            session.pop("pending_f2f_order_id", None)
            return jsonify({"error": "cis_error", "message": str(last_ship_error)}), 503

        shipping_id = ship_result["shippingId"]

        session.pop("pending_lock_order_id", None)
        session.pop("pending_lock_token", None)
        session.pop("pending_f2f_order_id", None)

        # Step 3.5: Notify CE integration of stock change
        try:
            from src.ce_client import post_stock_change
            ce_result = post_stock_change(cart_items)
            logging.getLogger(__name__).info(
                "CE stock change posted — eventId: %s, status: %s",
                ce_result.get("data", {}).get("eventId"),
                ce_result.get("data", {}).get("status"),
            )
        except Exception as e:
            logging.getLogger(__name__).warning("CE stock change failed: %s", e)

        # T4: Stub handoff to Delivery Execution team
        destination = {
            "addressLine1": body["addressLine1"],
            "addressLine2": body.get("addressLine2", ""),
            "city": body["city"],
            "province": body["province"],
            "postalCode": body.get("postalCode", ""),
        }
        submit_delivery(f2f_order_id, shipping_id, destination, drop_off)

        # T5: Notify C&S — increment delivery category counts
        user_token = session.get("user_token")
        client_id = session.get("client_id")  # pre-set by subscription flow (no JWT)
        if user_token or client_id:
            try:
                if user_token and not client_id:
                    import jwt as pyjwt
                    decoded = pyjwt.decode(
                        user_token,
                        Config.CS_JWT_PASS,
                        algorithms=["HS256"],
                    )
                    client_id = decoded.get("client_id")
                if client_id:
                    produce = sum(1 for i in cart_items if i.get("category") == "Produce")
                    meat = sum(1 for i in cart_items if i.get("category") == "Meat")
                    dairy = sum(1 for i in cart_items if i.get("category") == "Dairy")
                    requests.post(
                        f"{Config.CS_BASE_URL}/api/v1/update-delivery",
                        json={
                            "client_id": client_id,
                            "produce": produce,
                            "meat": meat,
                            "dairy": dairy,
                        },
                        timeout=5,
                    )
            except Exception as e:
                logging.getLogger(__name__).warning("C&S update-delivery failed: %s", e)

        session.pop("cart_items", None)
        session.pop("user_token", None)
        session.pop("client_id", None)
        return (
            jsonify(
                {
                    "status": "success",
                    "f2fOrderId": f2f_order_id,
                    "shippingId": shipping_id,
                    "message": "Your order has been placed successfully!",
                }
            ),
            200,
        )

    # ------------------------------------------------------------------
    # SAGA helper — compensating transaction for CIS inventory lock
    # ------------------------------------------------------------------

    def _release_pending_lock():
        """
        Compensating transaction for SAGA step T1 (CIS inventory lock).

        If a lock was created during a previous submit attempt and the user
        navigated back before shipping completed, this releases the lock so
        stock is freed immediately rather than waiting for the 60s TTL.

        CIS does not currently expose a release endpoint in the Sprint 2 spec,
        so the call is best-effort: on success the stock is freed immediately;
        on failure (404, network error) the lock expires naturally after 60s.
        When CIS exposes a release endpoint in Sprint 3, no changes needed here
        — the scaffolding is already in place.
        """
        lock_order_id = session.get("pending_lock_order_id")
        if not lock_order_id:
            return

        _log = logging.getLogger(__name__)
        lock_token = session.get("pending_lock_token")
        f2f_order_id = session.get("pending_f2f_order_id")

        try:
            resp = requests.post(
                f"{Config.CIS_BASE_URL}/orders/release",
                json={"lockOrderId": lock_order_id, "lockToken": lock_token},
                headers={"X-API-Key": Config.CIS_API_KEY},
                timeout=5,
            )
            if resp.ok:
                _log.info(
                    "SAGA compensating transaction: released CIS lock %s (f2fOrderId=%s)",
                    lock_order_id, f2f_order_id,
                )
            else:
                _log.warning(
                    "SAGA compensating transaction: CIS release returned %s for lock %s "
                    "(will expire naturally in 60s). f2fOrderId=%s",
                    resp.status_code, lock_order_id, f2f_order_id,
                )
        except requests.exceptions.RequestException as e:
            _log.warning(
                "SAGA compensating transaction: could not reach CIS to release lock %s "
                "(will expire naturally in 60s). f2fOrderId=%s. Error: %s",
                lock_order_id, f2f_order_id, e,
            )

        # Always clear from session regardless of CIS response
        session.pop("pending_lock_order_id", None)
        session.pop("pending_lock_token", None)
        session.pop("pending_f2f_order_id", None)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
