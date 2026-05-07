from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Sum, Count, F
from django.db.models.functions import TruncDate
from django.contrib.auth.decorators import login_required
from .models import Customer, Product, Sale, DataUpload, AuditLog, AnalysisSession
import plotly.express as px
import plotly.io as pio
import json
import os
import time
import pandas as pd
import shutil
from django.conf import settings
from django.core.files import File
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.contrib import messages
from django.core.cache import cache
from .services import AnalyticsService, DataNarrator, CohortAnalyzer, CLVCalculator, AssociationAnalyzer, WhatIfSimulator, ReportGenerator
from .forecasting import ForecastingService
from django.urls import reverse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


# ─── Helpers ──────────────────────────────────────────────────────────────────

def format_number(value):
    """Format large numbers with K/M suffixes for readability."""
    value = float(value)
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    elif abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:.0f}"


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    return x_forwarded.split(',')[0].strip() if x_forwarded else request.META.get('REMOTE_ADDR')


def log_action(user, action, detail='', request=None):
    AuditLog.objects.create(
        user=user if user and user.is_authenticated else None,
        action=action,
        detail=detail,
        ip_address=get_client_ip(request) if request else None,
    )


def get_dashboard_stats(queryset):
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Max, Min

    # Single aggregation query instead of multiple
    agg = queryset.aggregate(
        total_rev=Sum('total_sales'),
        total_profit=Sum('profit'),
        total_orders=Count('id'),
        total_customers=Count('customer', distinct=True),
        latest_date=Max('order_date'),
    )

    total_rev = float(agg['total_rev'] or 0)
    total_profit = float(agg['total_profit'] or 0)
    total_orders = agg['total_orders']
    total_customers = agg['total_customers']
    avg_margin = (total_profit / total_rev * 100) if total_rev > 0 else 0
    has_profit_data = total_profit != 0

    latest_date = agg['latest_date']
    revenue_growth = 0
    volume_growth = 0

    if latest_date:
        period_end = latest_date
        period_start = period_end - timedelta(days=30)
        prev_period_start = period_start - timedelta(days=30)

        current = queryset.filter(
            order_date__gt=period_start, order_date__lte=period_end
        ).aggregate(rev=Sum('total_sales'), vol=Count('id'))

        prev = queryset.filter(
            order_date__gt=prev_period_start, order_date__lte=period_start
        ).aggregate(rev=Sum('total_sales'), vol=Count('id'))

        current_rev = float(current['rev'] or 0)
        prev_rev = float(prev['rev'] or 0)
        current_vol = current['vol']
        prev_vol = prev['vol']

        revenue_growth = ((current_rev - prev_rev) / prev_rev * 100) if prev_rev > 0 else 0
        volume_growth = ((current_vol - prev_vol) / prev_vol * 100) if prev_vol > 0 else 0

    return {
        'revenue': total_rev,
        'profit': total_profit,
        'avg_margin': avg_margin,
        'orders': total_orders,
        'customers': total_customers,
        'revenue_growth': revenue_growth,
        'volume_growth': volume_growth,
        'has_profit_data': has_profit_data,
        'revenue_fmt': format_number(total_rev),
        'profit_fmt': format_number(total_profit) if has_profit_data else 'N/A',
        'orders_fmt': format_number(total_orders),
        'customers_fmt': format_number(total_customers),
    }


