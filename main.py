import asyncio
import logging
import re
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiocryptopay import AioCryptoPay, Networks

# --- ⚙️ НАСТРОЙКИ (ВСТАВЛЕНЫ ВАШИ ДАННЫЕ) ---
BOT_TOKEN = "8315937988:AAHaKhMNy0t-uXQjSumvkDk3nf2vyTHf63U"
CRYPTO_BOT_TOKEN = "505642:AATEFAUIQ3OE9ihgalDaLzhI4u7uH2CY0X5"
GAME_CHAT_ID = -1003582415216  # ID вашего чата
ADMIN_ID = 7323981601  # Замените на ваш ID, чтобы видеть /stats

CASINO_NAME = "Andron"
MIN_DEPOSIT_RUB = 100.0
MIN_WITHDRAW_RUB = 150.0
USD_TO_RUB_RATE = 100.0
HOUSE_COMMISSION = 0.05  # Комиссия 5%

# Логирование
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())

# Crypto Pay
try:
    crypto = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)
except:
    crypto = None

# --- БАЗА ДАННЫХ В ПАМЯТИ ---
user_db = {}
active_games = {}
TOTAL_PROFIT = 0.0 # Прибыль проекта

def get_user(user_id, username=None):
    if user_id not in user_db:
        user_db[user_id] = {'balance': 0.0, 'username': f"@{username}" if username else f"ID_{user_id}"}
    if username: user_db[user_id]['username'] = f"@{username}"
    return user_db[user_id]

def format_money(amount):
    return f"{amount:.0f} RUB"

# --- ТЕКСТЫ ---
RULES_TEXT = f"""
<b>✅🃏 ДОБРО ПОЖАЛОВАТЬ В {CASINO_NAME} 🃏✅</b>

Минимум пополнения: {MIN_DEPOSIT_RUB} RUB
Минимум вывода: {MIN_WITHDRAW_RUB} RUB
Комиссия проекта: {int(HOUSE_COMMISSION*100)}% с выигрыша.

ℹ️ <b>ИГРЫ TOTAL (Сумма бросков):</b>
Пример: <code>/cubtotal3 100</code> (3 броска по 100)
🎲 <code>/cubtotal[2-5] [ставка]</code>
🎯 <code>/dartotal[2-5] [ставка]</code>
🎳 <code>/boultotal[2-5] [ставка]</code>
🏀 <code>/bastotal[2-5] [ставка]</code>
⚽️ <code>/foottotal[2-5] [ставка]</code>

ℹ️ <b>CLASSIC (1 бросок):</b>
🎲 <code>/cub</code> | 🎯 <code>/dar</code> | 🎳 <code>/boul</code> | 🏀 <code>/bas</code> | ⚽️ <code>/foot</code>

💰 <code>/bal</code> - Баланс | 🆔 <code>/getid</code> - Ваш ID
"""

# --- КЛАВИАТУРЫ ---
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit"),
         InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")],
        [InlineKeyboardButton(text="📊 Профиль", callback_data="profile")]
    ])

def join_kb(game_id):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Вступить", callback_data=f"join_{game_id}")]])

# --- ЛОГИКА ИГР ---
GAME_TYPES = {
    'cub': {'emoji': '🎲', 'name': 'Кубик'},
    'dar': {'emoji': '🎯', 'name': 'Дартс'},
    'boul': {'emoji': '🎳', 'name': 'Боулинг'},
    'bas': {'emoji': '🏀', 'name': 'Баскетбол'},
    'foot': {'emoji': '⚽', 'name': 'Футбол'}
}

@dp.message(F.text.regexp(r"^/([a-zA-Z0-9]+)\s+(\d+)$"))
async def create_game(message: Message):
    if message.chat.id != GAME_CHAT_ID: return
    
    match = re.match(r"^/([a-zA-Z0-9]+)\s+(\d+)$", message.text)
    full_cmd = match.group(1).lower()
    bet = int(match.group(2))
    
    rolls = 1
    base_key = full_cmd
    if "total" in full_cmd:
        last = full_cmd[-1]
        if last.isdigit() and '2' <= last <= '5':
            rolls = int(last)
            base_key = full_cmd.replace(f"total{last}", "")

    if base_key not in GAME_TYPES or bet < 1: return

    user = get_user(message.from_user.id, message.from_user.username)
    if user['balance'] < bet:
        return await message.reply(f"❌ Недостаточно средств! Баланс: {user['balance']} RUB")

    user['balance'] -= bet
    gid = str(message.message_id)
    
    active_games[gid] = {
        'id': gid, 'emoji': GAME_TYPES[base_key]['emoji'], 'name': GAME_TYPES[base_key]['name'],
        'bet': bet, 'max_rolls': rolls, 'status': 'waiting',
        'p1': {'id': message.from_user.id, 'user': user['username'], 'score': 0, 'done': 0},
        'p2': None
    }

    txt = (f"<b>{CASINO_NAME} | НОВАЯ ИГРА</b>\n{GAME_TYPES[base_key]['emoji']} {GAME_TYPES[base_key]['name']}\n"
           f"👤 Создал: {user['username']}\n💰 Ставка: {bet} RUB\n🔢 Бросков: {rolls}")
    
    sent = await message.answer(txt, reply_markup=join_kb(gid))
    active_games[str(sent.message_id)] = active_games.pop(gid)

