import csv
import random
import os
from datetime import datetime, timedelta

random.seed(42)

# --- Shared reference data ---
first_names = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Krishna", "Ishaan",
    "Ananya", "Diya", "Myra", "Sara", "Aanya", "Aadhya", "Isha", "Pari", "Riya", "Neha",
    "Rahul", "Amit", "Priya", "Sneha", "Rohit", "Pooja", "Vikram", "Kavita", "Suresh", "Meena",
    "Deepak", "Sunita", "Rajesh", "Nisha", "Manoj", "Divya", "Karan", "Swati", "Nikhil", "Anjali",
    "James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda", "David", "Elizabeth",
    "William", "Susan", "Richard", "Jessica", "Joseph", "Sarah", "Thomas", "Karen", "Charles", "Lisa",
    "Daniel", "Nancy", "Matthew", "Betty", "Anthony", "Margaret", "Mark", "Sandra", "Donald", "Ashley",
    "Oliver", "Emma", "Noah", "Sophia", "Liam", "Isabella", "Lucas", "Mia", "Mason", "Charlotte",
]

last_names = [
    "Sharma", "Verma", "Gupta", "Singh", "Kumar", "Patel", "Joshi", "Reddy", "Nair", "Iyer",
    "Mehta", "Shah", "Desai", "Kulkarni", "Rao", "Pillai", "Menon", "Bhat", "Chopra", "Malhotra",
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
    "Anderson", "Taylor", "Thomas", "Hernandez", "Moore", "Martin", "Jackson", "Thompson", "White", "Lopez",
    "Lee", "Harris", "Clark", "Lewis", "Robinson", "Walker", "Young", "Allen", "King", "Wright",
]

categories = {
    "Electronics": [
        ("Wireless Mouse", 15.99, 49.99),
        ("Bluetooth Headphones", 29.99, 149.99),
        ("USB-C Hub", 19.99, 79.99),
        ("Portable Charger", 12.99, 59.99),
        ("Smartwatch", 49.99, 299.99),
        ("Webcam HD", 24.99, 89.99),
        ("Keyboard Mechanical", 39.99, 159.99),
        ("Monitor Stand", 19.99, 69.99),
        ("Laptop Stand", 22.99, 79.99),
        ("External SSD 1TB", 59.99, 179.99),
    ],
    "Clothing": [
        ("Cotton T-Shirt", 9.99, 34.99),
        ("Denim Jeans", 24.99, 89.99),
        ("Hoodie", 19.99, 69.99),
        ("Running Shoes", 39.99, 129.99),
        ("Formal Shirt", 19.99, 59.99),
        ("Winter Jacket", 49.99, 199.99),
        ("Casual Shorts", 14.99, 44.99),
        ("Sports Socks (3-pack)", 7.99, 19.99),
        ("Cap", 8.99, 29.99),
        ("Scarf", 12.99, 39.99),
    ],
    "Home & Kitchen": [
        ("Coffee Maker", 29.99, 129.99),
        ("Blender", 24.99, 89.99),
        ("Toaster", 19.99, 59.99),
        ("Non-Stick Pan", 14.99, 49.99),
        ("Knife Set", 29.99, 99.99),
        ("Water Bottle", 9.99, 29.99),
        ("Storage Containers", 12.99, 39.99),
        ("Cutting Board", 9.99, 34.99),
        ("Dish Rack", 14.99, 44.99),
        ("Tea Kettle", 19.99, 54.99),
    ],
    "Books": [
        ("Python Programming", 19.99, 49.99),
        ("Data Science Handbook", 24.99, 59.99),
        ("Machine Learning Guide", 29.99, 69.99),
        ("Web Development", 14.99, 44.99),
        ("Business Strategy", 12.99, 39.99),
        ("Self-Help Guide", 9.99, 24.99),
        ("Fiction Novel", 7.99, 19.99),
        ("History of AI", 14.99, 34.99),
        ("Cookbook", 12.99, 29.99),
        ("Travel Guide", 9.99, 24.99),
    ],
    "Sports": [
        ("Yoga Mat", 14.99, 49.99),
        ("Dumbbells (Pair)", 19.99, 79.99),
        ("Resistance Bands", 9.99, 29.99),
        ("Jump Rope", 7.99, 19.99),
        ("Football", 14.99, 39.99),
        ("Basketball", 19.99, 49.99),
        ("Tennis Racket", 29.99, 99.99),
        ("Swimming Goggles", 9.99, 29.99),
        ("Cycling Gloves", 12.99, 34.99),
        ("Gym Bag", 19.99, 59.99),
    ],
}

