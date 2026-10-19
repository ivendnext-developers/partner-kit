"""Stand-ins for the tests: a shop that answers the catalogue's reads from memory, and an invoice a template can read."""
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 40


class FakeShop:
    def __init__(self, prices, items, files):
        self.prices, self.items, self.files, self.asked = prices, items, files, []

    def list(self, doctype, fields, filters, start):
        if doctype == "Item Price":
            pl = next(f[2] for f in filters if f[0] == "price_list")
            rows = [r for r in self.prices if r["price_list"] == pl]
        else:
            codes = next(f[2] for f in filters if f[0] == "name")
            rows = [r for r in self.items if r["name"] in codes]
        return rows[start:start + 200]

    def file(self, path, limit):
        self.asked.append(path)
        data = self.files[path]
        if isinstance(data, Exception):
            raise data
        return None if len(data) > limit else data


def price(code, rate, **kw):
    return {"price_list": "WS", "item_code": code, "item_name": code, "uom": "Nos", "price_list_rate": rate,
            "currency": "USD", **kw}


def item(code, group="Phones", image=None, name=None, disabled=0):
    return {"name": code, "item_name": name or code, "item_group": group, "image": image, "stock_uom": "Nos", "disabled": disabled}


class Row:
    """A document or a row of one, as a print template reads it: attributes, and get_formatted(field)."""

    def __init__(self, **kw):
        self.__dict__.update(kw)

    def get_formatted(self, f):
        v = getattr(self, f, None)
        return "" if v is None else (f"{v:,.2f}" if isinstance(v, (int, float)) else str(v))


def invoice(customer, **kw):
    base = dict(name="SINV-0001", customer=customer, customer_name=customer, company="Demo Retail", company_tax_id="TAX-1",
                company_address_display="1 Main Street", address_display="2 Side Road", tax_id=None, posting_date="2026-10-16",
                due_date="2026-11-16", currency="USD", net_total=100.0, total_taxes_and_charges=15.0, grand_total=115.0,
                in_words="USD One Hundred Fifteen Only.", terms=None, remarks="No Remarks", po_no=None, po_date=None,
                territory=None, shipping_address=None,
                items=[Row(item_code="CASE", item_name="Phone case", uom="Nos", qty=2, rate=50.0, price_list_rate=50.0,
                           discount_percentage=0, amount=100.0, net_rate=50.0, net_amount=100.0, customer_item_code=None)],
                taxes=[Row(description="VAT", tax_amount=15.0)])
    base.update(kw)
    return Row(**base)
