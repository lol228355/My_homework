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

# --- ⚙️ КОНФИГУРАЦИЯ ---
BOT_TOKEN = "8315937988:AAHaKhMNy0t-uXQjSumvkDk3nf2vyTHf63U"
CRYPTO_BOT_TOKEN = "505642:AATEFAUIQ3OE9ihgalDaLzhI4u7uH2CY0X5"

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

# Временная база данных в оперативной памяти
user_db = {}

def get_user(user_id):
    if user_id not in user_db:
        user_db[user_id] = {'balance': 0.0, 'last_invoice_id': None}
    return user_db[user_id]

# Состояния FSM
class BotStates(StatesGroup):
    waiting_for_bet_amount = State()
    waiting_for_deposit_amount = State()

def format_balance(amount):
    return f"<b>{amount:.2f} $</b>"

# Функция для извлечения числа из текста
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

# Функция для стилизации сообщений
async def send_styled_message(target, text, reply_markup=None):
    formatted_text = f"<blockquote>👾 <b>Emoji Casino</b> ❞</blockquote>\n\n{text}"
    user_id = target.from_user.id
    
    if isinstance(target, CallbackQuery):
        try:
            await target.message.edit_text(text=formatted_text, reply_markup=reply_markup)
        except:
            await bot.send_message(chat_id=user_id, text=formatted_text, reply_markup=reply_markup)
    else:
        await bot.send_message(chat_id=user_id, text=formatted_text, reply_markup=reply_markup)

# --- КЛАВИАТУРЫ ---
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎲 Кубик (x2)", callback_data="sel_dice"),
         InlineKeyboardButton(text="🏀 Баскет (x2.5)", callback_data="sel_basketball")],
        [InlineKeyboardButton(text="🎯 Дартс (Меню)", callback_data="menu_darts"),
         InlineKeyboardButton(text="🎳 Боулинг (x5)", callback_data="sel_bowling")],
        [InlineKeyboardButton(text="🎰 Слоты (x50)", callback_data="sel_slot")],
        [InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit_start"),
         InlineKeyboardButton(text="💰 Баланс", callback_data="check_balance")]
    ])

def darts_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Мимо | 2.5x", callback_data="bets_darts_miss"),
         InlineKeyboardButton(text="Красное | 1.7x", callback_data="bets_darts_red")],
        [InlineKeyboardButton(text="Белое | 1.7x", callback_data="bets_darts_white"),
         InlineKeyboardButton(text="Центр | 2.5x", callback_data="bets_darts_bullseye")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")]
    ])

def check_payment_kb(pay_url):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Оплатить через CryptoBot", url=pay_url)],
        [InlineKeyboardButton(text="✅ Проверить оплату", callback_data="check_deposit_status")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
    ])

def cancel_deposit_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
    ])

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user = get_user(message.from_user.id)
    await send_styled_message(message, f"Добро пожаловать!\n\n💰 Твой баланс: {format_balance(user['balance'])}", main_menu_kb())

@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = get_user(callback.from_user.id)
    await send_styled_message(callback, f"Главное меню\n💰 Баланс: {format_balance(user['balance'])}", main_menu_kb())

