from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.request import HTTPXRequest

from config import TELEGRAM_BOT_API_TOKEN
from database import close_db, get_user, init_db
from services.city_service import remove_city_handler, set_city
from services.time_service import restore_jobs, set_time


async def post_init(app: Application):
    if await init_db():
        await restore_jobs(app)


async def post_shutdown(app: Application):
    await close_db()


# --- General Command Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "Hello! I can send you daily weather forecasts. 🌍\n\n"
        "1. Add a city: <code>/setcity &lt;City&gt;</code> (You can add multiple)\n"
        "2. Remove a city: <code>/removecity &lt;City&gt;</code>\n"
        "3. Set you notification time and timezone: <code>/settime &lt;HH:MM&gt; &lt;Timezone/Offset&gt;</code> (e.g. /settime 08:30 Europe/Berlin or /settime 08:30 +02:00)\n"
        "4. Show selection: <code>/showSelected</code>"
    )
    await update.effective_message.reply_text(welcome_message, parse_mode="HTML")


async def show_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = await get_user(chat_id)

    cities = user.get("cities", [])
    cities_str = ", ".join(cities) if cities else "Not set"
    time_str = user.get("time") or "Not set"
    tz_str = user.get("timezone") or "UTC"

    message = (
        "📌 <b>Your Current Selection:</b>\n"
        f"🏙 <b>Cities:</b> {cities_str}\n"
        f"⏰ <b>Notification Time:</b> {time_str} ({tz_str})"
    )
    await update.effective_message.reply_text(message, parse_mode="HTML")


# Log errors
async def log_error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f'Update {update} caused error {context.error}')


# --- Main Application Setup ---
def main():
    # Configure robust connection timeouts and pool sizes to prevent ConnectError
    request = HTTPXRequest(
        connection_pool_size=8,
        read_timeout=30.0,
        write_timeout=30.0,
        connect_timeout=30.0,
        pool_timeout=10.0,
    )
    get_updates_request = HTTPXRequest(
        connection_pool_size=1,
        read_timeout=50.0,
        write_timeout=50.0,
        connect_timeout=30.0,
        pool_timeout=10.0,
    )

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
    app.add_handler(CommandHandler("removecity", remove_city_handler))
    app.add_handler(CommandHandler("settime", set_time))
    app.add_handler(CommandHandler(["showselected", "showSelected"], show_selected))

    # Register error handler
    app.add_error_handler(log_error)

    # Start the bot (drop_pending_updates ignores lingering connections from restarted instances)
    print("Bot is starting...")
    app.run_polling(poll_interval=2, drop_pending_updates=True)


if __name__ == "__main__":
    main()