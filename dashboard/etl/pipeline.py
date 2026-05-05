"""
ETL Pipeline — Multi-file aware.

When multiple files are uploaded to the same session:
  1. Read each file, apply its column mapping → normalise to standard schema
  2. Combine all files into ONE DataFrame:
     - Same schema → stack (concat) rows
     - Different schema, shared keys → merge dimension data (customer/product
       info) by shared keys, then stack all transaction rows enriched with
       the merged dimensions
  3. Clean the combined DataFrame once
  4. Load to DB once

Single-file uploads work exactly the same — step 2 is a no-op.
"""

import pandas as pd
import numpy as np
import re
import io
import csv as csv_mod
from django.db import transaction, connection
from dashboard.models import Customer, Product, Sale, AnalysisSession


# ─── Canonical column names ──────────────────────────────────────────────────

EXPECTED_COLUMNS = [
    'Order ID', 'Order Date',
    'Customer ID', 'Customer Name', 'Region', 'City',
    'Product ID', 'Product Name', 'Category', 'Sub-Category',
    'Quantity', 'Unit Price', 'Discount', 'Sales', 'Profit',
    'Payment Mode', 'Delivery Time', 'Returned', 'Shipping Cost',
    'Age', 'Gender',
]

# Helper columns used for derivation but not stored directly
HELPER_COLUMNS = ['Cost']

# Columns that describe a customer (dimension data)
CUSTOMER_DIMS = ['Customer ID', 'Customer Name', 'Region', 'City', 'Age', 'Gender']

# Columns that describe a product (dimension data)
PRODUCT_DIMS = ['Product ID', 'Product Name', 'Category', 'Sub-Category']

# ─── Alias table ─────────────────────────────────────────────────────────────

ALIASES = {
    'order id': [
        'orderid', 'transactionid', 'transaction_id', 'txnid', 'txn_id',
        'invoiceid', 'invoice', 'orderno', 'order_no', 'order_number',
        'refid', 'ref_id', 'billno', 'receiptid', 'sonumber',
    ],
    'order date': [
        'orderdate', 'transactiondate', 'transaction_date', 'txndate',
        'purchasedate', 'saledate', 'sale_date', 'billdate', 'invoicedate',
        'date', 'created_at',
    ],
    'customer id': [
        'customerid', 'custid', 'cust_id', 'clientid', 'userid',
        'buyerid', 'accountid', 'memberid',
    ],
    'customer name': [
        'customername', 'custname', 'cust_name', 'customer', 'name',
        'client', 'buyer', 'fullname', 'full_name', 'contactname',
        'clientname', 'buyername', 'accountname',
    ],
    'region': [
        'customerregion', 'customer_region', 'custregion', 'area', 'zone',
        'state', 'territory', 'province', 'country', 'district',
        'salesregion', 'locationregion',
    ],
    'city': [
        'customercity', 'customer_city', 'custcity', 'location', 'town',
        'municipality', 'shippingcity', 'cityname', 'metro', 'place',
    ],
    'product id': [
        'productid', 'prodid', 'prod_id', 'sku', 'itemid', 'item_id',
        'articleid', 'skuid', 'itemcode', 'barcode', 'upc', 'asin',
    ],
    'product name': [
        'productname', 'product', 'item', 'itemname', 'article',
        'description', 'skuname', 'productdescription', 'itemdescription',
    ],
    'category': [
        'productcategory', 'product_category', 'prodcategory', 'type',
        'group', 'department', 'producttype', 'productgroup', 'segment',
        'productline', 'division', 'class',
    ],
    'sub-category': [
        'subcategory', 'sub_category', 'subclass', 'subgroup',
        'subtype', 'subsegment', 'productsubtype',
    ],
    'quantity': [
        'qty', 'units', 'count', 'volume', 'numitems', 'pieces',
        'noofunits', 'amount',
    ],
    'unit price': [
        'unitprice', 'price', 'productprice', 'product_price', 'prodprice',
        'rate', 'msrp', 'listprice', 'sellingprice', 'mrp',
        'itemprice', 'eachprice', 'perunit',
    ],
    'cost': [
        'costprice', 'cost_price', 'unitcost', 'unit_cost', 'cogs',
        'costofgoods', 'cost_of_goods', 'purchaseprice', 'purchase_price',
        'buyprice', 'buy_price', 'wholesaleprice', 'basecost',
        'manufacturingcost', 'productioncost',
    ],
    'discount': [
        'disc', 'discount_pct', 'discountpercent', 'discountrate',
        'off', 'reduction', 'rebate', 'promo', 'markdown', 'offer',
    ],
    'sales': [
        'revenue', 'totalsales', 'total_sales', 'totalamount', 'total_amount',
        'linetotal', 'grosssales', 'netsales', 'total', 'grandtotal',
        'saleamount', 'ordertotal', 'ordervalue', 'turnover',
    ],
    'profit': [
        'netprofit', 'net_profit', 'margin', 'gain', 'profitmargin',
        'earnings', 'netincome', 'grossprofit', 'contribution',
    ],
    'payment mode': [
        'paymentmode', 'payment', 'paymentmethod', 'payment_method',
        'paytype', 'paymode', 'paymenttype', 'tender', 'paymethod',
        'transactiontype', 'method',
    ],
    'delivery time': [
        'deliverytime', 'deliverytimedays', 'delivery_time_days',
        'shippingdays', 'transittime', 'leadtime', 'shipdays',
        'deliverydays', 'delivery_days', 'daystodeliver', 'tat',
    ],
    'returned': [
        'return', 'refunded', 'isreturned', 'is_returned',
        'returnstatus', 'refund', 'isrefunded', 'cancelled', 'voided',
    ],
    'shipping cost': [
        'shippingcost', 'shipping', 'freight', 'deliveryfee',
        'shipcharge', 'deliverycharge', 'logisticscost', 'postage',
    ],
    'age': [
        'customerage', 'customer_age', 'userage', 'buyerage', 'custage',
    ],
    'gender': [
        'customergender', 'customer_gender', 'sex', 'usergender', 'custgender',
    ],
}


