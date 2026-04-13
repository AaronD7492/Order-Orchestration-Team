import logging
import uuid
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, redirect, request, session

from src.cis_client import (
    CISError,
    InsufficientStockError,
    LockExpiredError,
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

        Returns 400 if no cart is present in session.
        """
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

        Flow:
          1. Lock inventory in CIS with real shipping address (60s TTL)
          2. Mock payment — always succeeds (real payment deferred)
          3. Ship locked order in CIS — happens immediately after lock,
             well within the 60s window
          4. Stub handoff to Delivery Execution team via ods_client
          5. Notify C&S update-delivery to increment delivery counts
        """
        body = request.get_json(silent=True)
        if not body:
            return jsonify({"error": "Invalid request body"}), 400

        for field in ("addressLine1", "city", "province"):
            if not body.get(field):
                return jsonify({"error": f"Missing required field: {field}"}), 400

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

        # Step 1: Lock inventory in CIS
        try:
            lock_result = request_order_lock(f2f_order_id, shipping_address, manifest)
        except InsufficientStockError as e:
            return jsonify({"error": "out_of_stock", "message": str(e)}), 409
        except CISError as e:
            return jsonify({"error": "cis_error", "message": str(e)}), 503

        lock_order_id = lock_result["lockOrderId"]
        lock_token = lock_result["lockToken"]

        # Step 2: Mock payment (real payment processor deferred to Sprint 3)

        # Step 3: Ship — immediately after lock, well within 60s TTL
        try:
            ship_result = ship_locked_order(lock_order_id, lock_token)
        except LockExpiredError:
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
            return jsonify({"error": "cis_error", "message": str(e)}), 503

        shipping_id = ship_result["shippingId"]

        # Step 4: Stub handoff to Delivery Execution team
        destination = {
            "addressLine1": body["addressLine1"],
            "addressLine2": body.get("addressLine2", ""),
            "city": body["city"],
            "province": body["province"],
            "postalCode": body.get("postalCode", ""),
        }
        submit_delivery(f2f_order_id, shipping_id, destination, drop_off)

        # Step 5: Notify C&S — increment delivery category counts
        user_token = session.get("user_token")
        if user_token:
            try:
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

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)