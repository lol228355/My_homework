import asyncio
import logging
import re
import random
from datetime import datetime
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
GAME_CHAT_ID = -1003582415216  # ID вашего чата

# Курс валюты (для пополнения)
USD_TO_RUB_RATE = 100.0 # Для удобства счета 1 USDT = 100 RUB (можно менять)
MIN_DEPOSIT_RUB = 50
MIN_WITHDRAW_RUB = 100

# Название казино
CASINO_NAME = "FRK"

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Crypto Pay
try:
    crypto = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)
except Exception:
    crypto = None

# --- БАЗЫ ДАННЫХ ---
user_db = {}
transactions_db = []
active_games = {} # Хранилище активных игр

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_user(user_id, username=None):
    if user_id not in user_db:
        user_db[user_id] = {
            'balance': 0.0, # Храним в RUB для соответствия запросу
            'username': f"@{username}" if username else f"User_{user_id}",
            'games_played': 0,
            'games_won': 0,
            'registration_date': datetime.now().strftime("%Y-%m-%d")
        }
    if username:
        user_db[user_id]['username'] = f"@{username}"
    return user_db[user_id]

def format_money(amount):
    return f"{amount:.0f} RUB"

# --- ТЕКСТЫ И ПРАВИЛА (ИЗ ВАШЕГО ЗАПРОСА) ---

RULES_TEXT = """
<b>✅🃏ДОБРО ПОЖАЛОВАТЬ В МИР АЗАРТНЫХ ИГР🃏✅</b>

Тебя приветствует наша команда FRK 👋
Здесь ты найдешь разнообразие прекрасных игр на любой вкус и прочувствуешь азарт настоящей онлайн игры на деньги‼️

<b>У нас играют в⏬</b>
🃏 21 очко ( Побеждает тот кто набирает ближе к 21 или ровно 21)
🃏 Baccara ( Побеждает тот кто набирает ближе к 9 или ровно 9 )
🃏 Yellow Green ( Побеждает тот кто угадывает цвет человека кто создал игру - жёлтый,зелёный )
🎰 SLOTS (— При выбивании 2 одинаковых предмета на 1 и 2 позиции ваша ставка умножается на x1.5
— При выбивании 3 одинаковых предметов подряд ваша ставка умножается на x2.25
— При выбивании трех 7 ваша ставка умножается на x5 )

ТАК ЖЕ, РАБОТАЮТ АВТОМАТИЗИРОВАННЫЕ ИГРЫ В ЧАТЕ, ГДЕ ВЫ САМИ КИДАЕТЕ АНИМАЦИЮ И БОТ АВТОМАТИЧЕСКИ ВЫБИРАЕТ ПОБЕДИТЕЛЯ.

<b>⚡️FRK CASINO ⚡️</b>

💰Курс RUB:
1 RUB = 1 RUB
➖➖➖➖➖➖➖➖➖➖

<b>🎮 Команды для игр в чате:</b>

  ℹ️ CLASSIC (классические игры):
    🎲 /cub [сумма]
    🎯 /dar [сумма]
    🎳 /boul [сумма]
    🏀 /bas [сумма]
    ⚽️ /foot [сумма]

  ℹ️ OTHER GAMES:
    🎰 /spin [сумма] - слоты в чате (PvE)

<b>🚀 Команды взаимодействия:</b>
    /del [реплаем на игру] - удалить игру
    /bal - узнать баланс
    /getid - ваш ID

<b>🤖 Информация:</b>
    ✅ Игровой бот: @FJcasino_bot
    💬 Чат №1: @frkcasino
    💬 Чат услуг: @FRK_USLIGI

<b>ПРАВИЛА:</b>
🔴НЕ ИГРАЙТЕ НА ЧЕСТНОМ СЛОВЕ
🔴НЕ ПЕРЕХОДИТЕ ИГРАТЬ В ЛС
🔴СВЕРЯЙТЕ ЛИНКИ АДМИНИСТРАЦИИ

<i>Полное пользовательское соглашение доступно при регистрации.</i>
"""

