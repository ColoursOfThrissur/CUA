#!/usr/bin/env python3
"""
Minimal CORS test server
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

# Add CORS - allow everything
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/test")
async def test():
    return {"message": "CORS test successful", "origin": "allowed"}

@app.get("/health")
async def health():
    return {"status": "healthy", "cors": "enabled"}

if __name__ == "__main__":
    print("Starting CORS test server on port 8002...")
    uvicorn.run(app, host="0.0.0.0", port=8002)