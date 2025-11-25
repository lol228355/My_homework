import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- НАСТРОЙКИ ---
API_TOKEN = '8137443845:AAFKkaiPG3Rv_TGCNh538VR7moAHSdFxQwU' 
ADMIN_ID = 8111456168
PAYMENT_DETAILS = "2200702067950258" # Сбер/Т-Банк
MIN_ORDER_STARS = 50 
RATE_STARS = 1.0 # 1 звезда = 1 рубль

# Цены на Премиум (в рублях)
PREM_PRICES = {
    "1m": 399,   # 1 месяц
    "6m": 1190,  # 6 месяцев
    "1y": 1990   # 1 год
}

# Цены на NFT (пример)
NFT_PRICES = {
    "nft1": {"name": "Anon Number #1337", "price": 500},
    "nft2": {"name": "Username @boss", "price": 5000}
}

# Ссылка на поддержку
LINK_SUPPORT = "https://t.me/username" # ЗАМЕНИ НА СВОЙ ЮЗЕРНЕЙМ
LINK_COLLAB = "https://t.me/+KR5pOwkARI0wZGZi"

# Логирование
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- МАШИНА СОСТОЯНИЙ ---
class ShopState(StatesGroup):
    entering_stars_amount = State() # Ждем ввода числа звезд
    confirm_payment = State()       # Ждем нажатия "Я оплатил"

# --- КЛАВИАТУРЫ ---

def kb_main_menu():
    buttons = [
        [InlineKeyboardButton(text="🌟 Купить Stars", callback_data="cat_stars")],
        [InlineKeyboardButton(text="💎 Купить Premium", callback_data="cat_prem"),
         InlineKeyboardButton(text="🖼 Купить NFT", callback_data="cat_nft")],
        [InlineKeyboardButton(text="💬 Поддержка", url=LINK_SUPPORT)]
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
    # Генерируем кнопки на основе словаря NFT_PRICES
    buttons = []
    for key, val in NFT_PRICES.items():
        btn_text = f"{val['name']} — {val['price']}₽"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=f"buy_nft_{key}")])
    
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

# --- ХЕНДЛЕРЫ: МЕНЮ ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    text = (
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        f"💎 Магазин цифровых товаров.\n"
        f"🤝 <b>Мы сотрудничаем с:</b> {LINK_COLLAB}\n\n"
        f"Выберите категорию товара:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=kb_main_menu())

