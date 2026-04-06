# Order Orchestration — C&S Integration Branch

**Course:** PROG73020 | **Section:** 1 | **Teams:** Order Orchestration × Customer & Subscription

This branch (`integrating-with-customer-and-subscriptions`) documents and tracks the integration work between the Order Orchestration team and the Customer & Subscription team.

---

## Integration Overview

The Customer & Subscription (C&S) service handles user authentication and client records. Order Orchestration (OO) handles the shop, cart, and order placement. Together they form the full customer-facing flow:

```
[C&S Service — port 7500]          [OO Service — port 5001]
  GET  /login        ──login──►   GET  /
  POST /login        ◄──JWT────   POST /checkout/initiate
  GET  /gettoken                  GET  /checkout
  POST /update-delivery ◄──────   POST /checkout/submit
```

### Full End-to-End Flow

1. Customer logs in at C&S (`POST /login`) → receives JWT cookie
2. Customer browses shop at OO (`GET /`) → live inventory from CIS + AgNet
3. Customer adds items to cart → clicks "Go to Checkout"
4. OO `POST /checkout/initiate` receives cart + C&S JWT, stores in session
5. Customer fills shipping address on OO checkout page
6. Customer clicks "Place Order" → OO `POST /checkout/submit`:
   - Locks inventory in CIS (`POST /orders/request`)
   - Ships locked order in CIS (`POST /orders/ship`)
   - Stubs handoff to Delivery Execution team
   - Notifies C&S (`POST /update-delivery`) to increment delivery counts
7. Success modal shows `f2fOrderId` and `shippingId`

---

## Running Both Services Together

### 1. Start Customer & Subscription (clone their repo first)

```bash
git clone https://github.com/MaksPyvo/Customer_-_Subscription_ESD.git CS_Team
cd CS_Team
pip install -r requirements.txt
```

Create `CS_Team/.env`:

```
DB_HOST=143.198.35.133
DB_NAME=farmforkdb
DB_USER=customer
DB_PASS=subscribers
CFP_HOST=68.183.203.17
CFP_PORT=22
CFP_USER=sec1
CFP_PASS=t&thmGV26cffZ@XoBrt0
JWT_PASS=jwtpass123
```

Run:

```bash
python -m app.app
# Starts on http://localhost:7500
```

### 2. Start Order Orchestration

```bash
cd Order-Orchestration-Team
pip install -r requirements.txt

CIS_API_KEY="S0MDKZEARVRd-_-ElR6viWycEosPIFNzTlaP8aTQIztJf9vT" \
AGNET_API_KEY="rnmhr3mo3wTDOXixi8BF0lTpA-ziln4knstoj5AcBFkbEZNP" \
SECRET_KEY="dev-secret" \
DB_HOST=143.198.35.133 DB_NAME=farmforkdb DB_USER=customer DB_PASSWORD=subscribers \
FLASK_APP=src/app.py flask run --port 5001
# Starts on http://localhost:5001
```

### 3. Test the flow

```bash
# Login via C&S and get a JWT
curl -c cookies.txt -X POST http://localhost:7500/login \
  -d "username=S297&password=5195551809"

JWT=$(curl -s -b cookies.txt http://localhost:7500/gettoken | python3 -c "import sys,json; print(json.load(sys.stdin)['jwt'])")

# Initiate checkout on OO
curl -c oo_cookies.txt -X POST http://localhost:5001/checkout/initiate \
  -H "Content-Type: application/json" \
  -d "{\"items\":[{\"productId\":\"WF-CARROTS\",\"productName\":\"Carrots\",\"quantity\":2.0,\"unit\":\"kg\"}],\"userToken\":\"$JWT\"}"

# Submit order
curl -b oo_cookies.txt -X POST http://localhost:5001/checkout/submit \
  -H "Content-Type: application/json" \
  -d '{"addressLine1":"721 King St.","city":"Kitchener","province":"ON","postalCode":"M0X3A6","dropOff":true}'
```

---

## Integration Points

### What's Implemented

| Point | Status | Notes |
|-------|--------|-------|
| C&S JWT passed to OO at checkout initiate | Done | `userToken` field in `POST /checkout/initiate` |
| OO reads C&S client data via CFP CSV cache | Done | `get_client(client_id)` in `cfp_client.py` |
| OO notifies C&S after order placed | Stubbed | Needs C&S server URL + JWT_PASS confirmed |
| C&S login → OO shop redirect | Manual | User navigates manually; no redirect yet |

### What's Pending

- **C&S → OO redirect after login:** C&S could redirect to `http://localhost:5001` after successful login so the user lands directly on the shop
- **JWT decoding in OO:** Decode the C&S JWT in `checkout/submit` to extract `client_id`, then call C&S `POST /update-delivery` automatically
- **Shared session / SSO:** Currently two separate cookie jars — one per service

---

## Known Issues

- **CIS Section 1 server instability:** `POST /orders/ship` returns 500 intermittently. This is a Section 1 infrastructure issue, not application code. The lock (`POST /orders/request`) works when CIS is healthy.
- **C&S `POST /update-delivery` not yet called:** Needs `client_id` from decoded JWT and C&S server URL to be confirmed for cross-service calls.

---

## Repo Links

- Order Orchestration: [AaronD7492/Order-Orchestration-Team](https://github.com/AaronD7492/Order-Orchestration-Team) — branch `dilraj`
- Customer & Subscription: [MaksPyvo/Customer\_-\_Subscription\_ESD](https://github.com/MaksPyvo/Customer_-_Subscription_ESD)
