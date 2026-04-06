# Order Orchestration — Sprint 2

**Course:** PROG73020 | **Section:** 1 | **Team:** Order Orchestration

This branch (`dilraj`) contains the full Sprint 2 implementation of the Order Orchestration service for the Farm2Fork enterprise system.

---

## What This Service Does

Order Orchestration is the middle layer of the F2F platform. It:

1. **Serves the customer-facing shop** — pulls live inventory from CIS (warehouse) and the full product catalog from AgNet (suppliers)
2. **Manages the checkout flow** — receives cart from the homepage, collects shipping address, locks inventory in CIS, confirms the order, and hands off to Delivery Execution
3. **Syncs client data from CFP** — downloads CSV files from the Community Food Partners SFTP server on startup

---

## Architecture

```
Customer (browser)
       │
       ▼
  Order Orchestration (this service — port 5001)
       │               │                  │
       ▼               ▼                  ▼
  CIS (inventory   AgNet (supplier    ODS (delivery
   lock + ship)     catalog)          handoff — stub)
       │
  CFP SFTP (client data sync)
```

**Integration with Customer & Subscription team:**
- C&S handles login and issues a JWT
- Their JWT is passed to our `/checkout/initiate` as `userToken`
- After order success, we call C&S `POST /update-delivery` to update delivery counts (pending JWT_PASS sharing)

---

## Running Locally

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Set environment variables

```bash
export CIS_API_KEY="S0MDKZEARVRd-_-ElR6viWycEosPIFNzTlaP8aTQIztJf9vT"
export AGNET_API_KEY="rnmhr3mo3wTDOXixi8BF0lTpA-ziln4knstoj5AcBFkbEZNP"
export ODS_API_KEY="kMJIoWBGA_A5xNOLH86NRc2yha_4N8n5u-r_zAmB6BZvDssj"
export SECRET_KEY="your-secret-key"
export DB_HOST=143.198.35.133
export DB_NAME=farmforkdb
export DB_USER=customer
export DB_PASSWORD=subscribers
```

### 3. Run

```bash
FLASK_APP=src/app.py flask run --port 5001
```

Or for a quick demo cart:

```
http://localhost:5001/checkout/demo
```

---

## Key Routes

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/` | Customer shop — live CIS inventory + AgNet catalog |
| `POST` | `/checkout/initiate` | Receives cart from homepage, stores in session |
| `GET` | `/checkout` | Renders checkout form |
| `POST` | `/checkout/submit` | Full order flow: CIS lock → ship → DE handoff |
| `GET` | `/api/inventory` | JSON proxy to CIS pooled inventory |
| `GET` | `/secret` | Team secret from shared DB |
| `GET` | `/checkout/demo` | Dev shortcut — pre-fills cart for testing |

---

## External APIs

| Service | Base URL | Purpose |
|---------|----------|---------|
| CIS | `http://138.197.144.135:8201/api/v1` | Inventory lock + ship |
| AgNet | `http://146.190.243.241:8301/api/v1` | Supplier product catalog |
| ODS | `http://178.128.226.23:8001/api/v1` | Delivery execution (stubbed) |
| CFP | SFTP `68.183.203.17:22` | Client data CSV sync |

---

## Source Layout

```
src/
  app.py              # Flask routes
  config.py           # Environment variable config
  agnet_client.py     # AgNet vendor catalog fetching
  cis_client.py       # CIS inventory lock + ship
  cfp_client.py       # CFP SFTP sync
  ods_client.py       # ODS delivery handoff (stubbed)
  db.py               # PostgreSQL connection
  static/
    styles.css         # F2F shared design system
    checkout.css       # Checkout page styles
    checkout.js        # Checkout form + order submission
    shop.js            # Homepage cart + filter logic
    components.js      # Header/footer loader
    header.html
    footer.html
  templates/
    index.html         # Homepage / shop
    checkout.html      # Checkout page
tests/
  unit/
  integration/
  system/
```
