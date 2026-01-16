#!/bin/bash

# Script to start FastAPI server with correct virtual environment

cd "$(dirname "$0")"

# Activate virtual environment and start server
.venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
