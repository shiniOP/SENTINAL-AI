# config.py

import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

PRIMARY_MODEL = "gemini-3.1-flash-lite"

FALLBACK_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-3.5-flash-lite",
]