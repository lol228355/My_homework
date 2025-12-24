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
            'balance': 0.0,
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

# Состояния FSM
class BotStates(StatesGroup):
    waiting_for_deposit_amount = State()
    waiting_for_withdraw_amount = State()
    waiting_for_withdraw_address = State()

def format_balance(amount):
    return f"<b>{amount:.2f} $</b>"

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
        "🎰 <b>Добро пожаловать в FRK Casino!</b>\n\n"
        "🎮 <b>Как играть:</b>\n"
        "1. Пополните баланс через этого бота\n"
        "2. Перейдите в игровой чат\n"
        "3. Кидайте эмодзи-кости (🎲, 🎯, 🎳, 🏀, 🎰)\n"
        "4. Автоматически получайте выигрыши\n\n"
        "💰 <b>Коэффициенты:</b>\n"
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
        "🏠 <b>Главное меню</b>\n\n"
        f"💰 Ваш баланс: {format_balance(user['balance'])}\n\n"
        "Выберите действие:",
        reply_markup=main_menu_kb()
    )

@dp.callback_query(F.data == "check_balance")
async def cb_balance(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    await callback.answer(f"💰 Ваш баланс: {user['balance']:.2f}$", show_alert=True)

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
        "💎 <b>Пополнение через CryptoBot</b>\n\n"
        "Введите сумму пополнения в $ (USDT)\n"
        "Минимальная сумма: <b>1 $</b>\n"
        "Максимальная сумма: <b>10000 $</b>\n\n"
        "Примеры: <code>10</code>, <code>50.5</code>, <code>100</code>",
        reply_markup=cancel_kb()
    )

