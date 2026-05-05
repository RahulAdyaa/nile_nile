"""
Generates fixtures/dummy_data.json with 500 sale records
plus associated customers and products.
"""
import json
import random
from datetime import date, timedelta

random.seed(42)

REGIONS = ['North', 'South', 'East', 'West', 'Central']
CITIES = {
    'North': ['Delhi', 'Chandigarh', 'Amritsar', 'Ludhiana', 'Jaipur'],
    'South': ['Bangalore', 'Chennai', 'Hyderabad', 'Kochi', 'Coimbatore'],
    'East':  ['Kolkata', 'Bhubaneswar', 'Patna', 'Guwahati', 'Ranchi'],
    'West':  ['Mumbai', 'Pune', 'Ahmedabad', 'Surat', 'Nagpur'],
    'Central': ['Bhopal', 'Indore', 'Raipur', 'Jabalpur', 'Gwalior'],
}
GENDERS = ['Male', 'Female', 'Other']

CATEGORIES = {
    'Electronics':  ['Laptops', 'Mobiles', 'Tablets', 'Accessories', 'Cameras'],
    'Clothing':     ['Men', 'Women', 'Kids', 'Sportswear', 'Ethnic'],
    'Groceries':    ['Dairy', 'Beverages', 'Snacks', 'Vegetables', 'Fruits'],
    'Furniture':    ['Sofas', 'Tables', 'Chairs', 'Beds', 'Cabinets'],
    'Books':        ['Fiction', 'Non-Fiction', 'Academic', 'Comics', 'Magazines'],
}

PAYMENT_MODES = ['Credit Card', 'Debit Card', 'UPI', 'Net Banking', 'Cash on Delivery', 'Wallet']

FIRST_NAMES = ['Arjun', 'Priya', 'Rohan', 'Sneha', 'Amit', 'Deepa', 'Vikram', 'Anjali',
               'Rahul', 'Kavya', 'Suresh', 'Nisha', 'Kiran', 'Pooja', 'Manoj', 'Divya',
               'Arun', 'Geeta', 'Ravi', 'Sunita', 'Nitin', 'Meera', 'Sanjay', 'Ritu',
               'Aditya', 'Shruti', 'Varun', 'Neha', 'Kartik', 'Swati']
LAST_NAMES  = ['Sharma', 'Patel', 'Kumar', 'Singh', 'Verma', 'Joshi', 'Gupta', 'Nair',
               'Rao', 'Mehta', 'Reddy', 'Iyer', 'Pillai', 'Das', 'Bose', 'Chatterjee',
               'Tiwari', 'Mishra', 'Pandey', 'Shah']

PRODUCT_NAMES = {
    'Electronics': {
        'Laptops':     ['ProBook 450', 'UltraSlim X1', 'GameForce G7', 'WorkStation Z5', 'AirNote 13'],
        'Mobiles':     ['Pixel 8', 'Nova S23', 'Flagship One', 'BudgetKing A5', 'Snap 12 Pro'],
        'Tablets':     ['TabPro 11', 'DrawPad 4', 'LiteTab 8', 'KidsTab', 'WorkTab X'],
        'Accessories': ['Wireless Charger', 'BT Earbuds', 'Smartwatch V3', 'USB-C Hub', 'Power Bank 20K'],
        'Cameras':     ['DSLR Z90', 'Mirrorless M50', 'Action Cam 4K', 'Webcam HD', 'Drone Mini'],
    },
    'Clothing': {
        'Men':        ['Formal Shirt Blue', 'Slim Jeans Dark', 'Polo Tee White', 'Chinos Khaki', 'Blazer Navy'],
        'Women':      ['Floral Kurti', 'Palazzo Set', 'Saree Banarasi', 'Anarkali Red', 'Maxi Dress'],
        'Kids':       ['Cartoon Tee', 'Dungaree Set', 'School Uniform', 'Party Frock', 'Track Suit'],
        'Sportswear': ['Running Shoes', 'Yoga Pants', 'Gym Tank', 'Compression Tights', 'Sports Jacket'],
        'Ethnic':     ['Sherwani Gold', 'Lehenga Pink', 'Pathani Suit', 'Nehru Jacket', 'Bandhani Dupatta'],
    },
    'Groceries': {
        'Dairy':      ['Full Cream Milk 1L', 'Paneer 200g', 'Cheddar Cheese', 'Dahi 400g', 'Butter 100g'],
        'Beverages':  ['Green Tea 100pcs', 'Orange Juice 1L', 'Cold Coffee Mix', 'Protein Shake', 'Sparkling Water'],
        'Snacks':     ['Baked Chips', 'Granola Bar', 'Mixed Nuts 200g', 'Dark Chocolate', 'Popcorn Caramel'],
        'Vegetables': ['Baby Spinach 500g', 'Cherry Tomatoes', 'Broccoli 1kg', 'Bell Peppers', 'Zucchini 500g'],
        'Fruits':     ['Strawberries 250g', 'Mango 1kg', 'Blueberries 125g', 'Kiwi 6pcs', 'Avocado 2pcs'],
    },
    'Furniture': {
        'Sofas':    ['3-Seater L Shape', 'Loveseat Grey', 'Recliner Oak', 'Ottoman Cube', 'Futon Sofa Bed'],
        'Tables':   ['Dining Table 6-Seat', 'Coffee Table Round', 'Study Desk', 'Console Table', 'Folding Table'],
        'Chairs':   ['Ergonomic Office Chair', 'Accent Chair Teal', 'Bar Stool Set', 'Bean Bag', 'Rocking Chair'],
        'Beds':     ['King Bed Frame', 'Queen Platform Bed', 'Bunk Bed Kids', 'Storage Bed', 'Daybed'],
        'Cabinets': ['Wardrobe 3-Door', 'Bookshelf 5-Tier', 'TV Cabinet', 'Shoe Rack', 'Filing Cabinet'],
    },
    'Books': {
        'Fiction':     ['The Lost Horizon', 'Midnight Echo', 'Crimson Tide', 'The Hollow King', 'Starfall'],
        'Non-Fiction': ['Atomic Habits', 'Sapiens', 'Deep Work', 'Zero to One', 'The Lean Startup'],
        'Academic':    ['Calculus Vol.2', 'Python for Data Science', 'Organic Chemistry', 'History of India', 'Microeconomics'],
        'Comics':      ['Spider-Man Vol.3', 'Tintin Moon', 'Asterix Gaul', 'Naruto Box Set', 'Batman Year One'],
        'Magazines':   ['National Geographic Apr', 'Forbes India', 'Vogue March', 'Time Weekly', 'Wired Tech'],
    },
}

