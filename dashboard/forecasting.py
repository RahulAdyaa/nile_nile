import pandas as pd
import numpy as np
from django.db.models import Sum, Count
from .models import Sale
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
import warnings


class ForecastingService:
    """
    Multi-horizon revenue forecasting engine.
    Uses STL decomposition to extract trend + seasonality, then forecasts
    with Holt-Winters (weekly seasonality) and overlays monthly aggregates
    for a clear business view.
    """

    @staticmethod
    def generate_forecast(forecast_days=90, session=None):
        """
        Returns a rich Plotly chart showing:
        - Historical weekly revenue with trend line
        - Seasonal pattern overlay
        - 90-day forecast with confidence bands
        - Monthly summary bars for quick reading
        - Key business metrics (growth rate, projected quarterly revenue)
        """
        # ── 1. Pull daily revenue from DB ──
        queryset = Sale.objects
        if session:
            queryset = queryset.filter(session=session)

        daily_data = list(
            queryset.values('order_date')
            .annotate(revenue=Sum('total_sales'), orders=Count('id'))
            .order_by('order_date')
        )

        if not daily_data or len(daily_data) < 30:
            return None

        df = pd.DataFrame(daily_data)
        df.rename(columns={'order_date': 'date', 'revenue': 'y'}, inplace=True)
        df['date'] = pd.to_datetime(df['date'])
        df['y'] = df['y'].apply(lambda x: float(x) if x is not None else 0.0)
        df['orders'] = df['orders'].apply(lambda x: int(x) if x is not None else 0)

        # Fill gaps for continuous time series
        df.set_index('date', inplace=True)
        df = df.asfreq('D', fill_value=0)

        # ── 2. Aggregate to weekly for smoother trend ──
        weekly = df['y'].resample('W-MON').sum()
        weekly = weekly[weekly.index >= weekly.index[0]]  # ensure clean start
        weekly_orders = df['orders'].resample('W-MON').sum()

        if len(weekly) < 8:
            return None

        # ── 3. Trend extraction via rolling average ──
        trend_window = min(12, len(weekly) // 2)
        trend = weekly.rolling(window=trend_window, center=True, min_periods=3).mean()

        # ── 4. Forecast with Holt-Winters (weekly seasonality) ──
        forecast_weeks = forecast_days // 7
        forecast_y = None
        model_name = 'Trend Extrapolation'

        try:
            from statsmodels.tsa.holtwinters import ExponentialSmoothing

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")

                # Use multiplicative if data is always positive and has enough periods
                seasonal_type = 'add'
                if (weekly > 0).all() and len(weekly) >= 52:
                    seasonal_type = 'mul'

                # Weekly data with ~52 weeks/year, but we may not have 2 full years
                # Use 4-week (monthly) seasonality if < 1 year, else try annual
                seasonal_periods = 4 if len(weekly) < 52 else 13  # quarterly cycle

                model = ExponentialSmoothing(
                    weekly.values,
                    trend='add',
                    seasonal=seasonal_type,
                    seasonal_periods=seasonal_periods,
                    initialization_method="heuristic",
                    use_boxcox=False,
                )
                fit = model.fit(optimized=False, use_brute=False)
                forecast_y = fit.forecast(forecast_weeks)
                residuals = fit.resid

                # Sanity: reject if forecast diverges wildly
                hist_max = weekly.max()
                hist_mean = weekly.mean()
                if forecast_y.max() > hist_max * 3 or forecast_y.min() < -hist_mean * 0.5:
                    forecast_y = None
                else:
                    model_name = f'Holt-Winters ({seasonal_type.title()} Seasonal)'
                    rmse = np.sqrt(np.mean(residuals ** 2))

        except Exception:
            forecast_y = None

        # ── 5. Fallback: Trend extrapolation with seasonality ──
        if forecast_y is None:
            recent_weeks = weekly.tail(min(26, len(weekly)))
            weights = np.linspace(0.5, 1.5, len(recent_weeks))
            weights /= weights.sum()
            base_weekly = float(np.dot(recent_weeks.values, weights))

            # Trend slope from linear regression on last 26 weeks
            x = np.arange(len(recent_weeks))
            coeffs = np.polyfit(x, recent_weeks.values, 1)
            weekly_trend = coeffs[0]

            forecast_values = []
            for i in range(forecast_weeks):
                val = base_weekly + weekly_trend * (i + 1)
                forecast_values.append(max(0, val))
            forecast_y = np.array(forecast_values)
            rmse = float(recent_weeks.std())

        # ── 6. Build forecast dates ──
        last_date = weekly.index[-1]
        future_dates = pd.date_range(
            start=last_date + pd.Timedelta(weeks=1),
            periods=forecast_weeks, freq='W-MON'
        )

        # ── 7. Confidence bands (widening over time) ──
        ci_scale = 1.96 * rmse * np.sqrt(np.arange(1, forecast_weeks + 1) / forecast_weeks * 3)
        upper = forecast_y + ci_scale
        lower = np.maximum(0, forecast_y - ci_scale)

        # ── 8. Compute business metrics ──
        last_12w = weekly.tail(12).sum()
        forecast_12w = float(forecast_y[:12].sum()) if len(forecast_y) >= 12 else float(forecast_y.sum())
        growth_pct = ((forecast_12w - last_12w) / last_12w * 100) if last_12w > 0 else 0

        avg_weekly_hist = weekly.tail(12).mean()
        avg_weekly_forecast = float(forecast_y.mean())

        # Monthly aggregates for bar chart
        monthly_hist = df['y'].resample('ME').sum().tail(12)
        monthly_forecast_values = []
        temp_series = pd.Series(forecast_y, index=future_dates)
        monthly_forecast = temp_series.resample('ME').sum()

        # ── 9. Build the chart ──
        fig = make_subplots(
            rows=2, cols=2,
            row_heights=[0.65, 0.35],
            column_widths=[0.7, 0.3],
            subplot_titles=(
                'Revenue Trend & Forecast', 'Quarterly Outlook',
                'Monthly Revenue', 'Forecast Summary'
            ),
            specs=[
                [{"type": "scatter"}, {"type": "indicator"}],
                [{"type": "bar"}, {"type": "table"}]
            ],
            vertical_spacing=0.14,
            horizontal_spacing=0.08,
        )

        # ── Main chart: Historical weekly revenue ──
        display_weeks = min(52, len(weekly))
        hist_display = weekly.tail(display_weeks)

        fig.add_trace(go.Scatter(
            x=hist_display.index.tolist(),
            y=[float(v) for v in hist_display.values],
            mode='lines',
            name='Weekly Revenue',
            line=dict(color='#111111', width=2),
            hovertemplate='%{x|%b %d, %Y}<br><b>$%{y:,.0f}</b><extra>Actual</extra>',
        ), row=1, col=1)

        # Trend line
        trend_display = trend.loc[hist_display.index[0]:].dropna()
        if len(trend_display) > 0:
            fig.add_trace(go.Scatter(
                x=trend_display.index.tolist(),
                y=[float(v) for v in trend_display.values],
                mode='lines',
                name='Trend',
                line=dict(color='#A1A1AA', width=1.5, dash='dash'),
                hoverinfo='skip',
            ), row=1, col=1)

        # Forecast line
        fig.add_trace(go.Scatter(
            x=future_dates.tolist(),
            y=[float(v) for v in forecast_y],
            mode='lines+markers',
            name=f'Forecast ({model_name})',
            line=dict(color='#E63B2E', width=3),
            marker=dict(size=4, color='#E63B2E'),
            hovertemplate='%{x|%b %d, %Y}<br><b>$%{y:,.0f}</b><extra>Forecast</extra>',
        ), row=1, col=1)

        # Confidence band
        fig.add_trace(go.Scatter(
            x=list(future_dates) + list(future_dates[::-1]),
            y=[float(v) for v in upper] + [float(v) for v in lower[::-1]],
            fill='toself',
            fillcolor='rgba(230, 59, 46, 0.08)',
            line=dict(color='rgba(0,0,0,0)'),
            name='95% Confidence',
            showlegend=True,
            hoverinfo='skip',
        ), row=1, col=1)

        # Divider line between historical and forecast
        fig.add_vline(
            x=last_date.timestamp() * 1000,
            line_dash="dot", line_color="#D4D4D8", line_width=1,
            row=1, col=1,
        )
        fig.add_annotation(
            x=last_date, y=float(hist_display.max()),
            text="Today", showarrow=False,
            font=dict(size=9, color='#A1A1AA', family='Inter, sans-serif'),
            yshift=10, row=1, col=1,
        )

        # ── Quarterly outlook indicator ──
        fig.add_trace(go.Indicator(
            mode="number+delta",
            value=forecast_12w,
            number=dict(
                prefix="$",
                font=dict(size=32, color='#111111', family='Outfit, sans-serif'),
                valueformat=",.0f",
            ),
            delta=dict(
                reference=float(last_12w),
                relative=True,
                valueformat=".1%",
                increasing=dict(color='#16A34A'),
                decreasing=dict(color='#E63B2E'),
                font=dict(size=14),
            ),
            title=dict(
                text="Next 12 Weeks<br><span style='font-size:11px;color:#A1A1AA'>vs Last 12 Weeks</span>",
                font=dict(size=13, color='#52525B', family='Inter, sans-serif'),
            ),
        ), row=1, col=2)

        # ── Monthly bar chart ──
        # Historical bars
        fig.add_trace(go.Bar(
            x=monthly_hist.index.tolist(),
            y=[float(v) for v in monthly_hist.values],
            name='Actual Monthly',
            marker_color='#111111',
            hovertemplate='%{x|%b %Y}<br><b>$%{y:,.0f}</b><extra></extra>',
        ), row=2, col=1)

        # Forecast bars
        if len(monthly_forecast) > 0:
            fig.add_trace(go.Bar(
                x=monthly_forecast.index.tolist(),
                y=[float(v) for v in monthly_forecast.values],
                name='Forecast Monthly',
                marker_color='#E63B2E',
                marker_pattern_shape='/',
                hovertemplate='%{x|%b %Y}<br><b>$%{y:,.0f}</b><extra>Forecast</extra>',
            ), row=2, col=1)

        # ── Summary table ──
        def fmt(val):
            v = float(val)
            if abs(v) >= 1_000_000:
                return f"${v/1_000_000:.1f}M"
            elif abs(v) >= 1_000:
                return f"${v/1_000:.1f}K"
            return f"${v:.0f}"

        summary_labels = [
            'Avg Weekly (Historical)',
            'Avg Weekly (Forecast)',
            f'{forecast_days}-Day Projected',
            'Growth Trend',
            'Model Used',
        ]
        summary_values = [
            fmt(avg_weekly_hist),
            fmt(avg_weekly_forecast),
            fmt(float(forecast_y.sum())),
            f"{growth_pct:+.1f}%",
            model_name.split('(')[0].strip(),
        ]

        fig.add_trace(go.Table(
            header=dict(
                values=['<b>Metric</b>', '<b>Value</b>'],
                fill_color='#F4F4F5',
                font=dict(size=10, color='#111111', family='Inter, sans-serif'),
                align='left',
                line_color='#E4E4E7',
                height=28,
            ),
            cells=dict(
                values=[summary_labels, summary_values],
                fill_color='white',
                font=dict(size=10, color='#52525B', family='Inter, sans-serif'),
                align='left',
                line_color='#E4E4E7',
                height=26,
            ),
        ), row=2, col=2)

        # ── Layout ──
        fig.update_layout(
            height=620,
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font=dict(family="Inter, sans-serif", size=11, color='#52525B'),
            margin=dict(t=40, b=20, l=50, r=20),
            hovermode='x unified',
            showlegend=True,
            legend=dict(
                orientation='h',
                yanchor='bottom', y=1.04,
                xanchor='center', x=0.35,
                font=dict(size=10, family='Inter, sans-serif'),
                bgcolor='rgba(255,255,255,0.8)',
            ),
            barmode='group',
        )

        # Style sub-axes
        fig.update_xaxes(showgrid=False, zeroline=False, row=1, col=1)
        fig.update_yaxes(
            showgrid=True, gridcolor='#F4F4F5', zeroline=False,
            tickprefix='$', tickformat=',',
            row=1, col=1,
        )
        fig.update_xaxes(showgrid=False, zeroline=False, row=2, col=1)
        fig.update_yaxes(
            showgrid=True, gridcolor='#F4F4F5', zeroline=False,
            tickprefix='$', tickformat=',',
            row=2, col=1,
        )

        # Style subplot titles
        for ann in fig.layout.annotations:
            ann.font = dict(size=12, color='#111111', family='Outfit, sans-serif')

        return pio.to_html(fig, full_html=False, include_plotlyjs=False)
