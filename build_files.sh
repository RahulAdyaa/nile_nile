#!/bin/bash

# Exit on error
set -o errexit

pip install -r requirements.txt

# Build Tailwind CSS
python manage.py tailwind build

# Collect static files
python manage.py collectstatic --noinput

# Create necessary directories
mkdir -p media/uploads media/reports media/server_datasets
mkdir -p data
mkdir -p staticfiles

# Run migrations
python manage.py migrate
