import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties # <--- ВАЖНЫЙ ИМПОРТ

# --- КОНФИГУРАЦИЯ ---
TOKEN = "8315937988:AAHaKhMNy0t-uXQjSumvkDk3nf2vyTHf63U"  # Вставьте токен

# --- НАСТРОЙКА ЛОГОВ И БОТА ---
logging.basicConfig(level=logging.INFO)

# --- ИСПРАВЛЕНИЕ ЗДЕСЬ ---
# Теперь настройки передаются через DefaultBotProperties
bot = Bot(
    token=TOKEN, 
    default=DefaultBotProperties(parse_mode="HTML")
)

dp = Dispatcher(storage=MemoryStorage())

# --- БАЗА ДАННЫХ (Временная, в памяти) ---
user_db = {}  # Формат: {user_id: {'balance': 100.0}}

# --- МАШИНА СОСТОЯНИЙ ---
class GameState(StatesGroup):
    choosing_game = State()
    waiting_for_bet = State()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def get_user(user_id):
    if user_id not in user_db:
        user_db[user_id] = {'balance': 10.0} # Стартовый бонус 10$
    return user_db[user_id]

def format_balance(amount):
    return f"<b>{amount:.2f}$</b>"

# --- КЛАВИАТУРЫ ---
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Кубик", callback_data="game_dice"),
         InlineKeyboardButton(text="🏀 Баскет", callback_data="game_basketball")],
        [InlineKeyboardButton(text="🎯 Дартс", callback_data="game_darts"),
         InlineKeyboardButton(text="🎳 Боулинг", callback_data="game_bowling")],
        [InlineKeyboardButton(text="🎰 Слоты (777)", callback_data="game_slot")],
        [InlineKeyboardButton(text="💳 Мой баланс", callback_data="balance")]
    ])

def back_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="menu")]
    ])

# --- ХЕНДЛЕРЫ (ОБРАБОТЧИКИ) ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user = get_user(message.from_user.id)
    text = (
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        f"Добро пожаловать в <b>Emoji Casino</b>.\n"
        f"Твой стартовый баланс: {format_balance(user['balance'])}\n\n"
        f"👇 <i>Выбери игру ниже:</i>"
    )
    await message.answer(text, reply_markup=main_menu_kb())

@dp.callback_query(F.data == "menu")
async def cb_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = get_user(callback.from_user.id)
    text = f"🏰 <b>Главное меню</b>\n💰 Баланс: {format_balance(user['balance'])}"
    await callback.message.edit_text(text, reply_markup=main_menu_kb())

@dp.callback_query(F.data == "balance")
async def cb_balance(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    await callback.answer(f"💰 Твой баланс: {user['balance']:.2f}$", show_alert=True)

# --- ЛОГИКА ВЫБОРА ИГРЫ ---
@dp.callback_query(F.data.startswith("game_"))
async def cb_game_select(callback: CallbackQuery, state: FSMContext):
    game_type = callback.data.split("_")[1]
    
    # Сохраняем выбранную игру в память
    await state.update_data(game_type=game_type)
    await state.set_state(GameState.waiting_for_bet)
    
    emoji_map = {
        "dice": "🎲", "basketball": "🏀", "darts": "🎯", "bowling": "🎳", "slot": "🎰"
    }
    
    user = get_user(callback.from_user.id)
    
    text = (
        f"{emoji_map[game_type]} <b>Игра: {game_type.upper()}</b>\n\n"
        f"💰 Твой баланс: {format_balance(user['balance'])}\n"
        f"💵 <b>Введите сумму ставки</b> (например: 0.5 или 5):"
    )
    
    await callback.message.edit_text(text, reply_markup=back_kb())

# --- ЛОГИКА ОБРАБОТКИ СТАВКИ И ИГРЫ ---
@dp.message(GameState.waiting_for_bet)
async def process_bet(message: Message, state: FSMContext):
    # Проверка на текст (чтобы не падало, если пришлют стикер)
    if not message.text:
        await message.answer("⚠️ Пожалуйста, введите число.")
        return

    try:
        bet = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("⚠️ <b>Ошибка!</b> Введите число. Например: 1.5")
        return

    user = get_user(message.from_user.id)
    
    # Проверки
    if bet < 0.1:
        await message.answer("⚠️ Минимальная ставка: <b>0.1$</b>")
        return
    if bet > user['balance']:
        await message.answer(f"⚠️ Недостаточно средств!\nВаш баланс: {format_balance(user['balance'])}")
        return

    # Списываем ставку
    user['balance'] -= bet
    data = await state.get_data()
    game_type = data.get("game_type")
    
    await message.answer(f"💸 Ставка <b>{bet}$</b> принята! Запускаем...")
    
    # Бросаем дайс!
    if game_type == "slot":
        dice_msg = await message.answer_dice(emoji="🎰")
    elif game_type == "basketball":
        dice_msg = await message.answer_dice(emoji="🏀")
    elif game_type == "darts":
        dice_msg = await message.answer_dice(emoji="🎯")
    elif game_type == "bowling":
        dice_msg = await message.answer_dice(emoji="🎳")
    else:
        dice_msg = await message.answer_dice(emoji="🎲")

    # Ждем пока анимация проиграется (около 3-4 сек)
    await asyncio.sleep(4)
    
    result_value = dice_msg.dice.value
    win_amount = 0
    is_win = False
    
    # --- ЛОГИКА ПОБЕДЫ ---
    # 🎲 КУБИК (1-6)
    if game_type == "dice":
        if result_value > 3:
            is_win = True
            win_amount = bet * 2

    # 🏀 БАСКЕТБОЛ (1-5)
    elif game_type == "basketball":
        if result_value in [4, 5]:
            is_win = True
            win_amount = bet * 2.5
            
    # 🎯 ДАРТС (1-6)
    elif game_type == "darts":
        if result_value == 6:
            is_win = True
            win_amount = bet * 4
        elif result_value == 5:
             is_win = True
             win_amount = bet

    # 🎳 БОУЛИНГ (1-6)
    elif game_type == "bowling":
        if result_value == 6:
            is_win = True
            win_amount = bet * 5
    
    # 🎰 СЛОТЫ (1-64)
    elif game_type == "slot":
        if result_value == 64: # Джекпот
            is_win = True
            win_amount = bet * 50
        elif result_value in [1, 22, 43]:
            is_win = True
            win_amount = bet * 3

    # --- РЕЗУЛЬТАТ ---
    if is_win:
        user['balance'] += win_amount
        await message.answer(
            f"🎉 <b>ПОБЕДА!</b>\n"
            f"Выпало значение: {result_value}\n"
            f"Вы выиграли: <b>+{win_amount:.2f}$</b>\n"
            f"💰 Текущий баланс: {format_balance(user['balance'])}",
            reply_markup=back_kb()
        )
    else:
        await message.answer(
            f"😢 <b>Проигрыш...</b>\n"
            f"Выпало значение: {result_value}\n"
            f"💰 Текущий баланс: {format_balance(user['balance'])}",
            reply_markup=back_kb()
        )
    
    # Очищаем состояние
    await state.clear()

# --- ЗАПУСК ---
async def main():
    print("Бот запущен...")
    # Удаляем старые апдейты, чтобы бот не отвечал на старые сообщения при запуске
    await bot.delete_webhook(drop_pending_updates=True) 
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
