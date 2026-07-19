import datetime
import os
import httpx
import asyncpg
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

TELEGRAM_BOT_API_TOKEN = os.getenv('TELEGRAM_BOT_API_TOKEN')
OPEN_WEATHER_API_TOKEN = os.getenv('OPEN_WEATHER_API_TOKEN')
DATABASE_URL = os.getenv('DATABASE_URL')

if not TELEGRAM_BOT_API_TOKEN or not OPEN_WEATHER_API_TOKEN:
    raise ValueError("API tokens missing! Please set TELEGRAM_BOT_API_TOKEN and OPEN_WEATHER_API_TOKEN environment variables or in a .env file.")

db_pool = None

async def post_init(app: Application):
    global db_pool
    if DATABASE_URL:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
        async with db_pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_prefs (
                    chat_id BIGINT PRIMARY KEY,
                    cities TEXT[],
                    notification_time VARCHAR(5)
                )
            ''')
        await restore_jobs(app)
    else:
        print("DATABASE_URL not set, skipping DB initialization.")

async def post_shutdown(app: Application):
    global db_pool
    if db_pool:
        await db_pool.close()

# --- Database Logic ---
async def get_user(chat_id):
    if not db_pool:
        return {"cities": [], "time": None}
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow('SELECT cities, notification_time FROM user_prefs WHERE chat_id = $1', chat_id)
    if row:
        return {"cities": row['cities'] or [], "time": row['notification_time']}
    return {"cities": [], "time": None}

async def add_city(chat_id, city):
    if not db_pool: return
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow('SELECT cities FROM user_prefs WHERE chat_id = $1', chat_id)
        if row:
            cities = row['cities'] or []
            if city not in cities:
                cities.append(city)
                await conn.execute('UPDATE user_prefs SET cities = $1 WHERE chat_id = $2', cities, chat_id)
        else:
            await conn.execute('INSERT INTO user_prefs (chat_id, cities) VALUES ($1, $2)', chat_id, [city])

async def set_user_time(chat_id, time_str):
    if not db_pool: return
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow('SELECT 1 FROM user_prefs WHERE chat_id = $1', chat_id)
        if row:
            await conn.execute('UPDATE user_prefs SET notification_time = $1 WHERE chat_id = $2', time_str, chat_id)
        else:
            await conn.execute('INSERT INTO user_prefs (chat_id, cities, notification_time) VALUES ($1, $2, $3)', chat_id, [], time_str)

# --- Weather Fetching Logic ---
async def get_weather(city: str) -> str:
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPEN_WEATHER_API_TOKEN}&units=metric"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
    
    if response.status_code == 200:
        data = response.json()
        temp = data['main']['temp']
        desc = data['weather'][0]['description'].capitalize()
        return f"🌤 <b>Today's forecast for {city}:</b>\nTemperature: {temp}°C\nConditions: {desc}"
    
    return f"Sorry, I couldn't find the weather data for {city}."

# --- Scheduled Job ---
async def send_daily_forecast(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.chat_id
    user = await get_user(chat_id)
    cities = user.get("cities", []) 
    
    if not cities:
        cities = ["Berlin"] # Default
        
    for city in cities:
        forecast = await get_weather(city)
        await context.bot.send_message(chat_id=chat_id, text=forecast, parse_mode="HTML")

# --- Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "Hello! I can send you daily weather forecasts. 🌍\n\n"
        "1. Add a city: <code>/setcity &lt;City&gt;</code> (You can add multiple)\n"
        "2. Set your time (UTC): <code>/settime &lt;HH:MM&gt;</code>\n"
        "3. Show selection: <code>/showSelected</code>"
    )
    await update.effective_message.reply_text(welcome_message, parse_mode="HTML")

async def set_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not context.args:
        await update.effective_message.reply_text("Please provide a city. Example: <code>/setcity Berlin</code>", parse_mode="HTML")
        return
    
    city = " ".join(context.args)
    await add_city(chat_id, city)
    
    await update.effective_message.reply_text(f"✅ City <b>{city}</b> successfully added to your list!", parse_mode="HTML")

async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    
    if not context.args:
        await update.effective_message.reply_text("Please provide a time in HH:MM format (UTC). Example: <code>/settime 08:30</code>", parse_mode="HTML")
        return
    
    time_str = context.args[0]
    user = await get_user(chat_id)
    
    # Ensure they have set at least one city first
    if not user.get("cities"):
        await update.effective_message.reply_text("Please set a city first using <code>/setcity &lt;City&gt;</code>.", parse_mode="HTML")
        return

    try:
        hour, minute = map(int, time_str.split(':'))
        t = datetime.time(hour=hour, minute=minute, tzinfo=datetime.timezone.utc)
        
        # Remove any existing scheduled jobs for this user
        current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
        for job in current_jobs:
            job.schedule_removal()

        # Schedule the new daily job
        context.job_queue.run_daily(
            send_daily_forecast, 
            time=t, 
            chat_id=chat_id, 
            name=str(chat_id)
        )
        
        await set_user_time(chat_id, time_str)
        
        cities_str = ", ".join(user["cities"])
        await update.effective_message.reply_text(f"⏰ All set! I will send the daily forecast for <b>{cities_str}</b> at <b>{time_str} UTC</b>.", parse_mode="HTML")
        
    except ValueError:
        await update.effective_message.reply_text("❌ Invalid time format. Please use HH:MM (e.g., 14:00).")

async def show_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = await get_user(chat_id)
    
    cities = user.get("cities", [])
    cities_str = ", ".join(cities) if cities else "Not set"
    time_str = user.get("time") or "Not set"
    
    message = (
        "📌 <b>Your Current Selection:</b>\n"
        f"🏙 <b>Cities:</b> {cities_str}\n"
        f"⏰ <b>Time (UTC):</b> {time_str}"
    )
    await update.effective_message.reply_text(message, parse_mode="HTML")

# Log errors
async def log_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f'Update {update} caused error {context.error}')

# --- Main Application Setup ---
async def restore_jobs(app: Application):
    if not db_pool:
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch('SELECT chat_id, notification_time FROM user_prefs WHERE notification_time IS NOT NULL')
    
    for row in rows:
        chat_id = row['chat_id']
        time_str = row['notification_time']
        try:
            hour, minute = map(int, time_str.split(':'))
            t = datetime.time(hour=hour, minute=minute, tzinfo=datetime.timezone.utc)
            app.job_queue.run_daily(
                send_daily_forecast, 
                time=t, 
                chat_id=chat_id, 
                name=str(chat_id)
            )
        except Exception as e:
            print(f"Failed to restore job for {chat_id}: {e}")

def main():
    # Configure robust connection timeouts and pool sizes to prevent ConnectError
    request = HTTPXRequest(connection_pool_size=8, read_timeout=30.0, write_timeout=30.0, connect_timeout=30.0, pool_timeout=10.0)
    get_updates_request = HTTPXRequest(connection_pool_size=1, read_timeout=50.0, write_timeout=50.0, connect_timeout=30.0, pool_timeout=10.0)

    # Build the application
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_API_TOKEN)
        .request(request)
        .get_updates_request(get_updates_request)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setcity", set_city))
    app.add_handler(CommandHandler("settime", set_time))
    app.add_handler(CommandHandler(["showselected", "showSelected"], show_selected))
    
    # Register error handler
    app.add_error_handler(log_error)

    # Start the bot (drop_pending_updates ignores lingering connections from restarted instances)
    print("Bot is starting...")
    app.run_polling(poll_interval=2, drop_pending_updates=True)

if __name__ == "__main__":
    main()