@dp.message(BotStates.waiting_for_deposit_amount)
async def dep_amount(message: Message, state: FSMContext):
    amount = extract_number(message.text)
    
    if amount is None:
        await message.answer("❌ Неверный формат! Введите число:", reply_markup=cancel_kb())
        return
    
    if amount < 1:
        await message.answer("❌ Минимальная сумма: 1$", reply_markup=cancel_kb())
        return
    
    if amount > 10000:
        await message.answer("❌ Максимальная сумма: 10000$", reply_markup=cancel_kb())
        return
    
    try:
        user = get_user(message.from_user.id)
        invoice = await crypto.create_invoice(asset='USDT', amount=amount)
        
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
            f"💳 Сумма: <b>{amount:.2f} $</b>\n"
            f"📝 ID: <code>{invoice.invoice_id}</code>\n"
            f"⏳ Счет действует 15 минут\n\n"
            f"Нажмите кнопку для оплаты:",
            reply_markup=check_payment_kb(pay_url) if pay_url else cancel_kb()
        )
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка создания счета: {e}")
        await message.answer(
            "❌ Ошибка при создании счета\n"
            "Попробуйте позже или обратитесь в поддержку",
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
            amt = float(invoice.amount)
            user['balance'] += amt
            user['total_deposit'] += amt
            user['last_invoice_id'] = None
            add_transaction(callback.from_user.id, 'deposit', amt)
            
            await callback.answer(f"✅ Зачислено {amt:.2f}$", show_alert=True)
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
    if user['balance'] < 1:
        await callback.answer("❌ Минимальная сумма вывода: 1$", show_alert=True)
        return
    
    await callback.message.edit_text(
        "💸 <b>Вывод средств</b>\n\n"
        f"💰 Доступно: {format_balance(user['balance'])}\n"
        f"💳 Минимальный вывод: <b>1 $</b>\n\n"
        "Выберите способ вывода:",
        reply_markup=withdraw_methods_kb()
    )

@dp.callback_query(F.data == "withdraw_usdt")
async def withdraw_usdt(callback: CallbackQuery, state: FSMContext):
    user = get_user(callback.from_user.id)
    if user['balance'] < 1:
        await callback.answer("❌ Недостаточно средств", show_alert=True)
        return
    
    await state.set_state(BotStates.waiting_for_withdraw_amount)
    await callback.message.edit_text(
        "💎 <b>Вывод USDT (TRC20)</b>\n\n"
        f"💰 Ваш баланс: {format_balance(user['balance'])}\n"
        f"💳 Минимальный вывод: <b>1 $</b>\n"
        f"📝 Комиссия: <b>0.5%</b>\n\n"
        "Введите сумму для вывода:",
        reply_markup=cancel_kb()
    )

@dp.message(BotStates.waiting_for_withdraw_amount)
async def withdraw_amount(message: Message, state: FSMContext):
    amount = extract_number(message.text)
    user = get_user(message.from_user.id)
    
    if amount is None:
        await message.answer("❌ Неверный формат! Введите число:", reply_markup=cancel_kb())
        return
    
    if amount < 1:
        await message.answer("❌ Минимальная сумма: 1$", reply_markup=cancel_kb())
        return
    
    if amount > user['balance']:
        await message.answer(f"❌ Недостаточно средств! Баланс: {user['balance']:.2f}$", reply_markup=cancel_kb())
        return
    
    # Рассчитываем с комиссией
    fee = amount * 0.005  # 0.5%
    final_amount = amount - fee
    
    await state.update_data(withdraw_amount=amount, final_amount=final_amount)
    await state.set_state(BotStates.waiting_for_withdraw_address)
    
    await message.answer(
        f"📊 <b>Детали вывода</b>\n\n"
        f"💳 Сумма: {format_balance(amount)}\n"
        f"📝 Комиссия (0.5%): {fee:.2f} $\n"
        f"💰 К получению: {format_balance(final_amount)}\n\n"
        "Введите адрес кошелька USDT (TRC20):",
        reply_markup=cancel_kb()
    )

@dp.message(BotStates.waiting_for_withdraw_address)
async def withdraw_address(message: Message, state: FSMContext):
    address = message.text.strip()
    
    # Простая валидация адреса TRC20
    if not re.match(r'^T[A-Za-z0-9]{33}$', address):
        await message.answer(
            "❌ Неверный формат адреса!\n"
            "Введите корректный адрес USDT (TRC20), начинающийся с 'T'",
            reply_markup=cancel_kb()
        )
        return
    
    data = await state.get_data()
    amount = data['withdraw_amount']
    final_amount = data['final_amount']
    user = get_user(message.from_user.id)
    
    # Списание средств
    user['balance'] -= amount
    user['total_withdraw'] += amount
    add_transaction(message.from_user.id, 'withdraw', -amount, 
                   status="pending", 
                   details=f"Адрес: {address}")
    
    # Здесь должна быть интеграция с платежной системой
    # Пока имитируем вывод
    
    await message.answer(
        f"✅ <b>Заявка на вывод создана!</b>\n\n"
        f"💳 Сумма: {format_balance(amount)}\n"
        f"💰 К получению: {format_balance(final_amount)}\n"
        f"📝 Адрес: <code>{address}</code>\n"
        f"⏳ Статус: <b>В обработке</b>\n\n"
        f"Заявка будет обработана в течение 24 часов.\n"
        f"ID транзакции: <code>{len(transactions_db)}</code>",
        reply_markup=main_menu_kb()
    )
    
    # Уведомление администратору (замените на ваш ID)
    admin_id = None  # Укажите ваш ID
    if admin_id:
        try:
            await bot.send_message(
                admin_id,
                f"🚨 <b>НОВАЯ ЗАЯВКА НА ВЫВОД</b>\n\n"
                f"👤 Пользователь: {user.get('username', message.from_user.id)}\n"
                f"💳 Сумма: {amount:.2f}$\n"
                f"💰 К выплате: {final_amount:.2f}$\n"
                f"📝 Адрес: <code>{address}</code>\n"
                f"🆔 ID транзакции: {len(transactions_db)}"
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
    
    await callback.message.edit_text(
        f"👤 <b>Профиль игрока</b>\n\n"
        f"🆔 ID: <code>{callback.from_user.id}</code>\n"
        f"📅 Регистрация: {user['registration_date']}\n\n"
        f"💰 Баланс: {format_balance(user['balance'])}\n"
        f"💳 Всего пополнено: {format_balance(user['total_deposit'])}\n"
        f"💸 Всего выведено: {format_balance(user['total_withdraw'])}\n\n"
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
    user_transactions = [t for t in transactions_db if t['user_id'] == user_id][-10:]  # Последние 10
    
    if not user_transactions:
        await callback.message.edit_text(
            "📋 <b>История операций</b>\n\n"
            "У вас еще нет операций.",
            reply_markup=main_menu_kb()
        )
        return
    
    history_text = "📋 <b>История операций</b>\n\n"
    
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
        
        amount_sign = "+" if tx['amount'] > 0 else ""
        history_text += f"{emoji} {tx['timestamp']} - {amount_sign}{tx['amount']:.2f}$ ({tx['type']})\n"
    
    await callback.message.edit_text(
        history_text,
        reply_markup=main_menu_kb()
    )

# --- ИНСТРУКЦИЯ ---
@dp.callback_query(F.data == "instructions")
async def instructions(callback: CallbackQuery):
    await callback.message.edit_text(
        "📚 <b>Инструкция по использованию</b>\n\n"
        "🎮 <b>Как начать играть:</b>\n"
        "1. Пополните баланс через раздел '💳 Пополнить'\n"
        "2. Получите ссылку на игровой чат у поддержки\n"
        "3. Войдите в игровой чат\n"
        "4. Кидайте эмодзи-кости в чат\n\n"
        
        "🎲 <b>Правила игр:</b>\n"
        "• 🎲 <b>Кубик (x2)</b> - победа если выпало 4-6\n"
        "• 🏀 <b>Баскетбол (x2.5)</b> - победа если выпало 4-5\n"
        "• 🎯 <b>Дартс (x2.5)</b> - победа если попал в центр (6)\n"
        "• 🎳 <b>Боулинг (x5)</b> - победа если страйк (6)\n"
        "• 🎰 <b>Слоты (x50)</b> - победа если джекпот (64)\n\n"
        
        "💸 <b>Вывод средств:</b>\n"
        "• Минимальный вывод: 1$\n"
        "• Комиссия: 0.5%\n"
        "• Время обработки: до 24 часов\n\n"
        
        "📞 <b>Поддержка:</b>\n"
        "По всем вопросам обращайтесь в раздел '👨‍💻 Поддержка'",
        reply_markup=main_menu_kb()
    )

# --- ПОДДЕРЖКА ---
@dp.callback_query(F.data == "support")
async def support(callback: CallbackQuery):
    await callback.message.edit_text(
        "👨‍💻 <b>Служба поддержки</b>\n\n"
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
    
    # Определяем минимальную ставку
    bet_amount = 0.1  # Минимальная ставка
    
    if user['balance'] < bet_amount:
        await message.reply(f"❌ Недостаточно средств! Минимальная ставка: {bet_amount}$. Пополните баланс.")
        return
    
    # Вычитаем ставку
    user['balance'] -= bet_amount
    user['games_played'] += 1
    add_transaction(user_id, 'loss', -bet_amount, details=f"Ставка в игре")
    
    # Ждем результат кубика (Telegram сам обрабатывает)
    await asyncio.sleep(4)
    
    # Получаем результат из сообщения с кубиком
    if message.dice:
        dice_value = message.dice.value
        emoji = message.dice.emoji
        
        win = False
        multiplier = 1.0
        
        # Проверяем выигрыш по эмодзи
        if emoji == "🎲":  # Кубик
            if dice_value > 3:  # 4, 5, 6
                win = True
                multiplier = 2.0
        elif emoji == "🏀":  # Баскетбол
            if dice_value in [4, 5]:
                win = True
                multiplier = 2.5
        elif emoji == "🎯":  # Дартс
            if dice_value == 6:  # Центр
                win = True
                multiplier = 2.5
        elif emoji == "🎳":  # Боулинг
            if dice_value == 6:  # Страйк
                win = True
                multiplier = 5.0
        elif emoji == "🎰":  # Слоты
            if dice_value == 64:  # Джекпот
                win = True
                multiplier = 50.0
        
        if win:
            win_amount = bet_amount * multiplier
            user['balance'] += win_amount
            user['games_won'] += 1
            add_transaction(user_id, 'win', win_amount, details=f"Выигрыш {multiplier}x")
            
            # Отправляем сообщение о выигрыше
            await message.reply(
                f"🎉 <b>ПОБЕДА!</b>\n\n"
                f"👤 Игрок: {message.from_user.first_name}\n"
                f"🎲 Выпало: {dice_value}\n"
                f"💰 Коэффициент: x{multiplier}\n"
                f"💵 Выигрыш: +{win_amount:.2f}$\n"
                f"🏦 Новый баланс: {user['balance']:.2f}$"
            )
        else:
            await message.reply(
                f"😢 <b>ПРОИГРЫШ</b>\n\n"
                f"👤 Игрок: {message.from_user.first_name}\n"
                f"🎲 Выпало: {dice_value}\n"
                f"💸 Потеряно: {bet_amount:.2f}$\n"
                f"🏦 Остаток: {user['balance']:.2f}$"
            )

# Регистрируем обработчик для кубиков в чатах
@dp.message(F.dice)
async def handle_dice(message: Message):
    await process_game_in_chat(message)

# --- АДМИН КОМАНДЫ ---
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    # Проверяем, является ли пользователь администратором
    admin_ids = []  # Добавьте ID администраторов
    
    if message.from_user.id not in admin_ids:
        return
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"),
         InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="💸 Выплаты", callback_data="admin_payouts"),
         InlineKeyboardButton(text="📊 Балансы", callback_data="admin_balances")]
    ])
    
    await message.answer("🛠 <b>Панель администратора</b>", reply_markup=keyboard)

# --- ЗАПУСК ---
async def main():
    print("🎰 FRK Casino Bot запущен!")
    print(f"🤖 Bot ID: {BOT_TOKEN[:10]}...")
    print(f"💰 Crypto токен: {CRYPTO_BOT_TOKEN[:10]}...")
    print("⚙️ Бот готов к работе!")
    
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