def generate_charts(queryset, session=None):
    import plotly.graph_objects as go
    from django.db.models import Sum, Count, Q
    from django.db.models.functions import TruncDate
    import hashlib

    # Build a cache key from the queryset's SQL
    query_sql = str(queryset.query)
    cache_key = f"charts_{hashlib.md5(query_sql.encode()).hexdigest()}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    if not queryset.exists():
        return {}

    # ── Shared theme ──────────────────────────────────────────────────────
    _font = 'Inter, -apple-system, sans-serif'
    _heading = 'Outfit, Inter, sans-serif'
    _text = '#18181B'
    _muted = '#71717A'
    _grid = 'rgba(228,228,231,0.5)'
    _red = '#E63B2E'
    _red_light = 'rgba(230,59,46,0.10)'
    _red_glow = 'rgba(230,59,46,0.25)'
    _dark = '#111111'
    _chart_h = 420

    layout_base = dict(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family=_font, size=12, color=_muted),
        margin=dict(t=20, b=50, l=55, r=25, pad=4),
        hovermode='x unified',
        hoverlabel=dict(
            bgcolor='white', bordercolor=_grid,
            font=dict(family=_font, size=12, color=_text),
        ),
        height=_chart_h,
        dragmode=False,
    )

    axis_x = dict(
        showgrid=False, zeroline=False,
        tickfont=dict(size=11, color=_muted),
        title_font=dict(size=12, family=_heading, color=_muted),
        linecolor=_grid, linewidth=1,
    )
    axis_y = dict(
        showgrid=True, gridcolor=_grid, gridwidth=1, griddash='dot',
        zeroline=False,
        tickfont=dict(size=11, color=_muted),
        title_font=dict(size=12, family=_heading, color=_muted),
    )

    # ── 1. Revenue Trend ─────────────────────────────────────────────────
    trend_data = list(
        queryset.values('order_date')
        .annotate(daily_total=Sum('total_sales'))
        .order_by('order_date')
    )
    trend_x = [r['order_date'] for r in trend_data]
    trend_y = [float(r['daily_total']) for r in trend_data]

    fig_trend = go.Figure()
    # Gradient fill area
    fig_trend.add_trace(go.Scatter(
        x=trend_x, y=trend_y,
        mode='lines', fill='tozeroy',
        name='Daily Revenue',
        line=dict(width=2.5, shape='spline', color=_red, smoothing=1.3),
        fillcolor='rgba(230,59,46,0.06)',
        hovertemplate='%{x|%b %d, %Y}<br><b>$%{y:,.0f}</b><extra></extra>',
    ))
    if len(trend_y) > 7:
        import numpy as np
        ma7 = pd.Series(trend_y).rolling(7, min_periods=1).mean().tolist()
        fig_trend.add_trace(go.Scatter(
            x=trend_x, y=ma7,
            mode='lines', name='7-Day Moving Avg',
            line=dict(width=2, color=_dark, dash='dot'),
            hovertemplate='%{x|%b %d, %Y}<br><b>$%{y:,.0f}</b><extra>7-Day Avg</extra>',
        ))
    if trend_y:
        peak_idx = trend_y.index(max(trend_y))
        fig_trend.add_annotation(
            x=trend_x[peak_idx], y=trend_y[peak_idx],
            text=f"Peak ${trend_y[peak_idx]:,.0f}",
            showarrow=True, arrowhead=2, arrowsize=1, arrowwidth=1.5,
            arrowcolor=_red, ax=0, ay=-45,
            bgcolor=_dark, font=dict(color='white', size=10, family=_font),
            bordercolor=_red, borderwidth=1.5, borderpad=5,
        )
    fig_trend.update_layout(
        **layout_base,
        legend=dict(
            orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1,
            font=dict(size=11, family=_font, color=_muted),
            bgcolor='rgba(0,0,0,0)',
        ),
        xaxis={**axis_x, 'title': ''},
        yaxis={**axis_y, 'title': 'Revenue ($)', 'tickprefix': '$', 'tickformat': ','},
    )

    # ── 2. Regional Revenue ──────────────────────────────────────────────
    region_data = list(
        queryset.values(country=F('customer__region'))
        .annotate(line_total=Sum('total_sales'))
        .order_by('-line_total')[:10]
    )
    region_data = [r for r in region_data if r['country'] and r['country'] != 'Unknown'] or region_data

    region_names = [r['country'] for r in region_data]
    region_values = [float(r['line_total']) for r in region_data]
    r_max = max(region_values) if region_values else 1
    region_colors = [_red if v == r_max else f'rgba(17,17,17,{0.25 + 0.65 * v / r_max:.2f})' for v in region_values]

    fig_country = go.Figure(data=[go.Bar(
        y=region_names[::-1], x=region_values[::-1],
        orientation='h', name='Revenue',
        marker=dict(color=region_colors[::-1], cornerradius=6),
        text=[f'${v:,.0f}' for v in region_values[::-1]],
        textposition='outside', textfont=dict(size=10, color=_muted, family=_font),
        hovertemplate='<b>%{y}</b><br>$%{x:,.0f}<extra></extra>',
    )])
    fig_country.update_layout(
        **{k: v for k, v in layout_base.items() if k not in ('height', 'margin')},
        showlegend=False, height=max(300, len(region_names) * 42 + 60),
        xaxis={**axis_y, 'title': '', 'tickprefix': '$', 'tickformat': ',', 'side': 'top'},
        yaxis={**axis_x, 'title': '', 'automargin': True},
        margin=dict(t=30, b=20, l=10, r=60),
    )

    # ── 3. Category Revenue ──────────────────────────────────────────────
    cat_data = list(
        queryset.values(category=F('product__category'))
        .annotate(line_total=Sum('total_sales'))
        .order_by('-line_total')
    )
    cat_data = [r for r in cat_data if r['category'] and r['category'] not in ('Unknown', 'Uncategorized')] or cat_data

    cat_names = [r['category'] for r in cat_data]
    cat_values = [float(r['line_total']) for r in cat_data]
    c_max = max(cat_values) if cat_values else 1
    cat_colors = [_red if v == c_max else f'rgba(17,17,17,{0.20 + 0.60 * v / c_max:.2f})' for v in cat_values]

    fig_prod = go.Figure(data=[go.Bar(
        x=cat_names, y=cat_values,
        name='Revenue', marker=dict(color=cat_colors, cornerradius=5),
        text=[f'${v:,.0f}' for v in cat_values],
        textposition='outside', textfont=dict(size=10, color=_muted, family=_font),
        hovertemplate='<b>%{x}</b><br>$%{y:,.0f}<extra></extra>',
    )])
    fig_prod.update_layout(
        **layout_base, showlegend=False,
        xaxis={**axis_x, 'title': '', 'tickangle': -25},
        yaxis={**axis_y, 'title': 'Revenue ($)', 'tickprefix': '$', 'tickformat': ','},
    )

    # ── 3.1 Demographics / Payment ───────────────────────────────────────
    age_counts = list(
        queryset.filter(customer__age__gt=0, customer__age__isnull=False)
        .values('customer__age')
        .annotate(cnt=Count('id'))
        .order_by('customer__age')
    )
    has_age_data = len(age_counts) > 0

    if has_age_data:
        age_flat = []
        for r in age_counts:
            age_flat.extend([r['customer__age']] * r['cnt'])
        fig_age = px.histogram(pd.DataFrame({'age': age_flat}), x='age', nbins=20,
                              template='plotly_white', color_discrete_sequence=[_red],
                              labels={'age': 'Customer Age', 'count': 'Orders'})
        fig_age.update_layout(**layout_base)
        fig_age.update_traces(
            name='Orders',
            hovertemplate='<b>Age %{x}</b><br>%{y:,} orders<extra></extra>',
            marker=dict(line=dict(width=1, color='white'), cornerradius=4),
        )
        fig_age.update_xaxes(**axis_x, title='Age')
        fig_age.update_yaxes(**axis_y, title='Orders')
    else:
        pay_data = list(
            queryset.exclude(payment_mode__in=['Unknown', '0', ''])
            .values('payment_mode')
            .annotate(line_total=Sum('total_sales'))
            .order_by('-line_total')
        )
        if not pay_data:
            pay_data = list(
                queryset.values('payment_mode')
                .annotate(line_total=Sum('total_sales'))
                .order_by('-line_total')
            )

        pay_labels = [r['payment_mode'] for r in pay_data]
        pay_values = [float(r['line_total']) for r in pay_data]

        pay_palette = ['#E63B2E', '#18181B', '#3B82F6', '#F59E0B', '#8B5CF6', '#10B981', '#A1A1AA', '#D4D4D8']
        pay_colors = pay_palette[:len(pay_labels)]

        fig_age = go.Figure(data=[go.Pie(
            labels=pay_labels, values=pay_values, hole=0.55,
            name='Payment Methods',
            textinfo='label+percent', textposition='outside',
            textfont=dict(size=11, family=_font, color=_muted),
            marker=dict(colors=pay_colors, line=dict(color='white', width=2.5)),
            hovertemplate='<b>%{label}</b><br>$%{value:,.0f}<br>%{percent}<extra></extra>',
            pull=[0.03] * len(pay_labels),
        )])
        fig_age.update_layout(
            **layout_base, showlegend=True,
            legend=dict(
                orientation='h', yanchor='top', y=-0.05, xanchor='center', x=0.5,
                font=dict(size=11, family=_font, color=_muted),
                bgcolor='rgba(0,0,0,0)',
            ),
        )

    # ── 3.2 Returns / Profit by Category ─────────────────────────────────
    return_data = list(
        queryset.filter(returned=True)
        .exclude(product__category__in=['Unknown', 'Uncategorized'])
        .values(category=F('product__category'))
        .annotate(return_count=Count('id'))
        .order_by('-return_count')
    )
    has_returns = len(return_data) > 0

    if has_returns:
        ret_names = [r['category'] for r in return_data]
        ret_values = [r['return_count'] for r in return_data]

        fig_return = go.Figure(data=[go.Bar(
            x=ret_names, y=ret_values,
            name='Returns', marker=dict(color=_dark, cornerradius=5),
            text=[str(v) for v in ret_values],
            textposition='outside', textfont=dict(size=10, color=_muted, family=_font),
            hovertemplate='<b>%{x}</b><br>%{y:,} returns<extra></extra>',
        )])
        fig_return.update_layout(
            **layout_base, showlegend=False,
            xaxis={**axis_x, 'title': '', 'tickangle': -25},
            yaxis={**axis_y, 'title': 'Returns'},
        )
    else:
        profit_data = list(
            queryset.exclude(product__category__in=['Unknown', 'Uncategorized'])
            .values(category=F('product__category'))
            .annotate(total_profit=Sum('profit'), total_revenue=Sum('total_sales'))
            .order_by('-total_profit')
        )
        if not profit_data:
            profit_data = list(
                queryset.values(category=F('product__category'))
                .annotate(total_profit=Sum('profit'))
                .order_by('-total_profit')
            )

        prof_names = [r['category'] for r in profit_data]
        prof_values = [float(r['total_profit']) for r in profit_data]
        prof_colors = ['#10B981' if v > 0 else _red for v in prof_values]

        fig_return = go.Figure(data=[go.Bar(
            x=prof_names, y=prof_values,
            name='Profit', marker=dict(color=prof_colors, cornerradius=5),
            text=[f'${v:,.0f}' for v in prof_values],
            textposition='outside', textfont=dict(size=10, color=_muted, family=_font),
            hovertemplate='<b>%{x}</b><br>$%{y:,.0f}<extra></extra>',
        )])
        fig_return.update_layout(
            **layout_base, showlegend=False,
            xaxis={**axis_x, 'title': '', 'tickangle': -25},
            yaxis={**axis_y, 'title': 'Profit ($)', 'tickprefix': '$', 'tickformat': ','},
        )

    # ── 4. RFM Segments (filter-aware) ───────────────────────────────────
    # Build RFM directly from the filtered queryset so customer counts
    # react to category / region / date-range changes.
    rfm_html = ""
    rfm_qs = queryset.values(
        'customer_id', 'order_id', 'order_date', 'total_sales'
    )
    rfm_df = pd.DataFrame(list(rfm_qs))
    if not rfm_df.empty:
        now = pd.to_datetime(rfm_df['order_date'].max()) + pd.Timedelta(days=1)
        rfm_df['order_date'] = pd.to_datetime(rfm_df['order_date'])

        rfm = rfm_df.groupby('customer_id').agg({
            'order_date': lambda x: (now - x.max()).days,
            'order_id': 'nunique',
            'total_sales': 'sum'
        }).rename(columns={
            'order_date': 'recency',
            'order_id': 'frequency',
            'total_sales': 'monetary'
        })

        try:
            rfm['r_score'] = pd.qcut(rfm['recency'].rank(method='first'), 5, labels=[5, 4, 3, 2, 1])
            rfm['f_score'] = pd.qcut(rfm['frequency'].rank(method='first'), 5, labels=[1, 2, 3, 4, 5])
            rfm['m_score'] = pd.qcut(rfm['monetary'].rank(method='first'), 5, labels=[1, 2, 3, 4, 5])
        except ValueError:
            rfm['r_score'] = 3
            rfm['f_score'] = 3
            rfm['m_score'] = 3

        rfm['rfm_score'] = rfm['r_score'].astype(str) + rfm['f_score'].astype(str) + rfm['m_score'].astype(str)

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

        segment_counts = rfm['segment'].value_counts().reset_index()
        segment_counts.columns = ['segment', 'count']
        segment_counts = segment_counts.sort_values('count', ascending=False)

        labels = segment_counts['segment'].tolist()
        values = [int(v) for v in segment_counts['count'].tolist()]
        total_customers = sum(values)

        seg_palette = {
            'Champions': '#10B981', 'Loyal Customers': '#34D399',
            'Potential Loyalists': '#6EE7B7', 'New Customers': '#3B82F6',
            'At Risk': '#F59E0B', "Can't Lose Them": '#EF4444',
            'Lost': '#18181B', 'Others': '#A1A1AA',
        }
        colors = [seg_palette.get(s, '#D4D4D8') for s in labels]

        fig_rfm = go.Figure(data=[go.Pie(
            labels=labels, values=values, hole=0.62,
            name='Segments',
            textinfo='label+percent', textposition='inside',
            textfont=dict(size=11, color='white', family=_font),
            insidetextorientation='radial',
            pull=[0.04 if i == 0 else 0 for i in range(len(labels))],
            marker=dict(colors=colors, line=dict(color='white', width=2.5)),
            hovertemplate='<b>%{label}</b><br>%{value:,} customers<br>%{percent}<extra></extra>',
            sort=False,
        )])
        fig_rfm.update_layout(
            **layout_base, showlegend=True,
            legend=dict(
                orientation='h', yanchor='top', y=-0.05, xanchor='center', x=0.5,
                font=dict(size=11, family=_font, color=_muted),
                bgcolor='rgba(0,0,0,0)',
            ),
            annotations=[dict(
                text=f'<b>{total_customers:,}</b><br><span style="font-size:10px;color:{_muted}">Customers</span>',
                x=0.5, y=0.5,
                font=dict(size=26, family=_heading, color=_text),
                showarrow=False,
            )],
        )
        rfm_html = pio.to_html(fig_rfm, full_html=False, include_plotlyjs=False)

    # ── 5. Forecasting ───────────────────────────────────────────────────
    forecast_cache_key = "forecast_chart_html_v2"
    chart_forecast = cache.get(forecast_cache_key)
    if chart_forecast is None:
        chart_forecast = ForecastingService.generate_forecast(session=session) or ""
        cache.set(forecast_cache_key, chart_forecast, timeout=600)

    result = {
        'chart_trend': pio.to_html(fig_trend, full_html=False, include_plotlyjs=False),
        'chart_country': pio.to_html(fig_country, full_html=False, include_plotlyjs=False),
        'chart_prod': pio.to_html(fig_prod, full_html=False, include_plotlyjs=False),
        'chart_rfm': rfm_html,
        'chart_age': pio.to_html(fig_age, full_html=False, include_plotlyjs=False) if fig_age else "",
        'chart_return': pio.to_html(fig_return, full_html=False, include_plotlyjs=False) if fig_return else "",
        'chart_forecast': chart_forecast,
    }
    cache.set(cache_key, result, timeout=120)
    return result


