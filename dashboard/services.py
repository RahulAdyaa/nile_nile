import pandas as pd
import numpy as np
from .models import Customer, Product, Sale
from django.db.models import Sum, F, Max, Count, Avg, Q as models_Q
from django.utils import timezone
import io

class AnalyticsService:
    @staticmethod
    def get_rfm_segments(session=None):
        """
        Perform RFM Analysis on the normalized dataset.
        Scoped to an analysis session if provided.
        """
        # 1. Load Data from Sales
        queryset = Sale.objects.all()
        if session:
            queryset = queryset.filter(session=session)

        queryset = queryset.values(
            'customer_id', 'order_id', 'order_date', 'total_sales'
        )
        df = pd.DataFrame(queryset)
        
        if df.empty:
            return pd.DataFrame()

        # 2. Recency, Frequency, Monetary calculations
        # Reference date set to one day after the last order
        now = pd.to_datetime(df['order_date'].max()) + pd.Timedelta(days=1)
        df['order_date'] = pd.to_datetime(df['order_date'])
        
        rfm = df.groupby('customer_id').agg({
            'order_date': lambda x: (now - x.max()).days,
            'order_id': 'nunique',
            'total_sales': 'sum'
        }).rename(columns={
            'order_date': 'recency',
            'order_id': 'frequency',
            'total_sales': 'monetary'
        })
        
        # 3. Scoring (1-5, where 5 is best)
        try:
            rfm['r_score'] = pd.qcut(rfm['recency'].rank(method='first'), 5, labels=[5, 4, 3, 2, 1])
            rfm['f_score'] = pd.qcut(rfm['frequency'].rank(method='first'), 5, labels=[1, 2, 3, 4, 5])
            rfm['m_score'] = pd.qcut(rfm['monetary'].rank(method='first'), 5, labels=[1, 2, 3, 4, 5])
        except ValueError:
            rfm['r_score'] = 3
            rfm['f_score'] = 3
            rfm['m_score'] = 3

        rfm['rfm_score'] = rfm['r_score'].astype(str) + rfm['f_score'].astype(str) + rfm['m_score'].astype(str)
        
        # 4. Segment Assignment
        def segment_it(row):
            score = row['rfm_score']
            if score in ['555', '554', '545', '455', '454', '544', '445']: return 'Champions'
            if score[0] >= '4' and score[1] >= '4': return 'Loyal Customers'
            if score[0] >= '4' and score[2] >= '4': return 'Potential Loyalists'
            if score[0] >= '4': return 'New Customers'
            if score[0] == '3' and score[2] >= '3': return 'At Risk'
            if score[0] <= '2' and score[2] >= '4': return "Can't Lose Them"
            if score[0] <= '2' and score[1] <= '2': return 'Lost'
            return 'Others'

        rfm['segment'] = rfm.apply(segment_it, axis=1)
        return rfm.reset_index()

    @staticmethod
    def generate_csv_report(queryset):
        """Generate a well-formatted CSV with all relevant fields."""
        data = list(queryset.values(
            'order_id', 'order_date',
            'customer__customer_id', 'customer__name', 'customer__region',
            'customer__city', 'customer__age', 'customer__gender',
            'product__product_id', 'product__name', 'product__category', 'product__sub_category',
            'quantity', 'unit_price', 'discount', 'total_sales', 'profit',
            'shipping_cost', 'delivery_time_days', 'returned', 'payment_mode'
        ))
        df = pd.DataFrame(data)
        if df.empty:
            return None

        column_map = {
            'order_id': 'Order ID',
            'order_date': 'Order Date',
            'customer__customer_id': 'Customer ID',
            'customer__name': 'Customer Name',
            'customer__region': 'Region',
            'customer__city': 'City',
            'customer__age': 'Age',
            'customer__gender': 'Gender',
            'product__product_id': 'Product ID',
            'product__name': 'Product Name',
            'product__category': 'Category',
            'product__sub_category': 'Sub-Category',
            'quantity': 'Quantity',
            'unit_price': 'Unit Price',
            'discount': 'Discount',
            'total_sales': 'Total Sales',
            'profit': 'Profit',
            'shipping_cost': 'Shipping Cost',
            'delivery_time_days': 'Delivery Days',
            'returned': 'Returned',
            'payment_mode': 'Payment Mode',
        }
        df = df.rename(columns=column_map)

        # Format values for readability
        if 'Order Date' in df.columns:
            df['Order Date'] = pd.to_datetime(df['Order Date']).dt.strftime('%Y-%m-%d')
        for col in ['Unit Price', 'Discount', 'Total Sales', 'Profit', 'Shipping Cost']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').round(2)
        if 'Returned' in df.columns:
            df['Returned'] = df['Returned'].map({True: 'Yes', False: 'No', 1: 'Yes', 0: 'No'})

        output = io.StringIO()
        df.to_csv(output, index=False)
        return output.getvalue()

    @staticmethod
    def generate_excel_report(queryset):
        """Generate a full analytics Excel report with charts on every sheet."""
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        from openpyxl.chart import BarChart, LineChart, PieChart, Reference

        data = list(queryset.values(
            'order_id', 'order_date',
            'customer__customer_id', 'customer__name', 'customer__region',
            'customer__city', 'customer__age', 'customer__gender',
            'product__product_id', 'product__name', 'product__category', 'product__sub_category',
            'quantity', 'unit_price', 'discount', 'total_sales', 'profit',
            'shipping_cost', 'delivery_time_days', 'returned', 'payment_mode'
        ))
        df = pd.DataFrame(data)
        if df.empty:
            return None

        column_map = {
            'order_id': 'Order ID', 'order_date': 'Order Date',
            'customer__customer_id': 'Customer ID', 'customer__name': 'Customer Name',
            'customer__region': 'Region', 'customer__city': 'City',
            'customer__age': 'Age', 'customer__gender': 'Gender',
            'product__product_id': 'Product ID', 'product__name': 'Product Name',
            'product__category': 'Category', 'product__sub_category': 'Sub-Category',
            'quantity': 'Quantity', 'unit_price': 'Unit Price', 'discount': 'Discount',
            'total_sales': 'Total Sales', 'profit': 'Profit',
            'shipping_cost': 'Shipping Cost', 'delivery_time_days': 'Delivery Days',
            'returned': 'Returned', 'payment_mode': 'Payment Mode',
        }
        df = df.rename(columns=column_map)

        if 'Order Date' in df.columns:
            df['Order Date'] = pd.to_datetime(df['Order Date']).dt.strftime('%Y-%m-%d')
        for col in ['Unit Price', 'Discount', 'Total Sales', 'Profit', 'Shipping Cost']:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').round(2)
        if 'Returned' in df.columns:
            df['Returned'] = df['Returned'].map({True: 'Yes', False: 'No', 1: 'Yes', 0: 'No'})

        # ── Reusable style helpers ──
        hdr_font = Font(name='Inter', bold=True, color='FFFFFF', size=10)
        hdr_fill = PatternFill(start_color='1A1A2E', end_color='1A1A2E', fill_type='solid')
        hdr_align = Alignment(horizontal='center', vertical='center', wrap_text=True)
        cell_font = Font(name='Inter', size=9)
        cell_align = Alignment(vertical='center')
        thin_border = Border(bottom=Side(style='thin', color='E4E4E7'))
        alt_fill = PatternFill(start_color='F9FAFB', end_color='F9FAFB', fill_type='solid')
        currency_cols = {'Unit Price', 'Discount', 'Total Sales', 'Profit', 'Shipping Cost', 'Revenue', 'Avg Revenue'}

        def style_sheet(ws, num_cols, num_rows):
            """Apply standard header + data styling to a worksheet."""
            for c in range(1, num_cols + 1):
                cell = ws.cell(row=1, column=c)
                cell.font = hdr_font
                cell.fill = hdr_fill
                cell.alignment = hdr_align
            col_widths = {}
            for c in range(1, num_cols + 1):
                col_widths[c] = len(str(ws.cell(row=1, column=c).value or '')) + 4
                for r in range(2, num_rows + 2):
                    cell = ws.cell(row=r, column=c)
                    cell.font = cell_font
                    cell.alignment = cell_align
                    cell.border = thin_border
                    if r % 2 == 0:
                        cell.fill = alt_fill
                    col_name = ws.cell(row=1, column=c).value or ''
                    if col_name in currency_cols and cell.value is not None:
                        cell.number_format = '#,##0.00'
                    val_len = len(str(cell.value)) if cell.value else 0
                    col_widths[c] = max(col_widths[c], min(val_len + 3, 35))
            for c, w in col_widths.items():
                ws.column_dimensions[get_column_letter(c)].width = w

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:

            # ═══════════════════════════════════════
            # Sheet 1: Sales Data (raw transactions)
            # ═══════════════════════════════════════
            df.to_excel(writer, index=False, sheet_name='Sales Data')
            ws1 = writer.sheets['Sales Data']
            style_sheet(ws1, len(df.columns), len(df))
            ws1.freeze_panes = 'A2'
            ws1.auto_filter.ref = ws1.dimensions

            # ═══════════════════════════════════════
            # Sheet 2: Summary KPIs
            # ═══════════════════════════════════════
            total_rev = df['Total Sales'].sum() if 'Total Sales' in df.columns else 0
            total_profit = df['Profit'].sum() if 'Profit' in df.columns else 0
            margin = (total_profit / total_rev * 100) if total_rev > 0 else 0
            total_qty = df['Quantity'].sum() if 'Quantity' in df.columns else 0
            avg_del = df['Delivery Days'].mean() if 'Delivery Days' in df.columns else 0
            ret_count = (df['Returned'] == 'Yes').sum() if 'Returned' in df.columns else 0
            ret_rate = (ret_count / len(df) * 100) if len(df) > 0 else 0
            u_cust = df['Customer Name'].nunique() if 'Customer Name' in df.columns else 0
            u_prod = df['Product Name'].nunique() if 'Product Name' in df.columns else 0
            date_rng = ''
            if 'Order Date' in df.columns and len(df) > 0:
                date_rng = f"{df['Order Date'].min()} to {df['Order Date'].max()}"
            top_reg = df.groupby('Region')['Total Sales'].sum().idxmax() if 'Region' in df.columns and len(df) > 0 else 'N/A'
            top_cat = df.groupby('Category')['Total Sales'].sum().idxmax() if 'Category' in df.columns and len(df) > 0 else 'N/A'

            summary_df = pd.DataFrame({
                'Metric': ['Total Records', 'Total Revenue', 'Total Profit', 'Profit Margin',
                           'Avg Order Value', 'Total Quantity Sold', 'Avg Delivery Days',
                           'Return Rate', 'Unique Customers', 'Unique Products',
                           'Date Range', 'Top Region', 'Top Category'],
                'Value': [f"{len(df):,}", f"${total_rev:,.2f}", f"${total_profit:,.2f}",
                          f"{margin:.1f}%", f"${(total_rev/max(len(df),1)):,.2f}",
                          f"{total_qty:,}", f"{avg_del:.1f} days", f"{ret_rate:.1f}%",
                          f"{u_cust:,}", f"{u_prod:,}", date_rng, str(top_reg), str(top_cat)]
            })
            summary_df.to_excel(writer, index=False, sheet_name='Summary')
            ws2 = writer.sheets['Summary']
            style_sheet(ws2, 2, len(summary_df))

            # ═══════════════════════════════════════
            # Sheet 3: Revenue Trend + Line Chart
            # ═══════════════════════════════════════
            if 'Order Date' in df.columns and 'Total Sales' in df.columns:
                df_temp = df.copy()
                df_temp['Month'] = pd.to_datetime(df_temp['Order Date']).dt.to_period('M').astype(str)
                monthly = df_temp.groupby('Month').agg(
                    Revenue=('Total Sales', 'sum'),
                    Profit=('Profit', 'sum'),
                    Orders=('Order ID', 'count')
                ).reset_index().sort_values('Month')

                monthly.to_excel(writer, index=False, sheet_name='Revenue Trend')
                ws3 = writer.sheets['Revenue Trend']
                style_sheet(ws3, 4, len(monthly))

                # Line chart: Revenue + Profit over months
                chart = LineChart()
                chart.title = "Monthly Revenue & Profit Trend"
                chart.y_axis.title = "Amount ($)"
                chart.x_axis.title = "Month"
                chart.style = 10
                chart.width = 22
                chart.height = 13
                cats = Reference(ws3, min_col=1, min_row=2, max_row=len(monthly) + 1)
                rev_data = Reference(ws3, min_col=2, min_row=1, max_row=len(monthly) + 1)
                pft_data = Reference(ws3, min_col=3, min_row=1, max_row=len(monthly) + 1)
                chart.add_data(rev_data, titles_from_data=True)
                chart.add_data(pft_data, titles_from_data=True)
                chart.set_categories(cats)
                chart.series[0].graphicalProperties.line.width = 25000
                chart.series[1].graphicalProperties.line.width = 25000
                ws3.add_chart(chart, f"A{len(monthly) + 4}")

            # ═══════════════════════════════════════
            # Sheet 4: Category Breakdown + Pie Chart
            # ═══════════════════════════════════════
            if 'Category' in df.columns and 'Total Sales' in df.columns:
                cat_df = df.groupby('Category').agg(
                    Revenue=('Total Sales', 'sum'),
                    Profit=('Profit', 'sum'),
                    Orders=('Order ID', 'count'),
                    AvgPrice=('Unit Price', 'mean')
                ).reset_index().sort_values('Revenue', ascending=False)
                cat_df['AvgPrice'] = cat_df['AvgPrice'].round(2)
                cat_df = cat_df.rename(columns={'AvgPrice': 'Avg Price'})

                cat_df.to_excel(writer, index=False, sheet_name='Category Analysis')
                ws4 = writer.sheets['Category Analysis']
                style_sheet(ws4, 5, len(cat_df))

                # Pie chart: Revenue by Category
                pie = PieChart()
                pie.title = "Revenue by Category"
                pie.style = 10
                pie.width = 18
                pie.height = 13
                labels = Reference(ws4, min_col=1, min_row=2, max_row=len(cat_df) + 1)
                vals = Reference(ws4, min_col=2, min_row=1, max_row=len(cat_df) + 1)
                pie.add_data(vals, titles_from_data=True)
                pie.set_categories(labels)
                ws4.add_chart(pie, f"A{len(cat_df) + 4}")

            # ═══════════════════════════════════════
            # Sheet 5: Regional Analysis + Bar Chart
            # ═══════════════════════════════════════
            if 'Region' in df.columns and 'Total Sales' in df.columns:
                reg_df = df.groupby('Region').agg(
                    Revenue=('Total Sales', 'sum'),
                    Profit=('Profit', 'sum'),
                    Orders=('Order ID', 'count'),
                    Customers=('Customer Name', 'nunique')
                ).reset_index().sort_values('Revenue', ascending=False)

                reg_df.to_excel(writer, index=False, sheet_name='Regional Analysis')
                ws5 = writer.sheets['Regional Analysis']
                style_sheet(ws5, 5, len(reg_df))

                # Bar chart: Revenue + Profit by Region
                bar = BarChart()
                bar.type = "col"
                bar.title = "Revenue & Profit by Region"
                bar.y_axis.title = "Amount ($)"
                bar.style = 10
                bar.width = 20
                bar.height = 13
                cats = Reference(ws5, min_col=1, min_row=2, max_row=len(reg_df) + 1)
                rev_data = Reference(ws5, min_col=2, min_row=1, max_row=len(reg_df) + 1)
                pft_data = Reference(ws5, min_col=3, min_row=1, max_row=len(reg_df) + 1)
                bar.add_data(rev_data, titles_from_data=True)
                bar.add_data(pft_data, titles_from_data=True)
                bar.set_categories(cats)
                ws5.add_chart(bar, f"A{len(reg_df) + 4}")

            # ═══════════════════════════════════════
            # Sheet 6: RFM Customer Segments + Chart
            # ═══════════════════════════════════════
            try:
                from .models import AnalysisSession
                session = queryset.first()
                if session:
                    session_obj = session.session if hasattr(session, 'session') else None
                    rfm = AnalyticsService.get_rfm_segments(session=session_obj)
                    if rfm is not None and not rfm.empty:
                        seg_counts = rfm['segment'].value_counts().reset_index()
                        seg_counts.columns = ['Segment', 'Customers']
                        seg_counts = seg_counts.sort_values('Customers', ascending=False)

                        seg_counts.to_excel(writer, index=False, sheet_name='Customer Segments')
                        ws6 = writer.sheets['Customer Segments']
                        style_sheet(ws6, 2, len(seg_counts))

                        # Bar chart: Customer count by RFM segment
                        seg_bar = BarChart()
                        seg_bar.type = "col"
                        seg_bar.title = "RFM Customer Segments"
                        seg_bar.y_axis.title = "Number of Customers"
                        seg_bar.style = 10
                        seg_bar.width = 20
                        seg_bar.height = 13
                        cats = Reference(ws6, min_col=1, min_row=2, max_row=len(seg_counts) + 1)
                        vals = Reference(ws6, min_col=2, min_row=1, max_row=len(seg_counts) + 1)
                        seg_bar.add_data(vals, titles_from_data=True)
                        seg_bar.set_categories(cats)
                        ws6.add_chart(seg_bar, f"A{len(seg_counts) + 4}")
            except Exception:
                pass  # RFM is optional; don't break the export

        return output.getvalue()


