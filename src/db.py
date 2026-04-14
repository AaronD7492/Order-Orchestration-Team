from datetime import date

import psycopg2
from src.config import Config


def get_db_connection():
    return psycopg2.connect(
        host=Config.db_host(),
        port=Config.db_port(),
        dbname=Config.db_name(),
        user=Config.db_user(),
        password=Config.db_password()
    )


def get_team_secret():
    query = """
        SELECT secret
        FROM dtsecrets
        WHERE teamname = %s
        LIMIT 1
    """

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, (Config.team_name(),))
            row = cursor.fetchone()

            if row is None:
                raise ValueError(f"No secret found for team '{Config.team_name()}'")

            return row[0]
    finally:
        conn.close()

def create_order(customer_id, status="pending"):
    """Insert a new order, returns the new order id"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO orders (customer_id, status, order_date, total_cost)
            VALUES (%s, %s, %s, %s)
            RETURNING id
            """,
            (customer_id, status, str(date.today()), 0.0)
        )
        order_id = cur.fetchone()[0]
        conn.commit()
        return order_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def add_order_item(order_id, product_id, quantity, unit, price):
    """Add a line item to an order"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO order_item (order_id, product_id, quantity, unit, price)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
            """,
            (order_id, product_id, quantity, unit, price)
        )
        item_id = cur.fetchone()[0]
        conn.commit()
        return item_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def update_order_total(order_id):
    """Recalculate and update the total_cost from order_items"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE orders
            SET total_cost = (
                SELECT COALESCE(SUM(quantity * price), 0)
                FROM order_item
                WHERE order_id = %s
            )
            WHERE id = %s
            """,
            (order_id, order_id)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def save_order_history(customer_id, order_id):
    """Record the order in order_history"""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO order_history (customer_id, order_id)
            VALUES (%s, %s)
            """,
            (customer_id, order_id)
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

def save_full_order(customer_id, items):
    """
    Save a complete order end-to-end.
    
    items: list of dicts with keys: product_id, quantity, unit, price
    
    Example:
        save_full_order(1, [
            {"product_id": 3, "quantity": 2.0, "unit": "kg", "price": 4.99},
            {"product_id": 7, "quantity": 1.0, "unit": "bunch", "price": 2.50}
        ])
    """
    order_id = create_order(customer_id)
    
    for item in items:
        add_order_item(order_id, item["product_id"], item["quantity"], item["unit"], item["price"])
    
    update_order_total(order_id)
    save_order_history(customer_id, order_id)
    
    return order_id