# ─── Dashboard Views ─────────────────────────────────────────────────────────

@login_required
def dashboard_home(request):
    from datetime import date, timedelta

    # Session-scoped queries: only show data from the active session
    active_session = AnalysisSession.get_active_session(request.user)
    # Handle no active session — show empty dashboard
    has_session_data = active_session and Sale.objects.filter(session=active_session).exists()

    if has_session_data:
        sales = Sale.objects.filter(session=active_session)
    else:
        sales = Sale.objects.filter(id__isnull=True)  # guaranteed-empty but valid queryset

    country = request.GET.get('country')
    category = request.GET.get('category')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    preset = request.GET.get('preset', '')

    # Preset timeframe shortcuts
    today = date.today()
    if preset == '7d':
        start_date = str(today - timedelta(days=7))
        end_date = str(today)
    elif preset == '30d':
        start_date = str(today - timedelta(days=30))
        end_date = str(today)
    elif preset == '90d':
        start_date = str(today - timedelta(days=90))
        end_date = str(today)
    elif preset == '1y':
        start_date = str(today - timedelta(days=365))
        end_date = str(today)
    elif preset == 'all':
        start_date = ''
        end_date = ''

    if has_session_data:
        if country and country != 'All':
            sales = sales.filter(customer__region=country)
        if category and category != 'All':
            sales = sales.filter(product__category=category)
        if start_date:
            sales = sales.filter(order_date__gte=start_date)
        if end_date:
            sales = sales.filter(order_date__lte=end_date)

    stats = get_dashboard_stats(sales) if has_session_data else {
        'revenue': 0, 'profit': 0, 'avg_margin': 0, 'orders': 0, 'customers': 0,
        'revenue_growth': 0, 'volume_growth': 0,
        'revenue_fmt': '0', 'profit_fmt': '0', 'orders_fmt': '0', 'customers_fmt': '0',
    }
    charts = generate_charts(sales, session=active_session) if has_session_data else {}

    # Session-scoped lookups for filter dropdowns
    if active_session:
        countries = Customer.objects.filter(session=active_session).values_list('region', flat=True).distinct().order_by('region')
        categories = Product.objects.filter(session=active_session).values_list('category', flat=True).distinct().order_by('category')
    else:
        countries = []
        categories = []

    latest_upload = DataUpload.objects.filter(
        uploaded_by=request.user, status=DataUpload.STATUS_SUCCESS
    ).order_by('-uploaded_at').first()
    recent_sales = list(sales.select_related('customer', 'product').order_by('-order_date', '-id')[:10]) if has_session_data else []

    rfm_summary = {}
    if has_session_data:
        cache_key = f"rfm_summary_{active_session.id}"
        rfm_summary = cache.get(cache_key)
        if rfm_summary is None:
            rfm_segments = AnalyticsService.get_rfm_segments(session=active_session)
            rfm_summary = rfm_segments['segment'].value_counts().to_dict() if not rfm_segments.empty else {}
            cache.set(cache_key, rfm_summary, timeout=300)

    context = {
        'stats': stats,
        'charts': charts,
        'data_narrative': DataNarrator.generate(stats, session=active_session) if has_session_data else [],
        'countries': countries,
        'categories': categories,
        'selected_country': country or 'All',
        'selected_category': category or 'All',
        'start_date': start_date or '',
        'end_date': end_date or '',
        'selected_preset': preset or '',
        'preset_choices': [('7D', '7d'), ('30D', '30d'), ('90D', '90d'), ('1Y', '1y'), ('All', 'all')],
        'latest_upload': latest_upload,
        'recent_sales': recent_sales,
        'rfm_summary': rfm_summary,
        'active_session': active_session,
    }

    if request.htmx:
        return render(request, 'dashboard/partials/charts_content.html', context)

    return render(request, 'dashboard/index.html', context)