class AnomalyDetector:
    """
    Detects anomalies in daily revenue and order volume using
    rolling Z-score (modified) + IQR methods. No hardcoded thresholds
    on values — only statistical deviation matters.
    """

    @staticmethod
    def detect(session, lookback_days=None):
        """
        Returns a dict with:
          - anomalies: list of dicts, one per anomalous day
          - chart_html: Plotly chart highlighting anomalies
          - summary: high-level stats
        """
        import plotly.graph_objects as go
        import plotly.io as pio

        qs = Sale.objects.filter(session=session)
        daily = list(
            qs.values('order_date')
            .annotate(
                revenue=Sum('total_sales'),
                orders=Count('id'),
                avg_discount=Avg('discount'),
                returns=Count('id', filter=models_Q(returned=True)),
            )
            .order_by('order_date')
        )

        if len(daily) < 14:
            return {'anomalies': [], 'chart_html': '', 'summary': _empty_summary()}

        df = pd.DataFrame(daily)
        df['date'] = pd.to_datetime(df['order_date'])
        df['revenue'] = df['revenue'].astype(float)
        df['orders'] = df['orders'].astype(int)
        df['returns'] = df['returns'].astype(int)
        df['avg_discount'] = df['avg_discount'].astype(float).fillna(0)
        df.set_index('date', inplace=True)
        df = df.asfreq('D', fill_value=0)

        if lookback_days:
            df = df.tail(lookback_days)

        # ── Rolling Z-score (window=14, min 7 days) ──
        window = min(14, len(df) // 2)
        if window < 5:
            window = 5

        roll_mean = df['revenue'].rolling(window=window, min_periods=5, center=False).mean()
        roll_std = df['revenue'].rolling(window=window, min_periods=5, center=False).std()
        # Avoid division by zero — if std is 0, no anomaly is possible
        roll_std = roll_std.replace(0, np.nan)
        df['z_revenue'] = (df['revenue'] - roll_mean) / roll_std

        roll_mean_o = df['orders'].rolling(window=window, min_periods=5, center=False).mean()
        roll_std_o = df['orders'].rolling(window=window, min_periods=5, center=False).std()
        roll_std_o = roll_std_o.replace(0, np.nan)
        df['z_orders'] = (df['orders'] - roll_mean_o) / roll_std_o

        # ── IQR check (global) ──
        q1_r, q3_r = df['revenue'].quantile(0.25), df['revenue'].quantile(0.75)
        iqr_r = q3_r - q1_r
        lower_r = q1_r - 1.5 * iqr_r
        upper_r = q3_r + 1.5 * iqr_r

        q1_o, q3_o = df['orders'].quantile(0.25), df['orders'].quantile(0.75)
        iqr_o = q3_o - q1_o
        lower_o = q1_o - 1.5 * iqr_o
        upper_o = q3_o + 1.5 * iqr_o

        # ── Flag anomalies ──
        # Criteria: |z| > 2.5 on revenue OR orders, OR outside IQR bounds
        z_thresh = 2.5
        df['is_anomaly'] = False
        df['reasons'] = ''

        for idx in df.index:
            reasons = []
            zr = df.loc[idx, 'z_revenue']
            zo = df.loc[idx, 'z_orders']
            rev = df.loc[idx, 'revenue']
            ords = df.loc[idx, 'orders']

            if pd.notna(zr) and abs(zr) > z_thresh:
                direction = 'spike' if zr > 0 else 'drop'
                reasons.append(f'Revenue {direction} (z={zr:.1f})')
            if pd.notna(zo) and abs(zo) > z_thresh:
                direction = 'spike' if zo > 0 else 'drop'
                reasons.append(f'Order volume {direction} (z={zo:.1f})')
            if iqr_r > 0 and (rev < lower_r or rev > upper_r):
                reasons.append('Revenue outside IQR range')
            if iqr_o > 0 and (ords < lower_o or ords > upper_o):
                reasons.append('Order volume outside IQR range')

            if reasons:
                df.loc[idx, 'is_anomaly'] = True
                df.loc[idx, 'reasons'] = '; '.join(reasons)

        anomaly_df = df[df['is_anomaly']].copy()

        # ── Build anomaly list ──
        anomalies = []
        for idx, row in anomaly_df.iterrows():
            severity = 'high'
            z_max = max(abs(row['z_revenue']) if pd.notna(row['z_revenue']) else 0,
                        abs(row['z_orders']) if pd.notna(row['z_orders']) else 0)
            if z_max < 3:
                severity = 'medium'
            if z_max < 2.5:
                severity = 'low'

            anomalies.append({
                'date': idx.strftime('%Y-%m-%d'),
                'date_display': idx.strftime('%b %d, %Y'),
                'revenue': float(row['revenue']),
                'orders': int(row['orders']),
                'returns': int(row['returns']),
                'z_revenue': float(row['z_revenue']) if pd.notna(row['z_revenue']) else None,
                'z_orders': float(row['z_orders']) if pd.notna(row['z_orders']) else None,
                'severity': severity,
                'reasons': row['reasons'],
            })

        # ── Summary ──
        total_days = len(df)
        anomaly_count = len(anomalies)
        high_count = sum(1 for a in anomalies if a['severity'] == 'high')
        med_count = sum(1 for a in anomalies if a['severity'] == 'medium')

        avg_rev = float(df['revenue'].mean())
        std_rev = float(df['revenue'].std()) if len(df) > 1 else 0
        avg_orders = float(df['orders'].mean())

        summary = {
            'total_days': total_days,
            'anomaly_count': anomaly_count,
            'anomaly_rate': round(anomaly_count / total_days * 100, 1) if total_days else 0,
            'high_count': high_count,
            'medium_count': med_count,
            'avg_revenue': avg_rev,
            'std_revenue': std_rev,
            'avg_orders': avg_orders,
        }

        # ── Chart ──
        _font = 'Inter, -apple-system, sans-serif'
        _muted = '#71717A'
        _red = '#E63B2E'
        _dark = '#18181B'
        _grid = 'rgba(228,228,231,0.5)'

        fig = go.Figure()

        # Revenue line
        fig.add_trace(go.Scatter(
            x=df.index.tolist(), y=df['revenue'].tolist(),
            mode='lines', name='Daily Revenue',
            line=dict(color=_dark, width=1.8, shape='spline'),
            hovertemplate='%{x|%b %d}<br>$%{y:,.0f}<extra>Revenue</extra>',
        ))

        # Rolling mean band
        if roll_mean is not None:
            upper_band = (roll_mean + z_thresh * roll_std).tolist()
            lower_band = (roll_mean - z_thresh * roll_std).clip(lower=0).tolist()
            fig.add_trace(go.Scatter(
                x=df.index.tolist() + df.index.tolist()[::-1],
                y=upper_band + lower_band[::-1],
                fill='toself', fillcolor='rgba(228,228,231,0.15)',
                line=dict(color='rgba(0,0,0,0)'),
                name='Normal Range (±2.5σ)', showlegend=True, hoverinfo='skip',
            ))

        # Anomaly markers
        if not anomaly_df.empty:
            colors = []
            for _, row in anomaly_df.iterrows():
                z_max = max(abs(row['z_revenue']) if pd.notna(row['z_revenue']) else 0,
                            abs(row['z_orders']) if pd.notna(row['z_orders']) else 0)
                colors.append(_red if z_max >= 3 else '#F59E0B')

            fig.add_trace(go.Scatter(
                x=anomaly_df.index.tolist(),
                y=anomaly_df['revenue'].tolist(),
                mode='markers', name='Anomalies',
                marker=dict(size=10, color=colors, symbol='diamond',
                            line=dict(width=2, color='white')),
                hovertemplate='<b>ANOMALY</b><br>%{x|%b %d, %Y}<br>$%{y:,.0f}<extra></extra>',
            ))

        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            font=dict(family=_font, size=12, color=_muted),
            margin=dict(t=20, b=40, l=55, r=20),
            height=400, hovermode='x unified', dragmode=False,
            legend=dict(
                orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1,
                font=dict(size=11, family=_font, color=_muted),
                bgcolor='rgba(0,0,0,0)',
            ),
            xaxis=dict(showgrid=False, zeroline=False,
                       tickfont=dict(size=11, color=_muted)),
            yaxis=dict(showgrid=True, gridcolor=_grid, griddash='dot',
                       zeroline=False, tickprefix='$', tickformat=',',
                       tickfont=dict(size=11, color=_muted)),
        )

        chart_html = pio.to_html(fig, full_html=False, include_plotlyjs=False)

        return {
            'anomalies': anomalies,
            'chart_html': chart_html,
            'summary': summary,
        }


