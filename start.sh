#!/bin/bash

# Install dependencies if not already installed
pip install --upgrade pip
pip install -r requirements.txt

# Try to start with gunicorn, fall back to python if not available
if command -v gunicorn &> /dev/null; then
    echo "Starting with gunicorn..."
    gunicorn --bind 0.0.0.0:$PORT app:app
else
    echo "Gunicorn not found, starting with python..."
    python app.py
fi 