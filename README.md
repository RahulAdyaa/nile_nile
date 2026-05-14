<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/Django-4.2-092E20?style=for-the-badge&logo=django&logoColor=white" />
  <img src="https://img.shields.io/badge/PostgreSQL-14+-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" />
  <img src="https://img.shields.io/badge/HTMX-1.x-3366CC?style=for-the-badge&logo=htmx&logoColor=white" />
  <img src="https://img.shields.io/badge/Tailwind_CSS-3.x-06B6D4?style=for-the-badge&logo=tailwindcss&logoColor=white" />
  <img src="https://img.shields.io/badge/Plotly-5.x-3F4F75?style=for-the-badge&logo=plotly&logoColor=white" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
</p>

# 🌊 Nile Analytics

**AI-Powered Sales Intelligence Platform** — Upload any CSV/Excel, get instant dashboards, forecasting, anomaly detection, and conversational AI analytics.

> _"Upload your data. Ask your questions. Get answers."_

---

## ✨ What is Nile Analytics?

Nile Analytics transforms raw e-commerce transaction data into actionable business insights. It combines an **intelligent ETL pipeline**, **interactive Plotly dashboards**, **Holt-Winters revenue forecasting**, **statistical anomaly detection**, and **AI-powered natural language querying** — all in a single Django application.

No SQL. No Python scripting. No expensive BI tools. Just upload and explore.

---

## 🎯 Key Features

| Feature | Description |
|---|---|
| 📊 **Interactive Dashboard** | Real-time KPI cards, revenue trends (7-day MA), regional/category breakdowns with HTMX-powered filters |
| 🤖 **Ask Your Data (AI)** | Natural language analytics via Groq (Llama 3.3 70B) with Google Gemini fallback |
| 📈 **Revenue Forecasting** | 90-day predictions using Holt-Winters exponential smoothing with confidence bands |
| 🔍 **Anomaly Detection** | Rolling Z-score + IQR-based spike/drop detection with severity classification |
| 👥 **RFM Segmentation** | Automatic customer segmentation into Champions, Loyal, At-Risk, Lost, etc. |
| 📦 **Smart ETL Pipeline** | Auto-maps columns from 120+ aliases — accepts virtually any CSV/Excel format |
| 🔄 **Multi-File Upload** | Upload customer data + sales data separately — ETL merges dimensions intelligently |
| 💰 **Customer Lifetime Value** | CLV calculation engine for marketing prioritization |
| 🧪 **What-If Simulator** | Model pricing/discount scenarios with instant recalculation |
| 🔗 **Product Associations** | Discover frequently co-purchased products |
| 📋 **Cohort Retention** | Monthly cohort retention heatmap for loyalty tracking |
| 📤 **Multi-Format Export** | CSV + multi-sheet Excel reports with embedded charts (up to 50K rows) |
| 🔐 **Role-Based Access** | Admin vs Analyst roles with JWT + OAuth (Google, GitHub) |
| 📝 **Audit Trail** | Every login, upload, export, and ETL operation is logged |

---

## 🏗️ Architecture

```
Browser (HTMX + Tailwind)
    │
    ▼
┌──────────────────────────────────────────────┐
│              Django Application               │
│                                              │
│  Views ──► Services ──► ETL Pipeline         │
│    │         │              │                │
│    │    (RFM, Cohort,   (Extract,            │
│    │     CLV, Anomaly)   Map, Clean,         │
│    │                     Load)               │
│    ▼         ▼              ▼                │
│  ┌─────────────────────────────────┐         │
│  │   PostgreSQL / SQLite           │         │
│  └─────────────────────────────────┘         │
│                                              │
│  Celery (Background Tasks)                   │
│  AI Service (Groq → Gemini fallback)         │
└──────────────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Django 4.2, Django REST Framework |
| **Frontend** | HTMX, Tailwind CSS |
| **Charts** | Plotly (Python, server-side) |
| **Database** | PostgreSQL (prod) / SQLite (dev) |
| **Auth** | Django Allauth (OAuth) + SimpleJWT |
| **AI** | Groq API (Llama 3.3 70B) + Google Gemini 2.0 Flash |
| **Data** | Pandas, NumPy, SciPy, Statsmodels |
| **Tasks** | Celery + Django Celery Beat |
| **Deployment** | Gunicorn, WhiteNoise, Render/Vercel |

---

## 🚀 Quick Start (5 minutes)

### Prerequisites

| Requirement | Required? | Notes |
|---|---|---|
| Python 3.10+ | ✅ Yes | Check: `python --version` |
| pip | ✅ Yes | Comes with Python |
| Git | ✅ Yes | To clone the repo |
| PostgreSQL | ❌ No | SQLite works out of the box |

---

### Step 1 — Clone and install dependencies

```bash
git clone https://github.com/your-username/nile-analytics.git
cd nile-analytics

# Create virtual environment
python -m venv venv

# Activate it
source venv/bin/activate          # macOS / Linux
# venv\Scripts\activate           # Windows (CMD)
# .\venv\Scripts\Activate.ps1    # Windows (PowerShell)

# Install all packages
pip install -r requirements.txt
```

---

### Step 2 — Create the `.env` file

> ⚠️ **This is the most important step. The project will NOT start without a `.env` file.**

```bash
cp .env.example .env
```

The default `.env.example` is pre-configured with **SQLite** — everything works immediately with zero database setup.

**Optional AI keys** (for the "Ask Your Data" feature):

| Provider | Free key from | Add to `.env` as |
|---|---|---|
| Groq (recommended) | https://console.groq.com/keys | `GROQ_API_KEY=your-key` |
| Google Gemini | https://aistudio.google.com/apikey | `GEMINI_API_KEY=your-key` |

> If you skip the AI keys, everything else works — only the AI chat feature is unavailable.

---

### Step 3 — Setup database and load data

```bash
# Create all database tables
python manage.py migrate

