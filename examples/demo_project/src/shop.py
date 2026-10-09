"""A small shop module used to demonstrate test-gap."""

TAX_RATE = 0.10


def apply_discount(price, percent):
    if percent < 0 or percent > 100:
        raise ValueError("percent must be between 0 and 100")
    return round(price * (1 - percent / 100), 2)


def calculate_total(prices, discount_percent=0, members=False):
    total = 0
    for price in prices:
        if price < 0:
            raise ValueError("prices cannot be negative")
        total += price
    if members and discount_percent == 0:
        discount_percent = 5
    total = apply_discount(total, discount_percent)
    return round(total * (1 + TAX_RATE), 2)


def format_receipt(items):
    lines = [f"{name}: {price:.2f}" for name, price in items]
    return "\n".join(lines) if lines else "(empty)"


class Cart:
    def __init__(self):
        self.items = []

    def add_item(self, name, price):
        self.items.append((name, price))

    def remove_item(self, name):
        self.items = [item for item in self.items if item[0] != name]

    def total(self):
        return calculate_total([price for _, price in self.items])