def _empty_summary():
    return {
        'total_days': 0, 'anomaly_count': 0, 'anomaly_rate': 0,
        'high_count': 0, 'medium_count': 0,
        'avg_revenue': 0, 'std_revenue': 0, 'avg_orders': 0,
    }


class DataNarrator:
    """
    Generates a plain-English summary of dashboard stats.
    Pure template-based NLG — no LLM, no hardcoded values.
    Every number comes from the stats dict or DB queries.
    """

    @staticmethod
    def generate(stats, session=None):
        """
        Takes the stats dict from get_dashboard_stats() and optional session,
        returns a list of narrative sentences.
        """
        lines = []
        revenue = stats.get('revenue', 0)
        profit = stats.get('profit', 0)
        orders = stats.get('orders', 0)
        customers = stats.get('customers', 0)
        margin = stats.get('avg_margin', 0)
        rev_growth = stats.get('revenue_growth', 0)
        vol_growth = stats.get('volume_growth', 0)
        has_profit = stats.get('has_profit_data', False)

        if orders == 0:
            return ["No sales data available for the selected period."]

        # ── Revenue headline ──
        def _fmt(v):
            if abs(v) >= 1_000_000:
                return f"${v/1_000_000:.1f}M"
            elif abs(v) >= 1_000:
                return f"${v/1_000:.1f}K"
            return f"${v:,.0f}"

        lines.append(f"Total revenue stands at {_fmt(revenue)} across {orders:,} orders from {customers:,} customers.")

        # ── Growth context ──
        if rev_growth != 0:
            direction = "increased" if rev_growth > 0 else "decreased"
            magnitude = abs(rev_growth)
            if magnitude > 20:
                intensity = "significantly "
            elif magnitude > 5:
                intensity = ""
            else:
                intensity = "slightly "
            lines.append(f"Revenue has {intensity}{direction} by {magnitude:.1f}% compared to the previous 30-day period.")

        if vol_growth != 0 and abs(vol_growth) > 2:
            direction = "up" if vol_growth > 0 else "down"
            lines.append(f"Order volume is {direction} {abs(vol_growth):.1f}% period-over-period.")

        # ── Profitability ──
        if has_profit and profit != 0:
            if margin > 20:
                lines.append(f"Profit margin is healthy at {margin:.1f}%, generating {_fmt(profit)} in net profit.")
            elif margin > 0:
                lines.append(f"Profit margin is {margin:.1f}% ({_fmt(profit)} net profit) — there may be room for optimization.")
            else:
                lines.append(f"The business is operating at a negative margin ({margin:.1f}%), with {_fmt(profit)} net loss.")

        # ── Top region & category from DB ──
        if session:
            top_region = (
                Sale.objects.filter(session=session)
                .values('customer__region')
                .annotate(total=Sum('total_sales'))
                .order_by('-total')
                .first()
            )
            if top_region and top_region['customer__region'] and top_region['customer__region'] != 'Unknown':
                region_name = top_region['customer__region']
                region_rev = float(top_region['total'])
                pct = (region_rev / revenue * 100) if revenue > 0 else 0
                lines.append(f"The top-performing region is {region_name}, contributing {pct:.0f}% of total revenue.")

            top_cat = (
                Sale.objects.filter(session=session)
                .values('product__category')
                .annotate(total=Sum('total_sales'))
                .order_by('-total')
                .first()
            )
            if top_cat and top_cat['product__category'] and top_cat['product__category'] not in ('Unknown', 'Uncategorized'):
                cat_name = top_cat['product__category']
                cat_rev = float(top_cat['total'])
                pct = (cat_rev / revenue * 100) if revenue > 0 else 0
                lines.append(f"{cat_name} is the leading product category at {pct:.0f}% of revenue.")

            # ── Return rate ──
            total_returned = Sale.objects.filter(session=session, returned=True).count()
            total_orders = Sale.objects.filter(session=session).count()
            if total_orders > 0 and total_returned > 0:
                return_rate = total_returned / total_orders * 100
                if return_rate > 10:
                    lines.append(f"Return rate is elevated at {return_rate:.1f}% — this warrants investigation.")
                elif return_rate > 0:
                    lines.append(f"Return rate is {return_rate:.1f}% across all orders.")

            # ── Average order value ──
            if orders > 0 and revenue > 0:
                aov = revenue / orders
                lines.append(f"Average order value is {_fmt(aov)}.")

        return lines


