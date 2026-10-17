import asyncpg
from config import DATABASE_URL

db_pool: asyncpg.Pool | None = None


def get_pool() -> asyncpg.Pool | None:
    return db_pool


async def init_db() -> bool:
    """Initialize the database connection pool and ensure tables exist."""
    global db_pool
    if not DATABASE_URL:
        print("DATABASE_URL not set, skipping DB initialization.")
        return False

    db_pool = await asyncpg.create_pool(DATABASE_URL)
    async with db_pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS user_prefs (
                chat_id BIGINT PRIMARY KEY,
                cities TEXT[],
                notification_time VARCHAR(5)
            )
        ''')
        # Add timezone column if it doesn't exist
        await conn.execute('''
            ALTER TABLE user_prefs ADD COLUMN IF NOT EXISTS timezone VARCHAR(50) DEFAULT 'UTC';
        ''')
    return True


async def close_db():
    """Close the database connection pool."""
    global db_pool
    if db_pool:
        await db_pool.close()
        db_pool = None


async def get_user(chat_id: int) -> dict:
    """Fetch user preferences from the database."""
    if not db_pool:
        return {"cities": [], "time": None, "timezone": "UTC"}
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT cities, notification_time, timezone FROM user_prefs WHERE chat_id = $1',
            chat_id,
        )
    if row:
        return {
            "cities": row['cities'] or [],
            "time": row['notification_time'],
            "timezone": row['timezone'] or 'UTC',
        }
    return {"cities": [], "time": None, "timezone": "UTC"}