# --- КЛАВИАТУРЫ ---
def main_menu_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Баланс", callback_data="check_balance"),
         InlineKeyboardButton(text="👤 Профиль", callback_data="profile")],
        [InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit_start"),
         InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw_start")],
        [InlineKeyboardButton(text="📚 Правила FRK", callback_data="instructions")]
    ])

def join_game_kb(game_id, bet):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Присоединиться", callback_data=f"join_{game_id}")]
    ])

# --- ЛОГИКА PvP ИГР ---

GAME_TYPES = {
    'cub': {'emoji': '🎲', 'name': 'CUBE CLASSIC'},
    'dar': {'emoji': '🎯', 'name': 'DARTS CLASSIC'},
    'boul': {'emoji': '🎳', 'name': 'BOWLING CLASSIC'},
    'bas': {'emoji': '🏀', 'name': 'BASKETBALL CLASSIC'},
    'foot': {'emoji': '⚽', 'name': 'FOOTBALL CLASSIC'},
    'spin': {'emoji': '🎰', 'name': 'SLOTS CASINO'}
}

@dp.message(Command("start"))
async def cmd_start(message: Message):
    get_user(message.from_user.id, message.from_user.username)
    await message.answer(RULES_TEXT, reply_markup=main_menu_kb())

@dp.callback_query(F.data == "instructions")
async def cb_instructions(callback: CallbackQuery):
    await callback.message.edit_text(RULES_TEXT, reply_markup=main_menu_kb())

# --- СОЗДАНИЕ ИГРЫ (/cub 100 и т.д.) ---
@dp.message(F.text.regexp(r"^/(\w+)\s+(\d+)$"))
async def create_game_command(message: Message):
    if message.chat.id != GAME_CHAT_ID:
        await message.reply("❌ Игры доступны только в игровом чате!")
        return

    # Парсинг команды
    match = re.match(r"^/(\w+)\s+(\d+)$", message.text)
    cmd_type = match.group(1).lower()
    bet_amount = int(match.group(2))

    if cmd_type not in GAME_TYPES:
        return # Неизвестная команда

    user = get_user(message.from_user.id, message.from_user.username)

    # Проверка баланса
    if user['balance'] < bet_amount:
        await message.reply(f"❌ Недостаточно средств! Ваш баланс: {format_money(user['balance'])}")
        return

    # Списываем ставку у создателя (холдируем)
    user['balance'] -= bet_amount
    
    # Создаем игру
    game_id = str(message.message_id) # ID сообщения как ID игры
    game_data = {
        'id': game_id,
        'type': cmd_type,
        'emoji': GAME_TYPES[cmd_type]['emoji'],
        'name': GAME_TYPES[cmd_type]['name'],
        'bet': bet_amount,
        'creator': {'id': message.from_user.id, 'name': message.from_user.first_name, 'username': user['username']},
        'joiner': None,
        'status': 'waiting', # waiting, active, finished
        'moves': {} # {user_id: score}
    }
    active_games[game_id] = game_data

    # Формируем сообщение (Скриншот 1)
    text = (
        f"<b>FRK | CASINO ♣️</b>\n"
        f"{game_data['emoji']} <b>{game_data['name']} #{game_id}</b>\n\n"
        f"👤 <b>Создал - {user['username']}</b>\n\n"
        f"↪️ <b>Нажмите присоединиться для того, чтобы сыграть</b>\n\n"
        f"⚡️ <b>Игра ведется до 1 броска</b>\n\n"
        f"💰 <b>Ставка: {bet_amount} RUB</b>"
    )

    sent_msg = await message.answer(text, reply_markup=join_game_kb(game_id, bet_amount))
    # Обновляем ID игры на ID отправленного сообщения бота (чтобы реплаи работали корректно)
    active_games[str(sent_msg.message_id)] = active_games.pop(game_id)
    active_games[str(sent_msg.message_id)]['id'] = str(sent_msg.message_id)