class CohortAnalyzer:
    """
    Groups customers by their first-purchase month and tracks
    retention (% who purchased again) in subsequent months.
    """

    @staticmethod
    def analyze(session):
        import plotly.graph_objects as go
        import plotly.io as pio

        qs = Sale.objects.filter(session=session).values(
            'customer_id', 'order_date', 'total_sales'
        )
        df = pd.DataFrame(list(qs))
        if df.empty or len(df) < 10:
            return {'chart_html': '', 'cohort_data': [], 'summary': {}}

        df['order_date'] = pd.to_datetime(df['order_date'])
        df['order_month'] = df['order_date'].dt.to_period('M')

        # First purchase month per customer
        first_purchase = df.groupby('customer_id')['order_month'].min().rename('cohort')
        df = df.merge(first_purchase, on='customer_id')

        # Period number: months since cohort — use ordinal subtraction (reliable across pandas versions)
        df['period'] = df['order_month'].apply(lambda p: p.ordinal) - df['cohort'].apply(lambda p: p.ordinal)

        # Cohort table: unique customers per (cohort, period)
        cohort_table = df.groupby(['cohort', 'period'])['customer_id'].nunique().reset_index()
        cohort_table = cohort_table.pivot(index='cohort', columns='period', values='customer_id').fillna(0)

        # Retention %: divide by period 0 (cohort size)
        cohort_sizes = cohort_table[0]
        retention = cohort_table.divide(cohort_sizes, axis=0) * 100

        # Limit to 12 periods max for readability
        max_periods = min(12, retention.shape[1])
        retention = retention.iloc[:, :max_periods]

        # Prepare data for template
        cohort_labels = [str(c) for c in retention.index]
        period_labels = [f'M{i}' for i in range(max_periods)]
        z_values = retention.values.tolist()
        sizes = cohort_sizes.tolist()

        # Heatmap
        _font = 'Inter, -apple-system, sans-serif'
        _heading = 'Outfit, Inter, sans-serif'

        fig = go.Figure(data=go.Heatmap(
            z=z_values,
            x=period_labels,
            y=cohort_labels,
            colorscale=[
                [0, '#FAFAFA'],
                [0.3, '#FECACA'],
                [0.6, '#F87171'],
                [1.0, '#E63B2E'],
            ],
            text=[[f'{v:.0f}%' if v > 0 else '' for v in row] for row in z_values],
            texttemplate='%{text}',
            textfont=dict(size=10, family=_font),
            hovertemplate='Cohort: %{y}<br>Period: %{x}<br>Retention: %{z:.1f}%<extra></extra>',
            colorbar=dict(
                title=dict(text='Retention %', font=dict(size=11, family=_font)),
                ticksuffix='%', len=0.6,
            ),
        ))

        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            font=dict(family=_font, size=12, color='#71717A'),
            margin=dict(t=20, b=40, l=80, r=20),
            height=max(300, len(cohort_labels) * 32 + 80),
            xaxis=dict(title='Months Since First Purchase', side='top',
                       tickfont=dict(size=11), title_font=dict(size=12, family=_heading)),
            yaxis=dict(title='Cohort', autorange='reversed',
                       tickfont=dict(size=10), title_font=dict(size=12, family=_heading)),
        )

        chart_html = pio.to_html(fig, full_html=False, include_plotlyjs=False)

        # Summary stats
        avg_m1 = float(retention.iloc[:, 1].mean()) if retention.shape[1] >= 2 else 0
        avg_m3 = float(retention.iloc[:, 3].mean()) if retention.shape[1] >= 4 else 0

        best_cohort_idx = retention.iloc[:, 1:].mean(axis=1).idxmax() if retention.shape[1] > 1 else None
        worst_cohort_idx = retention.iloc[:, 1:].mean(axis=1).idxmin() if retention.shape[1] > 1 else None

        summary = {
            'total_cohorts': len(cohort_labels),
            'avg_m1_retention': round(avg_m1, 1),
            'avg_m3_retention': round(avg_m3, 1) if avg_m3 else 'N/A',
            'best_cohort': str(best_cohort_idx) if best_cohort_idx else 'N/A',
            'worst_cohort': str(worst_cohort_idx) if worst_cohort_idx else 'N/A',
            'total_customers': int(cohort_sizes.sum()),
        }

        # Per-cohort data for table
        cohort_data = []
        for i, label in enumerate(cohort_labels):
            cohort_data.append({
                'label': label,
                'size': int(sizes[i]),
                'm1': f"{z_values[i][1]:.0f}%" if max_periods > 1 else 'N/A',
                'm3': f"{z_values[i][3]:.0f}%" if max_periods > 3 else 'N/A',
                'm6': f"{z_values[i][6]:.0f}%" if max_periods > 6 else 'N/A',
            })

        return {
            'chart_html': chart_html,
            'cohort_data': cohort_data,
            'summary': summary,
        }