START_DATE = date(2023, 1, 1)
END_DATE   = date(2024, 12, 31)

def rand_date():
    delta = (END_DATE - START_DATE).days
    return START_DATE + timedelta(days=random.randint(0, delta))

def rand_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"

# ── Build unique customers (50) ───────────────────────────────────────────────
customers = []
used_names = set()
pk_cust_start = 200001
for i in range(50):
    region = random.choice(REGIONS)
    city   = random.choice(CITIES[region])
    name   = rand_name()
    while name in used_names:
        name = rand_name()
    used_names.add(name)
    customers.append({
        "model": "dashboard.customer",
        "pk": pk_cust_start + i,
        "fields": {
            "customer_id": f"CUST{pk_cust_start + i}",
            "name": name,
            "region": region,
            "city": city,
            "age": random.randint(18, 65),
            "gender": random.choice(GENDERS),
        }
    })

# ── Build unique products (50) ────────────────────────────────────────────────
products = []
pk_prod_start = 300001
used_prods = set()
for i in range(50):
    cat     = random.choice(list(CATEGORIES.keys()))
    sub_cat = random.choice(CATEGORIES[cat])
    name    = random.choice(PRODUCT_NAMES[cat][sub_cat])
    key     = (name, cat, sub_cat)
    while key in used_prods:
        cat     = random.choice(list(CATEGORIES.keys()))
        sub_cat = random.choice(CATEGORIES[cat])
        name    = random.choice(PRODUCT_NAMES[cat][sub_cat])
        key     = (name, cat, sub_cat)
    used_prods.add(key)
    products.append({
        "model": "dashboard.product",
        "pk": pk_prod_start + i,
        "fields": {
            "product_id": f"PROD{pk_prod_start + i}",
            "name": name,
            "category": cat,
            "sub_category": sub_cat,
        }
    })

# ── Build 500 sales ───────────────────────────────────────────────────────────
sales = []
pk_sale_start = 400001
for i in range(500):
    cust    = random.choice(customers)
    prod    = random.choice(products)
    qty     = random.randint(1, 10)
    price   = round(random.uniform(50, 5000), 2)
    disc    = round(random.choice([0, 0, 0.05, 0.10, 0.15, 0.20]), 2)
    total   = round(qty * price * (1 - disc), 2)
    cost    = round(price * qty * random.uniform(0.4, 0.75), 2)
    profit  = round(total - cost, 2)
    shipping = round(random.uniform(0, 150), 2)
    returned = random.random() < 0.07   # 7% return rate
    flagged  = random.random() < 0.03   # 3% flagged

    sales.append({
        "model": "dashboard.sale",
        "pk": pk_sale_start + i,
        "fields": {
            "order_id": f"ORD-DUMMY-{pk_sale_start + i}",
            "order_date": rand_date().isoformat(),
            "customer": cust["pk"],
            "product": prod["pk"],
            "quantity": qty,
            "unit_price": str(price),
            "discount": str(disc),
            "total_sales": str(total),
            "profit": str(profit),
            "payment_mode": random.choice(PAYMENT_MODES),
            "delivery_time_days": random.randint(1, 14),
            "returned": returned,
            "shipping_cost": str(shipping),
            "is_flagged": flagged,
        }
    })

fixture = customers + products + sales

output_path = "fixtures/dummy_data.json"
with open(output_path, "w") as f:
    json.dump(fixture, f, indent=2)

print(f"Generated {len(customers)} customers, {len(products)} products, {len(sales)} sales")
print(f"Total records: {len(fixture)}")
print(f"Saved to: {output_path}")
