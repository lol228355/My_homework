import asyncio
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# --- НАСТРОЙКИ ---
API_TOKEN = 'ТВОЙ_ТОКЕН_ОТ_BOTFATHER'
ADMIN_ID = 123456789  # Твой цифровой ID (возьми в @userinfobot)
PAYMENT_DETAILS = "1234 5678 0000 0000 (Сбербанк)" # Твои реквизиты
MIN_ORDER = 50  # Минимальная сумма
RATE = 1.0  # Курс 1 звезда = 1 рубль

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Инициализация
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- МАШИНА СОСТОЯНИЙ ---
class BuyStars(StatesGroup):
    entering_amount = State()
    confirm_payment = State()

# --- КЛАВИАТУРЫ ---
def main_menu():
    kb = [
        [InlineKeyboardButton(text="🌟 Купить Звезды", callback_data="buy_start")],
        [InlineKeyboardButton(text="💬 Поддержка", url="https://t.me/ТВОЙ_ЮЗЕРНЕЙМ"),
         InlineKeyboardButton(text="📜 Отзывы", url="https://t.me/ТВОЙ_КАНАЛ")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def check_payment_kb():
    kb = [
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data="paid_check")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_confirm_kb(user_id, amount):
    kb = [
        [InlineKeyboardButton(text="✅ Подтвердить и отправить", callback_data=f"admin_ok_{user_id}_{amount}")],
        [InlineKeyboardButton(text="🚫 Фейк / Не пришли", callback_data=f"admin_no_{user_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- ХЕНДЛЕРЫ (ОБРАБОТЧИКИ) ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    text = (
        f"👋 <b>Привет, {message.from_user.first_name}!</b>\n\n"
        f"🤖 Это официальный бот по продаже Telegram Stars.\n"
        f"⚡️ <b>Моментальная автоматическая выдача.</b>\n\n"
        f"💎 <b>Курс:</b> 1 Звезда = {RATE}₽\n"
        f"📉 <b>Минимальный заказ:</b> {MIN_ORDER} звезд.\n\n"
        f"👇 Выберите действие ниже:"
    )
    await message.answer(text, parse_mode="HTML", reply_markup=main_menu())

@dp.callback_query(F.data == "buy_start")
async def start_buy(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✍️ <b>Введите количество звезд</b>, которое хотите купить.\n"
        f"<i>Минимум: {MIN_ORDER} шт.</i>",
        parse_mode="HTML"
    )
    await state.set_state(BuyStars.entering_amount)

@dp.message(BuyStars.entering_amount)
async def process_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("⚠️ Пожалуйста, введите только число.")
        return
    
    amount = int(message.text)
    
    if amount < MIN_ORDER:
        await message.answer(f"⚠️ Минимальная сумма заказа: <b>{MIN_ORDER} звезд</b>.", parse_mode="HTML")
        return

    price = amount * RATE
    
    # Сохраняем данные заказа
    await state.update_data(amount=amount, price=price)
    
    text = (
        f"🧾 <b>Сформирован счет на оплату</b>\n\n"
        f"⭐️ Товар: <b>{amount} Telegram Stars</b>\n"
        f"💰 К оплате: <b>{int(price)}₽</b>\n\n"
        f"💳 <b>Реквизиты для оплаты:</b>\n"
        f"<code>{PAYMENT_DETAILS}</code>\n\n"
        f"❗️ <i>После перевода обязательно нажмите кнопку «Я оплатил». Система проверит платеж автоматически в течение 1-2 минут.</i>"
    )
    
    await message.answer(text, parse_mode="HTML", reply_markup=check_payment_kb())
    await state.set_state(BuyStars.confirm_payment)

@dp.callback_query(F.data == "cancel", BuyStars.confirm_payment)
async def cancel_buy(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Покупка отменена.", reply_markup=None)
    await callback.message.answer("Главное меню:", reply_markup=main_menu())

@dp.callback_query(F.data == "paid_check", BuyStars.confirm_payment)
async def user_paid(callback: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    amount = user_data.get('amount')
    price = user_data.get('price')
    user = callback.from_user
    
    await callback.message.edit_text(
        "⏳ <b>Платеж проверяется системой...</b>\n"
        "Это может занять от 1 до 5 минут.\n"
        "Пожалуйста, не блокируйте бота.",
        parse_mode="HTML"
    )
    
    # Уведомление админу
    admin_text = (
        f"🚨 <b>НОВАЯ ЗАЯВКА!</b>\n"
        f"👤 Юзер: {user.full_name} (@{user.username})\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"💎 Звезды: {amount}\n"
        f"💰 Сумма: {price}₽\n\n"
        f"Проверь банк. Если деньги пришли — жми кнопку."
    )
    try:
        await bot.send_message(ADMIN_ID, admin_text, parse_mode="HTML", reply_markup=admin_confirm_kb(user.id, amount))
    exceptException as e:
        print(f"Ошибка отправки админу: {e}")

    await state.clear()

# --- АДМИНСКАЯ ЧАСТЬ ---

@dp.callback_query(F.data.startswith("admin_ok_"))
async def admin_approve(callback: types.CallbackQuery):
    # Парсим данные из кнопки
    _, _, user_id, amount = callback.data.split("_")
    
    # Убираем кнопки у админа
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(f"✅ Вы подтвердили выдачу {amount} звезд пользователю {user_id}.")
    
    # Сообщение пользователю
    success_text = (
        f"✅ <b>Оплата успешно подтверждена!</b>\n\n"
        f"⭐️ {amount} Telegram Stars были отправлены на ваш аккаунт.\n"
        f"Спасибо за покупку!"
    )
    try:
        await bot.send_message(chat_id=user_id, text=success_text, parse_mode="HTML")
    except Exception as e:
        await callback.message.answer(f"⚠️ Не удалось отправить сообщение юзеру (возможно заблокировал бота).")

@dp.callback_query(F.data.startswith("admin_no_"))
async def admin_reject(callback: types.CallbackQuery):
    _, _, user_id = callback.data.split("_")
    
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("❌ Заявка отклонена.")
    
    try:
        await bot.send_message(chat_id=user_id, text="❌ <b>Оплата не найдена.</b> Заявка отменена. Если это ошибка - напишите в поддержку.", parse_mode="HTML")
    except:
        pass

# Запуск
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