class CLVCalculator:
    """
    Calculates Customer Lifetime Value using historical purchase data.
    CLV = Avg Order Value x Purchase Frequency x 12 (annualized).
    All values derived from actual data — nothing hardcoded.
    """

    @staticmethod
    def calculate(session):
        import plotly.graph_objects as go
        import plotly.io as pio

        qs = Sale.objects.filter(session=session).values(
            'customer_id', 'customer__name', 'customer__region',
            'order_date', 'order_id', 'total_sales', 'profit'
        )
        df = pd.DataFrame(list(qs))
        if df.empty or len(df) < 10:
            return {'chart_html': '', 'top_customers': [], 'summary': {}}

        df['order_date'] = pd.to_datetime(df['order_date'])
        df['total_sales'] = df['total_sales'].astype(float)
        df['profit'] = df['profit'].astype(float)

        # Per-customer metrics
        cust = df.groupby('customer_id').agg(
            name=('customer__name', 'first'),
            region=('customer__region', 'first'),
            total_revenue=('total_sales', 'sum'),
            total_profit=('profit', 'sum'),
            order_count=('order_id', 'nunique'),
            first_order=('order_date', 'min'),
            last_order=('order_date', 'max'),
        ).reset_index()

        # AOV, frequency, lifespan
        cust['aov'] = cust['total_revenue'] / cust['order_count']
        max_date = df['order_date'].max()
        min_date = df['order_date'].min()
        data_span_days = (max_date - min_date).days or 1

        cust['lifespan_days'] = (cust['last_order'] - cust['first_order']).dt.days

        # Frequency: orders per month (normalize by data span)
        cust['freq_monthly'] = cust['order_count'] / (data_span_days / 30.0)

        # CLV = AOV x Monthly Frequency x 12 (annualized)
        cust['clv'] = cust['aov'] * cust['freq_monthly'] * 12

        # For single-order customers, CLV = their revenue (no projection)
        single_order = cust['order_count'] == 1
        cust.loc[single_order, 'clv'] = cust.loc[single_order, 'total_revenue']

        cust = cust.sort_values('clv', ascending=False)

        # Top 20 for display
        top_20 = cust.head(20)
        top_customers = []
        for _, row in top_20.iterrows():
            top_customers.append({
                'name': row['name'],
                'region': row['region'],
                'clv': float(row['clv']),
                'total_revenue': float(row['total_revenue']),
                'total_profit': float(row['total_profit']),
                'order_count': int(row['order_count']),
                'aov': float(row['aov']),
                'lifespan_days': int(row['lifespan_days']),
            })

        # Distribution chart
        _font = 'Inter, -apple-system, sans-serif'
        _red = '#E63B2E'
        _muted = '#71717A'
        _grid = 'rgba(228,228,231,0.5)'

        fig = go.Figure()
        fig.add_trace(go.Histogram(
            x=cust['clv'].tolist(), nbinsx=30, name='Customers',
            marker=dict(color=_red, line=dict(width=1, color='white'), cornerradius=4),
            hovertemplate='CLV Range: $%{x:,.0f}<br>Customers: %{y}<extra></extra>',
        ))

        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            font=dict(family=_font, size=12, color=_muted),
            margin=dict(t=20, b=50, l=55, r=20),
            height=380, dragmode=False,
            xaxis=dict(title='Customer Lifetime Value ($)', tickprefix='$', tickformat=',',
                       showgrid=False, zeroline=False, tickfont=dict(size=11, color=_muted)),
            yaxis=dict(title='Number of Customers', showgrid=True, gridcolor=_grid,
                       griddash='dot', zeroline=False, tickfont=dict(size=11, color=_muted)),
        )

        chart_html = pio.to_html(fig, full_html=False, include_plotlyjs=False)

        # Summary
        total_rev = float(cust['total_revenue'].sum())
        top_10_pct_count = max(1, len(cust) // 10)
        top_10_rev = float(cust.head(top_10_pct_count)['total_revenue'].sum())

        summary = {
            'total_customers': len(cust),
            'avg_clv': float(cust['clv'].mean()),
            'median_clv': float(cust['clv'].median()),
            'top_10_pct_revenue': round(top_10_rev / total_rev * 100, 1) if total_rev > 0 else 0,
            'avg_aov': float(cust['aov'].mean()),
            'avg_orders': float(cust['order_count'].mean()),
        }

        return {
            'chart_html': chart_html,
            'top_customers': top_customers,
            'summary': summary,
        }


class AssociationAnalyzer:
    """
    Market basket analysis: finds products frequently bought together.
    Uses co-purchase frequency + lift calculation.
    """

    @staticmethod
    def analyze(session, min_support_count=3, top_n=25):
        import plotly.graph_objects as go
        import plotly.io as pio
        from itertools import combinations

        qs = Sale.objects.filter(session=session).values(
            'order_id', 'product__name', 'product__category'
        )
        df = pd.DataFrame(list(qs))
        if df.empty:
            return {'rules': [], 'chart_html': '', 'summary': {
                'total_baskets': 0, 'multi_item_baskets': 0, 'rules_found': 0
            }}

        # Group products by order (basket)
        baskets = df.groupby('order_id')['product__name'].apply(list).reset_index()
        baskets = baskets[baskets['product__name'].apply(len) >= 2]

        total_baskets = len(df['order_id'].unique())
        multi_baskets = len(baskets)

        if baskets.empty:
            return {'rules': [], 'chart_html': '', 'summary': {
                'total_baskets': total_baskets, 'multi_item_baskets': 0, 'rules_found': 0
            }}

        # Product frequencies
        product_freq = df.groupby('product__name')['order_id'].nunique().to_dict()

        # Pair frequencies
        pair_counts = {}
        for _, row in baskets.iterrows():
            items = sorted(set(row['product__name']))
            for a, b in combinations(items, 2):
                key = (a, b)
                pair_counts[key] = pair_counts.get(key, 0) + 1

        # Filter by min support
        pair_counts = {k: v for k, v in pair_counts.items() if v >= min_support_count}

        if not pair_counts:
            return {'rules': [], 'chart_html': '', 'summary': {
                'total_baskets': total_baskets, 'multi_item_baskets': multi_baskets, 'rules_found': 0
            }}

        # Calculate confidence and lift
        rules = []
        for (a, b), count in pair_counts.items():
            freq_a = product_freq.get(a, 1)
            freq_b = product_freq.get(b, 1)
            support = count / total_baskets
            confidence_a_b = count / freq_a
            confidence_b_a = count / freq_b
            lift = (count * total_baskets) / (freq_a * freq_b)

            rules.append({
                'product_a': a,
                'product_b': b,
                'count': count,
                'support': round(support * 100, 2),
                'confidence': round(max(confidence_a_b, confidence_b_a) * 100, 1),
                'lift': round(lift, 2),
            })

        rules.sort(key=lambda x: x['lift'], reverse=True)
        rules = rules[:top_n]

        # Chart: top pairs by lift
        top_rules = rules[:15]
        pair_labels = [f"{r['product_a'][:20]} + {r['product_b'][:20]}" for r in top_rules]
        lift_values = [r['lift'] for r in top_rules]
        count_values = [r['count'] for r in top_rules]

        _font = 'Inter, -apple-system, sans-serif'
        _red = '#E63B2E'
        _dark = '#18181B'
        _muted = '#71717A'
        _grid = 'rgba(228,228,231,0.5)'

        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=pair_labels[::-1], x=lift_values[::-1],
            orientation='h', name='Lift',
            marker=dict(
                color=[_red if l > 2 else _dark for l in lift_values[::-1]],
                cornerradius=5,
            ),
            text=[f'{l:.1f}x' for l in lift_values[::-1]],
            textposition='outside', textfont=dict(size=10, color=_muted, family=_font),
            customdata=count_values[::-1],
            hovertemplate='<b>%{y}</b><br>Lift: %{x:.2f}x<br>Co-purchases: %{customdata}<extra></extra>',
        ))

        fig.update_layout(
            paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
            font=dict(family=_font, size=12, color=_muted),
            margin=dict(t=20, b=30, l=10, r=80),
            height=max(350, len(top_rules) * 35 + 80),
            dragmode=False, showlegend=False,
            xaxis=dict(title='Lift Score', showgrid=True, gridcolor=_grid, griddash='dot',
                       zeroline=False, tickfont=dict(size=11)),
            yaxis=dict(showgrid=False, automargin=True, tickfont=dict(size=10)),
        )

        chart_html = pio.to_html(fig, full_html=False, include_plotlyjs=False)

        summary = {
            'total_baskets': total_baskets,
            'multi_item_baskets': multi_baskets,
            'rules_found': len(rules),
            'avg_lift': round(np.mean([r['lift'] for r in rules]), 2) if rules else 0,
        }

        return {
            'rules': rules,
            'chart_html': chart_html,
            'summary': summary,
        }


