import logging
import requests
from src.config import Config

logger = logging.getLogger(__name__)


def post_stock_change(cart_items: list) -> dict:

    """
    Notify the CE integration team of a stock change after an order is shipped.
    Always posts with status 'pending' — CE team approves/declines on their side.
    """
    products = [
        {
            "productId": item["productId"],
            "quantityChange": -int(item["quantity"]),  # negative = stock reduced
            "unit": item.get("unit", "kg"),
        }
        for item in cart_items
    ]

    response = requests.post(
        f"{Config.CE_BASE_URL}/api/v1/stock_change",
        headers={
            "Content-Type": "application/json",
            "X-API-Key": Config.CE_API_KEY,
        },
        json={
            "products": products,
            "status": "pending",
        },
        timeout=5,
    )
    response.raise_for_status()
    return response.json()
