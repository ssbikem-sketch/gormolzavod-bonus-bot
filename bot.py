"""Гормолзавод бонус бағдарламасының Telegram боты."""
import asyncio
import logging
from pathlib import Path

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from admin_panel import ADMIN_BUTTONS, admin_keyboard, handle_admin_message
from config import Settings, load_settings
from database import Database

logger = logging.getLogger(__name__)
router = Router(name="gormolzavod_bonus")

REGISTER = "✅ Тіркелу"
ENTER_CODE = "✅ Код енгізу"
MY_POINTS = "✅ Менің ұпайларым"
REWARDS = "✅ Сыйлықтар"
TERMS = "✅ Акция шарттары"
CONTACT = "✅ Байланыс"
MENU_BUTTONS = {REGISTER, ENTER_CODE, MY_POINTS, REWARDS, TERMS, CONTACT}
REWARD_OPTIONS = {
    "500 ұпай ➜ 5% жеңілдік": 500,
    "1000 ұпай ➜ 10% жеңілдік": 1000,
    "2000 ұпай ➜ 15% жеңілдік": 2000,
    "5000 ұпай ➜ Тегін өнім": 5000,
    "10000 ұпай ➜ Өнімдер жиынтығы": 10000,
    "20000 ұпай ➜ Бас жүлде": 20000,
}

class CustomerStates(StatesGroup):
    waiting_for_code = State()
    choosing_reward = State()

def customer_keyboard(rewards: bool = False) -> list[list[KeyboardButton]]:
    if rewards:
        rows = [[KeyboardButton(text=name)] for name in REWARD_OPTIONS]
        rows.extend(
            [
                [KeyboardButton(text=MY_POINTS), KeyboardButton(text=TERMS)],
                [KeyboardButton(text=CONTACT), KeyboardButton(text=REGISTER)],
            ]
        )
        return rows
    return [
        [KeyboardButton(text=REGISTER), KeyboardButton(text=ENTER_CODE)],
        [KeyboardButton(text=MY_POINTS), KeyboardButton(text=REWARDS)],
        [KeyboardButton(text=TERMS), KeyboardButton(text=CONTACT)],
    ]


def main_keyboard(
    user_id: int,
    admin_ids: frozenset[int],
    rewards: bool = False,
) -> ReplyKeyboardMarkup:
    rows = customer_keyboard(rewards)
    if user_id in admin_ids:
        rows.extend(admin_keyboard())
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
async def show_start(message: Message, admin_ids: frozenset[int]) -> None:
    user_id = message.from_user.id if message.from_user else 0
    welcome = (
        "🏭 Гормолзавод Бонус Бағдарламасы\n\n"
        "Қош келдіңіз!\n\n"
        "✅ Ұпай жинаңыз\n"
        "✅ Сыйлықтар алыңыз\n"
        "✅ Қаптамадағы кодтарды тіркеңіз\n\n"
        "Өнім қаптамасындағы QR-кодты сканерлеп, Telegram ботқа кіріп, кодтарды тіркеңіз.\n\n"
        "Төмендегі мәзірден қажетті бөлімді таңдаңыз."
    )
    await message.answer(welcome, reply_markup=main_keyboard(user_id, admin_ids))

