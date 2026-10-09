from shop import Cart, apply_discount


def test_apply_discount_takes_percentage_off():
    assert apply_discount(200, 10) == 180.0


def test_cart_add_item_stores_name_and_price():
    cart = Cart()
    cart.add_item("pen", 2)
    assert cart.items == [("pen", 2)]
