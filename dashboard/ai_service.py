"""
AI-powered Natural Language Analytics Service.

Uses Groq API (free tier) with open-source Llama 3.3 70B to answer business
questions by analyzing real sales data. The AI never sees raw data — it receives
pre-computed statistical summaries and aggregations, then generates grounded,
accurate answers.

Provider: Groq (https://console.groq.com)
Model: Llama 3.3 70B Versatile (open-source, Meta)
Free tier: 30 requests/minute, 6000 tokens/minute
"""

import requests as http_requests
from django.conf import settings
from django.db.models import Sum, Count, Avg, Min, Max, Q
import pandas as pd
import json


GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'
GROQ_MODEL = 'llama-3.3-70b-versatile'


class AIAnalyticsService:
    """
    Bridges the user's natural language questions with the sales database.

    Flow:
    1. Build a data context snapshot (aggregated stats, not raw rows)
    2. Construct a system prompt that makes the AI a data analyst
    3. Send user question + data context to Groq (Llama 3.3 70B)
    4. Return the grounded answer
    """

    # ─── Suggested questions for the UI ────────────────────────────────────────
    SUGGESTED_QUESTIONS = [
        "Which region is performing the best this year?",
        "What are my top 5 selling products?",
        "Is my business growing month over month?",
        "Which category has the highest return rate?",
        "Who are my most valuable customers?",
        "What day of the week gets the most orders?",
        "Which products are losing money?",
        "Compare Technology vs Office Supplies performance",
    ]

    @classmethod
    def ask(cls, question, session):
        """
        Main entry point. Takes a natural language question and an AnalysisSession,
        returns the AI's answer as a string.
        """
        api_key = getattr(settings, 'GROQ_API_KEY', '')
        if not api_key or api_key == 'your-groq-api-key-here':
            return (
                "⚠️ **Groq API key not configured.**\n\n"
                "To enable AI analytics:\n"
                "1. Visit [console.groq.com](https://console.groq.com)\n"
                "2. Sign up (free) and create an API key\n"
                "3. Add it to your `.env` file as `GROQ_API_KEY=your-key`\n"
                "4. Restart the server"
            )

        # Build data context
        data_context = cls._build_data_context(session)
        if not data_context:
            return "No sales data available in the current session. Please upload data first."

        # Build the prompt
        system_prompt = cls._build_system_prompt(data_context)

        try:
            response = http_requests.post(
                GROQ_API_URL,
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': GROQ_MODEL,
                    'messages': [
                        {'role': 'system', 'content': system_prompt},
                        {'role': 'user', 'content': question},
                    ],
                    'temperature': 0.3,
                    'max_tokens': 1500,
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']

            # Handle specific HTTP errors
            error_body = response.text
            if response.status_code == 401:
                return (
                    "⚠️ **Invalid Groq API key.**\n\n"
                    "Please check your `GROQ_API_KEY` in the `.env` file "
                    "and make sure it's a valid key from "
                    "[console.groq.com](https://console.groq.com/keys)."
                )
            if response.status_code == 429:
                return (
                    "⚠️ **Rate limit reached.**\n\n"
                    "Groq free tier allows 30 requests/minute. "
                    "Please wait a moment and try again."
                )
            return f"⚠️ **API error ({response.status_code}):** {error_body[:200]}"

        except http_requests.exceptions.Timeout:
            return "⚠️ **Request timed out.** The AI took too long to respond. Please try again."
        except http_requests.exceptions.ConnectionError:
            return "⚠️ **Connection error.** Could not reach the Groq API. Check your internet connection."
        except Exception as e:
            return f"⚠️ **AI service error:** {str(e)}"

    @classmethod
    def _build_data_context(cls, session):
        """
        Build a comprehensive statistical summary of the session's sales data.
        This is what the AI 'sees' — pre-aggregated stats, NOT raw rows.
        """
        from .models import Sale, Customer, Product

        sales = Sale.objects.filter(session=session)
        if not sales.exists():
            return None

        # ── Overall metrics ──
        overall = sales.aggregate(
            total_revenue=Sum('total_sales'),
            total_profit=Sum('profit'),
            total_orders=Count('id'),
            unique_orders=Count('order_id', distinct=True),
            total_customers=Count('customer', distinct=True),
            total_products=Count('product', distinct=True),
            avg_order_value=Avg('total_sales'),
            avg_discount=Avg('discount'),
            avg_delivery_days=Avg('delivery_time_days'),
            total_shipping=Sum('shipping_cost'),
            min_date=Min('order_date'),
            max_date=Max('order_date'),
        )

        total_orders = overall['total_orders'] or 0
        returned_count = sales.filter(returned=True).count()
        return_rate = (returned_count / total_orders * 100) if total_orders else 0

        # ── Revenue by region ──
        by_region = list(
            sales.values('customer__region')
            .annotate(
                revenue=Sum('total_sales'),
                profit=Sum('profit'),
                orders=Count('id'),
                returns=Count('id', filter=Q(returned=True)),
            )
            .order_by('-revenue')[:10]
        )

        # ── Revenue by category ──
        by_category = list(
            sales.values('product__category')
            .annotate(
                revenue=Sum('total_sales'),
                profit=Sum('profit'),
                orders=Count('id'),
                returns=Count('id', filter=Q(returned=True)),
            )
            .order_by('-revenue')
        )

        # ── Top 10 products by revenue ──
        top_products = list(
            sales.values('product__name', 'product__category')
            .annotate(
                revenue=Sum('total_sales'),
                profit=Sum('profit'),
                qty=Sum('quantity'),
            )
            .order_by('-revenue')[:10]
        )

        # ── Top 10 customers by revenue ──
        top_customers = list(
            sales.values('customer__name', 'customer__region')
            .annotate(
                revenue=Sum('total_sales'),
                orders=Count('order_id', distinct=True),
            )
            .order_by('-revenue')[:10]
        )

        # ── Monthly trend ──
        monthly_rev = list(
            sales.extra(select={'month': "TO_CHAR(order_date, 'YYYY-MM')"})
            .values('month')
            .annotate(revenue=Sum('total_sales'), profit=Sum('profit'), orders=Count('id'))
            .order_by('month')
        )

        # ── Sub-category breakdown ──
        by_subcategory = list(
            sales.values('product__sub_category', 'product__category')
            .annotate(
                revenue=Sum('total_sales'),
                profit=Sum('profit'),
            )
            .order_by('-revenue')[:15]
        )

        # ── Day of week analysis ──
        dow_data = list(
            sales.extra(select={'dow': "EXTRACT(DOW FROM order_date)"})
            .values('dow')
            .annotate(orders=Count('id'), revenue=Sum('total_sales'))
            .order_by('dow')
        )

        # ── Payment mode breakdown ──
        by_payment = list(
            sales.values('payment_mode')
            .annotate(orders=Count('id'), revenue=Sum('total_sales'))
            .order_by('-orders')
        )

        # ── Loss-making products (negative profit) ──
        loss_products = list(
            sales.values('product__name', 'product__category')
            .annotate(profit=Sum('profit'))
            .filter(profit__lt=0)
            .order_by('profit')[:10]
        )

        # ── Build the context string ──
        def fmt(val):
            """Format Decimal/float safely."""
            if val is None:
                return '0'
            return f"{float(val):,.2f}"

        ctx = []
        ctx.append("=== BUSINESS DATA SUMMARY ===\n")

        ctx.append(f"Date range: {overall['min_date']} to {overall['max_date']}")
        ctx.append(f"Total revenue: ${fmt(overall['total_revenue'])}")
        ctx.append(f"Total profit: ${fmt(overall['total_profit'])}")
        profit_margin = (float(overall['total_profit'] or 0) / float(overall['total_revenue'] or 1)) * 100
        ctx.append(f"Profit margin: {profit_margin:.1f}%")
        ctx.append(f"Total orders: {overall['unique_orders']:,}")
        ctx.append(f"Total line items: {total_orders:,}")
        ctx.append(f"Unique customers: {overall['total_customers']:,}")
        ctx.append(f"Unique products: {overall['total_products']:,}")
        ctx.append(f"Avg order value: ${fmt(overall['avg_order_value'])}")
        ctx.append(f"Avg discount: {float(overall['avg_discount'] or 0):.1f}%")
        ctx.append(f"Avg delivery time: {float(overall['avg_delivery_days'] or 0):.1f} days")
        ctx.append(f"Return rate: {return_rate:.1f}% ({returned_count:,} returns)")
        ctx.append(f"Total shipping cost: ${fmt(overall['total_shipping'])}")

        ctx.append("\n--- REVENUE BY REGION (Top 10) ---")
        for r in by_region:
            ret_rate = (r['returns'] / r['orders'] * 100) if r['orders'] else 0
            ctx.append(f"  {r['customer__region']}: Revenue=${fmt(r['revenue'])}, Profit=${fmt(r['profit'])}, Orders={r['orders']}, Returns={ret_rate:.1f}%")

        ctx.append("\n--- REVENUE BY CATEGORY ---")
        for c in by_category:
            ret_rate = (c['returns'] / c['orders'] * 100) if c['orders'] else 0
            ctx.append(f"  {c['product__category']}: Revenue=${fmt(c['revenue'])}, Profit=${fmt(c['profit'])}, Orders={c['orders']}, Returns={ret_rate:.1f}%")

        ctx.append("\n--- TOP 10 PRODUCTS ---")
        for p in top_products:
            ctx.append(f"  {p['product__name']} ({p['product__category']}): Revenue=${fmt(p['revenue'])}, Profit=${fmt(p['profit'])}, Qty={p['qty']}")

        ctx.append("\n--- TOP 10 CUSTOMERS ---")
        for c in top_customers:
            ctx.append(f"  {c['customer__name']} ({c['customer__region']}): Revenue=${fmt(c['revenue'])}, Orders={c['orders']}")

        ctx.append("\n--- MONTHLY TREND ---")
        for m in monthly_rev:
            ctx.append(f"  {m['month']}: Revenue=${fmt(m['revenue'])}, Profit=${fmt(m['profit'])}, Orders={m['orders']}")

        ctx.append("\n--- SUB-CATEGORY BREAKDOWN (Top 15) ---")
        for s in by_subcategory:
            ctx.append(f"  {s['product__sub_category']} ({s['product__category']}): Revenue=${fmt(s['revenue'])}, Profit=${fmt(s['profit'])}")

        if dow_data:
            day_names = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
            ctx.append("\n--- ORDERS BY DAY OF WEEK ---")
            for d in dow_data:
                day_idx = int(d['dow']) if d['dow'] is not None else 0
                ctx.append(f"  {day_names[day_idx]}: Orders={d['orders']}, Revenue=${fmt(d['revenue'])}")

        if by_payment:
            ctx.append("\n--- PAYMENT MODES ---")
            for p in by_payment:
                ctx.append(f"  {p['payment_mode']}: Orders={p['orders']}, Revenue=${fmt(p['revenue'])}")

        if loss_products:
            ctx.append("\n--- LOSS-MAKING PRODUCTS ---")
            for p in loss_products:
                ctx.append(f"  {p['product__name']} ({p['product__category']}): Loss=${fmt(p['profit'])}")

        return '\n'.join(ctx)

    @classmethod
    def _build_system_prompt(cls, data_context):
        """Build the system instruction for the LLM."""
        return f"""You are an expert business data analyst for "Nile Analytics", an e-commerce analytics platform.

You have access to the following real business data summary from the user's uploaded dataset:

{data_context}

INSTRUCTIONS:
1. Answer the user's question ONLY using the data provided above. Never make up numbers.
2. Be specific — cite exact numbers, percentages, and names from the data.
3. Keep answers concise (3-6 paragraphs max). Use bullet points for comparisons.
4. Format numbers nicely (e.g., $1,234,567 not 1234567.00).
5. If the data doesn't contain enough information to answer, say so honestly.
6. Use markdown formatting: **bold** for key metrics, bullet points for lists.
7. When comparing metrics, calculate percentage differences.
8. If the user asks about trends, reference the monthly data.
9. End with a brief actionable insight when relevant.
10. Never reveal that you're reading from a summary — speak as if you analyzed the data directly."""
