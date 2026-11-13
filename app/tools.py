import json
import re
from datetime import date
from pathlib import Path

from langchain_core.tools import tool

DATA = json.loads((Path(__file__).resolve().parents[1] / "data" / "orders.json").read_text(encoding="utf-8"))
ORDERS = {o["order_id"]: o for o in DATA["orders"]}
TODAY = date.fromisoformat(DATA["store_today"])          # fixed, so every run gives the same answers

RETURN_WINDOW_DAYS = 10                                  # normal returns: within 10 days of delivery
DAMAGED_WINDOW_DAYS = 30                                 # damaged / defective / wrong item: within 30 days
NON_RETURNABLE = {"innerwear", "groceries", "gift_cards"}
REASONS = {"wrong_size", "changed_mind", "damaged", "defective", "wrong_item", "not_as_described"}
ORDER_ID = re.compile(r"^ORD-\d{5}$")
METRO_PREFIXES = {"11", "40", "50", "56", "60", "70"}    # Delhi, Mumbai, Hyderabad, Bengaluru, Chennai, Kolkata


def _find(order_id: str) -> dict:
    """Look an order up. GIVEN. Raises ValueError for an order that doesn't exist."""
    if not re.match(r"^ORD-\d{5}$", order_id):
        raise ValueError(f"order_id must look like ORD-12345, got {order_id!r}")
    if order_id not in ORDERS:
        raise ValueError(f"no order {order_id} - ask the customer to check the order number")
    return ORDERS[order_id]


@tool(parse_docstring=True)
def get_order_status(order_id: str) -> dict:
    """Status of ONE order: placed, shipped, out for delivery, delivered or cancelled, with its dates. Use when the
    customer asks where their order is or when it will arrive. Do NOT use it for general policy questions.

    Args:
        order_id: the order number exactly as the customer gave it, e.g. ORD-10233
    """
    o = _find(order_id)
    keys = ("order_id", "item", "status", "ordered_on", "delivered_on", "expected_delivery", "cancelled_on")
    return {k: o[k] for k in keys if k in o} | {"store_today": TODAY.isoformat()}


@tool(parse_docstring=True)
def get_delivery_estimate(pincode: str, speed: str = "standard") -> dict:
    """How many working days delivery takes to an Indian pincode, and what it costs. Use when the customer asks how
    long delivery will take to their area, or the price of express delivery.

    Args:
        pincode: the 6-digit Indian postal code, e.g. 500081
        speed: "standard" or "express"
    """
    if not re.match(r"^\d{6}$", str(pincode)):
        raise ValueError(f"pincode must be exactly 6 digits, got {pincode!r}")

    if speed not in {"standard", "express"}:
        raise ValueError(f"speed must be 'standard' or 'express', got {speed!r}")
    metro = pincode[:2] in METRO_PREFIXES
    if speed == "express":
        return {"pincode": pincode, "speed": "express", "days": "next day" if metro else "2-3 working days",
                "charge_rupees": 99}
    return {"pincode": pincode, "speed": "standard", "days": "2-3 working days" if metro else "4-6 working days",
            "charge_rupees": 0, "note": "free standard delivery on orders above Rs 499; Rs 49 below that"}


@tool(parse_docstring=True)
def check_return_eligibility(order_id: str, reason: str) -> dict:
    """
    Checks if an order is eligible for a return based on delivery status, item category, and the return window.
    Call this tool ONLY when the customer explicitly requests to return an item or asks for a refund for a specific order.
    DO NOT call this tool if the customer is only asking about delivery status, shipping estimates, or general policies.

    Args:
        order_id: The complete order number provided by the customer. Must strictly follow the format 'ORD-12345' ('ORD-' followed by 5 digits).
        reason: The customer's reason for the return. Must be one of the exact strings: "damaged", "defective", "wrong_item", or "other". If the customer provides a different reason, map it to "other".
    """
    o = _find(order_id)

    if reason not in REASONS:
        raise ValueError(f"reason must be one of {list(REASONS)}, got {reason!r}")
    if o.get("status") != "delivered":
        return json.dumps({
        "eligible": False, 
        "why": "not delivered yet, you can cancel it on the website"
        })
    if o.get("category") in NON_RETURNABLE:
        return json.dumps({
        "eligible": False, 
        "why": f"{o['category']} is non-returnable"
        })
    window = DAMAGED_WINDOW_DAYS if reason in {"damaged", "defective", "wrong_item"} else RETURN_WINDOW_DAYS
    days = (TODAY - date.fromisoformat(o["delivered_on"])).days
    if days > window:
        return json.dumps({
        "eligible": False, 
        "why": f"delivered {days} days ago; window is {window} days"
        })
    return json.dumps({
    "eligible": True,
    "days_since_delivery": days,
    "window_days": window,
    "refund_rupees": o.get("price"),
    "how": "start the return on the website: My Orders > Return"
})



TOOLS = {"get_order_status": get_order_status, "get_delivery_estimate": get_delivery_estimate,
         "check_return_eligibility": check_return_eligibility}
