def fulfillment_status(order: dict[str, object]) -> str:
    if order.get("cancelled"):
        return "cancelled"
    if order.get("shipped"):
        return "shipped"
    return "pending"