@login_required
def export_report(request, format):
    """Export filtered sales data as CSV or Excel."""
    import logging
    logger = logging.getLogger(__name__)

    export_format = format  # avoid shadowing builtin
    country = request.GET.get('country')
    category = request.GET.get('category')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    try:
        EXPORT_LIMIT = min(int(request.GET.get('limit', 50000)), 50000)
    except (ValueError, TypeError):
        EXPORT_LIMIT = 50000

    active_session = AnalysisSession.get_active_session(request.user)
    if not active_session:
        messages.error(request, "No active session. Upload data first.")
        return redirect('dashboard_home')

    sales = Sale.objects.filter(session=active_session)
    if country and country != 'All':
        sales = sales.filter(customer__region=country)
    if category and category != 'All':
        sales = sales.filter(product__category=category)
    if start_date:
        sales = sales.filter(order_date__gte=start_date)
    if end_date:
        sales = sales.filter(order_date__lte=end_date)

    sales = sales.order_by('-order_date')[:EXPORT_LIMIT]

    from .services import AnalyticsService
    try:
        if export_format == 'csv':
            content = AnalyticsService.generate_csv_report(sales)
            filename = f"nile_report_{timezone.now():%Y%m%d}.csv"
            content_type = 'text/csv; charset=utf-8'
        else:
            content = AnalyticsService.generate_excel_report(sales)
            filename = f"nile_report_{timezone.now():%Y%m%d}.xlsx"
            content_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    except Exception as e:
        logger.exception(f"Export generation failed: {e}")
        messages.error(request, f"Export failed: {str(e)}")
        return redirect('dashboard_home')

    if not content:
        messages.error(request, "No data available to export.")
        return redirect('dashboard_home')

    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    # Ensure the browser treats this as a download, not a page navigation
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@login_required
def flag_sale(request, sale_id):
    """Toggle the manual review flag on a sale via HTMX (POST only)."""
    if request.method != 'POST':
        return HttpResponse(status=405)
    sale = get_object_or_404(Sale, id=sale_id)
    sale.is_flagged = not sale.is_flagged
    sale.save(update_fields=['is_flagged'])
    
    color = "text-brand-red" if sale.is_flagged else "text-brand-muted"
    icon = "✓" if sale.is_flagged else "!"
    
    return HttpResponse(f"""
        <div hx-post="{reverse('flag_sale', args=[sale.id])}" hx-swap="outerHTML" hx-headers='{{"X-CSRFToken": "{request.META.get("CSRF_COOKIE", "")}"}}' class="cursor-pointer">
            <span class="font-bold {color} hover:scale-110 transition-transform">
                {icon}
            </span>
        </div>
    """)


