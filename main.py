import asyncio
import logging
import re
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiocryptopay import AioCryptoPay, Networks
from datetime import datetime

# --- ⚙️ КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8315937988:AAHaKhMNy0t-uXQjSumvkDk3nf2vyTHf63U"
CRYPTO_BOT_TOKEN = "505642:AATEFAUIQ3OE9ihgalDaLzhI4u7uH2CY0X5"
GAME_CHAT_ID = None  # Укажите ID игрового чата здесь

# Курс валюты (1$ = ~83₽, 100₽ = ~1.2$)
USD_TO_RUB_RATE = 83.0
MIN_DEPOSIT_RUB = 25  # Минимальное пополнение в рублях
MIN_WITHDRAW_RUB = 100  # Минимальный вывод в рублях

# Конвертация
MIN_DEPOSIT_USD = MIN_DEPOSIT_RUB / USD_TO_RUB_RATE  # ~0.3$
MIN_WITHDRAW_USD = MIN_WITHDRAW_RUB / USD_TO_RUB_RATE  # ~1.2$

# Название казино
CASINO_NAME = "Andron"

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Инициализация Crypto Pay (Mainnet)
try:
    crypto = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)
    logger.info("CryptoPay инициализирован успешно")
except Exception as e:
    logger.error(f"Ошибка инициализации CryptoPay: {e}")
    crypto = None

# База данных в оперативной памяти
user_db = {}
transactions_db = []  # История транзакций

