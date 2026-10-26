"""SQLite қоймасы: қазақша бонус ботының клиенттері, кодтары және сыйлық өтінімдері."""
import logging
import secrets
import string
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.database_path) as db:
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("PRAGMA foreign_keys=ON")
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS customers (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT NOT NULL,
                    balance INTEGER NOT NULL DEFAULT 0 CHECK(balance >= 0),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS bonus_codes (
                    code TEXT PRIMARY KEY COLLATE NOCASE,
                    amount INTEGER NOT NULL CHECK(amount > 0),
                    created_by INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    used_by INTEGER UNIQUE,
                    used_at TEXT,
                    FOREIGN KEY(used_by) REFERENCES customers(telegram_id)
                );
                CREATE TABLE IF NOT EXISTS bonus_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL,
                    code TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(telegram_id) REFERENCES customers(telegram_id),
                    FOREIGN KEY(code) REFERENCES bonus_codes(code)
                );
                CREATE TABLE IF NOT EXISTS reward_applications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER NOT NULL,
                    reward_name TEXT NOT NULL,
                    points_spent INTEGER NOT NULL CHECK(points_spent > 0),
                    status TEXT NOT NULL DEFAULT 'Жаңа өтінім',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(telegram_id) REFERENCES customers(telegram_id)
                );
                CREATE INDEX IF NOT EXISTS idx_transactions_customer
                    ON bonus_transactions(telegram_id);
                CREATE INDEX IF NOT EXISTS idx_applications_customer
                    ON reward_applications(telegram_id);
            """)
            await db.commit()
        logger.info("SQLite қоймасы дайын: %s", self.database_path)

    async def register_customer(self, telegram_id: int, username: str | None,
                                full_name: str) -> bool:
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                "INSERT OR IGNORE INTO customers(telegram_id, username, full_name) VALUES(?, ?, ?)",
                (telegram_id, username, full_name),
            )
            created = cursor.rowcount == 1
            if not created:
                await db.execute(
                    "UPDATE customers SET username=?, full_name=? WHERE telegram_id=?",
                    (username, full_name, telegram_id),
                )
            await db.commit()
            return created

    async def get_customer(self, telegram_id: int) -> dict[str, object] | None:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT telegram_id, username, full_name, balance, created_at "
                "FROM customers WHERE telegram_id=?", (telegram_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def create_bonus_code(self, amount: int, created_by: int) -> str:
        if not 1 <= amount <= 1_000_000:
            raise ValueError("Ұпай мөлшері 1 мен 1 000 000 аралығында болуы керек")
        alphabet = string.ascii_uppercase + string.digits
        async with aiosqlite.connect(self.database_path) as db:
            for _ in range(10):
                code = "GORMOL-" + "".join(secrets.choice(alphabet) for _ in range(10))
                try:
                    await db.execute(
                        "INSERT INTO bonus_codes(code, amount, created_by) VALUES(?, ?, ?)",
                        (code, amount, created_by),
                    )
                    await db.commit()
                    logger.info("Әкімші %s жаңа код жасады", created_by)
                    return code
                except aiosqlite.IntegrityError:
                    continue
        raise RuntimeError("Бірегей код жасау мүмкін болмады")

    async def redeem_bonus_code(self, telegram_id: int, submitted_code: str) -> tuple[str, int | None]:
        code = submitted_code.strip().upper()
        if not code or len(code) > 64:
            return "invalid", None
        async with aiosqlite.connect(self.database_path, timeout=15) as db:
            try:
                await db.execute("BEGIN IMMEDIATE")
                cursor = await db.execute(
                    "SELECT amount, used_by FROM bonus_codes WHERE code=? COLLATE NOCASE", (code,)
                )
                row = await cursor.fetchone()
                if row is None:
                    await db.rollback()
                    return "invalid", None
                if row[1] is not None:
                    await db.rollback()
                    return "used", None
                amount = int(row[0])
                cursor = await db.execute(
                    "UPDATE bonus_codes SET used_by=?, used_at=CURRENT_TIMESTAMP "
                    "WHERE code=? COLLATE NOCASE AND used_by IS NULL", (telegram_id, code),
                )
                if cursor.rowcount != 1:
                    await db.rollback()
                    return "used", None
                await db.execute(
                    "UPDATE customers SET balance=balance+? WHERE telegram_id=?",
                    (amount, telegram_id),
                )
                cursor = await db.execute("SELECT changes()")
                if int((await cursor.fetchone())[0]) != 1:
                    raise RuntimeError("Тіркелмеген клиентке ұпай беру әрекеті")
                await db.execute(
                    "INSERT INTO bonus_transactions(telegram_id, amount, code) VALUES(?, ?, ?)",
                    (telegram_id, amount, code),
                )
                await db.commit()
                logger.info("%s клиентіне %s ұпай есептелді", telegram_id, amount)
                return "accepted", amount
            except Exception:
                await db.rollback()
                raise

    async def create_reward_application(self, telegram_id: int, reward_name: str,
                                        points: int) -> tuple[bool, int]:
        if not 1 <= points <= 1_000_000:
            raise ValueError("Сыйлық ұпайы жарамсыз")
        async with aiosqlite.connect(self.database_path, timeout=15) as db:
            try:
                await db.execute("BEGIN IMMEDIATE")
                cursor = await db.execute(
                    "SELECT balance FROM customers WHERE telegram_id=?", (telegram_id,)
                )
                row = await cursor.fetchone()
                if row is None:
                    await db.rollback()
                    raise RuntimeError("Клиент тіркелмеген")
                balance = int(row[0])
                if balance < points:
                    await db.rollback()
                    return False, balance
                cursor = await db.execute(
                    "UPDATE customers SET balance=balance-? WHERE telegram_id=? AND balance>=?",
                    (points, telegram_id, points),
                )
                if cursor.rowcount != 1:
                    await db.rollback()
                    return False, balance
                await db.execute(
                    "INSERT INTO reward_applications(telegram_id, reward_name, points_spent) "
                    "VALUES(?, ?, ?)", (telegram_id, reward_name, points),
                )
                await db.commit()
                logger.info("Клиент %s %s сыйлығына өтінім берді", telegram_id, reward_name)
                return True, balance - points
            except Exception:
                await db.rollback()
                raise

    async def get_statistics(self) -> dict[str, int]:
        async with aiosqlite.connect(self.database_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*), COALESCE(SUM(balance), 0) FROM customers"
            )
            customers, balance = await cursor.fetchone()
            cursor = await db.execute("SELECT COUNT(*) FROM bonus_transactions")
            transaction_count = (await cursor.fetchone())[0]
            cursor = await db.execute("SELECT COALESCE(SUM(amount), 0) FROM bonus_transactions")
            total_awarded = (await cursor.fetchone())[0]
            cursor = await db.execute(
                "SELECT COUNT(*) FROM bonus_codes WHERE used_by IS NULL"
            )
            active_codes = (await cursor.fetchone())[0]
            cursor = await db.execute(
                "SELECT COUNT(*) FROM reward_applications WHERE status='Жаңа өтінім'"
            )
            pending_applications = (await cursor.fetchone())[0]
            return {
                "customers": int(customers), "total_balance": int(balance),
                "transactions": int(transaction_count), "total_awarded": int(total_awarded),
                "active_codes": int(active_codes),
                "pending_applications": int(pending_applications),
            }

    async def get_reward_applications(self, limit: int = 30) -> list[dict[str, object]]:
        async with aiosqlite.connect(self.database_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT r.id, r.telegram_id, c.full_name, c.username, r.reward_name, "
                "r.points_spent, r.status, r.created_at FROM reward_applications AS r "
                "JOIN customers AS c ON c.telegram_id=r.telegram_id "
                "ORDER BY r.id DESC LIMIT ?", (limit,),
            )
            return [dict(row) for row in await cursor.fetchall()]

    async def close(self) -> None:
        """Әр сұрау жеке SQLite байланысын ашады және жабады."""
