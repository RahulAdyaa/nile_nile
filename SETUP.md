# Nile Analytics — Setup Guide

Works with **any database** — PostgreSQL, MySQL, or SQLite.

## Requirements
- Python 3.10+
- PostgreSQL **or** MySQL **or** SQLite (your choice)
- Git

---

## Step 1 — Clone & navigate
```bash
git clone <your-repo-url>
cd nile-corpo/nile_django
```

---

## Step 2 — Virtual environment & dependencies
```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

---

## Step 3 — Create your .env file

Create a file called `.env` in `nile_django/`:

### Option A: SQLite (simplest — no installation needed)
```env
DEBUG=True
SECRET_KEY=django-insecure-change-this-in-production
DATABASE_URL=sqlite:///db.sqlite3
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_SECRET=
GITHUB_OAUTH_CLIENT_ID=
GITHUB_OAUTH_SECRET=
```

### Option B: PostgreSQL
```env
DEBUG=True
SECRET_KEY=django-insecure-change-this-in-production
DATABASE_URL=postgresql://<your-username>:@127.0.0.1:5432/nile_db
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_SECRET=
GITHUB_OAUTH_CLIENT_ID=
GITHUB_OAUTH_SECRET=
```

### Option C: MySQL
```env
DEBUG=True
SECRET_KEY=django-insecure-change-this-in-production
DATABASE_URL=mysql://<your-username>:<your-password>@127.0.0.1:3306/nile_db
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_SECRET=
GITHUB_OAUTH_CLIENT_ID=
GITHUB_OAUTH_SECRET=
```

---

## Step 4 — Create the database (skip if using SQLite)

**PostgreSQL:**
```bash
psql -U postgres -c "CREATE DATABASE nile_db;"
```

**MySQL:**
```bash
mysql -u root -p -e "CREATE DATABASE nile_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
```

---

## Step 5 — Run migrations (creates all tables)
```bash
python manage.py migrate
```

---

## Step 6 — Load all data (34,500+ sales records)
```bash
python manage.py loaddata fixtures/users.json
python manage.py loaddata fixtures/initial_data.json
```

This loads all customers, products, sales, and user accounts. **Done — no ETL pipeline needed.**

---

## Step 7 — Run the server
```bash
python manage.py runserver
```

Open: **http://127.0.0.1:8000**

---

## Notes
- Login with the same credentials as the original project
- Or create a new superuser: `python manage.py createsuperuser`
- OAuth (Google/GitHub login) requires your own OAuth app credentials — leave blank if not needed
- For MySQL, also install: `pip install mysqlclient`

---

## Updating the fixtures (when data changes)
```bash
python manage.py dumpdata dashboard --natural-foreign --natural-primary --indent 2 -o fixtures/initial_data.json
python manage.py dumpdata accounts --natural-foreign --natural-primary --indent 2 -o fixtures/users.json
```

Then commit both files to git.
