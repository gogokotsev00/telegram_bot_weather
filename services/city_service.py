from telegram import Update
from telegram.ext import ContextTypes

from database import get_pool, get_user


async def add_city(chat_id: int, city: str):
    """Add a city to a user's saved list in the database."""
    db_pool = get_pool()
    if not db_pool:
        return
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow('SELECT cities FROM user_prefs WHERE chat_id = $1', chat_id)
        if row:
            cities = row['cities'] or []
            if city not in cities:
                cities.append(city)
                await conn.execute('UPDATE user_prefs SET cities = $1 WHERE chat_id = $2', cities, chat_id)
        else:
            await conn.execute(
                'INSERT INTO user_prefs (chat_id, cities, timezone) VALUES ($1, $2, $3)',
                chat_id,
                [city],
                'UTC',
            )


async def remove_city(chat_id: int, city: str):
    """Remove a city from a user's saved list in the database."""
    db_pool = get_pool()
    if not db_pool:
        return
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow('SELECT cities FROM user_prefs WHERE chat_id = $1', chat_id)
        if row:
            cities = row['cities'] or []
            if city in cities:
                cities.remove(city)
                await conn.execute('UPDATE user_prefs SET cities = $1 WHERE chat_id = $2', cities, chat_id)


async def set_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler for /setcity."""
    chat_id = update.effective_chat.id

    if not context.args:
        await update.effective_message.reply_text(
            "Please provide a city. Example: <code>/setcity Berlin</code>",
            parse_mode="HTML",
        )
        return

    city = " ".join(context.args)
    await add_city(chat_id, city)

    await update.effective_message.reply_text(
        f"✅ City <b>{city}</b> successfully added to your list!",
        parse_mode="HTML",
    )


async def remove_city_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command handler for /removecity."""
    chat_id = update.effective_chat.id

    if not context.args:
        await update.effective_message.reply_text(
            "Please provide a city. Example: <code>/removecity Berlin</code>",
            parse_mode="HTML",
        )
        return

    city = " ".join(context.args)
    user = await get_user(chat_id)
    cities = user.get("cities", [])

    if city in cities:
        await remove_city(chat_id, city)
        await update.effective_message.reply_text(
            f"✅ City <b>{city}</b> successfully removed from your list!",
            parse_mode="HTML",
        )
    else:
        await update.effective_message.reply_text(
            f"❌ City <b>{city}</b> is not in your list.",
            parse_mode="HTML",
        )