# ─── Admin Control Center ────────────────────────────────────────────────────

@login_required
def control_center(request):
    """Data operations hub: file upload + ETL trigger + session management."""
    # List files from the server's data folder
    server_data_dir = os.path.join(settings.BASE_DIR, 'data')
    server_files = []
    if os.path.exists(server_data_dir):
        for f in os.listdir(server_data_dir):
            if f.endswith(('.csv', '.xlsx')):
                server_files.append(f)

    active_session = AnalysisSession.get_active_session(request.user)
    user_uploads = DataUpload.objects.filter(uploaded_by=request.user)

    # Show uploads for the active session, or all if no session
    if active_session:
        session_uploads = user_uploads.filter(session=active_session)
    else:
        session_uploads = user_uploads

    uploads = session_uploads.order_by('-uploaded_at')[:20]
    processing_active = session_uploads.filter(status__in=['pending', 'processing']).exists()

    # Auto-redirect to dashboard when ETL completes successfully (HTMX polling)
    if request.htmx:
        was_processing = request.session.get('etl_was_processing', False)
        if was_processing and not processing_active:
            request.session.pop('etl_was_processing', None)
            last_upload = uploads.first()
            if last_upload and last_upload.status == DataUpload.STATUS_SUCCESS:
                messages.success(request, f'✓ Data ingestion complete — dashboard updated with {last_upload.rows_processed} records.')
                response = HttpResponse()
                response['HX-Redirect'] = reverse('dashboard_home')
                return response
        elif processing_active:
            request.session['etl_was_processing'] = True

    # Session-scoped stats
    if active_session:
        total_sales = Sale.objects.filter(session=active_session).count()
        total_customers = Customer.objects.filter(session=active_session).count()
        total_products = Product.objects.filter(session=active_session).count()
    else:
        total_sales = 0
        total_customers = 0
        total_products = 0

    # Previous sessions for the sidebar
    archived_sessions = AnalysisSession.objects.filter(
        user=request.user, is_active=False
    ).order_by('-updated_at')[:10]

    context = {
        'uploads': uploads,
        'processing_active': processing_active,
        'server_files': sorted(server_files),
        'total_sales': total_sales,
        'total_customers': total_customers,
        'total_products': total_products,
        'active_session': active_session,
        'archived_sessions': archived_sessions,
    }
    return render(request, 'dashboard/control_center.html', context)


@login_required
def upload_data(request):
    if request.method != 'POST' or not request.FILES.getlist('file'):
        return JsonResponse({'error': 'No file provided.'}, status=400)

    uploaded_files = request.FILES.getlist('file')

    # Determine session: add to existing or create new
    session_action = request.POST.get('session_action', 'add')  # 'add' or 'new'
    active_session = AnalysisSession.get_active_session(request.user)

    if session_action == 'new' or not active_session:
        # Archive current and create fresh session
        active_session = AnalysisSession.create_new_session(request.user)

    # Process ALL uploaded files (multi-file support)
    upload_ids = []
    for uploaded_file in uploaded_files:
        filename = uploaded_file.name

        if not filename.endswith(('.csv', '.xlsx')):
            messages.error(request, f"Skipped {filename}: Only CSV and Excel files are accepted.")
            continue

        # Save upload record linked to the active session
        upload = DataUpload.objects.create(
            session=active_session,
            file=uploaded_file,
            original_filename=filename,
            uploaded_by=request.user,
            status=DataUpload.STATUS_PENDING,
        )
        upload_ids.append(upload.id)
        log_action(request.user, AuditLog.ACTION_UPLOAD, f'Uploaded {filename} to session "{active_session.name}"', request)

    if not upload_ids:
        messages.error(request, "No valid files to process.")
        return redirect('control_center')

    # If single file, go to mapping review
    if len(upload_ids) == 1:
        upload = DataUpload.objects.get(id=upload_ids[0])
        from dashboard.etl.pipeline import ETLPipeline
        try:
            pipeline = ETLPipeline(upload.file.path)
            pipeline.get_mapping_preview()  # Validate file is readable

            if request.headers.get('HX-Request'):
                response = HttpResponse()
                response['HX-Redirect'] = reverse('review_mapping', kwargs={'upload_id': upload.id})
                return response
            return redirect('review_mapping', upload_id=upload.id)
        except Exception as e:
            upload.status = DataUpload.STATUS_FAILED
            upload.error_message = str(e)
            upload.save()
            messages.error(request, f'Upload failed for {upload.original_filename}: {str(e)}')
            return redirect('control_center')

    # Multiple files: redirect to the first file's mapping, then chain
    # Store remaining upload IDs in the session for sequential processing
    request.session['pending_upload_ids'] = upload_ids[1:]
    first_upload = DataUpload.objects.get(id=upload_ids[0])
    from dashboard.etl.pipeline import ETLPipeline
    try:
        pipeline = ETLPipeline(first_upload.file.path)
        pipeline.get_mapping_preview()

        if request.headers.get('HX-Request'):
            response = HttpResponse()
            response['HX-Redirect'] = reverse('review_mapping', kwargs={'upload_id': first_upload.id})
            return response
        return redirect('review_mapping', upload_id=first_upload.id)
    except Exception as e:
        first_upload.status = DataUpload.STATUS_FAILED
        first_upload.error_message = str(e)
        first_upload.save()
        messages.error(request, f'Upload failed for {first_upload.original_filename}: {str(e)}')

    if request.headers.get('HX-Request'):
        user_uploads = DataUpload.objects.filter(uploaded_by=request.user, session=active_session)
        uploads = user_uploads.order_by('-uploaded_at')[:20]
        processing_active = user_uploads.filter(status__in=['pending', 'processing']).exists()
        return render(request, 'dashboard/partials/upload_history.html', {
            'uploads': uploads,
            'processing_active': processing_active
        })

    return redirect('control_center')


