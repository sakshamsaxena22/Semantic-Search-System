import os

class Config:
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    DATA_DIR = "backend/data"