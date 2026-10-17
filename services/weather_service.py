import httpx
from telegram.ext import ContextTypes

from config import OPEN_WEATHER_API_TOKEN
from database import get_user


async def get_weather(city: str) -> str:
    """Fetch current weather for a city from OpenWeatherMap."""
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPEN_WEATHER_API_TOKEN}&units=metric"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)

    if response.status_code == 200:
        data = response.json()
        temp = data['main']['temp']
        desc = data['weather'][0]['description'].capitalize()
        return f"🌤 <b>Today's forecast for {city}:</b>\nTemperature: {temp}°C\nConditions: {desc}"

    return f"Sorry, I couldn't find the weather data for {city}."


async def send_daily_forecast(context: ContextTypes.DEFAULT_TYPE):
    """Scheduled job callback that sends the daily weather forecast to a user."""
    chat_id = context.job.chat_id
    user = await get_user(chat_id)
    cities = user.get("cities", [])

    if not cities:
        cities = ["Berlin"]  # Default

    for city in cities:
        forecast = await get_weather(city)
        await context.bot.send_message(chat_id=chat_id, text=forecast, parse_mode="HTML")