@login_required
def process_server_file(request):
    """Handles ingestion of a file already present on the server."""
    filename = request.POST.get('filename')
    if not filename:
        messages.error(request, "No file selected.")
        return redirect('control_center')

    # Prevent path traversal — only allow basenames within the data folder
    filename = os.path.basename(filename)
    server_data_dir = os.path.join(settings.BASE_DIR, 'data')
    server_file_path = os.path.join(server_data_dir, filename)
    if not os.path.commonpath([server_data_dir, os.path.realpath(server_file_path)]) == os.path.realpath(server_data_dir):
        messages.error(request, "Invalid file path.")
        return redirect('control_center')
    if not os.path.exists(server_file_path):
        messages.error(request, f"File {filename} not found on server.")
        return redirect('control_center')

    # Session handling
    session_action = request.POST.get('session_action', 'add')
    active_session = AnalysisSession.get_active_session(request.user)

    if session_action == 'new' or not active_session:
        active_session = AnalysisSession.create_new_session(request.user)

    # Register it as a DataUpload
    with open(server_file_path, 'rb') as f:
        upload = DataUpload.objects.create(
            session=active_session,
            original_filename=filename,
            uploaded_by=request.user,
            status=DataUpload.STATUS_PENDING,
        )
        upload.file.save(filename, File(f))
        upload.save()

    log_action(request.user, AuditLog.ACTION_UPLOAD, f'Selected server file: {filename}', request)

    from dashboard.etl.pipeline import ETLPipeline
    try:
        pipeline = ETLPipeline(upload.file.path)
        pipeline.get_mapping_preview()  # Validate file is readable
        
        # Redirect to mapping review page
        if request.headers.get('HX-Request'):
            response = HttpResponse()
            response['HX-Redirect'] = reverse('review_mapping', kwargs={'upload_id': upload.id})
            return response
        return redirect('review_mapping', upload_id=upload.id)
        
    except Exception as e:
        messages.error(request, f"ETL Pipeline Error: {str(e)}")

    if request.headers.get('HX-Request'):
        user_uploads = DataUpload.objects.filter(uploaded_by=request.user)
        uploads = user_uploads.order_by('-uploaded_at')[:20]
        processing_active = user_uploads.filter(status__in=['pending', 'processing']).exists()
        return render(request, 'dashboard/partials/upload_history.html', {
            'uploads': uploads,
            'processing_active': processing_active
        })

    return redirect('control_center')


@login_required
def review_mapping(request, upload_id):
    """The ETL Wizard: Allows user to correct column mappings. Chains multi-file uploads."""
    from dashboard.etl.pipeline import ETLPipeline
    upload = get_object_or_404(DataUpload, id=upload_id)
    
    if request.method == 'POST':
        # Process the submitted mapping
        mapping = {}
        for key, value in request.POST.items():
            if key.startswith('map_') and value:
                actual_file_col = key[4:]  # The header from the uploaded file
                expected_system_col = value # The standard system header selected
                mapping[actual_file_col] = expected_system_col
                
        upload.column_mapping = mapping
        upload.save()
        
        # Only wipe if explicitly requested AND this is the first file in the batch
        wipe_existing = request.POST.get('wipe_existing') == 'on'
        
        # Run ETL in background — use Celery if available, fall back to thread
        import threading
        from dashboard.tasks import process_data_upload
        
        try:
            process_data_upload.delay(upload.id, wipe_existing=wipe_existing)
        except Exception:
            threading.Thread(
                target=process_data_upload,
                args=(upload.id,),
                kwargs={'wipe_existing': wipe_existing},
                daemon=True,
            ).start()
        
        # Check if there are more files to process (multi-file chain)
        pending_ids = request.session.get('pending_upload_ids', [])
        if pending_ids:
            next_id = pending_ids.pop(0)
            request.session['pending_upload_ids'] = pending_ids
            messages.success(request, f'✓ Mapping confirmed for {upload.original_filename}. Next file...')
            return redirect('review_mapping', upload_id=next_id)
        
        messages.success(request, f'Mapping confirmed. Processing {upload.original_filename} in the background.')
        return redirect('control_center')
        
    # GET request: generate preview
    pipeline = ETLPipeline(upload.file.path)
    preview = pipeline.get_mapping_preview()
    
    preview_data = []
    for actual in preview['headers']:
        preview_data.append({
            'actual': actual,
            'mapped_to': preview['mapping'].get(actual, '')
        })

    # Show how many files remain in multi-file chain
    pending_ids = request.session.get('pending_upload_ids', [])
    files_remaining = len(pending_ids)
        
    context = {
        'upload': upload,
        'preview_data': preview_data,
        'expected': preview['expected'],
        'files_remaining': files_remaining,
    }
    return render(request, 'dashboard/confirm_mapping.html', context)




# ─── Security Telemetry (Audit Log) ──────────────────────────────────────────

@login_required
def audit_log_view(request):
    """Security telemetry dashboard showing all platform activity."""
    logs = AuditLog.objects.select_related('user').all()[:100]
    context = {'logs': logs}
    return render(request, 'dashboard/audit_log.html', context)


# ─── JWT-Protected API Endpoints ─────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_dashboard_stats(request):
    """GET /api/dashboard/stats/ — Returns key metrics for API consumers."""
    active_session = AnalysisSession.get_active_session(request.user)
    if active_session:
        sales = Sale.objects.filter(session=active_session)
    else:
        return Response({'revenue': 0, 'profit': 0, 'orders': 0, 'customers': 0})
    country = request.query_params.get('region')
    if country and country != 'All':
        sales = sales.filter(customer__region=country)
    stats = get_dashboard_stats(sales)
    return Response(stats)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_trigger_etl(request):
    """POST /api/dashboard/etl/trigger/ — Admin-only ETL trigger."""
    if not request.user.is_admin_user:
        return Response({'error': 'Admin privileges required.'}, status=403)

    from dashboard.etl.pipeline import ETLPipeline

    file_path = request.data.get('file_path', '')
    if not file_path or not os.path.exists(file_path):
        return Response({'error': 'File not found.'}, status=400)

    # Prevent path traversal — only allow files within BASE_DIR
    allowed_root = os.path.realpath(str(settings.BASE_DIR))
    real_path = os.path.realpath(file_path)
    if not real_path.startswith(allowed_root):
        return Response({'error': 'Access denied: path outside project directory.'}, status=403)

    try:
        active_session = AnalysisSession.get_active_session(request.user)
        if not active_session:
            active_session = AnalysisSession.create_new_session(request.user)

        pipeline = ETLPipeline(file_path, session_id=active_session.id)
        pipeline.run()
        log_action(request.user, AuditLog.ACTION_ETL_TRIGGER, f'API ETL: {file_path}', request)
        return Response({
            'status': 'success',
            'message': f'ETL pipeline completed. {Sale.objects.filter(session=active_session).count()} total sale records in session.',
        })
    except Exception as e:
        return Response({'error': str(e)}, status=500)