class WhatIfSimulator:
    """
    What-If scenario simulator with a realistic economic model.

    Cost structure derived from actual data:
      - COGS (Cost of Goods Sold) = Revenue - Profit - Shipping
      - Variable cost per unit = COGS / total_units
      - Fixed costs = Shipping (doesn't scale with volume linearly)

    Effects:
      - Price ↑ → Revenue per unit ↑, but demand ↓ (price elasticity)
      - Discount ↑ → Effective price ↓ (revenue drag), but demand ↑ (discount elasticity)
      - Volume ↑ → More units sold (manual override)
      - Elasticity is user-adjustable (-0.5 to -3.0)

    Profit = Gross Revenue - Variable Costs - Fixed Costs
    """

    @staticmethod
    def get_baselines(session):
        """Return current dataset baselines derived from real data."""
        from django.db.models import Avg

        qs = Sale.objects.filter(session=session)
        if not qs.exists():
            return None

        agg = qs.aggregate(
            total_revenue=Sum('total_sales'),
            total_profit=Sum('profit'),
            total_orders=Count('order_id', distinct=True),
            total_units=Sum('quantity'),
            total_shipping=Sum('shipping_cost'),
            avg_unit_price=Avg('unit_price'),
            avg_discount=Avg('discount'),
        )

        total_revenue = float(agg['total_revenue'] or 0)
        total_profit = float(agg['total_profit'] or 0)
        total_units = int(agg['total_units'] or 1)
        total_shipping = float(agg['total_shipping'] or 0)

        # Derive cost structure from real data
        total_cost = total_revenue - total_profit          # everything that isn't profit
        cogs = max(0, total_cost - total_shipping)         # cost of goods (variable)
        variable_cost_per_unit = cogs / total_units if total_units else 0
        # Shipping is semi-fixed (scales slower than volume)
        shipping_per_unit = total_shipping / total_units if total_units else 0

        return {
            'total_revenue': total_revenue,
            'total_profit': total_profit,
            'total_orders': int(agg['total_orders'] or 0),
            'total_units': total_units,
            'avg_unit_price': float(agg['avg_unit_price'] or 0),
            'avg_discount_pct': float(agg['avg_discount'] or 0),
            'profit_margin': total_profit / total_revenue * 100 if total_revenue else 0,
            # Cost breakdown
            'total_cost': total_cost,
            'cogs': cogs,
            'total_shipping': total_shipping,
            'variable_cost_per_unit': variable_cost_per_unit,
            'shipping_per_unit': shipping_per_unit,
        }

    @staticmethod
    def simulate(baselines, price_change_pct=0, discount_change_pct=0,
                 volume_change_pct=0, elasticity=-1.5):
        """
        Simulate What-If scenario with proper economic modeling.

        Args:
            baselines: dict from get_baselines()
            price_change_pct: -50 to +50, % change in unit price
            discount_change_pct: -50 to +50, % change in discount rate
            volume_change_pct: -50 to +50, manual % change in volume
            elasticity: -0.5 to -3.0, price elasticity of demand
        """
        if not baselines:
            return None

        base_units = baselines['total_units']
        base_price = baselines['avg_unit_price']
        base_discount = baselines['avg_discount_pct']
        vcpu = baselines['variable_cost_per_unit']       # variable cost per unit
        spu = baselines['shipping_per_unit']              # shipping per unit

        # ── 1. New unit price ──
        new_price = base_price * (1 + price_change_pct / 100)

        # ── 2. New discount rate ──
        # Discount is an absolute %, clamp to [0, 80] so it stays realistic
        new_discount = max(0, min(80, base_discount * (1 + discount_change_pct / 100)))

        # ── 3. Demand effects ──
        # Price elasticity: volume drops/rises with price changes
        price_volume_effect = 1 + (elasticity * price_change_pct / 100)

        # Discount elasticity: higher discounts attract ~0.5x more volume
        # (weaker than price elasticity — discounts boost demand but less aggressively)
        discount_elasticity = 0.5
        discount_volume_effect = 1 + (discount_elasticity * discount_change_pct / 100)

        # Manual volume adjustment stacks on top
        manual_volume_effect = 1 + (volume_change_pct / 100)

        # Effective volume = all three multiplied, floor at 5% of base
        effective_volume_mult = max(0.05, price_volume_effect * discount_volume_effect * manual_volume_effect)
        new_units = base_units * effective_volume_mult

        # ── 4. Revenue ──
        # Effective selling price = unit price × (1 - discount%)
        effective_sell_price = new_price * (1 - new_discount / 100)
        new_revenue = new_units * effective_sell_price

        # ── 5. Costs (from real data) ──
        # Variable costs scale linearly with volume
        new_variable_cost = new_units * vcpu

        # Shipping scales at 70% of volume change (bulk shipping discounts)
        shipping_scale = 1 + (effective_volume_mult - 1) * 0.7
        new_shipping = baselines['total_shipping'] * max(0.1, shipping_scale)

        new_total_cost = new_variable_cost + new_shipping

        # ── 6. Profit ──
        new_profit = new_revenue - new_total_cost
        new_margin = (new_profit / new_revenue * 100) if new_revenue > 0 else 0

        return {
            'revenue': round(float(new_revenue), 2),
            'profit': round(float(new_profit), 2),
            'units': round(float(new_units)),
            'avg_price': round(float(new_price), 2),
            'effective_price': round(float(effective_sell_price), 2),
            'discount_pct': round(float(new_discount), 1),
            'margin': round(float(new_margin), 1),
            'total_cost': round(float(new_total_cost), 2),
            'variable_cost': round(float(new_variable_cost), 2),
            'shipping_cost': round(float(new_shipping), 2),
            'revenue_change': round((new_revenue / baselines['total_revenue'] - 1) * 100, 1) if baselines['total_revenue'] else 0,
            'profit_change': round((new_profit / baselines['total_profit'] - 1) * 100, 1) if baselines['total_profit'] else 0,
            'volume_change': round((effective_volume_mult - 1) * 100, 1),
        }


