import os
import django
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
os.environ["DEBUG"] = "True"
django.setup()
from django.test import Client
from django.contrib.auth import get_user_model

# Create a test client
c = Client()
User = get_user_model()

# Login or create user
user, created = User.objects.get_or_create(username='admin')
if created:
    user.set_password('admin123')
    user.save()
c.force_login(user)

# 1. Test normal page load
response = c.get('/')
print(f"Normal load status: {response.status_code}")

# 2. Test HTMX page load with filters
headers = {'HTTP_HX_REQUEST': 'true'}
response = c.get('/?country=All&category=Electronics&start_date=2024-01-01&end_date=2024-12-31', **headers)
print(f"HTMX filter load status: {response.status_code}")
if response.status_code == 200:
    print("HTMX load returned OK. Snippet:")
    print(response.content.decode('utf-8')[:500])
else:
    print("Error in HTMX load:")
    print(response.content)