# ─── Session Management Views ────────────────────────────────────────────────

@login_required
def new_session(request):
    """Create a new analysis session, archiving the current one."""
    name = request.POST.get('session_name', '').strip()
    session = AnalysisSession.create_new_session(request.user, name=name or None)
    log_action(request.user, 'session_create', f'Created new session: {session.name}', request)
    messages.success(request, f'New analysis session "{session.name}" created. Previous session archived.')
    return redirect('control_center')


@login_required
def session_list(request):
    """View all sessions (active + archived)."""
    sessions = AnalysisSession.objects.filter(user=request.user).order_by('-updated_at')
    
    session_data = []
    for s in sessions:
        session_data.append({
            'session': s,
            'file_count': DataUpload.objects.filter(session=s).count(),
            'sale_count': Sale.objects.filter(session=s).count(),
            'customer_count': Customer.objects.filter(session=s).count(),
        })

    context = {
        'session_data': session_data,
    }
    return render(request, 'dashboard/sessions.html', context)


@login_required
def restore_session(request, session_id):
    """Restore an archived session — makes it active, archives the current one."""
    session = get_object_or_404(AnalysisSession, id=session_id, user=request.user)
    session.activate()
    log_action(request.user, 'session_restore', f'Restored session: {session.name}', request)
    messages.success(request, f'Session "{session.name}" restored as active. Previous session archived.')
    cache.clear()
    return redirect('dashboard_home')


@login_required
def delete_session(request, session_id):
    """Delete an archived session and all its data."""
    session = get_object_or_404(AnalysisSession, id=session_id, user=request.user)
    if session.is_active:
        messages.error(request, "Cannot delete the active session. Create a new session first.")
        return redirect('session_list')
    name = session.name
    session.delete()  # CASCADE deletes Customer, Product, Sale, DataUpload
    log_action(request.user, 'session_delete', f'Deleted session: {name}', request)
    messages.success(request, f'Session "{name}" and all its data deleted.')
    return redirect('session_list')


@login_required
def rename_session(request, session_id):
    """Rename a session."""
    session = get_object_or_404(AnalysisSession, id=session_id, user=request.user)
    new_name = request.POST.get('session_name', '').strip()
    if new_name:
        session.name = new_name
        session.save(update_fields=['name', 'updated_at'])
        messages.success(request, f'Session renamed to "{new_name}".')
    return redirect('session_list')


# ─── New Sidebar Pages ───────────────────────────────────────────────────────

def homepage(request):
    """Landing / home page."""
    return render(request, 'dashboard/homepage.html')


def about(request):
    """About us page."""
    return render(request, 'dashboard/about.html')


@login_required
def profile(request):
    """User profile page."""
    uploads = DataUpload.objects.filter(
        uploaded_by=request.user
    ).order_by('-uploaded_at')[:10]

    sessions = AnalysisSession.objects.filter(
        user=request.user
    ).order_by('-updated_at')

    return render(request, 'dashboard/profile.html', {
        'uploads': uploads,
        'sessions': sessions,
    })


@login_required
def upload_history(request):
    """Processing history page — shows all uploads."""
    session = request.session.get('active_session_id')
    if session:
        uploads = DataUpload.objects.filter(
            session_id=session
        ).order_by('-uploaded_at')
    else:
        uploads = DataUpload.objects.filter(
            uploaded_by=request.user
        ).order_by('-uploaded_at')

    return render(request, 'dashboard/upload_history_page.html', {
        'uploads': uploads,
    })


@login_required
def graphs_page(request):
    """Dedicated charts-only page."""
    session = AnalysisSession.get_active_session(request.user)

    if session:
        queryset = Sale.objects.filter(session=session)
    else:
        queryset = Sale.objects.none()

    charts = generate_charts(queryset, session=session) if queryset.exists() else {}

    return render(request, 'dashboard/graphs.html', {
        'charts': charts,
        'session': session,
    })


@login_required
def forecasting_page(request):
    """Dedicated forecasting page."""
    session = AnalysisSession.get_active_session(request.user)

    chart_forecast = ForecastingService.generate_forecast(session=session) or ""

    return render(request, 'dashboard/forecasting_page.html', {
        'chart_forecast': chart_forecast,
        'session': session,
    })


@login_required
def task_monitor(request):
    """Celery task monitor — shows recent task results."""
    from django_celery_results.models import TaskResult

    tasks = TaskResult.objects.order_by('-date_done')[:50]

    return render(request, 'dashboard/task_monitor.html', {
        'tasks': tasks,
    })


@login_required
def cron_jobs(request):
    """Cron Jobs monitoring page — shows all scheduled tasks and their execution history."""
    from .models import CronLog
    from core.celery import app
    from dashboard.apps import CRON_LABELS

    schedule = app.conf.beat_schedule or {}

    # Build enriched list of cron jobs
    jobs = []
    for key, entry in schedule.items():
        sched = entry['schedule']
        label = CRON_LABELS.get(key, key)

        # Build human-readable schedule string
        if hasattr(sched, '_orig_hour'):
            h = str(sched._orig_hour)
            m = str(sched._orig_minute)
            dow = str(sched._orig_day_of_week)

            if dow != '*':
                sched_str = f"{dow.capitalize()} at {h}:{m.zfill(2)}"
            elif h.startswith('*/'):
                sched_str = f"Every {h[2:]}h at :{m.zfill(2)}"
            else:
                sched_str = f"Daily at {h}:{m.zfill(2)}"
        elif isinstance(sched, (int, float)):
            mins = int(sched) // 60
            if mins >= 60:
                sched_str = f"Every {mins // 60}h {mins % 60}m"
            else:
                sched_str = f"Every {mins} min"
        else:
            sched_str = str(sched)

        # Get last execution from CronLog
        last_log = CronLog.objects.filter(task_name=key).first()

        jobs.append({
            'key': key,
            'label': label,
            'task_path': entry['task'],
            'schedule': sched_str,
            'last_run': last_log,
        })

    # Recent execution logs (all tasks, last 50)
    recent_logs = CronLog.objects.all()[:50]

    # Stats
    total_runs = CronLog.objects.count()
    success_runs = CronLog.objects.filter(status='success').count()
    failed_runs = CronLog.objects.filter(status='failed').count()

    return render(request, 'dashboard/cron_jobs.html', {
        'jobs': jobs,
        'recent_logs': recent_logs,
        'total_runs': total_runs,
        'success_runs': success_runs,
        'failed_runs': failed_runs,
    })


