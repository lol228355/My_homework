import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- НАСТРОЙКИ (ОБНОВЛЕНО) ---
API_TOKEN = '8137443845:AAFKkaiPG3Rv_TGCNh538VR7moAHSdFxQwU' 
# !!! СПИСОК ID АДМИНИСТРАТОРОВ !!!
ADMIN_IDS = [8111456168, 8394356460] 

PAYMENT_DETAILS = "2200702067950258" # Т-Банк / Сбер
MIN_ORDER_STARS = 10
RATE_STARS = 1.5 # 1 звезда = 1 рубль

# Ссылка на сотрудничество
LINK_COLLAB = "https://t.me/+KR5pOwkARI0wZGZi"

# Цены на Премиум 
PREM_PRICES = {
    "1m": 179,  # 1 месяц
    "6m": 899,  # 6 месяцев
    "1y": 1399  # 1 год
}

# --- СПИСОК NFT ---
NFT_PRICES = {
    "nft_anon_1": {"name": "+888 00 123 45", "price": 1500},
    "nft_anon_2": {"name": "+888 09 777 77", "price": 5000},
    "nft_user_1": {"name": "@king", "price": 99000},
    "nft_user_2": {"name": "@boss_shop", "price": 4500},
    "nft_punk":   {"name": "TON Punk #304", "price": 2300},
    "nft_diamond": {"name": "TON Diamond", "price": 7000},
    "nft_fish":   {"name": "Ton Fish #1", "price": 150},
    "nft_dns":    {"name": "wallet.ton", "price": 12000},
    "nft_rock":   {"name": "Ether Rock", "price": 500},
    "nft_cat":    {"name": "Rich Cat #55", "price": 800}
}

# Логирование
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- МАШИНА СОСТОЯНИЙ ---
class ShopState(StatesGroup):
    entering_stars_amount = State()
    confirm_payment = State()

# --- КЛАВИАТУРЫ ---

