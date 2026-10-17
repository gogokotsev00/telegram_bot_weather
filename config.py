import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TELEGRAM_BOT_API_TOKEN = os.getenv('TELEGRAM_BOT_API_TOKEN')
OPEN_WEATHER_API_TOKEN = os.getenv('OPEN_WEATHER_API_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

if not TELEGRAM_BOT_API_TOKEN or not OPEN_WEATHER_API_TOKEN:
    raise ValueError(
        "API tokens missing! Please set TELEGRAM_BOT_API_TOKEN and "
        "OPEN_WEATHER_API_TOKEN environment variables or in a .env file."
    )
