#!/usr/bin/env bash
# Render build script for RailCore ERP.
# Render runs this once per deploy, before starting the web process.
set -o errexit

echo "==> Installing Python dependencies"
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Collecting static files"
python manage.py collectstatic --no-input

echo "==> Applying database migrations"
python manage.py migrate --no-input

echo "==> Build finished"
