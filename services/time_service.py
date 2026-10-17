import datetime
import pytz
from telegram import Update
from telegram.ext import Application, ContextTypes

from database import get_pool, get_user
from services.weather_service import send_daily_forecast


def parse_timezone(tz_str: str) -> datetime.tzinfo | None:
    """Parse a timezone name (e.g. Europe/Berlin) or UTC offset (e.g. +02:00)."""
    if not tz_str:
        return datetime.timezone.utc
    try:
        return pytz.timezone(tz_str)
    except pytz.UnknownTimeZoneError:
        pass

    if tz_str.startswith('+') or tz_str.startswith('-'):
        try:
            sign = 1 if tz_str.startswith('+') else -1
            tz_val = tz_str[1:]
            if ':' in tz_val:
                hours, minutes = map(int, tz_val.split(':'))
            elif len(tz_val) == 4:
                hours, minutes = int(tz_val[:2]), int(tz_val[2:])
            else:
                hours = int(tz_val)
                minutes = 0
            return datetime.timezone(datetime.timedelta(hours=hours * sign, minutes=minutes * sign))
        except ValueError:
            pass

    return None


async def set_user_time(chat_id: int, time_str: str, timezone_str: str):
    """Save a user's notification time and timezone in the database."""
    db_pool = get_pool()
    if not db_pool:
        return
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow('SELECT 1 FROM user_prefs WHERE chat_id = $1', chat_id)
        if row:
            await conn.execute(
                'UPDATE user_prefs SET notification_time = $1, timezone = $2 WHERE chat_id = $3',
                time_str,
                timezone_str,
                chat_id,
            )
        else:
            await conn.execute(
                'INSERT INTO user_prefs (chat_id, cities, notification_time, timezone) VALUES ($1, $2, $3, $4)',
                chat_id,
                [],
                time_str,
                timezone_str,
            )


async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler for /settime."""
    chat_id = update.effective_chat.id

    if len(context.args) < 2:
        await update.effective_message.reply_text(
            "Please provide a time and your timezone. Example: <code>/settime 08:30 Europe/Berlin</code> or <code>/settime 08:30 +02:00</code>",
            parse_mode="HTML",
        )
        return

    time_str = context.args[0]
    tz_input = context.args[1]

    tz = parse_timezone(tz_input)
    if not tz:
        await update.effective_message.reply_text(
            "❌ Unknown timezone format. Please use a region (e.g. <code>Europe/Berlin</code>) or an offset (e.g. <code>+02:00</code>).",
            parse_mode="HTML",
        )
        return

    user = await get_user(chat_id)

    # Ensure they have set at least one city first
    if not user.get("cities"):
        await update.effective_message.reply_text(
            "Please set a city first using <code>/setcity &lt;City&gt;</code>.",
            parse_mode="HTML",
        )
        return

    try:
        hour, minute = map(int, time_str.split(':'))
        t = datetime.time(hour=hour, minute=minute, tzinfo=tz)

        # Remove any existing scheduled jobs for this user
        current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
        for job in current_jobs:
            job.schedule_removal()

        # Schedule the new daily job
        context.job_queue.run_daily(
            send_daily_forecast,
            time=t,
            chat_id=chat_id,
            name=str(chat_id),
        )

        await set_user_time(chat_id, time_str, tz_input)

        cities_str = ", ".join(user["cities"])
        await update.effective_message.reply_text(
            f"⏰ All set! I will send the daily forecast for <b>{cities_str}</b> at <b>{time_str} ({tz_input})</b>.",
            parse_mode="HTML",
        )

    except ValueError:
        await update.effective_message.reply_text(
            "❌ Invalid time format. Please use HH:MM (e.g., 14:00)."
        )


async def restore_jobs(app: Application):
    """Restore scheduled daily forecast jobs from the database on startup."""
    db_pool = get_pool()
    if not db_pool:
        return
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            'SELECT chat_id, notification_time, timezone FROM user_prefs WHERE notification_time IS NOT NULL'
        )

    for row in rows:
        chat_id = row['chat_id']
        time_str = row['notification_time']
        tz_str = row.get('timezone') or 'UTC'

        tz = parse_timezone(tz_str)
        if not tz:
            tz = datetime.timezone.utc

        try:
            hour, minute = map(int, time_str.split(':'))
            t = datetime.time(hour=hour, minute=minute, tzinfo=tz)
            app.job_queue.run_daily(
                send_daily_forecast,
                time=t,
                chat_id=chat_id,
                name=str(chat_id),
            )
        except Exception as e:
            print(f"Failed to restore job for {chat_id}: {e}")