def kb_main_menu():
    buttons = [
        [InlineKeyboardButton(text="🌟 Купить Stars", callback_data="cat_stars")],
        [InlineKeyboardButton(text="💎 Premium", callback_data="cat_prem"),
         InlineKeyboardButton(text="🖼 NFT Market", callback_data="cat_nft")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_prem_menu():
    buttons = [
        [InlineKeyboardButton(text=f"🗓 1 Месяц - {PREM_PRICES['1m']}₽", callback_data="buy_prem_1m")],
        [InlineKeyboardButton(text=f"🗓 6 Месяцев - {PREM_PRICES['6m']}₽", callback_data="buy_prem_6m")],
        [InlineKeyboardButton(text=f"🗓 1 Год - {PREM_PRICES['1y']}₽", callback_data="buy_prem_1y")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_nft_menu():
    buttons = []
    row = []
    for key, val in NFT_PRICES.items():
        btn_text = f"{val['name']} — {val['price']}₽"
        row.append(InlineKeyboardButton(text=btn_text, callback_data=f"buy_nft_{key}"))
        
        if len(row) == 2:
            buttons.append(row)
            row = []
            
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_cancel():
    buttons = [[InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")]]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_check_payment():
    buttons = [
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data="paid_check")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_admin_decision(user_id, product_name):
    buttons = [
        [InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"admin_ok_{user_id}")],
        [InlineKeyboardButton(text="🚫 Отклонить", callback_data=f"admin_no_{user_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    text = (
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        f"🛒 Добро пожаловать в цифровой магазин.\n"
        f"🤝 <b>Партнер:</b> {LINK_COLLAB}\n\n"
        f"👇 Выберите категорию:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=kb_main_menu())

@dp.callback_query(F.data == "back_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Главное меню:", reply_markup=kb_main_menu())

# --- ЗВЕЗДЫ ---
@dp.callback_query(F.data == "cat_stars")
async def category_stars(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"🌟 <b>Покупка Stars</b>\n"
        f"Курс: 1 к {RATE_STARS}₽\n"
        f"Минимум: {MIN_ORDER_STARS} шт.\n\n"
        f"✍️ <b>Введите количество:</b>",
        parse_mode="HTML",
        reply_markup=kb_cancel()
    )
    await state.set_state(ShopState.entering_stars_amount)

@dp.message(StateFilter(ShopState.entering_stars_amount))
async def process_stars_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Введите число.", reply_markup=kb_cancel())
        return
    
    amount = int(message.text)
    if amount < MIN_ORDER_STARS:
        await message.answer(f"⚠️ Минимум {MIN_ORDER_STARS} звезд.", reply_markup=kb_cancel())
        return

    price = amount * RATE_STARS
    await state.update_data(product_type="stars", product_name=f"{amount} Stars", price=price)
    await send_invoice(message, f"{amount} Stars", price)
    await state.set_state(ShopState.confirm_payment)

# --- ПРЕМИУМ ---
@dp.callback_query(F.data == "cat_prem")
async def category_prem(callback: types.CallbackQuery):
    await callback.message.edit_text("💎 <b>Выберите период Premium:</b>", parse_mode="HTML", reply_markup=kb_prem_menu())

@dp.callback_query(F.data.startswith("buy_prem_"))
async def process_prem(callback: types.CallbackQuery, state: FSMContext):
    period = callback.data.split("_")[2]
    price = PREM_PRICES.get(period, 0)
    
    name_map = {"1m": "1 Месяц", "6m": "6 Месяцев", "1y": "1 Год"}
    name = f"Premium ({name_map.get(period)})"
    
    await state.update_data(product_type="premium", product_name=name, price=price)
    await send_invoice(callback.message, name, price)
    await state.set_state(ShopState.confirm_payment)

# --- NFT ---
@dp.callback_query(F.data == "cat_nft")
async def category_nft(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🖼 <b>Доступные NFT лоты:</b>\n"
        "Нажмите на товар для покупки.",
        parse_mode="HTML", 
        reply_markup=kb_nft_menu()
    )

@dp.callback_query(F.data.startswith("buy_nft_"))
async def process_nft(callback: types.CallbackQuery, state: FSMContext):
    nft_key = callback.data.split("buy_nft_")[1]
    item = NFT_PRICES.get(nft_key)
    
    if not item:
        await callback.answer("Ошибка")
        return

    await state.update_data(product_type="nft", product_name=item['name'], price=item['price'])
    await send_invoice(callback.message, item['name'], item['price'])
    await state.set_state(ShopState.confirm_payment)

# --- ФУНКЦИИ ОПЛАТЫ ---
async def send_invoice(message: types.Message, product_name, price):
    text = (
        f"🧾 <b>СЧЕТ НА ОПЛАТУ</b>\n\n"
        f"🛍 <b>{product_name}</b>\n"
        f"💰 <b>{int(price)}₽</b>\n\n"
        f"💳 <b>Реквизиты:</b>\n"
        f"<code>{PAYMENT_DETAILS}</code>\n\n"
        f"⚠️ Оплатите точную сумму и нажмите кнопку подтверждения."
    )
    try:
        await message.edit_text(text, parse_mode="HTML", reply_markup=kb_check_payment())
    except:
        await message.answer(text, parse_mode="HTML", reply_markup=kb_check_payment())

@dp.callback_query(F.data == "paid_check", StateFilter(ShopState.confirm_payment))
async def user_paid(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product = data.get('product_name')
    price = data.get('price')
    user = callback.from_user

    await callback.message.edit_text("⏳ <b>Проверка платежа...</b>\nОжидайте выдачи товара.", parse_mode="HTML")

    # Уведомление админам (МНОЖЕСТВЕННАЯ ОТПРАВКА)
    msg = (
        f"🚨 <b>НОВАЯ ПОКУПКА!</b>\n"
        f"👤 Клиент: {user.full_name} (@{user.username})\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"🛍 Товар: <b>{product}</b>\n"
        f"💰 Сумма: <b>{int(price)}₽</b>"
    )
    
    # Отправляем сообщение каждому администратору
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, msg, parse_mode="HTML", reply_markup=kb_admin_decision(user.id, product))
        except Exception as e:
            logging.error(f"Err sending to admin {admin_id}: {e}")
    
    await state.clear()

# --- АДМИНКА (ПРОВЕРКА) ---
@dp.callback_query(F.data.startswith("admin_ok_"))
async def admin_ok(callback: types.CallbackQuery):
    # Проверяем, что ID нажавшего есть в списке администраторов
    if callback.from_user.id not in ADMIN_IDS: 
        await callback.answer("Вы не администратор!", show_alert=True)
        return
        
    uid = int(callback.data.split("_")[2])
    await callback.message.edit_text("✅ Выдано.")
    try:
        await bot.send_message(uid, "✅ <b>Оплата получена!</b>\nТовар выдан/отправлен.", parse_mode="HTML")
    except: pass

@dp.callback_query(F.data.startswith("admin_no_"))
async def admin_no(callback: types.CallbackQuery):
    # Проверяем, что ID нажавшего есть в списке администраторов
    if callback.from_user.id not in ADMIN_IDS: 
        await callback.answer("Вы не администратор!", show_alert=True)
        return

    uid = int(callback.data.split("_")[2])
    await callback.message.edit_text("❌ Отклонено.")
    try:
        await bot.send_message(uid, "❌ <b>Платеж не найден.</b>", parse_mode="HTML")
    except: pass

async def main():
    print("Бот запущен...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
