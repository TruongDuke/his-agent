"""Entry point — load .env rồi chạy FastAPI server."""

import os
from dotenv import load_dotenv

load_dotenv()

import uvicorn
from api import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