@dp.callback_query(F.data == "back_main")
async def back_to_main(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Главное меню:", reply_markup=kb_main_menu())

# --- ХЕНДЛЕРЫ: ЗВЕЗДЫ ---

@dp.callback_query(F.data == "cat_stars")
async def category_stars(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        f"🌟 <b>Покупка Telegram Stars</b>\n"
        f"Курс: 1 звезда = {RATE_STARS}₽\n"
        f"Минимум: {MIN_ORDER_STARS} шт.\n\n"
        f"✍️ <b>Введите количество звезд:</b>",
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
    
    # Сохраняем: тип товара, название, цену
    await state.update_data(
        product_type="stars",
        product_name=f"{amount} Stars",
        price=price
    )
    
    await send_invoice(message, f"{amount} Stars", price)
    await state.set_state(ShopState.confirm_payment)

# --- ХЕНДЛЕРЫ: ПРЕМИУМ ---

@dp.callback_query(F.data == "cat_prem")
async def category_prem(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "💎 <b>Telegram Premium</b>\n"
        "Выберите срок подписки:",
        parse_mode="HTML",
        reply_markup=kb_prem_menu()
    )

@dp.callback_query(F.data.startswith("buy_prem_"))
async def process_prem_selection(callback: types.CallbackQuery, state: FSMContext):
    period = callback.data.split("_")[2] # "1m", "6m" или "1y"
    price = PREM_PRICES.get(period, 0)
    
    name_map = {"1m": "Premium 1 мес", "6m": "Premium 6 мес", "1y": "Premium 1 год"}
    product_name = name_map.get(period, "Premium")

    await state.update_data(product_type="premium", product_name=product_name, price=price)
    await send_invoice(callback.message, product_name, price)
    await state.set_state(ShopState.confirm_payment)

# --- ХЕНДЛЕРЫ: NFT ---

@dp.callback_query(F.data == "cat_nft")
async def category_nft(callback: types.CallbackQuery):
    await callback.message.edit_text(
        "🖼 <b>Магазин NFT</b>\n"
        "Выберите доступный лот:",
        parse_mode="HTML",
        reply_markup=kb_nft_menu()
    )

@dp.callback_query(F.data.startswith("buy_nft_"))
async def process_nft_selection(callback: types.CallbackQuery, state: FSMContext):
    nft_key = callback.data.split("buy_nft_")[1]
    item = NFT_PRICES.get(nft_key)
    
    if not item:
        await callback.answer("Ошибка товара")
        return

    await state.update_data(product_type="nft", product_name=item['name'], price=item['price'])
    await send_invoice(callback.message, item['name'], item['price'])
    await state.set_state(ShopState.confirm_payment)

# --- ОБЩАЯ ФУНКЦИЯ ВЫСТАВЛЕНИЯ СЧЕТА ---

async def send_invoice(message: types.Message, product_name, price):
    text = (
        f"🧾 <b>Счет на оплату</b>\n\n"
        f"🛍 Товар: <b>{product_name}</b>\n"
        f"💰 К оплате: <b>{int(price)}₽</b>\n\n"
        f"💳 <b>Реквизиты (Сбер/Т-Банк):</b>\n"
        f"<code>{PAYMENT_DETAILS}</code>\n\n"
        f"⚠️ После перевода нажмите кнопку «Я оплатил»."
    )
    # Если вызываем из callback, message нужно редактировать, если из текста - отправлять
    try:
        await message.edit_text(text, parse_mode="HTML", reply_markup=kb_check_payment())
    except:
        await message.answer(text, parse_mode="HTML", reply_markup=kb_check_payment())

# --- ПОДТВЕРЖДЕНИЕ ОПЛАТЫ ---

@dp.callback_query(F.data == "paid_check", StateFilter(ShopState.confirm_payment))
async def user_paid(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product_name = data.get('product_name')
    price = data.get('price')
    user = callback.from_user

    # Сообщение юзеру
    await callback.message.edit_text(
        "⏳ <b>Платеж проверяется...</b>\n"
        "Администратор скоро проверит поступление средств и выдаст товар.",
        parse_mode="HTML"
    )

    # Сообщение админу
    admin_text = (
        f"🚨 <b>НОВАЯ ПОКУПКА!</b>\n"
        f"👤 Клиент: {user.full_name} (@{user.username})\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"🛍 Товар: <b>{product_name}</b>\n"
        f"💰 Сумма: <b>{int(price)}₽</b>\n\n"
        f"👉 Проверь поступление на карту!"
    )

    try:
        # Сохраняем имя товара в кнопку, чтобы админ знал, что подтверждает (упрощенно)
        # В реальном проекте лучше хранить ID заказа в базе данных
        await bot.send_message(
            ADMIN_ID, 
            admin_text, 
            parse_mode="HTML", 
            reply_markup=kb_admin_decision(user.id, product_name)
        )
    except Exception as e:
        logging.error(f"Ошибка отправки админу: {e}")

    await state.clear()

# --- АДМИНСКИЕ КНОПКИ ---

@dp.callback_query(F.data.startswith("admin_ok_"))
async def admin_ok(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return
    
    user_id = int(callback.data.split("_")[2])
    
    await callback.message.edit_text(f"✅ Заказ для {user_id} подтвержден.")
    
    try:
        await bot.send_message(
            user_id,
            "✅ <b>Оплата подтверждена!</b>\n"
            "Ваш товар будет выдан в ближайшее время (или уже отправлен).\n"
            "Спасибо за покупку!",
            parse_mode="HTML"
        )
    except:
        pass

@dp.callback_query(F.data.startswith("admin_no_"))
async def admin_no(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return

    user_id = int(callback.data.split("_")[2])
    
    await callback.message.edit_text(f"❌ Заказ для {user_id} отклонен.")
    
    try:
        await bot.send_message(
            user_id,
            "❌ <b>Оплата не найдена.</b>\n"
            "Если произошла ошибка, напишите в поддержку.",
            parse_mode="HTML"
        )
    except:
        pass

async def main():
    print("Бот запущен...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен.")
