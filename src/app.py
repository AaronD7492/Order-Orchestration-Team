import logging
import uuid
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, redirect, render_template, request, session

from src.agnet_client import AgNetError, get_product_catalog
from src.cis_client import (
    CISError,
    InsufficientStockError,
    LockExpiredError,
    lock_inventory,
    request_order_lock,
    ship_locked_order,
    ship_order,
)
from src.cfp_client import sync_primary_files
from src.config import Config
from src.db import get_customer, get_team_secret
from src.ods_client import submit_delivery


# In-memory delivery store — populated when orders are placed
_deliveries = []


def create_app():
    app = Flask(__name__)
    app.secret_key = Config.SECRET_KEY

    # Sync CFP primary files on startup — non-blocking, failure is logged only
    try:
        sync_primary_files()
    except Exception as e:
        logging.getLogger(__name__).warning("CFP startup sync failed: %s", e)

    # ------------------------------------------------------------------
    # Homepage — shop (inventory from CIS + AgNet catalog)
    # ------------------------------------------------------------------

    @app.route("/", methods=["GET"])
    def index():
        """
        Customer-facing shop. Fetches live inventory from CIS (warehouse stock)
        and the AgNet product catalog (supplier offerings) to build the shop.

        CIS inventory = what can be ordered RIGHT NOW (productIds used for checkout lock).
        AgNet catalog = full supplier product range shown as the browsable catalog.
        """
        _log = logging.getLogger(__name__)

        # Fetch CIS pooled inventory (warehouse stock — authoritative for checkout)
        cis_items = []
        for _attempt in range(3):
            try:
                cis_resp = requests.get(
                    f"{Config.CIS_BASE_URL}/inventory/pooled",
                    headers={"X-API-Key": Config.CIS_API_KEY},
                    timeout=8,
                )
                cis_resp.raise_for_status()
                cis_items = cis_resp.json().get("items", [])
                break
            except Exception as e:
                _log.warning("CIS inventory fetch failed (attempt %d): %s", _attempt + 1, e)
                if _attempt == 2:
                    _log.warning("CIS inventory unavailable after 3 attempts")

        # Fetch AgNet vendor catalog (deduplicated by productId)
        agnet_catalog = {}
        try:
            agnet_catalog = get_product_catalog()
        except AgNetError as e:
            _log.warning("AgNet catalog fetch failed: %s", e)

        return render_template(
            "index.html",
            cis_items=cis_items,
            agnet_catalog=list(agnet_catalog.values()),
            client_id=session.get("client_id"),
        )

    @app.route("/api/inventory", methods=["GET"])
    def api_inventory():
        """Proxy to CIS pooled inventory — used by JS if it needs fresh data."""
        last_err = None
        for _ in range(3):
            try:
                resp = requests.get(
                    f"{Config.CIS_BASE_URL}/inventory/pooled",
                    headers={"X-API-Key": Config.CIS_API_KEY},
                    timeout=8,
                )
                resp.raise_for_status()
                return jsonify(resp.json()), 200
            except Exception as e:
                last_err = e
        return jsonify({"error": str(last_err)}), 503

    # ------------------------------------------------------------------
    # Sprint 1 — team secret
    # ------------------------------------------------------------------

    @app.route("/secret", methods=["GET"])
    def secret():
        secret_value = get_team_secret()
        return jsonify({"secret": secret_value}), 200

    # ------------------------------------------------------------------
    # C&S Authentication — login / callback / logout
    # ------------------------------------------------------------------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        """
        GET  — render the login form.
        POST — validate client_id + mobile against farmforkdb, issue JWT, store in session.
        """
        _log = logging.getLogger(__name__)

        if request.method == "GET":
            return render_template("login.html", error=None)

        client_id = (request.form.get("client_id") or "").strip()
        mobile    = (request.form.get("mobile") or "").strip()

        if not client_id or not mobile:
            return render_template("login.html", error="Please enter your Client ID and mobile number.")

        try:
            customer = get_customer(client_id, mobile)
        except Exception as e:
            _log.warning("DB error during login: %s", e)
            return render_template("login.html", error="Service unavailable. Please try again.")

        if not customer:
            return render_template("login.html", error="Invalid Client ID or mobile number.")

        import jwt as pyjwt
        from datetime import timedelta
        token = pyjwt.encode(
            {
                "client_id": customer["client_id"],
                "exp": datetime.now(timezone.utc) + timedelta(hours=4),
            },
            Config.CS_JWT_PASS,
            algorithm="HS256",
        )
        session["user_token"] = token
        session["client_id"]  = customer["client_id"]

        return redirect("/")

    @app.route("/auth/cs", methods=["GET"])
    def auth_cs():
        """
        Optional fallback — accepts a C&S-issued JWT via query param.
        Primary login is handled by POST /login (direct DB validation).

        Expected query param:
            token=<jwt_token>   (the jwt_token issued by the C&S server)
        """
        _log = logging.getLogger(__name__)
        token = request.args.get("token", "").strip()

        if not token:
            return redirect("/login")

        try:
            import jwt as pyjwt
            decoded = pyjwt.decode(token, Config.CS_JWT_PASS, algorithms=["HS256"])
            client_id = decoded.get("client_id")
            if not client_id:
                raise ValueError("JWT missing client_id")
            session["user_token"] = token
            session["client_id"] = client_id
        except Exception as e:
            _log.warning("C&S auth callback failed: %s", e)
            return redirect("/login")

        return redirect("/")

    @app.route("/logout", methods=["GET"])
    def logout():
        """Clear the session and send the user back to the homepage."""
        session.pop("user_token", None)
        session.pop("client_id", None)
        session.pop("cart_items", None)
        return redirect("/")

    # ------------------------------------------------------------------
    # Legacy pass-through routes (kept for API testing / Sprint 1 work)
    # ------------------------------------------------------------------

    @app.route("/orders/request", methods=["POST"])
    def orders_request():
        body = request.get_json(silent=True)
        if not body or "items" not in body:
            return jsonify({"error": "Missing required field: items"}), 400

        items = body["items"]
        if not isinstance(items, list) or len(items) == 0:
            return jsonify({"error": "items must be a non-empty list"}), 400

        try:
            result = lock_inventory(items)
            return jsonify(result), 200
        except InsufficientStockError as e:
            return jsonify({"error": str(e)}), 409
        except CISError as e:
            return jsonify({"error": str(e)}), e.status_code

    @app.route("/orders/ship", methods=["POST"])
    def orders_ship():
        body = request.get_json(silent=True)
        if not body or "order_id" not in body:
            return jsonify({"error": "Missing required field: order_id"}), 400

        order_id = body["order_id"]

        try:
            result = ship_order(order_id)
            return jsonify(result), 200
        except LockExpiredError as e:
            return jsonify({"error": str(e)}), 410
        except InsufficientStockError as e:
            return jsonify({"error": str(e)}), 409
        except CISError as e:
            return jsonify({"error": str(e)}), e.status_code

    # ------------------------------------------------------------------
    # Dev-only demo route — loads sample cart and renders checkout page
    # ------------------------------------------------------------------

    @app.route("/checkout/demo", methods=["GET"])
    def checkout_demo():
        """Pre-fills session with sample cart data for local development/demo."""
        session["cart_items"] = [
            {"productId": "PROD-CARROTS", "productName": "Carrots", "quantity": 2.5, "unit": "kg"},
            {"productId": "PROD-ONIONS", "productName": "Onions", "quantity": 1.0, "unit": "kg"},
            {"productId": "PROD-MILK", "productName": "Whole Milk", "quantity": 2.0, "unit": "l"},
        ]
        session["user_token"] = "demo-token"
        return redirect("/checkout")

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
        if body.get("userToken"):
            session["user_token"] = body.get("userToken")

        return jsonify({"redirect_url": "/checkout"}), 200

    # ------------------------------------------------------------------
    # Checkout — page render
    # ------------------------------------------------------------------

    @app.route("/checkout", methods=["GET"])
    def checkout():
        """Render the checkout page, hydrated with cart items and CFP address."""
        cart_items = session.get("cart_items")
        if not cart_items:
            return (
                jsonify({"error": "No cart found. Please start from the store."}),
                400,
            )

        # Try to pre-fill address from CFP using the C&S JWT
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
                    # Parse "721 King St., Kitchener, ON M0X3A6"
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
                logging.getLogger(__name__).warning("CFP address prefill failed: %s", e)

        return render_template("checkout.html", cart_items=cart_items, prefill=prefill)

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
            "dropOff":      bool
        }

        Flow:
          1. Lock inventory in CIS with real shipping address (60s TTL)
          2. Mock payment — always succeeds (real payment deferred)
          3. Ship locked order in CIS — happens immediately after lock,
             well within the 60s window
          4. Stub handoff to Delivery Execution team
        """
        body = request.get_json(silent=True)
        if not body:
            return jsonify({"error": "Invalid request body"}), 400

        for field in ("addressLine1", "city", "province"):
            if not body.get(field):
                return jsonify({"error": f"Missing required field: {field}"}), 400

        # Accept updated cart from checkout page (user may have changed quantities)
        cart_items = body.get("items") or session.get("cart_items")
        if not cart_items:
            return (
                jsonify({"error": "No cart found. Please start from the store."}),
                400,
            )

        drop_off = body.get("dropOff", True)

        # Build CIS manifest from cart
        manifest = [
            {
                "productId": item["productId"],
                "quantity": item["quantity"],
                "unit": item["unit"],
            }
            for item in cart_items
        ]

        # Build shipping address string for CIS
        parts = [body["addressLine1"]]
        if body.get("addressLine2"):
            parts.append(body["addressLine2"])
        postal = body.get("postalCode", "").strip()
        city_line = f"{body['city']}, {body['province']}"
        if postal:
            city_line += f" {postal}"
        parts.append(city_line)
        shipping_address = ", ".join(parts)

        # Generate unique F2F order ID
        f2f_order_id = (
            f"F2F-{datetime.now(timezone.utc).strftime('%Y%m%d')}"
            f"-{uuid.uuid4().hex[:8].upper()}"
        )

        # Step 1: Lock inventory in CIS
        try:
            lock_result = request_order_lock(f2f_order_id, shipping_address, manifest)
        except InsufficientStockError as e:
            # TODO: Trigger restock pipeline (P&I / AgNet) — deferred pending team discussion
            return jsonify({"error": "out_of_stock", "message": str(e)}), 409
        except CISError as e:
            return jsonify({"error": "cis_error", "message": str(e)}), 503

        lock_order_id = lock_result["lockOrderId"]
        lock_token = lock_result["lockToken"]

        # Step 2: Mock payment,
        # TODO:Possibly Integrate real payment processor when sprint3 begins.

        # Step 3: Ship — happens immediately after lock, well within 60s TTL
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

        # Step 4: Submit to ODS via ods_client, then notify DE UI
        destination = {
            "addressLine1": body["addressLine1"],
            "addressLine2": body.get("addressLine2", ""),
            "city": body["city"],
            "province": body["province"],
            "postalCode": body["postalCode"],
        }
        submit_delivery(f2f_order_id, shipping_id, destination, drop_off)

        # Step 4b: Register assignment in Delivery Execution store
        address_str = body["addressLine1"]
        if body.get("addressLine2"):
            address_str += f", {body['addressLine2']}"
        address_str += f", {body['city']}, {body['province']}"
        if body.get("postalCode"):
            address_str += f" {body['postalCode']}"

        _deliveries.append({
            "order_id": f2f_order_id,
            "customer_name": session.get("client_id", "Customer"),
            "address": address_str,
            "items": [i.get("productName", i.get("productId", "")) for i in cart_items],
            "status": "Assigned",
            "eta": "TBD",
            "driver": "Unassigned",
        })

        # Step 5: Notify C&S — increment their delivery category counts
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
                    # Tally cart items by category (Produce / Meat / Dairy)
                    produce = sum(1 for i in cart_items if i.get("category") == "Produce")
                    meat    = sum(1 for i in cart_items if i.get("category") == "Meat")
                    dairy   = sum(1 for i in cart_items if i.get("category") == "Dairy")
                    requests.post(
                        f"{Config.CS_BASE_URL}/update-delivery",
                        json={"client_id": client_id, "produce": produce, "meat": meat, "dairy": dairy},
                        timeout=5,
                    )
            except Exception as e:
                logging.getLogger(__name__).warning("C&S update-delivery failed: %s", e)

        # Clear checkout session after successful order
        session.pop("cart_items", None)
        session.pop("user_token", None)

        return (
            jsonify(
                {
                    "status": "success",
                    "f2fOrderId": f2f_order_id,
                    "shippingId": shipping_id,
                    "message": "Your order has been placed successfully!",
                    "deliveryDashboardUrl": "/delivery",
                }
            ),
            200,
        )

    # ------------------------------------------------------------------
    # Delivery Execution UI routes
    # ------------------------------------------------------------------

    @app.route("/delivery", methods=["GET"])
    def delivery_dashboard():
        return render_template("delivery_dashboard.html", deliveries=_deliveries)

    @app.route("/delivery/<order_id>", methods=["GET"])
    def delivery_details(order_id):
        delivery = next((d for d in _deliveries if d["order_id"] == order_id), None)
        if not delivery:
            return jsonify({"error": "Delivery not found"}), 404
        return render_template("delivery_details.html", delivery=delivery)

    @app.route("/api/delivery/assignments", methods=["POST"])
    def create_delivery_assignment():
        data = request.get_json(silent=True) or {}
        entry = {
            "order_id": data.get("order_id"),
            "customer_name": data.get("customer_name"),
            "address": data.get("address"),
            "items": data.get("items", []),
            "status": data.get("status", "Assigned"),
            "eta": data.get("eta", "TBD"),
            "driver": data.get("driver", "Unassigned"),
        }
        _deliveries.append(entry)
        return jsonify({"status": "success", "data": {"message": "Delivery assignment received", "delivery": entry}}), 201

    @app.route("/api/deliveries", methods=["GET"])
    def get_deliveries():
        return jsonify({"status": "success", "data": _deliveries}), 200

    @app.route("/api/delivery/status", methods=["POST"])
    def update_delivery_status():
        data = request.get_json(silent=True) or {}
        delivery = next((d for d in _deliveries if d["order_id"] == data.get("order_id")), None)
        if not delivery:
            return jsonify({"status": "error", "error": {"code": "NOT_FOUND"}}), 404
        delivery["status"] = data.get("status", delivery["status"])
        return jsonify({"status": "success", "data": {"delivery": delivery}}), 200

    @app.route("/api/delivery/complete", methods=["POST"])
    def complete_delivery():
        data = request.get_json(silent=True) or {}
        delivery = next((d for d in _deliveries if d["order_id"] == data.get("order_id")), None)
        if not delivery:
            return jsonify({"status": "error", "error": {"code": "NOT_FOUND"}}), 404
        delivery["status"] = "Delivered"
        return jsonify({"status": "success", "data": {"delivery": delivery}}), 200

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