class ReportGenerator:
    """
    Generates a comprehensive analytics report as structured data.
    The template renders it as a print-optimized HTML page (browser Print → PDF).
    """

    @staticmethod
    def format_metric(value, prefix='', suffix=''):
        if value is None:
            return 'NaN'
        try:
            v = float(value)
        except (ValueError, TypeError):
            return 'NaN'

        if v == 0:
            return 'NaN'
        
        abs_v = abs(v)
        if abs_v >= 1_000_000:
            formatted = f"{abs_v / 1_000_000:.1f}M"
        elif abs_v >= 1_000:
            formatted = f"{abs_v / 1_000:.1f}K"
        else:
            if abs_v.is_integer():
                formatted = f"{int(abs_v)}"
            else:
                formatted = f"{abs_v:.1f}"

        res = f"{prefix}{formatted}{suffix}"
        if v < 0:
            return f"-{res}"
        return res

    @staticmethod
    def generate(session):
        from django.db.models import Avg, Max, Min
        from django.db.models.functions import TruncMonth

        qs = Sale.objects.filter(session=session)
        if not qs.exists():
            return None

        # Core metrics
        agg = qs.aggregate(
            total_revenue=Sum('total_sales'),
            total_profit=Sum('profit'),
            total_orders=Count('order_id', distinct=True),
            total_units=Sum('quantity'),
            total_customers=Count('customer', distinct=True),
            total_products=Count('product', distinct=True),
            avg_discount=Avg('discount'),
            avg_delivery=Avg('delivery_time_days'),
            date_min=Min('order_date'),
            date_max=Max('order_date'),
        )

        total_rev = float(agg['total_revenue'] or 0)
        total_prof = float(agg['total_profit'] or 0)

        # Return rate
        total_sales = qs.count()
        returned_count = qs.filter(returned=True).count()
        return_rate = (returned_count / total_sales * 100) if total_sales > 0 else 0

        # Top 10 products by revenue
        top_products = list(
            qs.values('product__name', 'product__category')
            .annotate(revenue=Sum('total_sales'), units=Sum('quantity'))
            .order_by('-revenue')[:10]
        )

        # Top 10 customers by revenue
        top_customers = list(
            qs.values('customer__name', 'customer__region')
            .annotate(revenue=Sum('total_sales'), orders=Count('order_id', distinct=True))
            .order_by('-revenue')[:10]
        )

        # Revenue by region
        by_region = list(
            qs.values('customer__region')
            .annotate(revenue=Sum('total_sales'), profit=Sum('profit'))
            .order_by('-revenue')
        )

        # Revenue by category
        by_category = list(
            qs.values('product__category')
            .annotate(revenue=Sum('total_sales'), profit=Sum('profit'))
            .order_by('-revenue')
        )

        # Monthly trend
        monthly = list(
            qs.annotate(month=TruncMonth('order_date'))
            .values('month')
            .annotate(revenue=Sum('total_sales'), orders=Count('order_id', distinct=True))
            .order_by('month')
        )

        return {
            'overview': {
                'total_revenue': total_rev,
                'total_revenue_fmt': ReportGenerator.format_metric(total_rev, prefix='$'),
                'total_profit': total_prof,
                'total_profit_fmt': ReportGenerator.format_metric(total_prof, prefix='$'),
                'profit_margin': round(total_prof / total_rev * 100, 1) if total_rev else 0,
                'profit_margin_fmt': ReportGenerator.format_metric(total_prof / total_rev * 100 if total_rev else 0, suffix='%'),
                'total_orders': agg['total_orders'],
                'total_orders_fmt': ReportGenerator.format_metric(agg['total_orders']),
                'total_units': agg['total_units'],
                'total_units_fmt': ReportGenerator.format_metric(agg['total_units']),
                'total_customers': agg['total_customers'],
                'total_customers_fmt': ReportGenerator.format_metric(agg['total_customers']),
                'total_products': agg['total_products'],
                'total_products_fmt': ReportGenerator.format_metric(agg['total_products']),
                'aov': round(total_rev / agg['total_orders'], 2) if agg['total_orders'] else 0,
                'aov_fmt': ReportGenerator.format_metric(total_rev / agg['total_orders'] if agg['total_orders'] else 0, prefix='$'),
                'avg_discount': round(float(agg['avg_discount'] or 0), 1),
                'avg_delivery': round(float(agg['avg_delivery'] or 0), 1),
                'return_rate': round(return_rate, 1),
                'return_rate_fmt': ReportGenerator.format_metric(return_rate, suffix='%'),
                'date_range': f"{agg['date_min']} — {agg['date_max']}" if agg['date_min'] else 'N/A',
            },
            'top_products': [{
                'name': p['product__name'],
                'category': p['product__category'],
                'revenue': float(p['revenue']),
                'revenue_fmt': ReportGenerator.format_metric(p['revenue'], prefix='$'),
                'units': p['units'],
                'units_fmt': ReportGenerator.format_metric(p['units']),
            } for p in top_products],
            'top_customers': [{
                'name': c['customer__name'],
                'region': c['customer__region'],
                'revenue': float(c['revenue']),
                'revenue_fmt': ReportGenerator.format_metric(c['revenue'], prefix='$'),
                'orders': c['orders'],
                'orders_fmt': ReportGenerator.format_metric(c['orders']),
            } for c in top_customers],
            'by_region': [{
                'region': r['customer__region'],
                'revenue': float(r['revenue']),
                'revenue_fmt': ReportGenerator.format_metric(r['revenue'], prefix='$'),
                'profit': float(r['profit']),
                'profit_fmt': ReportGenerator.format_metric(r['profit'], prefix='$'),
            } for r in by_region],
            'by_category': [{
                'category': c['product__category'],
                'revenue': float(c['revenue']),
                'revenue_fmt': ReportGenerator.format_metric(c['revenue'], prefix='$'),
                'profit': float(c['profit']),
                'profit_fmt': ReportGenerator.format_metric(c['profit'], prefix='$'),
            } for c in by_category],
            'monthly': [{
                'month': m['month'].strftime('%Y-%m'),
                'revenue': float(m['revenue']),
                'revenue_fmt': ReportGenerator.format_metric(m['revenue'], prefix='$'),
                'orders': m['orders'],
                'orders_fmt': ReportGenerator.format_metric(m['orders']),
            } for m in monthly],
        }
