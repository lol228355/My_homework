import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiocryptopay import AioCryptoPay, Networks

# --- ⚙️ КОНФИГУРАЦИЯ ---
# ВСТАВЬТЕ СЮДА НОВЫЕ ТОКЕНЫ!
BOT_TOKEN = "ВАШ_НОВЫЙ_ТОКЕН"
CRYPTO_BOT_TOKEN = "ВАШ_НОВЫЙ_КРИПТО_ТОКЕН"
HEADER_IMG_URL = "https://media1.tenor.com/m/JgYc2sQz9ZAAAAAC/money-cash.gif"

logging.basicConfig(level=logging.INFO)

# Инициализация
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
crypto = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)

user_db = {}

def get_user(user_id):
    if user_id not in user_db:
        user_db[user_id] = {'balance': 0.0, 'last_invoice_id': None}
    return user_db[user_id]

class BotStates(StatesGroup):
    waiting_for_bet_amount = State()
    waiting_for_deposit_amount = State()

def format_balance(amount):
    return f"<b>{amount:.2f} $</b>"

async def send_styled_message(target, text, reply_markup=None, show_header=True):
    formatted_text = f"<blockquote>👾 <b>Выберите действие:</b> ❞</blockquote>\n\n{text}"
    user_id = target.from_user.id
    
    if isinstance(target, CallbackQuery):
        try:
            await target.message.delete()
        except:
            pass
            
    if show_header:
        await bot.send_animation(chat_id=user_id, animation=HEADER_IMG_URL, caption=formatted_text, reply_markup=reply_markup)
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

def back_to_main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◀️ Меню", callback_data="main_menu")]])

def check_payment_kb(url):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Оплатить", url=url)],
        [InlineKeyboardButton(text="✅ Проверить", callback_data="check_deposit_status")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
    ])

# --- ХЕНДЛЕРЫ ---
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user = get_user(message.from_user.id)
    await send_styled_message(message, f"Привет! Твой баланс: {format_balance(user['balance'])}", main_menu_kb())

@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user = get_user(callback.from_user.id)
    await send_styled_message(callback, f"Главное меню\nБаланс: {format_balance(user['balance'])}", main_menu_kb())

@dp.callback_query(F.data == "deposit_start")
async def dep_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BotStates.waiting_for_deposit_amount)
    await callback.message.answer("Введите сумму пополнения в $ (мин 0.1):")

@dp.message(BotStates.waiting_for_deposit_amount)
async def dep_proc(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
        invoice = await crypto.create_invoice(asset='USDT', amount=amount)
        get_user(message.from_user.id)['last_invoice_id'] = invoice.invoice_id
        await message.answer(f"Счет на {amount} USDT создан:", reply_markup=check_payment_kb(invoice.pay_url))
        await state.clear()
    except:
        await message.answer("Ошибка. Введите число.")

@dp.callback_query(F.data == "check_deposit_status")
async def check_dep(callback: CallbackQuery):
    user = get_user(callback.from_user.id)
    inv_id = user['last_invoice_id']
    if inv_id:
        invoices = await crypto.get_invoices(invoice_ids=[inv_id])
        if invoices and invoices[0].status == 'paid':
            amt = float(invoices[0].amount)
            user['balance'] += amt
            user['last_invoice_id'] = None
            await callback.answer(f"Зачислено {amt}$!", show_alert=True)
            await cb_main_menu(callback, None)
            return
    await callback.answer("Оплата не найдена.")

@dp.callback_query(F.data == "menu_darts")
async def d_menu(callback: CallbackQuery):
    await send_styled_message(callback, "🎯 Выберите исход:", darts_menu_kb())

@dp.callback_query(F.data.startswith("bets_darts_"))
async def d_bet(callback: CallbackQuery, state: FSMContext):
    await state.update_data(game_mode="darts", bet_target=callback.data.split("_")[2])
    await state.set_state(BotStates.waiting_for_bet_amount)
    await callback.message.answer("Введите сумму ставки:")

@dp.callback_query(F.data.startswith("sel_"))
async def s_game(callback: CallbackQuery, state: FSMContext):
    await state.update_data(game_mode=callback.data.split("_")[1], bet_target="any")
    await state.set_state(BotStates.waiting_for_bet_amount)
    await callback.message.answer("Введите сумму ставки:")

@dp.message(BotStates.waiting_for_bet_amount)
async def game_proc(message: Message, state: FSMContext):
    try:
        bet = float(message.text.replace(',', '.'))
        user = get_user(message.from_user.id)
        if bet > user['balance'] or bet < 0.1:
            await message.answer("Недостаточно средств или неверная сумма.")
            return
        
        user['balance'] -= bet
        data = await state.get_data()
        mode, target = data['game_mode'], data['bet_target']
        
        msg = await message.answer_dice(emoji={"dice":"🎲","basketball":"🏀","darts":"🎯","bowling":"🎳","slot":"🎰"}.get(mode, "🎲"))
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
            user['balance'] += bet * coeff
            await message.answer(f"Победа! +{bet*coeff:.2f}$")
        else:
            await message.answer("Проигрыш.")
        await state.clear()
        await cmd_start(message)
    except:
        await message.answer("Ошибка. Введите число.")

# --- ВАЖНАЯ ЧАСТЬ: ЗАПУСК ---
async def main():
    print("--- БОТ ЗАПУЩЕН (LOG CHECK) ---") # Это появится в логах
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Бот остановлен")
