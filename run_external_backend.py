#!/usr/bin/env python3
"""
Simple CORS-enabled backend for external access
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import the main app
from api.server import app as main_app

# Create a new app with explicit CORS
app = FastAPI(title="CUA External Access API")

# Add CORS middleware with explicit settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Mount the main app
app.mount("/", main_app)

if __name__ == "__main__":
    print("Starting CORS-enabled CUA backend...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )