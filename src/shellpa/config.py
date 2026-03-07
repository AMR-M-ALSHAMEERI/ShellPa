import os
from dotenv import load_dotenv

def load_config():
    """Load config from .env file into environment variables."""
    # This will load .env from the current working directory, 
    # ensuring litellm will find the OPENAI_API_KEY or GEMINI_API_KEY.
    load_dotenv()
