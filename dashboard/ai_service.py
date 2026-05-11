"""
AI-powered Natural Language Analytics Service.

Multi-provider architecture with automatic fallback:
  1. Groq  (Llama 3.3 70B) — fast, free, open-source
  2. Google Gemini (2.0 Flash) — free fallback if Groq is blocked by firewall

The AI never sees raw data — it receives pre-computed statistical summaries
and aggregations, then generates grounded, accurate answers.
"""

import requests as http_requests
from django.conf import settings
from django.db.models import Sum, Count, Avg, Min, Max, Q
import pandas as pd
import json
import logging

logger = logging.getLogger(__name__)

# ─── Provider configs ─────────────────────────────────────────────────────────
GROQ_API_URL = 'https://api.groq.com/openai/v1/chat/completions'
GROQ_MODEL = 'llama-3.3-70b-versatile'

GEMINI_API_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent'


class AIAnalyticsService:
    """
    Bridges the user's natural language questions with the sales database.

    Flow:
    1. Build a data context snapshot (aggregated stats, not raw rows)
    2. Construct a system prompt that makes the AI a data analyst
    3. Try Groq first → fall back to Gemini if blocked
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

        Tries Groq first, then Gemini as fallback.
        """
        groq_key = getattr(settings, 'GROQ_API_KEY', '')
        gemini_key = getattr(settings, 'GEMINI_API_KEY', '')

        has_groq = groq_key and groq_key != 'your-groq-api-key-here'
        has_gemini = gemini_key and gemini_key != 'your-gemini-api-key-here'

        if not has_groq and not has_gemini:
            return (
                "⚠️ **No AI API key configured.**\n\n"
                "To enable AI analytics, add at least one key to your `.env` file:\n\n"
                "**Option 1 — Groq (recommended):**\n"
                "1. Visit [console.groq.com](https://console.groq.com)\n"
                "2. Sign up (free) and create an API key\n"
                "3. Add `GROQ_API_KEY=your-key` to `.env`\n\n"
                "**Option 2 — Google Gemini (good for corporate networks):**\n"
                "1. Visit [aistudio.google.com/apikey](https://aistudio.google.com/apikey)\n"
                "2. Create an API key (free)\n"
                "3. Add `GEMINI_API_KEY=your-key` to `.env`\n\n"
                "4. Restart the server"
            )

        # Build data context
        data_context = cls._build_data_context(session)
        if not data_context:
            return "No sales data available in the current session. Please upload data first."

        system_prompt = cls._build_system_prompt(data_context)

        # ── Try Groq first ──
        if has_groq:
            result = cls._call_groq(groq_key, system_prompt, question)
            if result is not None:
                return result
            logger.warning("[Nile AI] Groq failed, trying Gemini fallback...")

        # ── Fallback to Gemini ──
        if has_gemini:
            result = cls._call_gemini(gemini_key, system_prompt, question)
            if result is not None:
                return result

        return (
            "⚠️ **Both AI providers failed.**\n\n"
            "This is likely due to network/firewall restrictions.\n"
            "- **Groq** — may be blocked by your corporate firewall\n"
            "- **Gemini** — check that your API key is valid\n\n"
            "Try again later or check your network settings."
        )

    # ─── Provider: Groq ────────────────────────────────────────────────────────
    @classmethod
    def _call_groq(cls, api_key, system_prompt, question):
        """Call Groq API. Returns answer string or None on failure."""
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

            # Other errors → fall through to Gemini
            logger.warning(f"[Nile AI] Groq HTTP {response.status_code}: {response.text[:200]}")
            return None

        except http_requests.exceptions.ConnectionError:
            logger.warning("[Nile AI] Groq connection refused (firewall?)")
            return None
        except http_requests.exceptions.Timeout:
            logger.warning("[Nile AI] Groq request timed out")
            return None
        except Exception as e:
            logger.warning(f"[Nile AI] Groq error: {e}")
            return None

    # ─── Provider: Google Gemini ───────────────────────────────────────────────
    @classmethod
    def _call_gemini(cls, api_key, system_prompt, question):
        """Call Google Gemini API. Returns answer string or None on failure."""
        try:
            response = http_requests.post(
                f'{GEMINI_API_URL}?key={api_key}',
                headers={'Content-Type': 'application/json'},
                json={
                    'system_instruction': {
                        'parts': [{'text': system_prompt}]
                    },
                    'contents': [
                        {
                            'parts': [{'text': question}]
                        }
                    ],
                    'generationConfig': {
                        'temperature': 0.3,
                        'maxOutputTokens': 1500,
                    }
                },
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                # Gemini response structure
                candidates = data.get('candidates', [])
                if candidates:
                    parts = candidates[0].get('content', {}).get('parts', [])
                    if parts:
                        return parts[0].get('text', '')

            if response.status_code == 400:
                error_msg = response.json().get('error', {}).get('message', '')
                logger.warning(f"[Nile AI] Gemini 400: {error_msg}")
                return f"⚠️ **Gemini API error:** {error_msg[:200]}"

            if response.status_code == 403:
                return (
                    "⚠️ **Invalid Gemini API key.**\n\n"
                    "Please check your `GEMINI_API_KEY` in the `.env` file "
                    "and make sure it's valid from "
                    "[aistudio.google.com/apikey](https://aistudio.google.com/apikey)."
                )

            if response.status_code == 429:
                return (
                    "⚠️ **Gemini rate limit reached.**\n\n"
                    "Free tier allows 15 requests/minute. "
                    "Please wait a moment and try again."
                )

            logger.warning(f"[Nile AI] Gemini HTTP {response.status_code}: {response.text[:200]}")
            return None

        except http_requests.exceptions.ConnectionError:
            logger.warning("[Nile AI] Gemini connection refused")
            return None
        except http_requests.exceptions.Timeout:
            logger.warning("[Nile AI] Gemini request timed out")
            return None
        except Exception as e:
            logger.warning(f"[Nile AI] Gemini error: {e}")
            return None

    # ─── Data Context Builder ──────────────────────────────────────────────────
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