@dp.callback_query(F.data == "check_balance")
async def cb_bal(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    await callback.answer(f"Ваш баланс: {user['balance']:.2f}$", show_alert=True)

# Логика пополнения - ИСПРАВЛЕННАЯ ВЕРСИЯ
@dp.callback_query(F.data == "deposit_start")
async def dep_start(callback: CallbackQuery, state: FSMContext):
    if crypto is None:
        await callback.answer("❌ Сервис оплаты временно недоступен", show_alert=True)
        return
    await state.set_state(BotStates.waiting_for_deposit_amount)
    await send_styled_message(callback, 
        "💵 <b>Введите сумму пополнения</b>\n\n"
        "Минимальная сумма: <b>0.1 $</b>\n"
        "Максимальная сумма: <b>10000 $</b>\n\n"
        "Примеры ввода:\n"
        "• <code>10</code>\n"
        "• <code>5.50</code>\n"
        "• <code>2,75</code>", 
        cancel_deposit_kb()
    )

@dp.message(BotStates.waiting_for_deposit_amount)
async def dep_proc(message: Message, state: FSMContext):
    if crypto is None:
        await message.answer("❌ Сервис оплаты временно недоступен")
        return
    
    amount = extract_number(message.text)
    
    if amount is None:
        await message.answer("❌ <b>Неверный формат!</b>\n\nПожалуйста, введите число.\nПример: <code>10</code> или <code>5.50</code>")
        return
    
    if amount < 0.1:
        await message.answer(f"❌ <b>Сумма слишком мала!</b>\n\nМинимальная сумма пополнения: <b>0.1 $</b>")
        return
    
    if amount > 10000:
        await message.answer(f"❌ <b>Сумма слишком велика!</b>\n\nМаксимальная сумма пополнения: <b>10000 $</b>")
        return
    
    try:
        user = get_user(message.from_user.id)
        
        # Создаем счет - ПРАВИЛЬНЫЙ СПОСОБ
        invoice = await crypto.create_invoice(asset='USDT', amount=amount)
        
        # Получаем ссылку на оплату ПРАВИЛЬНЫМ способом
        # Проверяем доступные атрибуты
        logger.info(f"Инвойс создан: {invoice}")
        logger.info(f"Атрибуты инвойса: {dir(invoice)}")
        
        # Попробуем разные варианты получения ссылки
        pay_url = None
        
        # Вариант 1: проверяем атрибут 'url'
        if hasattr(invoice, 'url'):
            pay_url = invoice.url
        
        # Вариант 2: проверяем атрибут 'pay_url' (старый вариант)
        elif hasattr(invoice, 'pay_url'):
            pay_url = invoice.pay_url
        
        # Вариант 3: если есть bot_invoice_url (для ссылки на бота)
        elif hasattr(invoice, 'bot_invoice_url'):
            pay_url = invoice.bot_invoice_url
        
        # Вариант 4: получаем через bot_url (если есть)
        elif hasattr(invoice, 'bot_url'):
            pay_url = invoice.bot_url
        
        # Вариант 5: смотрим в invoice.data если это словарь
        elif hasattr(invoice, 'data') and isinstance(invoice.data, dict):
            if 'url' in invoice.data:
                pay_url = invoice.data['url']
            elif 'pay_url' in invoice.data:
                pay_url = invoice.data['pay_url']
        
        if not pay_url:
            # Если не нашли ссылку, создаем через API CryptoBot напрямую
            logger.warning("Не найдена ссылка в объекте инвойса")
            await message.answer(
                f"✅ <b>Счет создан!</b>\n\n"
                f"💳 Сумма: <b>{amount:.2f} $</b>\n"
                f"📝 ID счета: <code>{invoice.invoice_id}</code>\n\n"
                f"Для оплаты перейдите в @CryptoBot и введите команду:\n"
                f"<code>/pay {invoice.invoice_id}</code>"
            )
            user['last_invoice_id'] = invoice.invoice_id
            await state.clear()
            return
        
        # Сохраняем ID счета
        user['last_invoice_id'] = invoice.invoice_id
        
        await message.answer(
            f"✅ <b>Счет создан!</b>\n\n"
            f"💳 Сумма: <b>{amount:.2f} $</b>\n"
            f"📝 ID счета: <code>{invoice.invoice_id}</code>\n\n"
            f"Нажмите на кнопку ниже для оплаты:",
            reply_markup=check_payment_kb(pay_url)
        )
        await state.clear()
        
    except Exception as e:
        logger.error(f"Ошибка при создании счета: {e}")
        await message.answer(
            f"❌ <b>Ошибка при создании счета:</b>\n\n"
            f"<code>{str(e)}</code>\n\n"
            f"Попробуйте еще раз или обратитесь в поддержку."
        )

@dp.callback_query(F.data == "check_deposit_status")
async def check_dep(callback: CallbackQuery):
    if crypto is None:
        await callback.answer("❌ Сервис оплаты временно недоступен", show_alert=True)
        return
    
    user = get_user(callback.from_user.id)
    inv_id = user.get('last_invoice_id')
    
    if not inv_id:
        await callback.answer("❌ Не найден активный счет для проверки", show_alert=True)
        return
    
    try:
        invoices = await crypto.get_invoices(invoice_ids=[inv_id])
        
        if not invoices:
            await callback.answer("❌ Счет не найден", show_alert=True)
            return
        
        invoice = invoices[0]
        
        # Проверяем статус счета
        if hasattr(invoice, 'status'):
            status = invoice.status
        elif hasattr(invoice, 'paid'):
            status = 'paid' if invoice.paid else 'active'
        else:
            status = 'unknown'
        
        if status == 'paid':
            amt = float(invoice.amount)
            user['balance'] += amt
            user['last_invoice_id'] = None
            await callback.answer(f"✅ Успешно! Зачислено {amt:.2f}$", show_alert=True)
            await cb_main_menu(callback, None)
        elif status == 'active':
            await callback.answer("⏳ Счет ожидает оплаты", show_alert=True)
        elif status == 'expired':
            await callback.answer("❌ Счет истек", show_alert=True)
            user['last_invoice_id'] = None
        else:
            await callback.answer(f"Статус: {status}", show_alert=True)
            
    except Exception as e:
        logger.error(f"Ошибка при проверке счета: {e}")
        await callback.answer("❌ Ошибка при проверке статуса", show_alert=True)

# Обработчики игр (без изменений)
@dp.callback_query(F.data == "menu_darts")
async def d_menu(callback: CallbackQuery):
    await send_styled_message(callback, "🎯 <b>Дартс</b>\nВыберите, куда попадет дротик:", darts_menu_kb())

@dp.callback_query(F.data.startswith("bets_darts_"))
async def d_bet(callback: CallbackQuery, state: FSMContext):
    await state.update_data(game_mode="darts", bet_target=callback.data.split("_")[2])
    await state.set_state(BotStates.waiting_for_bet_amount)
    await callback.message.answer("💸 Введите сумму вашей ставки:")

@dp.callback_query(F.data.startswith("sel_"))
async def s_game(callback: CallbackQuery, state: FSMContext):
    await state.update_data(game_mode=callback.data.split("_")[1], bet_target="any")
    await state.set_state(BotStates.waiting_for_bet_amount)
    await callback.message.answer("💸 Введите сумму вашей ставки:")

@dp.message(BotStates.waiting_for_bet_amount)
async def game_proc(message: Message, state: FSMContext):
    try:
        bet = extract_number(message.text)
        
        if bet is None:
            await message.answer("⚠️ Пожалуйста, введите числовое значение ставки.")
            return
            
        user = get_user(message.from_user.id)
        
        if bet > user['balance']:
            await message.answer(f"❌ Недостаточно средств!\nВаш баланс: {user['balance']:.2f}$")
            return
            
        if bet < 0.1:
            await message.answer(f"❌ Минимальная ставка: 0.1$")
            return
        
        user['balance'] -= bet
        data = await state.get_data()
        mode, target = data['game_mode'], data['bet_target']
        
        emoji_choice = {"dice":"🎲","basketball":"🏀","darts":"🎯","bowling":"🎳","slot":"🎰"}.get(mode, "🎲")
        msg = await message.answer_dice(emoji=emoji_choice)
        await asyncio.sleep(4)
        val = msg.dice.value
        
        win, coeff = False, 0.0
        if mode == "darts":
            if target=="miss" and val==1: win, coeff = True, 2.5
            elif target=="white" and val in [2,4]: win, coeff = True, 1.7
            elif target=="red" and val in [3,5]: win, coeff = True, 1.7
            elif target=="bullseye" and val==6: win, coeff = True, 2.5
        elif mode=="dice" and val > 3: win, coeff = True, 2.0
        elif mode=="basketball" and val in [4,5]: win, coeff = True, 2.5
        elif mode=="bowling" and val==6: win, coeff = True, 5.0
        elif mode=="slot" and val==64: win, coeff = True, 50.0

        if win:
            prize = bet * coeff
            user['balance'] += prize
            await message.answer(f"🎉 <b>ПОБЕДА!</b>\nВыигрыш: +{prize:.2f}$")
        else:
            await message.answer(f"😢 <b>Проигрыш.</b>\nВыпало: {val}")
            
        await state.clear()
        await asyncio.sleep(1)
        await cmd_start(message, state)
    except Exception as e:
        logger.error(f"Ошибка в игре: {e}")
        await message.answer("⚠️ Произошла ошибка. Попробуйте еще раз.")

# Запуск
async def main():
    print("--- БОТ ЗАПУЩЕН ---")
    print(f"Crypto токен: {CRYPTO_BOT_TOKEN[:10]}...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