@dp.callback_query(F.data.startswith("join_"))
async def join_game(cb: CallbackQuery):
    gid = cb.data.split("_")[1]
    if gid not in active_games or active_games[gid]['status'] != 'waiting':
        return await cb.answer("Игра недоступна")
    
    game = active_games[gid]
    user = get_user(cb.from_user.id, cb.from_user.username)
    
    if cb.from_user.id == game['p1']['id']:
        return await cb.answer("Нельзя играть с собой", show_alert=True)
    if user['balance'] < game['bet']:
        return await cb.answer(f"Нужно {game['bet']} RUB", show_alert=True)

    user['balance'] -= game['bet']
    game['p2'] = {'id': cb.from_user.id, 'user': user['username'], 'score': 0, 'done': 0}
    game['status'] = 'active'
    
    await cb.message.edit_text(
        f"<b>{CASINO_NAME} | ИГРА НАЧАТА</b>\n"
        f"👥 {game['p1']['user']} VS {game['p2']['user']}\n"
        f"💰 Банк: {game['bet']*2} RUB\n"
        f"— Отправьте {game['emoji']} в ответ на это сообщение!", reply_markup=None
    )

@dp.message(F.dice)
async def play_dice(msg: Message):
    if not msg.reply_to_message: return
    gid = str(msg.reply_to_message.message_id)
    if gid not in active_games: return
    
    game = active_games[gid]
    if game['status'] != 'active' or msg.dice.emoji != game['emoji']: return
    
    p = None
    if msg.from_user.id == game['p1']['id']: p = game['p1']
    elif msg.from_user.id == game['p2']['id']: p = game['p2']
    
    if not p or p['done'] >= game['max_rolls']: return

    p['score'] += msg.dice.value
    p['done'] += 1
    
    await asyncio.sleep(3.5)
    await msg.reply(f"🎲 {p['user']} выбросил {msg.dice.value}!\nСумма: {p['score']} ({p['done']}/{game['max_rolls']})")

    if game['p1']['done'] == game['max_rolls'] and game['p2']['done'] == game['max_rolls']:
        await finish(msg, gid)

async def finish(msg, gid):
    global TOTAL_PROFIT
    game = active_games[gid]
    p1, p2 = game['p1'], game['p2']
    bank = game['bet'] * 2
    
    fee = bank * HOUSE_COMMISSION
    win_sum = bank - fee
    
    res = f"🏁 <b>ИТОГИ:</b>\n{p1['user']}: {p1['score']}\n{p2['user']}: {p2['score']}\n\n"
    
    if p1['score'] > p2['score']:
        get_user(p1['id'])['balance'] += win_sum
        TOTAL_PROFIT += fee
        res += f"🏆 Победил {p1['user']}!\nЗачислено: {format_money(win_sum)} (с учетом комиссии)"
    elif p2['score'] > p1['score']:
        get_user(p2['id'])['balance'] += win_sum
        TOTAL_PROFIT += fee
        res += f"🏆 Победил {p2['user']}!\nЗачислено: {format_money(win_sum)} (с учетом комиссии)"
    else:
        get_user(p1['id'])['balance'] += game['bet']
        get_user(p2['id'])['balance'] += game['bet']
        res += "🤝 Ничья! Возврат ставок."

    await msg.answer(res)
    del active_games[gid]

@dp.message(Command("stats"))
async def admin_stats(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer(f"📊 <b>Статистика {CASINO_NAME}</b>\n\n💰 Прибыль: {format_money(TOTAL_PROFIT)}\n👤 Юзеров: {len(user_db)}")

@dp.message(Command("start"))
async def start(m: Message):
    get_user(m.from_user.id, m.from_user.username)
    await m.answer(RULES_TEXT, reply_markup=main_kb())

@dp.message(Command("bal"))
async def bal(m: Message):
    u = get_user(m.from_user.id)
    await m.reply(f"💰 Баланс: {format_money(u['balance'])}")

@dp.message(Command("getid"))
async def get_id_cmd(m: Message):
    await m.answer(f"🆔 Ваш ID: <code>{m.from_user.id}</code>")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