def get_user(user_id):
    if user_id not in user_db:
        user_db[user_id] = {
            'balance': 0.0,  # В долларах
            'last_invoice_id': None,
            'username': '',
            'games_played': 0,
            'games_won': 0,
            'total_deposit': 0.0,
            'total_withdraw': 0.0,
            'registration_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    return user_db[user_id]

def add_transaction(user_id, tx_type, amount, status="completed", details=""):
    transactions_db.append({
        'user_id': user_id,
        'type': tx_type,  # deposit, withdraw, win, loss
        'amount': amount,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'status': status,
        'details': details
    })

# Конвертация валют
def usd_to_rub(usd_amount):
    return usd_amount * USD_TO_RUB_RATE

def rub_to_usd(rub_amount):
    return rub_amount / USD_TO_RUB_RATE

def format_balance_usd(amount_usd):
    amount_rub = usd_to_rub(amount_usd)
    return f"<b>{amount_usd:.2f} $</b> ≈ <b>{amount_rub:.0f}₽</b>"

def format_rub(amount_rub):
    return f"<b>{amount_rub:.0f}₽</b>"

def format_usd(amount_usd):
    return f"<b>{amount_usd:.2f} $</b>"

# Состояния FSM
class BotStates(StatesGroup):
    waiting_for_deposit_amount = State()
    waiting_for_withdraw_amount = State()
    waiting_for_withdraw_address = State()

def extract_number(text):
    if not text:
        return None
    match = re.search(r'(\d+[.,]?\d*)', str(text))
    if match:
        number_str = match.group(1).replace(',', '.')
        try:
            return float(number_str)
        except ValueError:
            return None
    return None

# --- КЛАВИАТУРЫ ---
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Баланс", callback_data="check_balance")],
        [InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit_start"),
         InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw_start")],
        [InlineKeyboardButton(text="📊 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="📋 История", callback_data="history")],
        [InlineKeyboardButton(text="📚 Инструкция", callback_data="instructions")],
        [InlineKeyboardButton(text="👨‍💻 Поддержка", callback_data="support")]
    ])

def deposit_methods_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 CryptoBot (USDT)", callback_data="deposit_crypto")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

def withdraw_methods_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 USDT (TRC20)", callback_data="withdraw_usdt")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

def check_payment_kb(pay_url):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Оплатить через CryptoBot", url=pay_url)],
        [InlineKeyboardButton(text="✅ Проверить оплату", callback_data="check_deposit_status")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

def cancel_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
    ])

# --- ОБРАБОТЧИКИ КОМАНД ---

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = get_user(message.from_user.id)
    if not user['username'] and message.from_user.username:
        user['username'] = f"@{message.from_user.username}"
    
    await message.answer(
        f"🎰 <b>Добро пожаловать в {CASINO_NAME} Casino!</b>\n\n"
        "🎮 <b>Как играть:</b>\n"
        "1. Пополните баланс через этого бота\n"
        "2. Перейдите в игровой чат\n"
        "3. Кидайте эмодзи-кости (🎲, 🎯, 🎳, 🏀, 🎰)\n"
        "4. Автоматически получайте выигрыши\n\n"
        
        f"💰 <b>Минимальные суммы:</b>\n"
        f"• Пополнение: {format_rub(MIN_DEPOSIT_RUB)} ({format_usd(MIN_DEPOSIT_USD)})\n"
        f"• Вывод: {format_rub(MIN_WITHDRAW_RUB)} ({format_usd(MIN_WITHDRAW_USD)})\n\n"
        
        "🎲 <b>Коэффициенты:</b>\n"
        "• 🎲 Кубик (x2) - выпало 4-6\n"
        "• 🏀 Баскетбол (x2.5) - выпало 4-5\n"
        "• 🎯 Дартс (x2.5) - попал в центр\n"
        "• 🎳 Боулинг (x5) - страйк (6)\n"
        "• 🎰 Слоты (x50) - джекпот (64)\n\n"
        
        "Выберите действие:",
        reply_markup=main_menu_kb()
    )

@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = get_user(callback.from_user.id)
    await callback.message.edit_text(
        f"🏠 <b>Главное меню | {CASINO_NAME} Casino</b>\n\n"
        f"💰 Ваш баланс: {format_balance_usd(user['balance'])}\n\n"
        "Выберите действие:",
        reply_markup=main_menu_kb()
    )

@dp.callback_query(F.data == "check_balance")
async def cb_balance(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    balance_rub = usd_to_rub(user['balance'])
    await callback.answer(
        f"💰 Баланс:\n"
        f"{user['balance']:.2f} $\n"
        f"≈ {balance_rub:.0f}₽",
        show_alert=True
    )

# --- ПОПОЛНЕНИЕ ---
@dp.callback_query(F.data == "deposit_start")
async def dep_start(callback: CallbackQuery):
    if crypto is None:
        await callback.answer("❌ Сервис оплаты временно недоступен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "💳 <b>Выберите способ пополнения:</b>",
        reply_markup=deposit_methods_kb()
    )

@dp.callback_query(F.data == "deposit_crypto")
async def dep_crypto(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_deposit_amount)
    
    await callback.message.edit_text(
        f"💎 <b>Пополнение через CryptoBot</b>\n\n"
        f"Минимальная сумма: {format_rub(MIN_DEPOSIT_RUB)} ({format_usd(MIN_DEPOSIT_USD)})\n"
        f"Максимальная сумма: {format_rub(100000)} ({format_usd(rub_to_usd(100000))})\n\n"
        f"<b>Введите сумму в рублях (₽):</b>\n"
        f"Примеры: <code>100</code>, <code>500</code>, <code>1000</code>\n\n"
        f"<i>Курс: 1$ ≈ {USD_TO_RUB_RATE}₽</i>",
        reply_markup=cancel_kb()
    )

@dp.message(BotStates.waiting_for_deposit_amount)
async def dep_amount(message: Message, state: FSMContext):
    rub_amount = extract_number(message.text)
    
    if rub_amount is None:
        await message.answer(
            f"❌ Неверный формат! Введите число в рублях.\n"
            f"Пример: <code>{MIN_DEPOSIT_RUB}</code> или <code>1000</code>",
            reply_markup=cancel_kb()
        )
        return
    
    if rub_amount < MIN_DEPOSIT_RUB:
        await message.answer(
            f"❌ Минимальная сумма пополнения: {format_rub(MIN_DEPOSIT_RUB)}!",
            reply_markup=cancel_kb()
        )
        return
    
    if rub_amount > 100000:  # Максимум 100,000₽
        await message.answer(
            f"❌ Максимальная сумма пополнения: {format_rub(100000)}!",
            reply_markup=cancel_kb()
        )
        return
    
    # Конвертируем в доллары для CryptoBot
    usd_amount = rub_to_usd(rub_amount)
    
    try:
        user = get_user(message.from_user.id)
        invoice = await crypto.create_invoice(asset='USDT', amount=usd_amount)
        
        # Получаем ссылку на оплату
        pay_url = None
        if hasattr(invoice, 'url'):
            pay_url = invoice.url
        elif hasattr(invoice, 'pay_url'):
            pay_url = invoice.pay_url
        elif hasattr(invoice, 'bot_invoice_url'):
            pay_url = invoice.bot_invoice_url
        
        user['last_invoice_id'] = invoice.invoice_id
        
        await message.answer(
            f"✅ <b>Счет создан!</b>\n\n"
            f"💳 Сумма: {format_rub(rub_amount)} ({format_usd(usd_amount)})\n"
            f"📝 ID счета: <code>{invoice.invoice_id}</code>\n"
            f"⏳ Счет действует 15 минут\n\n"
            f"Нажмите кнопку для оплаты:",
            reply_markup=check_payment_kb(pay_url) if pay_url else cancel_kb()
        )
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка создания счета: {e}")
        await message.answer(
            f"❌ Ошибка при создании счета\n"
            f"Попробуйте позже или обратитесь в поддержку",
            reply_markup=cancel_kb()
        )

@dp.callback_query(F.data == "check_deposit_status")
async def check_deposit(callback: CallbackQuery):
    if crypto is None:
        await callback.answer("❌ Сервис недоступен", show_alert=True)
        return
    
    user = get_user(callback.from_user.id)
    inv_id = user.get('last_invoice_id')
    
    if not inv_id:
        await callback.answer("❌ Нет активных счетов", show_alert=True)
        return
    
    try:
        invoices = await crypto.get_invoices(invoice_ids=[inv_id])
        
        if not invoices:
            await callback.answer("❌ Счет не найден", show_alert=True)
            return
        
        invoice = invoices[0]
        
        # Определяем статус
        if hasattr(invoice, 'status'):
            status = invoice.status
        elif hasattr(invoice, 'paid'):
            status = 'paid' if invoice.paid else 'active'
        else:
            status = 'unknown'
        
        if status == 'paid':
            amt_usd = float(invoice.amount)
            amt_rub = usd_to_rub(amt_usd)
            
            user['balance'] += amt_usd
            user['total_deposit'] += amt_usd
            user['last_invoice_id'] = None
            add_transaction(callback.from_user.id, 'deposit', amt_usd)
            
            await callback.answer(
                f"✅ Зачислено!\n"
                f"{format_usd(amt_usd)}\n"
                f"≈ {format_rub(amt_rub)}",
                show_alert=True
            )
            await cb_main_menu(callback, None)
            
        elif status == 'active':
            await callback.answer("⏳ Ожидает оплаты", show_alert=True)
        elif status == 'expired':
            await callback.answer("❌ Счет истек", show_alert=True)
            user['last_invoice_id'] = None
        else:
            await callback.answer(f"Статус: {status}", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка проверки: {e}")
        await callback.answer("❌ Ошибка проверки", show_alert=True)

# --- ВЫВОД ---
@dp.callback_query(F.data == "withdraw_start")
async def withdraw_start(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    user_balance_rub = usd_to_rub(user['balance'])
    
    if user_balance_rub < MIN_WITHDRAW_RUB:
        await callback.answer(
            f"❌ Минимальная сумма вывода: {format_rub(MIN_WITHDRAW_RUB)}!\n"
            f"Ваш баланс: {format_rub(user_balance_rub)}",
            show_alert=True
        )
        return
    
    await callback.message.edit_text(
        "💸 <b>Вывод средств</b>\n\n"
        f"💰 Доступно: {format_balance_usd(user['balance'])}\n"
        f"💳 Минимальный вывод: {format_rub(MIN_WITHDRAW_RUB)} ({format_usd(MIN_WITHDRAW_USD)})\n"
        f"📝 Комиссия: <b>0.5%</b>\n\n"
        "Выберите способ вывода:",
        reply_markup=withdraw_methods_kb()
    )

@dp.callback_query(F.data == "withdraw_usdt")
async def withdraw_usdt(callback: CallbackQuery, state: FSMContext):
    user = get_user(callback.from_user.id)
    user_balance_rub = usd_to_rub(user['balance'])
    
    if user_balance_rub < MIN_WITHDRAW_RUB:
        await callback.answer(
            f"❌ Недостаточно средств!\n"
            f"Минимум: {format_rub(MIN_WITHDRAW_RUB)}",
            show_alert=True
        )
        return
    
    await state.set_state(BotStates.waiting_for_withdraw_amount)
    
    await callback.message.edit_text(
        f"💎 <b>Вывод USDT (TRC20)</b>\n\n"
        f"💰 Ваш баланс: {format_balance_usd(user['balance'])}\n"
        f"💳 Минимальный вывод: {format_rub(MIN_WITHDRAW_RUB)} ({format_usd(MIN_WITHDRAW_USD)})\n"
        f"📝 Комиссия: <b>0.5%</b>\n\n"
        f"<b>Введите сумму в рублях (₽):</b>\n"
        f"Примеры: <code>100</code>, <code>500</code>, <code>1000</code>\n\n"
        f"<i>Курс: 1$ ≈ {USD_TO_RUB_RATE}₽</i>",
        reply_markup=cancel_kb()
    )

@dp.message(BotStates.waiting_for_withdraw_amount)
async def withdraw_amount(message: Message, state: FSMContext):
    rub_amount = extract_number(message.text)
    user = get_user(message.from_user.id)
    user_balance_rub = usd_to_rub(user['balance'])
    
    if rub_amount is None:
        await message.answer("❌ Неверный формат! Введите число в рублях:", reply_markup=cancel_kb())
        return
    
    if rub_amount < MIN_WITHDRAW_RUB:
        await message.answer(f"❌ Минимальная сумма вывода: {format_rub(MIN_WITHDRAW_RUB)}!", reply_markup=cancel_kb())
        return
    
    if rub_amount > user_balance_rub:
        await message.answer(
            f"❌ Недостаточно средств!\n"
            f"Ваш баланс: {format_rub(user_balance_rub)}\n"
            f"Запрошено: {format_rub(rub_amount)}",
            reply_markup=cancel_kb()
        )
        return
    
    # Конвертируем в доллары
    usd_amount = rub_to_usd(rub_amount)
    
    # Рассчитываем с комиссией
    fee_usd = usd_amount * 0.005  # 0.5%
    fee_rub = usd_to_rub(fee_usd)
    final_usd_amount = usd_amount - fee_usd
    final_rub_amount = usd_to_rub(final_usd_amount)
    
    await state.update_data(
        withdraw_rub=rub_amount,
        withdraw_usd=usd_amount,
        final_rub=final_rub_amount,
        final_usd=final_usd_amount
    )
    await state.set_state(BotStates.waiting_for_withdraw_address)
    
    await message.answer(
        f"📊 <b>Детали вывода</b>\n\n"
        f"💳 Сумма: {format_rub(rub_amount)} ({format_usd(usd_amount)})\n"
        f"📝 Комиссия (0.5%): {format_rub(fee_rub)} ({format_usd(fee_usd)})\n"
        f"💰 К получению: {format_rub(final_rub_amount)} ({format_usd(final_usd_amount)})\n\n"
        f"<b>Введите адрес кошелька USDT (TRC20):</b>\n"
        f"Адрес должен начинаться с буквы 'T'",
        reply_markup=cancel_kb()
    )

@dp.message(BotStates.waiting_for_withdraw_address)
async def withdraw_address(message: Message, state: FSMContext):
    address = message.text.strip()
    
    # Валидация адреса TRC20
    if not re.match(r'^T[A-Za-z0-9]{33}$', address):
        await message.answer(
            "❌ Неверный формат адреса!\n"
            "Введите корректный адрес USDT (TRC20), начинающийся с 'T'\n"
            "Пример: <code>TAbCdEfGhIjKlMnOpQrStUvWxYz0123456789</code>",
            reply_markup=cancel_kb()
        )
        return
    
    data = await state.get_data()
    rub_amount = data['withdraw_rub']
    usd_amount = data['withdraw_usd']
    final_rub_amount = data['final_rub']
    final_usd_amount = data['final_usd']
    
    user = get_user(message.from_user.id)
    
    # Списание средств
    user['balance'] -= usd_amount
    user['total_withdraw'] += usd_amount
    add_transaction(
        message.from_user.id, 
        'withdraw', 
        -usd_amount,
        status="pending", 
        details=f"Адрес: {address}, Сумма: {rub_amount}₽"
    )
    
    # Сообщение пользователю
    await message.answer(
        f"✅ <b>Заявка на вывод создана!</b>\n\n"
        f"💳 Сумма: {format_rub(rub_amount)} ({format_usd(usd_amount)})\n"
        f"💰 К получению: {format_rub(final_rub_amount)} ({format_usd(final_usd_amount)})\n"
        f"📝 Адрес: <code>{address}</code>\n"
        f"⏳ Статус: <b>В обработке</b>\n\n"
        f"Заявка будет обработана в течение 24 часов.\n"
        f"ID транзакции: <code>{len(transactions_db)}</code>",
        reply_markup=main_menu_kb()
    )
    
    # Уведомление администратору
    admin_id = None  # Укажите ваш ID
    if admin_id:
        try:
            await bot.send_message(
                admin_id,
                f"🚨 <b>НОВАЯ ЗАЯВКА НА ВЫВОД | {CASINO_NAME}</b>\n\n"
                f"👤 Пользователь: {user.get('username', message.from_user.id)}\n"
                f"💳 Сумма: {rub_amount}₽ ({usd_amount:.2f}$)\n"
                f"💰 К выплате: {final_rub_amount:.0f}₽ ({final_usd_amount:.2f}$)\n"
                f"📝 Адрес: <code>{address}</code>\n"
                f"🆔 ID транзакции: {len(transactions_db)}\n"
                f"⏰ Время: {datetime.now().strftime('%H:%M:%S')}"
            )
        except:
            pass
    
    await state.clear()

# --- ПРОФИЛЬ ---
@dp.callback_query(F.data == "profile")
async def profile(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    
    win_rate = 0
    if user['games_played'] > 0:
        win_rate = (user['games_won'] / user['games_played']) * 100
    
    total_deposit_rub = usd_to_rub(user['total_deposit'])
    total_withdraw_rub = usd_to_rub(user['total_withdraw'])
    balance_rub = usd_to_rub(user['balance'])
    
    await callback.message.edit_text(
        f"👤 <b>Профиль игрока | {CASINO_NAME}</b>\n\n"
        f"🆔 ID: <code>{callback.from_user.id}</code>\n"
        f"👤 Имя: {callback.from_user.first_name}\n"
        f"📅 Регистрация: {user['registration_date']}\n\n"
        f"💰 Баланс: {format_balance_usd(user['balance'])}\n"
        f"💳 Всего пополнено: {format_rub(total_deposit_rub)} ({format_usd(user['total_deposit'])})\n"
        f"💸 Всего выведено: {format_rub(total_withdraw_rub)} ({format_usd(user['total_withdraw'])})\n\n"
        f"🎮 Статистика игр:\n"
        f"• Сыграно игр: {user['games_played']}\n"
        f"• Побед: {user['games_won']}\n"
        f"• Процент побед: {win_rate:.1f}%\n\n"
        f"🎲 Играйте в нашем игровом чате!",
        reply_markup=main_menu_kb()
    )

# --- ИСТОРИЯ ---
@dp.callback_query(F.data == "history")
async def history(callback: CallbackQuery):
    user_id = callback.from_user.id
    user_transactions = [t for t in transactions_db if t['user_id'] == user_id][-10:]
    
    if not user_transactions:
        await callback.message.edit_text(
            "📋 <b>История операций</b>\n\n"
            "У вас еще нет операций.",
            reply_markup=main_menu_kb()
        )
        return
    
    history_text = f"📋 <b>История операций | {CASINO_NAME}</b>\n\n"
    
    for tx in reversed(user_transactions):
        emoji = ""
        if tx['type'] == 'deposit':
            emoji = "💳"
        elif tx['type'] == 'withdraw':
            emoji = "💸"
        elif tx['type'] == 'win':
            emoji = "🎉"
        elif tx['type'] == 'loss':
            emoji = "😢"
        
        amount_usd = tx['amount']
        amount_rub = usd_to_rub(abs(amount_usd))
        amount_sign = "+" if amount_usd > 0 else "-"
        
        # Форматируем время
        time_str = tx['timestamp'][11:16]  # Берем только часы:минуты
        
        history_text += f"{emoji} {time_str} - {amount_sign}{format_rub(amount_rub)} ({amount_sign}{format_usd(abs(amount_usd))})\n"
    
    await callback.message.edit_text(
        history_text,
        reply_markup=main_menu_kb()
    )

# --- ИНСТРУКЦИЯ ---
@dp.callback_query(F.data == "instructions")
async def instructions(callback: CallbackQuery):
    await callback.message.edit_text(
        f"📚 <b>Инструкция по использованию | {CASINO_NAME}</b>\n\n"
        
        "🎮 <b>Как начать играть:</b>\n"
        "1. Пополните баланс через раздел '💳 Пополнить'\n"
        "2. Получите ссылку на игровой чат у поддержки\n"
        "3. Войдите в игровой чат\n"
        "4. Кидайте эмодзи-кости в чат\n\n"
        
        f"💰 <b>Финансовые условия:</b>\n"
        f"• Минимальное пополнение: {format_rub(MIN_DEPOSIT_RUB)}\n"
        f"• Минимальный вывод: {format_rub(MIN_WITHDRAW_RUB)}\n"
        f"• Комиссия на вывод: 0.5%\n"
        f"• Курс: 1$ ≈ {USD_TO_RUB_RATE}₽\n\n"
        
        "🎲 <b>Правила игр:</b>\n"
        "• 🎲 <b>Кубик (x2)</b> - победа если выпало 4-6\n"
        "• 🏀 <b>Баскетбол (x2.5)</b> - победа если выпало 4-5\n"
        "• 🎯 <b>Дартс (x2.5)</b> - победа если попал в центр (6)\n"
        "• 🎳 <b>Боулинг (x5)</b> - победа если страйк (6)\n"
        "• 🎰 <b>Слоты (x50)</b> - победа если джекпот (64)\n\n"
        
        "⚠️ <b>Важно:</b>\n"
        "• Играйте ответственно\n"
        "• Минимальная ставка: 0.1$\n"
        "• Игры проходят в игровом чате",
        reply_markup=main_menu_kb()
    )

# --- ПОДДЕРЖКА ---
@dp.callback_query(F.data == "support")
async def support(callback: CallbackQuery):
    await callback.message.edit_text(
        f"👨‍💻 <b>Служба поддержки | {CASINO_NAME}</b>\n\n"
        "📞 <b>Связь с администратором:</b>\n"
        "• Технические проблемы\n"
        "• Вопросы по выплатам\n"
        "• Получение ссылки на игровой чат\n"
        "• Предложения и жалобы\n\n"
        "✉️ <b>Написать в поддержку:</b>\n"
        "• @username_admin (замените на реальный)\n\n"
        "⏰ <b>Время работы:</b>\n"
        "Круглосуточно, 7 дней в неделю\n\n"
        "⚠️ <b>Важно:</b>\n"
        "Администратор никогда не просит пароли или приватные ключи!",
        reply_markup=main_menu_kb()
    )

# --- ОБРАБОТКА ИГР В ЧАТЕ ---
async def process_game_in_chat(message: Message):
    """Обработка игр в игровом чате"""
    if not GAME_CHAT_ID or message.chat.id != GAME_CHAT_ID:
        return
    
    user_id = message.from_user.id
    user = get_user(user_id)
    
    # Минимальная ставка в долларах
    min_bet_usd = 0.1  # 0.1$ ≈ 8.3₽
    min_bet_rub = usd_to_rub(min_bet_usd)
    
    if user['balance'] < min_bet_usd:
        await message.reply(
            f"❌ Недостаточно средств!\n"
            f"Минимальная ставка: {format_usd(min_bet_usd)} ({format_rub(min_bet_rub)})\n"
            f"Ваш баланс: {format_balance_usd(user['balance'])}"
        )
        return
    
    # Вычитаем ставку
    user['balance'] -= min_bet_usd
    user['games_played'] += 1
    add_transaction(user_id, 'loss', -min_bet_usd, details=f"Ставка в игре")
    
    # Ждем результат кубика
    await asyncio.sleep(4)
    
    # Получаем результат
    if message.dice:
        dice_value = message.dice.value
        emoji = message.dice.emoji
        
        win = False
        multiplier = 1.0
        
        # Проверяем выигрыш
        if emoji == "🎲":  # Кубик
            if dice_value > 3:
                win = True
                multiplier = 2.0
        elif emoji == "🏀":  # Баскетбол
            if dice_value in [4, 5]:
                win = True
                multiplier = 2.5
        elif emoji == "🎯":  # Дартс
            if dice_value == 6:
                win = True
                multiplier = 2.5
        elif emoji == "🎳":  # Боулинг
            if dice_value == 6:
                win = True
                multiplier = 5.0
        elif emoji == "🎰":  # Слоты
            if dice_value == 64:
                win = True
                multiplier = 50.0
        
        if win:
            win_amount_usd = min_bet_usd * multiplier
            win_amount_rub = usd_to_rub(win_amount_usd)
            
            user['balance'] += win_amount_usd
            user['games_won'] += 1
            add_transaction(user_id, 'win', win_amount_usd, details=f"Выигрыш {multiplier}x")
            
            await message.reply(
                f"🎉 <b>ПОБЕДА! | {CASINO_NAME}</b>\n\n"
                f"👤 Игрок: {message.from_user.first_name}\n"
                f"🎲 Выпало: {dice_value} ({emoji})\n"
                f"💰 Коэффициент: x{multiplier}\n"
                f"💵 Выигрыш: +{format_usd(win_amount_usd)} ({format_rub(win_amount_rub)})\n"
                f"🏦 Баланс: {format_balance_usd(user['balance'])}"
            )
        else:
            await message.reply(
                f"😢 <b>ПРОИГРЫШ | {CASINO_NAME}</b>\n\n"
                f"👤 Игрок: {message.from_user.first_name}\n"
                f"🎲 Выпало: {dice_value} ({emoji})\n"
                f"💸 Потеряно: {format_usd(min_bet_usd)} ({format_rub(min_bet_rub)})\n"
                f"🏦 Баланс: {format_balance_usd(user['balance'])}"
            )

# Регистрируем обработчик для кубиков
@dp.message(F.dice)
async def handle_dice(message: Message):
    await process_game_in_chat(message)

# --- ЗАПУСК ---
async def main():
    print(f"🎰 {CASINO_NAME} Casino Bot запущен!")
    print(f"🤖 Bot ID: {BOT_TOKEN[:10]}...")
    print(f"💰 Crypto токен: {CRYPTO_BOT_TOKEN[:10]}...")
    print(f"💵 Курс: 1$ = {USD_TO_RUB_RATE}₽")
    print(f"💳 Мин. пополнение: {MIN_DEPOSIT_RUB}₽ ({MIN_DEPOSIT_USD:.2f}$)")
    print(f"💸 Мин. вывод: {MIN_WITHDRAW_RUB}₽ ({MIN_WITHDRAW_USD:.2f}$)")
    
    if GAME_CHAT_ID:
        print(f"🎮 Игровой чат: {GAME_CHAT_ID}")
    else:
        print("⚠️ Игровой чат не указан! Укажите GAME_CHAT_ID в коде")
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