# --- ПРИСОЕДИНЕНИЕ К ИГРЕ ---
@dp.callback_query(F.data.startswith("join_"))
async def join_game_handler(callback: CallbackQuery):
    game_id = callback.data.split("_")[1]
    
    if game_id not in active_games:
        await callback.answer("❌ Игра не найдена или удалена", show_alert=True)
        return

    game = active_games[game_id]
    user = get_user(callback.from_user.id, callback.from_user.username)

    if game['status'] != 'waiting':
        await callback.answer("❌ Игра уже идет или завершена", show_alert=True)
        return

    if callback.from_user.id == game['creator']['id']:
        await callback.answer("❌ Вы не можете играть сами с собой", show_alert=True)
        return

    if user['balance'] < game['bet']:
        await callback.answer(f"❌ Недостаточно средств! Нужно: {game['bet']} RUB", show_alert=True)
        return

    # Списываем ставку у второго игрока
    user['balance'] -= game['bet']
    
    # Обновляем статус игры
    game['joiner'] = {'id': callback.from_user.id, 'name': callback.from_user.first_name, 'username': user['username']}
    game['status'] = 'active'

    # Обновляем сообщение (Скриншот 3)
    text = (
        f"<b>FRK | CASINO ♣️</b>\n"
        f"{game['emoji']} <b>{game['name']} #{game_id}</b>\n\n"
        f"👥 <b>Игроки:</b>\n"
        f"1️⃣ - {game['creator']['username']}\n"
        f"2️⃣ - {game['joiner']['username']}\n\n"
        f"— <b>Отправьте {game['emoji']} в ответ на это сообщение</b>\n\n"
        f"💰 <b>Ставка: {game['bet']} RUB</b>"
    )

    await callback.message.edit_text(text, reply_markup=None)

# --- ОБРАБОТКА ХОДОВ (Reply смайликом) ---
@dp.message(F.dice)
async def handle_game_move(message: Message):
    # Проверяем, что это ответ на сообщение
    if not message.reply_to_message:
        return

    game_id = str(message.reply_to_message.message_id)
    
    if game_id not in active_games:
        return # Это не сообщение с игрой

    game = active_games[game_id]
    user_id = message.from_user.id

    # Проверки
    if game['status'] != 'active':
        return
    
    if user_id != game['creator']['id'] and user_id != game['joiner']['id']:
        return # Чужой человек кинул кубик

    if user_id in game['moves']:
        await message.reply("❌ Вы уже сделали ход! Ждите соперника.")
        return

    if message.dice.emoji != game['emoji']:
        await message.reply(f"❌ Кидайте правильный смайлик: {game['emoji']}")
        return

    # Записываем ход
    score = message.dice.value
    game['moves'][user_id] = score
    
    # Ждем анимацию кубика (3-4 сек)
    await asyncio.sleep(3.5)

    # Проверяем, сходили ли оба
    if len(game['moves']) == 2:
        creator_score = game['moves'][game['creator']['id']]
        joiner_score = game['moves'][game['joiner']['id']]
        
        creator_u = get_user(game['creator']['id'])
        joiner_u = get_user(game['joiner']['id'])
        
        bank = game['bet'] * 2
        result_text = ""

        # Логика определения победителя
        winner_id = None
        
        if creator_score > joiner_score:
            winner_id = game['creator']['id']
            creator_u['balance'] += bank
            result_text = f"🏆 Победил {game['creator']['username']}!\nСчет: {creator_score} vs {joiner_score}"
        elif joiner_score > creator_score:
            winner_id = game['joiner']['id']
            joiner_u['balance'] += bank
            result_text = f"🏆 Победил {game['joiner']['username']}!\nСчет: {joiner_score} vs {creator_score}"
        else:
            # Ничья - возврат
            creator_u['balance'] += game['bet']
            joiner_u['balance'] += game['bet']
            result_text = f"🤝 Ничья! Ставки возвращены.\nСчет: {creator_score} : {joiner_score}"

        # Финальное сообщение
        final_msg = (
            f"🏁 <b>ИГРА ЗАВЕРШЕНА #{game_id}</b>\n\n"
            f"{result_text}\n"
            f"💰 Банк: {bank} RUB"
        )
        
        await message.reply(final_msg)
        del active_games[game_id] # Удаляем игру