def _normalise(text: str) -> str:
    return re.sub(r'[^a-z0-9]', '', str(text).lower())


# ─────────────────────────────────────────────────────────────────────────────
# Multi-file combiner
# ─────────────────────────────────────────────────────────────────────────────

def combine_dataframes(dfs: list[pd.DataFrame]) -> pd.DataFrame:
    """
    Combine multiple normalised DataFrames (all with EXPECTED_COLUMNS) into one.

    Strategy:
      1. Build a master customer dimension table from ALL files (merged by
         Customer ID — take the most complete info for each customer).
      2. Build a master product dimension table from ALL files (merged by
         Product ID — take the most complete info for each product).
      3. Stack all transaction rows from every file.
      4. Replace each row's customer/product dimension columns with the
         merged (most complete) dimension data.

    This ensures that if File A has (Cust ID, Name) and File B has
    (Cust ID, Name, Region, City, Age, Gender), every row for that
    customer — regardless of which file it came from — gets the full
    (Name, Region, City, Age, Gender) data.
    """
    if len(dfs) == 1:
        return dfs[0]

    print(f"\n[Combine] Merging {len(dfs)} files...")
    for i, df in enumerate(dfs):
        print(f"  File {i+1}: {len(df)} rows")

    # Helper: for a group of rows sharing a key, pick the row with the most
    # non-empty / non-default values
    placeholder_vals = {'', '0', 'Unknown', 'Uncategorized', 'General', 'nan', 'None'}

    def _pick_best(group, dim_cols):
        def score(row):
            return sum(
                1 for col in dim_cols
                if pd.notna(row[col]) and str(row[col]).strip() not in placeholder_vals
            )
        group = group.copy()
        group['_score'] = group.apply(score, axis=1)
        return group.sort_values('_score', ascending=False).iloc[0].drop('_score')

    # --- 1. Master customer dimension ---
    cust_frames = []
    for df in dfs:
        c = df[CUSTOMER_DIMS].copy()
        c = c[c['Customer ID'].notna() & (c['Customer ID'].astype(str).str.strip() != '')]
        if not c.empty:
            cust_frames.append(c.drop_duplicates(subset=['Customer ID']))

    if cust_frames:
        all_custs = pd.concat(cust_frames, ignore_index=True)
        best_rows = []
        for _, grp in all_custs.groupby('Customer ID', group_keys=False):
            best_rows.append(_pick_best(grp, CUSTOMER_DIMS))
        master_custs = pd.DataFrame(best_rows, columns=CUSTOMER_DIMS)
        print(f"  Master customers: {len(master_custs)} unique IDs")
    else:
        master_custs = pd.DataFrame(columns=CUSTOMER_DIMS)

    # --- 2. Master product dimension ---
    prod_frames = []
    for df in dfs:
        p = df[PRODUCT_DIMS].copy()
        p = p[p['Product ID'].notna() & (p['Product ID'].astype(str).str.strip() != '')]
        if not p.empty:
            prod_frames.append(p.drop_duplicates(subset=['Product ID']))

    if prod_frames:
        all_prods = pd.concat(prod_frames, ignore_index=True)
        best_rows = []
        for _, grp in all_prods.groupby('Product ID', group_keys=False):
            best_rows.append(_pick_best(grp, PRODUCT_DIMS))
        master_prods = pd.DataFrame(best_rows, columns=PRODUCT_DIMS)
        print(f"  Master products: {len(master_prods)} unique IDs")
    else:
        master_prods = pd.DataFrame(columns=PRODUCT_DIMS)

    # --- 3. Stack all transaction rows ---
    combined = pd.concat(dfs, ignore_index=True)
    print(f"  Stacked rows: {len(combined)}")

    # --- 4. Enrich rows with master dimension data ---
    # Replace dimension columns with best-known values (from any file)
    non_cust_key = [c for c in CUSTOMER_DIMS if c != 'Customer ID']
    non_prod_key = [c for c in PRODUCT_DIMS if c != 'Product ID']

    if not master_custs.empty:
        combined.drop(columns=non_cust_key, inplace=True)
        combined = combined.merge(master_custs, on='Customer ID', how='left')

    if not master_prods.empty:
        combined.drop(columns=non_prod_key, errors='ignore', inplace=True)
        combined = combined.merge(master_prods, on='Product ID', how='left')

    # Ensure all expected columns exist (fill any gaps from merge)
    for col in EXPECTED_COLUMNS:
        if col not in combined.columns:
            combined[col] = np.nan

    combined = combined[EXPECTED_COLUMNS].copy()

    # Dedup: if the same Order ID appears in multiple files, keep first
    before = len(combined)
    combined.drop_duplicates(subset=['Order ID'], keep='first', inplace=True)
    if len(combined) < before:
        print(f"  Deduped: {before} → {len(combined)} (removed {before - len(combined)} duplicate Order IDs)")

    print(f"  Final combined: {len(combined)} rows")
    return combined


