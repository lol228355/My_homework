import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiocryptopay import AioCryptoPay, Networks

# --- ⚙️ КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8315937988:AAHaKhMNy0t-uXQjSumvkDk3nf2vyTHf63U"
CRYPTO_BOT_TOKEN = "505642:AATEFAUIQ3OE9ihgalDaLzhI4u7uH2CY0X5" # Возьмите в @CryptoBot -> Crypto Pay

# Ссылка на GIF/Картинку для заголовка сообщений (как на скриншотах)
HEADER_IMG_URL = "https://media1.tenor.com/m/JgYc2sQz9ZAAAAAC/money-cash.gif"

# --- НАСТРОЙКА ---
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Инициализация Crypto Pay (используем MAIN_NET для реальных денег, или TEST_NET для тестов)
crypto = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)

# --- БАЗА ДАННЫХ (В памяти) ---
# Храним баланс и ID последнего инвойса crypto bot
user_db = {}
def get_user(user_id):
    if user_id not in user_db:
        # balance: текущий баланс
        # last_invoice_id: для проверки оплаты
        user_db[user_id] = {'balance': 0.0, 'last_invoice_id': None}
    return user_db[user_id]

# --- МАШИНА СОСТОЯНИЙ ---
class BotStates(StatesGroup):
    waiting_for_bet_amount = State() # Ждем сумму ставки
    waiting_for_deposit_amount = State() # Ждем сумму пополнения

# --- 🎨 ФУНКЦИИ ОФОРМЛЕНИЯ ---

def format_balance(amount):
    return f"<b>{amount:.2f} $</b>"

# Функция для отправки красивых сообщений с картинкой и стилем цитаты
async def send_styled_message(target: Message | CallbackQuery, text: str, reply_markup=None, show_header=True):
    # Эмуляция стиля из скриншота с использованием blockquote
    formatted_text = (
         f"<blockquote>👾 <b>Выберите действие:</b> ❞</blockquote>\n\n"
         f"{text}"
    )

    if isinstance(target, CallbackQuery):
        # Если это коллбэк, мы не можем прикрепить новое фото к edit_text,
        # поэтому удаляем старое и шлем новое (если нужен заголовок)
        await target.message.delete()
        if show_header:
             await bot.send_animation(
                chat_id=target.from_user.id,
                animation=HEADER_IMG_URL,
                caption=formatted_text,
                reply_markup=reply_markup
            )
        else:
             await bot.send_message(
                chat_id=target.from_user.id,
                text=formatted_text,
                reply_markup=reply_markup
            )
    else:
        # Если это обычное сообщение
        if show_header:
            await target.answer_animation(
                animation=HEADER_IMG_URL,
                caption=formatted_text,
                reply_markup=reply_markup
            )
        else:
             await target.answer(formatted_text, reply_markup=reply_markup)


# --- 🎹 КЛАВИАТУРЫ ---

def main_menu_kb():
    kb = [
        [InlineKeyboardButton(text="🎲 Кубик (x2)", callback_data="sel_dice"),
         InlineKeyboardButton(text="🏀 Баскет (x2.5)", callback_data="sel_basketball")],
        [InlineKeyboardButton(text="🎯 Дартс (Меню)", callback_data="menu_darts"),
         InlineKeyboardButton(text="🎳 Боулинг (x5)", callback_data="sel_bowling")],
        [InlineKeyboardButton(text="🎰 Слоты (x50)", callback_data="sel_slot")],
         [InlineKeyboardButton(text="💳 Пополнить баланс", callback_data="deposit_start")],
        [InlineKeyboardButton(text="💰 Мой баланс", callback_data="check_balance")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# Специальное меню для Дартса (как на фото 5)
def darts_menu_kb():
    kb = [
        # Используем префиксы bets_ для конкретных видов ставок
        [InlineKeyboardButton(text="Дартс мимо | 2.5x", callback_data="bets_darts_miss"),
         InlineKeyboardButton(text="Дартс красное | 1.7x", callback_data="bets_darts_red")],
        [InlineKeyboardButton(text="Дартс белое | 1.7x", callback_data="bets_darts_white"),
         InlineKeyboardButton(text="Дартс центр | 2.5x", callback_data="bets_darts_bullseye")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def back_to_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ В главное меню", callback_data="main_menu")]
    ])

# Клавиатура для проверки оплаты
def check_payment_kb(invoice_url):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Оплатить (CryptoBot)", url=invoice_url)],
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data="check_deposit_status")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
    ])


# --- 🟢 ГЛАВНОЕ МЕНЮ И НАВИГАЦИЯ ---

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = get_user(message.from_user.id)
    text = (
        f"👋 Добро пожаловать в <b>Emoji Casino</b>!\n"
        f"Ваш баланс: {format_balance(user['balance'])}\n\n"
        f"👇 Выберите игру или пополните баланс:"
    )
    await send_styled_message(message, text, main_menu_kb())