regions = ["North", "South", "East", "West", "Central"]
cities = {
    "North": ["Delhi", "Chandigarh", "Jaipur", "Lucknow", "Amritsar"],
    "South": ["Bangalore", "Chennai", "Hyderabad", "Kochi", "Coimbatore"],
    "East": ["Kolkata", "Bhubaneswar", "Patna", "Guwahati", "Ranchi"],
    "West": ["Mumbai", "Pune", "Ahmedabad", "Surat", "Goa"],
    "Central": ["Bhopal", "Indore", "Nagpur", "Raipur", "Jabalpur"],
}
payment_methods = ["Credit Card", "Debit Card", "UPI", "Net Banking", "Cash on Delivery", "Wallet"]
statuses = ["Completed", "Completed", "Completed", "Completed", "Pending", "Returned", "Cancelled"]
genders = ["Male", "Female", "Other"]

# Generate consistent customers
NUM_CUSTOMERS = 800
customers = []
for i in range(1, NUM_CUSTOMERS + 1):
    fname = random.choice(first_names)
    lname = random.choice(last_names)
    region = random.choice(regions)
    city = random.choice(cities[region])
    customers.append({
        "cust_id": f"CUST-{i:04d}",
        "name": f"{fname} {lname}",
        "age": random.randint(18, 70),
        "gender": random.choice(genders),
        "email": f"{fname.lower()}.{lname.lower()}{i}@example.com",
        "region": region,
        "city": city,
    })

# Generate consistent products
products = []
pid = 1
for cat, items in categories.items():
    for name, low, high in items:
        products.append({
            "product_id": f"PROD-{pid:04d}",
            "name": name,
            "category": cat,
            "price": round(random.uniform(low, high), 2),
        })
        pid += 1

NUM_ROWS = random.randint(7000, 8500)
start_date = datetime(2024, 1, 1)
end_date = datetime(2025, 12, 31)
date_range_days = (end_date - start_date).days

# ---- Dataset 1: Sales Transactions ----
dataset1_path = os.path.join("data", "sales_transactions.csv")
os.makedirs("data", exist_ok=True)

print(f"Generating Dataset 1 with {NUM_ROWS} rows...")

with open(dataset1_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "Sr No", "Cust Name", "Cust ID", "Product Name", "Product ID",
        "Product Price", "Quantity", "Transaction ID", "Transaction Date"
    ])
    for i in range(1, NUM_ROWS + 1):
        cust = random.choice(customers)
        prod = random.choice(products)
        qty = random.choices([1, 2, 3, 4, 5], weights=[40, 30, 15, 10, 5])[0]
        txn_date = start_date + timedelta(days=random.randint(0, date_range_days))
        txn_id = f"TXN-{i:06d}"

        writer.writerow([
            i,
            cust["name"],
            cust["cust_id"],
            prod["name"],
            prod["product_id"],
            prod["price"],
            qty,
            txn_id,
            txn_date.strftime("%Y-%m-%d"),
        ])

print(f"Dataset 1 saved to {dataset1_path}")

# ---- Dataset 2: Order Details (different columns) ----
NUM_ROWS_2 = random.randint(6000, 9000)
dataset2_path = os.path.join("data", "order_details.csv")

print(f"Generating Dataset 2 with {NUM_ROWS_2} rows...")

with open(dataset2_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow([
        "Order ID", "Cust Name", "Cust ID", "Customer Email",
        "Customer Age", "Customer Gender",
        "Customer Region", "Customer City",
        "Product Name", "Product ID", "Product Category",
        "Unit Price", "Quantity", "Discount (%)", "Total Amount",
        "Payment Method", "Order Status", "Order Date", "Delivery Days",
        "Rating"
    ])
    for i in range(1, NUM_ROWS_2 + 1):
        cust = random.choice(customers)
        prod = random.choice(products)
        qty = random.choices([1, 2, 3, 4, 5], weights=[40, 30, 15, 10, 5])[0]
        discount = random.choices([0, 5, 10, 15, 20, 25], weights=[30, 25, 20, 12, 8, 5])[0]
        total = round(prod["price"] * qty * (1 - discount / 100), 2)
        order_date = start_date + timedelta(days=random.randint(0, date_range_days))
        status = random.choice(statuses)
        delivery_days = random.randint(1, 15) if status == "Completed" else None
        rating = random.choices([1, 2, 3, 4, 5, None], weights=[3, 5, 15, 35, 30, 12])[0] if status == "Completed" else None
        order_id = f"ORD-{i:06d}"

        writer.writerow([
            order_id,
            cust["name"],
            cust["cust_id"],
            cust["email"],
            cust["age"],
            cust["gender"],
            cust["region"],
            cust["city"],
            prod["name"],
            prod["product_id"],
            prod["category"],
            prod["price"],
            qty,
            discount,
            total,
            random.choice(payment_methods),
            status,
            order_date.strftime("%Y-%m-%d"),
            delivery_days if delivery_days else "",
            rating if rating else "",
        ])

print(f"Dataset 2 saved to {dataset2_path}")
print("Done!")