# ─────────────────────────────────────────────────────────────────────────────
# ETL Pipeline
# ─────────────────────────────────────────────────────────────────────────────

class ETLPipeline:
    """ETL pipeline for single or multi-file e-commerce data."""

    def __init__(self, file_path, column_mapping=None, session_id=None):
        self.file_path = file_path
        self.column_mapping = column_mapping or {}
        self.session_id = session_id
        self.raw_df: pd.DataFrame | None = None
        self.final_df: pd.DataFrame | None = None

    # ─── Public API ───────────────────────────────────────────────────────

    def run(self, wipe_existing=False):
        """Single-file pipeline: extract → map → clean → load."""
        print(f"\n{'='*60}")
        print(f"ETL Pipeline: {self.file_path}")
        print(f"{'='*60}")

        self.extract()
        self._apply_mapping()
        self.clean()
        self.load(wipe_existing=wipe_existing)

        print(f"Pipeline complete — {len(self.final_df)} rows loaded.\n")

    @classmethod
    def run_multi(cls, file_configs: list[dict], session_id: int,
                  wipe_existing=False):
        """
        Multi-file pipeline.

        file_configs: [{'file_path': str, 'column_mapping': dict}, ...]

        Steps:
          1. Extract + map each file independently
          2. Combine into one DataFrame (merge dimensions, stack transactions)
          3. Clean once
          4. Load once
        """
        print(f"\n{'='*60}")
        print(f"Multi-File ETL Pipeline ({len(file_configs)} files)")
        print(f"{'='*60}")

        normalised_dfs = []
        for i, cfg in enumerate(file_configs):
            print(f"\n--- File {i+1}: {cfg['file_path']} ---")
            p = cls(cfg['file_path'], cfg.get('column_mapping', {}), session_id)
            p.extract()
            p._apply_mapping()
            normalised_dfs.append(p.raw_df)

        combined = combine_dataframes(normalised_dfs)

        pipeline = cls(file_configs[0]['file_path'], session_id=session_id)
        pipeline.raw_df = combined
        pipeline.clean()
        pipeline.load(wipe_existing=wipe_existing)

        print(f"\nMulti-file pipeline complete — {len(pipeline.final_df)} rows loaded.\n")
        return pipeline

    def get_mapping_preview(self):
        if self.raw_df is None:
            self.extract()
        mapping = self._build_auto_mapping()
        return {
            'headers': list(self.raw_df.columns),
            'mapping': mapping,
            'expected': EXPECTED_COLUMNS + HELPER_COLUMNS,
            'confidence': len(mapping) / len(EXPECTED_COLUMNS),
        }

    # ─── Extract ──────────────────────────────────────────────────────────

    def extract(self):
        path = self.file_path
        if path.endswith('.csv'):
            self.raw_df = self._read_csv(path)
        elif path.endswith(('.xlsx', '.xls')):
            self.raw_df = self._read_excel(path)
        else:
            raise ValueError("Unsupported file type. Use .csv or .xlsx")

        self.raw_df.dropna(how='all', inplace=True)
        self.raw_df.dropna(axis=1, how='all', inplace=True)
        self.raw_df.columns = [str(c).strip() for c in self.raw_df.columns]
        print(f"[Extract] {len(self.raw_df)} rows × {len(self.raw_df.columns)} cols")

    @staticmethod
    def _read_csv(path):
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        for enc in encodings:
            try:
                with open(path, 'r', encoding=enc) as f:
                    sample = f.read(8192)
                dialect = csv_mod.Sniffer().sniff(sample, delimiters=',;\t|')
                return pd.read_csv(path, encoding=enc, sep=dialect.delimiter,
                                   on_bad_lines='skip')
            except (UnicodeDecodeError, csv_mod.Error):
                continue
        return pd.read_csv(path, encoding='latin-1', on_bad_lines='skip')

    @staticmethod
    def _read_excel(path):
        xls = pd.ExcelFile(path, engine='openpyxl')
        if len(xls.sheet_names) == 1:
            return pd.read_excel(xls, sheet_name=xls.sheet_names[0])
        best, best_n = xls.sheet_names[0], 0
        for s in xls.sheet_names:
            n = len(pd.read_excel(xls, sheet_name=s))
            if n > best_n:
                best, best_n = s, n
        return pd.read_excel(xls, sheet_name=best)

    # ─── Column Mapping ──────────────────────────────────────────────────

    def _build_auto_mapping(self) -> dict:
        raw_cols = list(self.raw_df.columns)
        mapping = {}
        used_raw = set()

        all_targets = EXPECTED_COLUMNS + HELPER_COLUMNS
        for expected in all_targets:
            norm_exp = _normalise(expected)
            matched = None

            for col in raw_cols:
                if col in used_raw:
                    continue
                if _normalise(col) == norm_exp:
                    matched = col
                    break

            if not matched:
                alias_key = expected.lower()
                if alias_key in ALIASES:
                    for col in raw_cols:
                        if col in used_raw:
                            continue
                        if _normalise(col) in [_normalise(a) for a in ALIASES[alias_key]]:
                            matched = col
                            break

            if matched:
                mapping[matched] = expected
                used_raw.add(matched)

        return mapping

    def _apply_mapping(self):
        if not self.column_mapping:
            self.column_mapping = self._build_auto_mapping()

        df = self.raw_df.copy()
        df.rename(columns=self.column_mapping, inplace=True)

        mapped = list(self.column_mapping.values())
        missing = [c for c in EXPECTED_COLUMNS if c not in df.columns]

        print(f"[Map] {len(mapped)}/{len(EXPECTED_COLUMNS)} columns matched")
        if missing:
            print(f"  Missing (defaults): {missing}")

        # Check if Cost helper column was mapped
        has_cost_col = 'Cost' in df.columns
        if has_cost_col:
            print("  [Map] Cost/COGS column detected — will derive Profit from Sales - Cost")

        for col in missing:
            if col in ('Quantity',):
                df[col] = 1
            elif col in ('Unit Price', 'Discount', 'Sales', 'Profit',
                         'Shipping Cost', 'Delivery Time'):
                df[col] = 0
            elif col == 'Order Date':
                df[col] = pd.Timestamp.now()
            elif col == 'Returned':
                df[col] = False
            elif col in ('Customer ID', 'Product ID', 'Gender'):
                df[col] = ''
            elif col == 'Age':
                df[col] = np.nan
            else:
                df[col] = 'Unknown'

        # Keep Cost column temporarily for profit derivation in clean()
        keep_cols = EXPECTED_COLUMNS + (['Cost'] if has_cost_col else [])
        self.raw_df = df[[c for c in keep_cols if c in df.columns]].copy()

    # ─── Clean ────────────────────────────────────────────────────────────

    def clean(self):
        df = self.raw_df.copy()
        n0 = len(df)

        df = df.astype(object)

        nan_strings = {
            'nan', 'NaN', 'null', 'NULL', 'None', 'none', 'N/A', 'n/a',
            'NA', '#N/A', '#NA', '#VALUE!', '#REF!', '-', '--', '', ' ',
            'undefined', 'nil', 'missing',
        }
        for col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df.loc[df[col].isin(nan_strings), col] = np.nan

        num_cols = {
            'Quantity': 0, 'Unit Price': 0, 'Discount': 0, 'Sales': 0,
            'Profit': 0, 'Shipping Cost': 0, 'Delivery Time': 0,
        }
        for col, default in num_cols.items():
            df[col] = (df[col].astype(str)
                       .str.replace(r'[\$£€₹,\s]', '', regex=True)
                       .str.replace(r'^\((.*)\)$', r'-\1', regex=True))
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(default).astype(float)

        df['Age'] = pd.to_numeric(df['Age'], errors='coerce')

        df = df[df['Quantity'] > 0].copy()
        df = df[df['Unit Price'] >= 0].copy()

        raw_dates = df['Order Date'].copy()
        df['Order Date'] = pd.to_datetime(raw_dates, errors='coerce', format='mixed')
        nat = df['Order Date'].isna()
        if nat.any():
            df.loc[nat, 'Order Date'] = pd.to_datetime(
                raw_dates[nat], dayfirst=True, errors='coerce')
        df = df.dropna(subset=['Order Date']).copy()
        df = df[df['Order Date'] <= pd.Timestamp.now() + pd.Timedelta(days=30)].copy()

        if (df['Discount'] > 0).any():
            median_disc = df.loc[df['Discount'] > 0, 'Discount'].median()
            if median_disc > 1:
                df['Discount'] = df['Discount'] / 100.0
        df['Discount'] = df['Discount'].clip(0, 1)

        no_sales = (df['Sales'] == 0) & (df['Quantity'] > 0) & (df['Unit Price'] > 0)
        df.loc[no_sales, 'Sales'] = (
            df.loc[no_sales, 'Quantity']
            * df.loc[no_sales, 'Unit Price']
            * (1 - df.loc[no_sales, 'Discount'])
        )

        # Derive profit from Cost column if available
        if 'Cost' in df.columns:
            df['Cost'] = (df['Cost'].astype(str)
                          .str.replace(r'[\$£€₹,\s]', '', regex=True)
                          .str.replace(r'^\((.*)\)$', r'-\1', regex=True))
            df['Cost'] = pd.to_numeric(df['Cost'], errors='coerce').fillna(0).astype(float)

            no_profit = (df['Profit'] == 0) & (df['Sales'] > 0)
            if no_profit.mean() > 0.90:
                df.loc[no_profit, 'Profit'] = df.loc[no_profit, 'Sales'] - (
                    df.loc[no_profit, 'Quantity'] * df.loc[no_profit, 'Cost']
                )
                print(f"  [Clean] Profit derived from Sales - (Qty × Cost) for {no_profit.sum()} rows")
            df.drop(columns=['Cost'], inplace=True)
        elif (df['Profit'] == 0).mean() > 0.95 and (df['Sales'] > 0).any():
            print("  [Clean] No Profit or Cost column in source data — profit will show as N/A")

        text_defaults = {
            'Customer Name': 'Unknown Customer', 'Region': 'Unknown',
            'City': 'Unknown', 'Category': 'Uncategorized',
            'Sub-Category': 'General', 'Payment Mode': 'Unknown',
            'Customer ID': '', 'Product ID': '', 'Gender': '',
        }
        for col, default in text_defaults.items():
            df[col] = df[col].fillna(default)
            df.loc[df[col].astype(str).str.strip().str.lower().isin(
                ['0', '0.0', 'unknown', 'nan', 'none', '']), col] = default

        for col in ['Customer Name', 'Region', 'City', 'Category',
                     'Sub-Category', 'Product Name', 'Payment Mode']:
            df[col] = df[col].astype(str).str.strip().str.title()

        gmap = {'m': 'Male', 'male': 'Male', 'f': 'Female', 'female': 'Female',
                'other': 'Other', 'nonbinary': 'Other', 'non-binary': 'Other'}
        df['Gender'] = df['Gender'].astype(str).str.strip().str.lower().map(gmap).fillna('')

        bmap = {'yes': True, 'no': False, '1': True, '0': False,
                'true': True, 'false': False, '1.0': True, '0.0': False,
                'y': True, 'n': False, 'completed': False, 'pending': False,
                'returned': True, 'cancelled': False}
        df['Returned'] = df['Returned'].astype(str).str.strip().str.lower().map(bmap).fillna(False)

        pay_map = {
            'Cc': 'Credit Card', 'Credit': 'Credit Card', 'Visa': 'Credit Card',
            'Mastercard': 'Credit Card', 'Debit': 'Debit Card',
            'Cash': 'COD', 'Cash On Delivery': 'COD', 'Cod': 'COD',
            'Paypal': 'PayPal', 'Pay Pal': 'PayPal',
            'Upi': 'UPI', 'Gpay': 'UPI', 'Google Pay': 'UPI', 'Phonepe': 'UPI',
            'Netbanking': 'Net Banking', 'Net-Banking': 'Net Banking',
            'Net Banking': 'Net Banking',
        }
        df['Payment Mode'] = df['Payment Mode'].replace(pay_map)

        df['Age'] = df['Age'].clip(0, 120).replace(0, np.nan)
        df['Delivery Time'] = df['Delivery Time'].clip(0, 365)
        df['Shipping Cost'] = df['Shipping Cost'].clip(0)

        df.drop_duplicates(inplace=True)

        self.final_df = df.reset_index(drop=True)
        print(f"[Clean] {n0} → {len(df)} rows ({n0 - len(df)} dropped)")

    # ─── Load to DB ───────────────────────────────────────────────────────

    def load(self, wipe_existing=False):
        df = self.final_df
        if df is None or len(df) == 0:
            raise ValueError("No valid rows to load after cleaning.")

        session = None
        if self.session_id:
            session = AnalysisSession.objects.get(id=self.session_id)

        sess_kw = {'session': session} if session else {}

        with transaction.atomic():
            if wipe_existing:
                Sale.objects.filter(**sess_kw).delete()
                Customer.objects.filter(**sess_kw).delete()
                Product.objects.filter(**sess_kw).delete()
                print("[Load] Wiped existing session data.")

            # ── Customers ──
            # Deduplicate by name+region+city (the DB constraint), not just Customer ID
            cust_dedup_cols = ['Customer Name', 'Region', 'City']
            unique_custs = df[CUSTOMER_DIMS].drop_duplicates(subset=cust_dedup_cols)

            all_existing = list(Customer.objects.filter(**sess_kw))
            by_cid = {c.customer_id: c for c in all_existing if c.customer_id}
            by_nrc = {(c.name, c.region, c.city): c for c in all_existing}

            new_count = 0
            for _, row in unique_custs.iterrows():
                cid = str(row['Customer ID']).strip() if pd.notna(row['Customer ID']) and row['Customer ID'] != '' else None
                name = row['Customer Name']
                region = row['Region']
                city = row['City']
                age = int(row['Age']) if pd.notna(row['Age']) and float(row['Age']) > 0 else None
                gender = row['Gender'] if row['Gender'] not in ('', None, 'nan') else None

                found = by_cid.get(cid) if cid else None
                if not found:
                    found = by_nrc.get((name, region, city))

                if found:
                    updates = {}
                    if not found.age and age:
                        updates['age'] = age
                    if not found.gender and gender:
                        updates['gender'] = gender
                    if (not found.region or found.region == 'Unknown') and region != 'Unknown':
                        updates['region'] = region
                    if (not found.city or found.city == 'Unknown') and city != 'Unknown':
                        updates['city'] = city
                    if not found.customer_id and cid:
                        updates['customer_id'] = cid
                    if updates:
                        new_r = updates.get('region', found.region)
                        new_c = updates.get('city', found.city)
                        collision = Customer.objects.filter(
                            session=session, name=found.name,
                            region=new_r, city=new_c,
                        ).exclude(id=found.id).exists()
                        if not collision:
                            Customer.objects.filter(id=found.id).update(**updates)
                else:
                    c, created = Customer.objects.get_or_create(
                        session=session, name=name, region=region, city=city,
                        defaults={
                            'customer_id': cid, 'age': age, 'gender': gender,
                        },
                    )
                    if cid:
                        by_cid[cid] = c
                    if created:
                        by_nrc[(name, region, city)] = c
                        new_count += 1
                    else:
                        by_nrc[(name, region, city)] = c

            all_custs = list(Customer.objects.filter(**sess_kw).values(
                'id', 'customer_id', 'name', 'region', 'city'))
            cust_by_id = {c['customer_id']: c['id'] for c in all_custs if c['customer_id']}
            cust_by_nrc = {(c['name'], c['region'], c['city']): c['id'] for c in all_custs}
            print(f"[Load] Customers: {new_count} new, {len(all_custs)} total")

            # ── Products ──
            unique_prods = df[PRODUCT_DIMS].drop_duplicates(subset=['Product Name'])
            existing_by_pid = {p.product_id: p for p in Product.objects.filter(**sess_kw) if p.product_id}
            existing_by_name = {p.name: p for p in Product.objects.filter(**sess_kw)}

            new_prod = 0
            for _, row in unique_prods.iterrows():
                pid = str(row['Product ID']).strip() if pd.notna(row['Product ID']) and row['Product ID'] != '' else None
                name = row['Product Name']

                found = existing_by_pid.get(pid) if pid else None
                if not found:
                    found = existing_by_name.get(name)

                if found:
                    updates = {}
                    if (not found.category or found.category in ('Uncategorized', 'Unknown')) and row['Category'] not in ('Uncategorized', 'Unknown'):
                        updates['category'] = row['Category']
                    if (not found.sub_category or found.sub_category == 'General') and row['Sub-Category'] != 'General':
                        updates['sub_category'] = row['Sub-Category']
                    if not found.product_id and pid:
                        updates['product_id'] = pid
                    if updates:
                        Product.objects.filter(id=found.id).update(**updates)
                else:
                    p, created = Product.objects.get_or_create(
                        session=session, name=name,
                        defaults={
                            'product_id': pid,
                            'category': row['Category'],
                            'sub_category': row['Sub-Category'],
                        },
                    )
                    if pid:
                        existing_by_pid[pid] = p
                    existing_by_name[name] = p
                    if created:
                        new_prod += 1

            all_prods = list(Product.objects.filter(**sess_kw).values(
                'id', 'product_id', 'name'))
            prod_by_id = {p['product_id']: p['id'] for p in all_prods if p['product_id']}
            prod_by_name = {p['name']: p['id'] for p in all_prods}
            print(f"[Load] Products: {new_prod} new, {len(all_prods)} total")

            # ── Sales ──
            def resolve_customer(row):
                cid = str(row['Customer ID']).strip() if pd.notna(row['Customer ID']) and row['Customer ID'] != '' else ''
                if cid and cid in cust_by_id:
                    return cust_by_id[cid]
                return cust_by_nrc.get((row['Customer Name'], row['Region'], row['City']))

            def resolve_product(row):
                pid = str(row['Product ID']).strip() if pd.notna(row['Product ID']) and row['Product ID'] != '' else ''
                if pid and pid in prod_by_id:
                    return prod_by_id[pid]
                return prod_by_name.get(row['Product Name'])

            df = df.copy()
            df['_cust_db_id'] = df.apply(resolve_customer, axis=1)
            df['_prod_db_id'] = df.apply(resolve_product, axis=1)

            before = len(df)
            df = df.dropna(subset=['_cust_db_id', '_prod_db_id'])
            if len(df) < before:
                print(f"  Warning: {before - len(df)} rows dropped (unresolved FK)")

            if session:
                existing_orders = set(
                    Sale.objects.filter(session=session).values_list('order_id', flat=True))
                before = len(df)
                df = df[~df['Order ID'].isin(existing_orders)]
                if len(df) < before:
                    print(f"  Skipped {before - len(df)} duplicate order IDs")

            if len(df) == 0:
                print("[Load] No new rows to insert.")
                self.final_df = df
                return

            session_id_val = session.id if session else ''
            sale_cols = [
                'order_id', 'order_date', 'customer_id', 'product_id',
                'quantity', 'unit_price', 'discount', 'total_sales', 'profit',
                'payment_mode', 'delivery_time_days', 'returned', 'shipping_cost',
                'is_flagged', 'session_id',
            ]

            is_postgres = connection.vendor == 'postgresql'

            if is_postgres:
                buf = io.StringIO()
                writer = csv_mod.writer(buf)
                for _, row in df.iterrows():
                    dt = row['Delivery Time']
                    writer.writerow([
                        row['Order ID'],
                        row['Order Date'].strftime('%Y-%m-%d'),
                        int(row['_cust_db_id']),
                        int(row['_prod_db_id']),
                        int(row['Quantity']),
                        float(row['Unit Price']),
                        float(row['Discount']),
                        float(row['Sales']),
                        float(row['Profit']),
                        row['Payment Mode'],
                        int(dt) if pd.notna(dt) and dt > 0 else '',
                        't' if row['Returned'] else 'f',
                        float(row['Shipping Cost']),
                        'f',
                        session_id_val,
                    ])
                buf.seek(0)

                copy_sql = (
                    f"COPY dashboard_sale ({', '.join(sale_cols)}) "
                    "FROM STDIN WITH (FORMAT CSV, NULL '')"
                )
                with connection.cursor() as cursor:
                    cursor.copy_expert(copy_sql, buf)
                print(f"[Load] {len(df)} sales inserted via COPY.")
            else:
                sales_objs = []
                for _, row in df.iterrows():
                    dt = row['Delivery Time']
                    sales_objs.append(Sale(
                        session=session,
                        order_id=row['Order ID'],
                        order_date=row['Order Date'],
                        customer_id=int(row['_cust_db_id']),
                        product_id=int(row['_prod_db_id']),
                        quantity=int(row['Quantity']),
                        unit_price=float(row['Unit Price']),
                        discount=float(row['Discount']),
                        total_sales=float(row['Sales']),
                        profit=float(row['Profit']),
                        payment_mode=row['Payment Mode'],
                        delivery_time_days=int(dt) if pd.notna(dt) and dt > 0 else None,
                        returned=bool(row['Returned']),
                        shipping_cost=float(row['Shipping Cost']),
                        is_flagged=False,
                    ))
                Sale.objects.bulk_create(sales_objs, batch_size=2000)
                print(f"[Load] {len(sales_objs)} sales inserted via bulk_create.")

            self.final_df = df