@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = get_user(callback.from_user.id)
    text = f"🏰 Главное меню\nВаш баланс: {format_balance(user['balance'])}"
    await send_styled_message(callback, text, main_menu_kb())

@dp.callback_query(F.data == "check_balance")
async def cb_balance(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    await callback.answer(f"💰 Ваш баланс: {user['balance']:.2f} $", show_alert=True)


# --- 💳 ЛОГИКА ПОПОЛНЕНИЯ ЧЕРЕЗ CRYPTO BOT ---

@dp.callback_query(F.data == "deposit_start")
async def cb_deposit_start(callback: CallbackQuery, state: FSMContext):
    text = (
        "💵 <b>Пополнение баланса (USDT)</b>\n\n"
        "Введите сумму пополнения в долларах (минимум 1$):\n"
        "<i>Например: 10 или 5.5</i>"
    )
    await state.set_state(BotStates.waiting_for_deposit_amount)
    # Используем edit_caption для изменения текста под картинкой, если она уже есть
    try:
        await callback.message.edit_caption(caption=text, reply_markup=back_to_main_kb())
    except:
         await send_styled_message(callback, text, back_to_main_kb(), show_header=False)


@dp.message(BotStates.waiting_for_deposit_amount)
async def process_deposit_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
        if amount < 0.1: # Минималка CryptoBot для USDT около 0.1$
            await message.answer("⚠️ Минимальная сумма пополнения: 0.1$")
            return
    except ValueError:
        await message.answer("⚠️ Введите корректное число.")
        return

    # Создаем счет в Crypto Bot (в USDT)
    try:
        invoice = await crypto.create_invoice(asset='USDT', amount=amount)
        
        # Сохраняем ID инвойса пользователю
        user = get_user(message.from_user.id)
        user['last_invoice_id'] = invoice.invoice_id

        text = (
            f"🧾 <b>Счет на оплату создан!</b>\n"
            f"Сумма: <b>{amount} USDT</b>\n\n"
            f"Нажмите кнопку ниже для оплаты через Crypto Bot.\n"
            f"После оплаты нажмите '✅ Я оплатил'."
        )
        await message.answer(text, reply_markup=check_payment_kb(invoice.pay_url))
        await state.clear()
        
    except Exception as e:
        logging.error(f"CryptoPay Error: {e}")
        await message.answer("⚠️ Ошибка создания счета. Попробуйте позже.")

@dp.callback_query(F.data == "check_deposit_status")
async def cb_check_deposit(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    invoice_id = user.get('last_invoice_id')

    if not invoice_id:
        await callback.answer("❌ Нет активных счетов.", show_alert=True)
        return

    try:
        # Проверяем статус инвойса
        invoice_data = await crypto.get_invoices(invoice_ids=[invoice_id])
        
        if invoice_data and invoice_data[0].status == 'paid':
            # Оплата прошла!
            amount_paid = float(invoice_data[0].amount)
            user['balance'] += amount_paid
            user['last_invoice_id'] = None # Сбрасываем ID
            
            text = (
                f"✅ <b>Оплата получена!</b>\n"
                f"Ваш баланс пополнен на {format_balance(amount_paid)}\n"
                f"💰 Текущий баланс: {format_balance(user['balance'])}"
            )
            await send_styled_message(callback, text, main_menu_kb())
        else:
            await callback.answer("⏳ Оплата еще не поступила. Попробуйте через минуту.", show_alert=True)

    except Exception as e:
        logging.error(f"Check Invoice Error: {e}")
        await callback.answer("⚠️ Ошибка проверки. Попробуйте позже.", show_alert=True)


# --- 🎯 ЛОГИКА ИГР И СТАВОК ---

# 1. Обработчик выбора простых игр (которые сразу просят ставку)
@dp.callback_query(F.data.startswith("sel_"))
async def cb_select_simple_game(callback: CallbackQuery, state: FSMContext):
    game_type = callback.data.split("_")[1]
    # Сохраняем тип игры ("dice", "basketball" и т.д.)
    await state.update_data(game_mode=game_type, bet_target="any") 
    await request_bet_amount(callback, state)

# 2. Обработчик перехода в меню Дартса
@dp.callback_query(F.data == "menu_darts")
async def cb_darts_menu(callback: CallbackQuery):
    text = "🎯 <b>Дартс: Выберите исход</b>\nСделайте ставку на конкретный результат броска."
    # Используем edit_caption для плавности, если возможно
    try:
         formatted_text = f"<blockquote>👾 <b>Выберите исход:</b> ❞</blockquote>\n\n{text}"
         await callback.message.edit_caption(caption=formatted_text, reply_markup=darts_menu_kb())
    except:
         await send_styled_message(callback, text, darts_menu_kb(), show_header=False)

# 3. Обработчик выбора конкретной ставки в Дартсе
@dp.callback_query(F.data.startswith("bets_darts_"))
async def cb_select_darts_bet(callback: CallbackQuery, state: FSMContext):
    target = callback.data.split("_")[2] # "miss", "red", "white", "bullseye"
    # Сохраняем режим "darts" и конкретную цель
    await state.update_data(game_mode="darts", bet_target=target)
    await request_bet_amount(callback, state)


# Вспомогательная функция запроса суммы ставки
async def request_bet_amount(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_bet_amount)
    user = get_user(callback.from_user.id)
    text = (
        f"💵 <b>Введите сумму ставки</b>\n"
        f"Ваш баланс: {format_balance(user['balance'])}\n"
        f"<i>Минимум: 0.1 $</i>"
    )
    # Пытаемся редактировать подпись, чтобы не слать новое фото
    try:
        formatted_text = f"<blockquote>👾 <b>Сделайте ставку:</b> ❞</blockquote>\n\n{text}"
        await callback.message.edit_caption(caption=formatted_text, reply_markup=back_to_main_kb())
    except:
         await send_styled_message(callback, text, back_to_main_kb(), show_header=False)


# --- 🔥 ГЛАВНАЯ ФУНКЦИЯ ИГРЫ (ОБРАБОТКА СТАВКИ) ---

@dp.message(BotStates.waiting_for_bet_amount)
async def process_game(message: Message, state: FSMContext):
    try:
        bet = float(message.text.replace(',', '.'))
    except ValueError:
        await message.answer("⚠️ Введите число. Например: 1.5")
        return

    user = get_user(message.from_user.id)
    if bet < 0.1:
        await message.answer("⚠️ Минимальная ставка: 0.1 $")
        return
    if bet > user['balance']:
        await message.answer(f"⚠️ Недостаточно средств! Ваш баланс: {format_balance(user['balance'])}")
        return

    # Списываем ставку
    user['balance'] -= bet
    
    # Получаем данные о выбранной игре
    data = await state.get_data()
    game_mode = data.get("game_mode")   # 'dice', 'basketball', 'darts', ...
    bet_target = data.get("bet_target") # 'any' или конкретная цель для дартса

    # Определяем эмодзи
    emoji_map = {"dice": "🎲", "basketball": "🏀", "darts": "🎯", "bowling": "🎳", "slot": "🎰"}
    game_emoji = emoji_map.get(game_mode, "🎲")

    await message.answer(f"💸 Ставка <b>{bet}$</b> принята! Бросаем {game_emoji}...")
    
    # Бросаем дайс
    dice_msg = await message.answer_dice(emoji=game_emoji)
    await asyncio.sleep(4) # Ждем анимацию
    result_value = dice_msg.dice.value
    
    win_amount = 0
    is_win = False
    coeff = 0.0

    # --- ЛОГИКА ОПРЕДЕЛЕНИЯ ПОБЕДЫ ---
    
    # 🎯 ДАРТС (Специфичные ставки)
    # Значения Telegram Darts: 1-мимо, 2-белое, 3-красное, 4-белое, 5-красное, 6-центр
    if game_mode == "darts":
        if bet_target == "miss" and result_value == 1:
            is_win = True; coeff = 2.5
        elif bet_target == "white" and result_value in [2, 4]:
            is_win = True; coeff = 1.7
        elif bet_target == "red" and result_value in [3, 5]:
             is_win = True; coeff = 1.7
        elif bet_target == "bullseye" and result_value == 6:
             is_win = True; coeff = 2.5
             
    # 🎲 КУБИК (Простая ставка на 4,5,6)
    elif game_mode == "dice" and result_value > 3:
         is_win = True; coeff = 2.0

    # 🏀 БАСКЕТБОЛ (Попадание 4,5)
    elif game_mode == "basketball" and result_value in [4, 5]:
         is_win = True; coeff = 2.5
            
    # 🎳 БОУЛИНГ (Страйк 6)
    elif game_mode == "bowling" and result_value == 6:
         is_win = True; coeff = 5.0
    
    # 🎰 СЛОТЫ (Джекпот 64)
    elif game_mode == "slot" and result_value == 64:
         is_win = True; coeff = 50.0

    # --- РЕЗУЛЬТАТ ---
    await state.clear()
    
    if is_win:
        win_amount = bet * coeff
        user['balance'] += win_amount
        text = (
            f"🎉 <b>ПОБЕДА! (x{coeff})</b>\n"
            f"Выпало: {result_value}\n"
            f"Выигрыш: <b>+{win_amount:.2f} $</b>\n"
            f"💰 Баланс: {format_balance(user['balance'])}"
        )
        await send_styled_message(message, text, main_menu_kb())
    else:
        text = (
            f"😢 <b>Проигрыш...</b>\n"
            f"Выпало: {result_value}\n"
            f"💰 Баланс: {format_balance(user['balance'])}"
        )
        await send_