# Load pre-built data (34,500+ sales records + users + products)
python manage.py loaddata fixtures/users.json
python manage.py loaddata fixtures/initial_data.json
```

---

### Step 4 — Create your login

```bash
python manage.py createsuperuser
```

Follow the prompts to set username, email, and password.

---

### Step 5 — Run the server

```bash
python manage.py runserver
```

Open **http://127.0.0.1:8000** in your browser and login with the account you just created. 🎉

---

### ⚡ TL;DR — Run everything in one go

```bash
git clone https://github.com/your-username/nile-analytics.git
cd nile-analytics
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py loaddata fixtures/users.json
python manage.py loaddata fixtures/initial_data.json
python manage.py createsuperuser
python manage.py runserver
```

---

## ❓ Troubleshooting

| Problem | Solution |
|---|---|
| `ModuleNotFoundError: No module named '...'` | Make sure your virtualenv is activated and run `pip install -r requirements.txt` |
| `django.core.exceptions.ImproperlyConfigured` | You're missing the `.env` file. Run `cp .env.example .env` |
| `OperationalError: no such table` | Run `python manage.py migrate` |
| Port 8000 already in use | Kill it: `lsof -ti:8000 \| xargs kill` (Mac/Linux) or use `python manage.py runserver 8080` |
| AI "Ask Your Data" not working | Add `GROQ_API_KEY` or `GEMINI_API_KEY` to your `.env` file |
| OAuth login buttons don't work | Add Google/GitHub OAuth credentials to `.env` (or just use username/password login) |
| `loaddata` fails with UTF errors | Make sure you're using Python 3.10+ |
| Forecast page shows no chart | Need at least 30 days of historical data loaded |

---

## 🗄️ Database Options

| Database | Setup | `.env` value |
|---|---|---|
| **SQLite** (default) | No setup needed | `DATABASE_URL=sqlite:///db.sqlite3` |
| **PostgreSQL** | `psql -U postgres -c "CREATE DATABASE nile_db;"` | `DATABASE_URL=postgres://user:pass@localhost:5432/nile_db` |
| **MySQL** | `pip install mysqlclient` + create DB | `DATABASE_URL=mysql://user:pass@localhost:3306/nile_db` |

---

## 🔑 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `SECRET_KEY` | ✅ | Django secret key (any random string) |
| `DEBUG` | ❌ | `True` for development (default) |
| `DATABASE_URL` | ❌ | DB connection string (default: SQLite) |
| `GROQ_API_KEY` | ❌ | Enables AI "Ask Your Data" feature |
| `GEMINI_API_KEY` | ❌ | AI fallback provider |
| `GOOGLE_OAUTH_CLIENT_ID` | ❌ | Google social login |
| `GOOGLE_OAUTH_SECRET` | ❌ | Google social login |
| `GITHUB_OAUTH_CLIENT_ID` | ❌ | GitHub social login |
| `GITHUB_OAUTH_SECRET` | ❌ | GitHub social login |

---

## 📁 Project Structure

```
nile-analytics/
├── accounts/           # User auth, JWT middleware, OAuth
│   ├── middleware.py    # JWT cookie auth with silent refresh
│   ├── views.py        # Login, register, API endpoints
│   └── models.py       # Custom User model (admin/analyst roles)
├── dashboard/          # Core analytics application
│   ├── views.py        # Dashboard, charts, export, AI views
│   ├── analytics.py    # AnalyticsService (RFM, cohorts, CLV)
│   ├── forecasting.py  # Holt-Winters forecasting engine
│   ├── ai_service.py   # Groq + Gemini AI analytics
│   ├── anomaly.py      # Z-score + IQR anomaly detection
│   ├── tasks.py        # Celery background tasks
│   └── etl/
│       └── pipeline.py # Multi-file ETL with 120+ alias mapping
├── core/               # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── celery.py
├── templates/          # HTML templates (HTMX + Tailwind)
├── static/             # CSS, JS, images
├── fixtures/           # Pre-built data (34,500+ records)
├── data/               # Sample CSV/Excel files for testing
├── .env.example        # Template env file — copy to .env
├── requirements.txt
└── manage.py
```

---

## 📊 Sample Data

The `data/` directory includes ready-to-use test files:

| File | Description |
|---|---|
| `nile_complete_dataset.xlsx` | Full dataset (649 KB) |
| `sales_transactions.csv` | Sales transactions (648 KB) |
| `nile_supplementary.csv` | Supplementary customer/product data (529 KB) |
| `nile_messy_test.csv` | Intentionally messy data for ETL testing (4 KB) |

---

## 🧪 Running with Celery (Optional)

For background task processing (async uploads, scheduled reports):

```bash
# Terminal 1 — Django server
python manage.py runserver

# Terminal 2 — Celery worker
celery -A core worker --loglevel=info

# Terminal 3 — Celery Beat (scheduled tasks)
celery -A core beat --loglevel=info
```

> Celery is **not required** for basic usage. Without it, ETL runs synchronously.

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit your changes: `git commit -m "Add my feature"`
4. Push to the branch: `git push origin feature/my-feature`
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License.

---

## 👤 Author

**Rahul Adya** — Full-Stack Developer, Data Engineer, AI Integration Lead

---

<p align="center">
  Built with ❤️ using Django, HTMX, and Plotly
</p>