async def handle_customer_action(message: Message, state: FSMContext, database: Database,
                                admin_ids: frozenset[int], text: str) -> None:
    user = message.from_user
    if user is None:
        return
    if text == REGISTER:
        try:
            created = await database.register_customer(user.id, user.username, user.full_name or "Клиент")
            if created:
                await message.answer(
                    "✅ Сәтті тіркелдіңіз!\n\n"
                    "Сіздің бонус шотыңыз құрылды.\n\n"
                    "Енді қаптамадағы кодтарды енгізіп, ұпай жинай аласыз.",
                    reply_markup=main_keyboard(user.id, admin_ids),
                )
            else:
                await message.answer(
                    "Сіз бұрын тіркелгенсіз. Қаптамадағы кодтарды енгізіп, ұпай жинай аласыз.",
                    reply_markup=main_keyboard(user.id, admin_ids),
                )
        except Exception:
            logger.exception("Клиентті тіркеу мүмкін болмады: %s", user.id)
            await message.answer("Тіркеу кезінде қате болды. Кейінірек қайталап көріңіз.")
        return
    if text == ENTER_CODE:
        customer = await database.get_customer(user.id)
        if customer is None:
            await message.answer("Алдымен «✅ Тіркелу» бөлімін таңдаңыз.",
                                 reply_markup=main_keyboard(user.id, admin_ids))
            return
        await state.set_state(CustomerStates.waiting_for_code)
        await message.answer("Қаптамадағы бірегей кодты енгізіңіз.",
                             reply_markup=main_keyboard(user.id, admin_ids))
        return
    if text == MY_POINTS:
        customer = await database.get_customer(user.id)
        if customer is None:
            await message.answer("Алдымен «✅ Тіркелу» бөлімін таңдаңыз.",
                                 reply_markup=main_keyboard(user.id, admin_ids))
            return
        await message.answer(f"💰 Сіздің балансыңыз:\n\n{customer['balance']} ұпай",
                             reply_markup=main_keyboard(user.id, admin_ids))
        return
    if text == REWARDS:
        customer = await database.get_customer(user.id)
        if customer is None:
            await message.answer("Алдымен «✅ Тіркелу» бөлімін таңдаңыз.",
                                 reply_markup=main_keyboard(user.id, admin_ids))
            return
        rewards_text = (
            "🎁 Қолжетімді сыйлықтар\n\n"
            "500 ұпай ➜ 5% жеңілдік\n\n"
            "1000 ұпай ➜ 10% жеңілдік\n\n"
            "2000 ұпай ➜ 15% жеңілдік\n\n"
            "5000 ұпай ➜ Тегін өнім\n\n"
            "10000 ұпай ➜ Өнімдер жиынтығы\n\n"
            "20000 ұпай ➜ Бас жүлде\n\n"
            "Өтінім беру үшін төмендегі сыйлықты таңдаңыз."
        )
        await state.set_state(CustomerStates.choosing_reward)
        await message.answer(rewards_text,
                             reply_markup=main_keyboard(user.id, admin_ids, rewards=True))
        return
    if text in REWARD_OPTIONS:
        customer = await database.get_customer(user.id)
        if customer is None:
            await state.clear()
            await message.answer("Алдымен «✅ Тіркелу» бөлімін таңдаңыз.",
                                 reply_markup=main_keyboard(user.id, admin_ids))
            return
        points = REWARD_OPTIONS[text]
        try:
            accepted, current_balance = await database.create_reward_application(
                user.id, text, points
            )
            await state.clear()
            if accepted:
                await message.answer(
                    "✅ Өтінім қабылданды!\n\n"
                    "Сіздің өтініміңіз жүйеде тіркелді.\n\n"
                    "📞 Сыйлықты алу жөнінде сізбен жақын арада менеджер байланысады.",
                    reply_markup=main_keyboard(user.id, admin_ids),
                )
            else:
                await message.answer(
                    f"❌ Ұпай жеткіліксіз.\n\nҚазіргі балансыңыз: {current_balance} ұпай",
                    reply_markup=main_keyboard(user.id, admin_ids),
                )
        except Exception:
            logger.exception("Сыйлыққа өтінім беру мүмкін болмады: %s", user.id)
            await state.clear()
            await message.answer("Өтінімді тіркеу мүмкін болмады. Кейінірек қайталап көріңіз.",
                                 reply_markup=main_keyboard(user.id, admin_ids))
        return
    if text == TERMS:
        await message.answer(
            "📋 Акция шарттары\n\n"
            "1. Өнім қаптамасындағы QR-кодты сканерлеңіз.\n"
            "2. Telegram ботқа өтіңіз.\n"
            "3. Тіркеліңіз.\n"
            "4. Қаптамадағы бірегей кодты енгізіңіз.\n"
            "5. Ұпай жинаңыз.\n"
            "6. Ұпайларды сыйлықтарға айырбастаңыз.\n\n"
            "⚠️ Әр код тек бір рет қолданылады.",
            reply_markup=main_keyboard(user.id, admin_ids),
        )
        return
    if text == CONTACT:
        await message.answer(
            "📞 Байланыс\n\n"
            "Instagram: @gormolzavod\n"
            "Telegram: @gormolzavod\n\n"
            "Жұмыс уақыты:\n09:00–18:00",
            reply_markup=main_keyboard(user.id, admin_ids),
        )
        return
    current_state = await state.get_state()
    if current_state == CustomerStates.waiting_for_code.state:
        try:
            result, points = await database.redeem_bonus_code(user.id, text)
            if result == "used":
                await state.clear()
                await message.answer(
                    "⚠️ Бұл код бұрын қолданылған.",
                    reply_markup=main_keyboard(user.id, admin_ids),
                )
                return
            if result == "invalid" or points is None:
                await message.answer("❌ Қате код.\nҚайта тексеріп көріңіз.",
                                     reply_markup=main_keyboard(user.id, admin_ids))
                return
            customer = await database.get_customer(user.id)
            balance = int(customer["balance"]) if customer else 0
            await state.clear()
            await message.answer(
                f"✅ Код қабылданды!\n🎉 Сізге {points} ұпай есептелді.\n\n"
                f"💰 Жалпы балансыңыз: {balance} ұпай",
                reply_markup=main_keyboard(user.id, admin_ids),
            )
        except Exception:
            logger.exception("Бонус кодын өңдеу мүмкін болмады: %s", user.id)
            await message.answer("Кодты тексеру мүмкін болмады. Кейінірек қайталап көріңіз.")
        return
    if current_state == CustomerStates.choosing_reward.state:
        await message.answer("Төмендегі мәзірден сыйлықты таңдаңыз.",
                             reply_markup=main_keyboard(user.id, admin_ids, rewards=True))
        return
    await message.answer("Төмендегі мәзірден қажетті бөлімді таңдаңыз.",
                         reply_markup=main_keyboard(user.id, admin_ids))

