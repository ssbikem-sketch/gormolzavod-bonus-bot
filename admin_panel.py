"""Әкімші Reply Keyboard мәзірі: кодтар, статистика және сыйлық өтінімдері."""
import logging
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import KeyboardButton, Message
from database import Database

logger = logging.getLogger(__name__)
CREATE_CODE = "➕ Код жасау"
VIEW_USERS = "👥 Пайдаланушылар саны"
VIEW_STATS = "📊 Статистика"
VIEW_APPLICATIONS = "📋 Өтінімдер"
ADMIN_BUTTONS = {CREATE_CODE, VIEW_USERS, VIEW_STATS, VIEW_APPLICATIONS}

class AdminStates(StatesGroup):
    waiting_for_points = State()

async def handle_admin_message(message: Message, state: FSMContext, database: Database,
                               admin_ids: frozenset[int]) -> bool:
    """Әкімші хабарын өңдейді; әкімшіге қатысы болмаса False қайтарады."""
    user = message.from_user
    if user is None or user.id not in admin_ids:
        return False
    text = (message.text or "").strip()
    current_state = await state.get_state()
    if current_state == AdminStates.waiting_for_points.state:
        if text in ADMIN_BUTTONS:
            await state.clear()
        else:
            try:
                points = int(text)
                if not 1 <= points <= 1_000_000:
                    raise ValueError
            except ValueError:
                await message.answer("1 мен 1 000 000 аралығындағы бүтін ұпай санын енгізіңіз.")
                return True
            try:
                code = await database.create_bonus_code(points, user.id)
                await state.clear()
                await message.answer(
                    f"✅ Код жасалды: {code}\nКодты енгізген клиентке {points} ұпай беріледі."
                )
            except Exception:
                logger.exception("Әкімші коды жасалмады")
                await state.clear()
                await message.answer("Код жасау мүмкін болмады. Қайталап көріңіз.")
            return True
    if text == CREATE_CODE:
        await state.set_state(AdminStates.waiting_for_points)
        await message.answer("Кодқа берілетін ұпай санын жіберіңіз. Мысалы: 50")
        return True
    if text == VIEW_USERS:
        try:
            stats = await database.get_statistics()
            await message.answer(f"👥 Тіркелген пайдаланушылар саны: {stats['customers']}")
        except Exception:
            logger.exception("Клиенттер санын алу мүмкін болмады")
            await message.answer("Пайдаланушылар санын алу мүмкін болмады.")
        return True
    if text == VIEW_STATS:
        try:
            stats = await database.get_statistics()
            await message.answer(
                "📊 Статистика\n\n"
                f"Жалпы есептелген ұпай: {stats['total_awarded']}\n"
                f"Қолданыстағы клиент ұпайлары: {stats['total_balance']}\n"
                f"Қолданылған кодтар: {stats['transactions']}\n"
                f"Белсенді кодтар: {stats['active_codes']}\n"
                f"Жаңа сыйлық өтінімдері: {stats['pending_applications']}"
            )
        except Exception:
            logger.exception("Ұпай статистикасын алу мүмкін болмады")
            await message.answer("Статистиканы алу мүмкін болмады.")
        return True
    if text == VIEW_APPLICATIONS:
        try:
            applications = await database.get_reward_applications()
            if not applications:
                await message.answer("Сыйлыққа өтінімдер әзірге жоқ.")
                return True
            lines = ["📋 Сыйлық өтінімдері:"]
            for item in applications:
                username = f"@{item['username']}" if item["username"] else "жоқ"
                lines.append(
                    f"\n№{item['id']} · {item['full_name']} · {username}\n"
                    f"ID: {item['telegram_id']} · {item['reward_name']} · "
                    f"{item['points_spent']} ұпай · {item['status']} · {item['created_at']}"
                )
            await message.answer("\n".join(lines))
        except Exception:
            logger.exception("Сыйлық өтінімдерін оқу мүмкін болмады")
            await message.answer("Өтінімдерді алу мүмкін болмады.")
        return True
    return False

def admin_keyboard() -> list[list[KeyboardButton]]:
    return [
        [KeyboardButton(text=CREATE_CODE), KeyboardButton(text=VIEW_USERS)],
        [KeyboardButton(text=VIEW_STATS), KeyboardButton(text=VIEW_APPLICATIONS)],
    ]
