"""Generate seeded, synthetic raw e-commerce CSVs (with deliberate dirt for the ETL to clean)."""
import csv
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

CATEGORIES = {
    "Electronics": (25, 600),
    "Home & Kitchen": (8, 150),
    "Apparel": (10, 120),
    "Books": (5, 40),
    "Sports": (12, 250),
    "Beauty": (6, 90),
}
COUNTRIES = ["US", "US", "US", "CA", "GB", "DE", "FR", "AU", "IN"]
METHODS = ["card", "card", "card", "paypal", "bank_transfer", "gift_card"]
FIRST = ["Ava", "Liam", "Noah", "Mia", "Zoe", "Eli", "Ivy", "Omar", "Priya", "Chen", "Sofia", "Lucas"]
LAST = ["Smith", "Patel", "Garcia", "Kim", "Nguyen", "Brown", "Lopez", "Khan", "Muller", "Rossi"]


def _write(path: Path, header: list[str], rows: list[list]) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def generate(out_dir: Path, seed: int = 42, n_customers: int = 40000, n_products: int = 150,
             n_orders: int = 60000) -> dict[str, int]:
    rng = random.Random(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    start, end = date(2023, 1, 1), date(2024, 12, 31)
    span = (end - start).days

    # products: some prices carry a "$" prefix (raw feeds are messy)
    products = []
    for pid in range(1, n_products + 1):
        cat = rng.choice(list(CATEGORIES))
        lo, hi = CATEGORIES[cat]
        price = round(rng.uniform(lo, hi), 2)
        shown = f"${price}" if rng.random() < 0.1 else price
        products.append([pid, f"{cat.split()[0]} Item {pid:03d}", cat, shown, round(price * rng.uniform(0.4, 0.7), 2)])
    price_of = {p[0]: float(str(p[3]).lstrip("$")) for p in products}

    # customers: ~5% duplicated with a newer updated_at; messy casing/whitespace; some null countries
    customers, signup = [], {}
    for cid in range(1, n_customers + 1):
        fn, ln = rng.choice(FIRST), rng.choice(LAST)
        sd = start + timedelta(days=rng.randint(0, span - 60))
        signup[cid] = sd
        country = rng.choice(COUNTRIES) if rng.random() > 0.03 else ""
        email = f"{fn}.{ln}{cid}@example.com"
        customers.append([cid, f" {fn} ", ln.upper() if rng.random() < 0.1 else ln, email, country, sd.isoformat(), sd.isoformat()])
    for row in rng.sample(customers, n_customers // 20):
        dup = list(row)
        dup[3] = dup[3].upper()
        dup[6] = (date.fromisoformat(row[6]) + timedelta(days=30)).isoformat()
        customers.append(dup)

    orders, items, payments = [], [], []
    item_id = pay_id = 0
    for oid in range(1, n_orders + 1):
        cid = rng.randint(1, n_customers)
        od = min(end, signup[cid] + timedelta(days=int(rng.expovariate(1 / 150))))
        status = rng.choices(["completed", "cancelled", "returned"], [0.88, 0.07, 0.05])[0]
        orders.append([oid, cid, od.isoformat(), status])
        total = Decimal(0)
        for pid in rng.sample(range(1, n_products + 1), rng.choices([1, 2, 3, 4], [5, 3, 2, 1])[0]):
            item_id += 1
            qty = rng.choices([1, 2, 3], [0.7, 0.2, 0.1])[0]
            disc = rng.choice([0, 0, 0, 0.05, 0.1, 0.2])
            items.append([item_id, oid, pid, qty, price_of[pid], disc])
            # line amounts are rounded to cents, exactly as the warehouse does, so payments reconcile
            total += (Decimal(str(price_of[pid])) * qty * (1 - Decimal(str(disc)))).quantize(Decimal('0.01'), ROUND_HALF_UP)
        if status != "cancelled":
            pay_id += 1
            payments.append([pay_id, oid, rng.choice(METHODS), total, (od + timedelta(days=rng.randint(0, 2))).isoformat()])
    orders += [list(o) for o in rng.sample(orders, 100)]  # exact duplicate order rows

    _write(out_dir / "customers.csv", ["customer_id", "first_name", "last_name", "email", "country", "signup_date", "updated_at"], customers)
    _write(out_dir / "products.csv", ["product_id", "product_name", "category", "unit_price", "cost"], products)
    _write(out_dir / "orders.csv", ["order_id", "customer_id", "order_date", "status"], orders)
    _write(out_dir / "order_items.csv", ["order_item_id", "order_id", "product_id", "quantity", "unit_price", "discount"], items)
    _write(out_dir / "payments.csv", ["payment_id", "order_id", "payment_method", "amount", "payment_date"], payments)
    return {"customers": len(customers), "products": len(products), "orders": len(orders),
            "order_items": len(items), "payments": len(payments)}


if __name__ == "__main__":
    print(generate(Path("data/raw")))