@router.message()
async def all_messages(message: Message, state: FSMContext, database: Database,
                       admin_ids: frozenset[int]) -> None:
    text = (message.text or "").strip()
    if text.startswith("/start"):
        await state.clear()
        await show_start(message, admin_ids)
        return
    if not text:
        user_id = message.from_user.id if message.from_user else 0
        await message.answer("Мәтіндік хабарлама жіберіңіз немесе мәзірден бөлімді таңдаңыз.",
                             reply_markup=main_keyboard(user_id, admin_ids))
        return
    try:
        if await handle_admin_message(message, state, database, admin_ids):
            return
        if message.from_user and (await state.get_state()) == CustomerStates.waiting_for_code.state:
            if text in MENU_BUTTONS or text in ADMIN_BUTTONS:
                await state.clear()
            else:
                await handle_customer_action(message, state, database, admin_ids, text)
                return
        if message.from_user and (await state.get_state()) == CustomerStates.choosing_reward.state:
            if text in MENU_BUTTONS or text in ADMIN_BUTTONS:
                await state.clear()
            else:
                await handle_customer_action(message, state, database, admin_ids, text)
                return
        await handle_customer_action(message, state, database, admin_ids, text)
    except Exception:
        logger.exception("Хабарламаны өңдеу кезінде күтпеген қате")
        user_id = message.from_user.id if message.from_user else 0
        await message.answer("Әрекетті орындау мүмкін болмады. Қайталап көріңіз.",
                             reply_markup=main_keyboard(user_id, admin_ids))

async def run_bot(settings: Settings) -> None:
    database = Database(settings.database_path)
    await database.initialize()
    bot = Bot(settings.bot_token, default=DefaultBotProperties())
    dispatcher = Dispatcher()
    dispatcher["database"] = database
    dispatcher["admin_ids"] = settings.admin_ids
    dispatcher.include_router(router)
    try:
        logger.info("Бонус боты іске қосылды")
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await database.close()
        await bot.session.close()
        logger.info("Бонус боты тоқтады")

def main() -> None:
    try:
        settings = load_settings()
    except (RuntimeError, ValueError) as error:
        logging.basicConfig(level=logging.ERROR)
        logging.getLogger(__name__).error("Баптаулар қатесі: %s", error)
        raise SystemExit(1) from error
    logging.basicConfig(level=settings.log_level,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(run_bot(settings))
    except KeyboardInterrupt:
        logger.info("Ботты тоқтату сигналы алынды")

if __name__ == "__main__":
    main()
ы