@login_required
def ask_data(request):
    """AI-powered natural language analytics — 'Ask Your Data' chat interface."""
    from .ai_service import AIAnalyticsService
    from .models import ChatMessage

    session = AnalysisSession.get_active_session(request.user)
    has_data = session and Sale.objects.filter(session=session).exists()

    if request.method == 'POST':
        import json as _json
        try:
            body = _json.loads(request.body)
            question = body.get('question', '').strip()
        except (ValueError, KeyError):
            question = request.POST.get('question', '').strip()

        if not question:
            return JsonResponse({'answer': '⚠️ Please enter a question.'})

        if not has_data:
            return JsonResponse({'answer': 'No data loaded. Please upload a dataset first.'})

        answer = AIAnalyticsService.ask(question, session)

        # Persist both the question and answer to the database
        if session:
            ChatMessage.objects.create(session=session, role='user', content=question)
            ChatMessage.objects.create(session=session, role='ai', content=answer)

        return JsonResponse({'answer': answer})

    # GET — load chat history from the database
    chat_history = []
    if session:
        chat_history = list(
            ChatMessage.objects.filter(session=session)
            .order_by('created_at')
            .values('role', 'content')
        )

    return render(request, 'dashboard/ask_data.html', {
        'suggested_questions': AIAnalyticsService.SUGGESTED_QUESTIONS,
        'has_data': has_data,
        'active_session': session,
        'chat_history': json.dumps(chat_history),
    })


@login_required
def clear_chat(request):
    """Clear all chat messages for the active session."""
    from .models import ChatMessage

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    session = AnalysisSession.get_active_session(request.user)
    if session:
        ChatMessage.objects.filter(session=session).delete()

    return JsonResponse({'status': 'ok'})


@login_required
def anomaly_page(request):
    """Anomaly detection page — flags unusual spikes/drops in revenue & orders."""
    from .services import AnomalyDetector

    session = AnalysisSession.get_active_session(request.user)
    result = {'anomalies': [], 'chart_html': '', 'summary': {
        'total_days': 0, 'anomaly_count': 0, 'anomaly_rate': 0,
        'high_count': 0, 'medium_count': 0,
        'avg_revenue': 0, 'std_revenue': 0, 'avg_orders': 0,
    }}

    lookback = request.GET.get('lookback', '')
    lookback_days = None
    if lookback and lookback.isdigit():
        lookback_days = int(lookback)

    if session and Sale.objects.filter(session=session).exists():
        result = AnomalyDetector.detect(session, lookback_days=lookback_days)

    return render(request, 'dashboard/anomaly.html', {
        'anomalies': result['anomalies'],
        'chart_html': result['chart_html'],
        'summary': result['summary'],
        'session': session,
        'selected_lookback': lookback or 'all',
    })


@login_required
def cohort_page(request):
    """Cohort retention analysis."""
    session = AnalysisSession.get_active_session(request.user)
    result = {'chart_html': '', 'cohort_data': [], 'summary': {}}

    if session and Sale.objects.filter(session=session).exists():
        result = CohortAnalyzer.analyze(session)

    return render(request, 'dashboard/cohort.html', {
        'chart_html': result['chart_html'],
        'cohort_data': result['cohort_data'],
        'summary': result['summary'],
        'session': session,
    })


@login_required
def clv_page(request):
    """Customer Lifetime Value analysis."""
    session = AnalysisSession.get_active_session(request.user)
    result = {'chart_html': '', 'top_customers': [], 'summary': {}}

    if session and Sale.objects.filter(session=session).exists():
        result = CLVCalculator.calculate(session)

    return render(request, 'dashboard/clv.html', {
        'chart_html': result['chart_html'],
        'top_customers': result['top_customers'],
        'summary': result['summary'],
        'session': session,
    })


@login_required
def associations_page(request):
    """Product association / market basket analysis."""
    session = AnalysisSession.get_active_session(request.user)
    result = {'rules': [], 'chart_html': '', 'summary': {
        'total_baskets': 0, 'multi_item_baskets': 0, 'rules_found': 0
    }}

    if session and Sale.objects.filter(session=session).exists():
        result = AssociationAnalyzer.analyze(session)

    return render(request, 'dashboard/associations.html', {
        'rules': result['rules'],
        'chart_html': result['chart_html'],
        'summary': result['summary'],
        'session': session,
    })


@login_required
def whatif_page(request):
    """What-If Simulator page."""
    session = AnalysisSession.get_active_session(request.user)
    baselines = None
    if session and Sale.objects.filter(session=session).exists():
        baselines = WhatIfSimulator.get_baselines(session)

    return render(request, 'dashboard/whatif.html', {
        'baselines': json.dumps(baselines) if baselines else 'null',
        'baselines_obj': baselines,
        'session': session,
    })


@login_required
def whatif_simulate(request):
    """AJAX endpoint for What-If simulation."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    session = AnalysisSession.get_active_session(request.user)
    if not session:
        return JsonResponse({'error': 'No active session'}, status=400)

    baselines = WhatIfSimulator.get_baselines(session)
    if not baselines:
        return JsonResponse({'error': 'No data'}, status=400)

    try:
        data = json.loads(request.body)
        price_change = float(data.get('price_change', 0))
        discount_change = float(data.get('discount_change', 0))
        volume_change = float(data.get('volume_change', 0))
        elasticity = float(data.get('elasticity', -1.5))
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({'error': 'Invalid input'}, status=400)

    # Clamp values to reasonable range
    price_change = max(-50, min(50, price_change))
    discount_change = max(-50, min(50, discount_change))
    volume_change = max(-50, min(50, volume_change))
    elasticity = max(-3.0, min(-0.5, elasticity))

    result = WhatIfSimulator.simulate(baselines, price_change, discount_change, volume_change, elasticity)
    return JsonResponse({'result': result, 'baselines': baselines})


@login_required
def report_page(request):
    """Printable analytics report page (use browser Print → Save as PDF)."""
    session = AnalysisSession.get_active_session(request.user)
    report = None
    if session and Sale.objects.filter(session=session).exists():
        report = ReportGenerator.generate(session)

    return render(request, 'dashboard/report.html', {
        'report': report,
        'session': session,
    })