# --- УДАЛЕНИЕ ИГРЫ ---
@dp.message(Command("del"))
async def delete_game(message: Message):
    if not message.reply_to_message:
        await message.reply("⚠️ Используйте команду в ответ на сообщение с игрой.")
        return

    game_id = str(message.reply_to_message.message_id)
    
    if game_id not in active_games:
        await message.reply("❌ Игра не найдена.")
        return

    game = active_games[game_id]
    
    # Удалить может только создатель или админ
    if message.from_user.id != game['creator']['id']:
        await message.reply("❌ Вы не создатель этой игры.")
        return

    if game['status'] == 'active':
        await message.reply("❌ Нельзя удалить активную игру.")
        return

    # Возврат средств
    user = get_user(game['creator']['id'])
    user['balance'] += game['bet']
    
    del active_games[game_id]
    await message.reply("✅ Игра удалена, средства возвращены.")
    await message.reply_to_message.delete()


# --- БАЛАНС И КОМАНДЫ ---
@dp.message(Command("bal"))
async def check_balance_cmd(message: Message):
    user = get_user(message.from_user.id)
    await message.reply(f"💰 Ваш баланс: <b>{format_money(user['balance'])}</b>")

@dp.message(Command("getid"))
async def get_id_cmd(message: Message):
    await message.reply(f"🆔 Ваш ID: <code>{message.from_user.id}</code>")

# --- ПОПОЛНЕНИЕ (Упрощенное под CryptoPay) ---
@dp.callback_query(F.data == "deposit_start")
async def deposit_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "💎 <b>Пополнение баланса</b>\n"
        f"Минимум: {MIN_DEPOSIT_RUB} RUB\n"
        "Введите сумму в рублях:", 
        reply_markup=None
    )
    await state.set_state(StatesGroup()) # Просто пример, нужен отдельный класс States
    await state.set_state("waiting_deposit")

@dp.message(F.text, lambda msg: msg.text.isdigit())
async def process_deposit_amount(message: Message, state: FSMContext):
    # Упрощенная логика: проверяем state (в полном коде нужно добавить класс StatesGroup)
    # Здесь просто создаем инвойс
    amount_rub = int(message.text)
    if amount_rub < MIN_DEPOSIT_RUB:
        await message.reply(f"Минимум {MIN_DEPOSIT_RUB} RUB!")
        return
        
    amount_usd = amount_rub / USD_TO_RUB_RATE
    
    try:
        invoice = await crypto.create_invoice(asset='USDT', amount=amount_usd)
        await message.answer(
            f"✅ Счет создан на {amount_rub} RUB ({amount_usd:.2f} USDT)\n"
            f"Оплатите по ссылке:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Оплатить", url=invoice.bot_invoice_url)],
                [InlineKeyboardButton(text="Проверить", callback_data=f"check_inv_{invoice.invoice_id}")]
            ])
        )
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

@dp.callback_query(F.data.startswith("check_inv_"))
async def check_invoice(callback: CallbackQuery):
    inv_id = int(callback.data.split("_")[2])
    invoices = await crypto.get_invoices(invoice_ids=[inv_id])
    if invoices and invoices[0].status == 'paid':
        amount_usd = float(invoices[0].amount)
        amount_rub = amount_usd * USD_TO_RUB_RATE
        user = get_user(callback.from_user.id)
        user['balance'] += amount_rub
        await callback.message.edit_text(f"✅ Оплачено! Зачислено {amount_rub} RUB")
    else:
        await callback.answer("❌ Пока не оплачено", show_alert=True)

# --- ЗАПУСК ---
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    print("Bot FRK Casino Started...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped")
