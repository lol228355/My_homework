import asyncio
import logging
import re
import uuid
import sqlite3
import os

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties

# --- ⚙️ НАСТРОЙКИ (ОБЯЗАТЕЛЬНО ЗАПОЛНИ) ---
BOT_TOKEN = "8315937988:AAHaKhMNy0t-uXQjSumvkDk3nf2vyTHf63U"
GAME_CHAT_ID = -1003582415216 # ID твоего игрового чата
ADMIN_ID = 7323981601         # Твой Telegram ID

CASINO_NAME = "FRK | CASINO ♣️"
HOUSE_COMMISSION = 0.10 # Комиссия 10%

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())

# --- 🗄 РАБОТА С БАЗОЙ ДАННЫХ (SQLite) ---
class Database:
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0)")
        self.cursor.execute("CREATE TABLE IF NOT EXISTS stats (id INTEGER PRIMARY KEY, total_profit REAL DEFAULT 0.0)")
        self.cursor.execute("INSERT OR IGNORE INTO stats (id, total_profit) VALUES (1, 0.0)")
        self.conn.commit()

    def get_user(self, user_id, username=None):
        self.cursor.execute("SELECT user_id, username, balance FROM users WHERE user_id = ?", (user_id,))
        user = self.cursor.fetchone()
        u_name = f"@{username}" if username else f"ID_{user_id}"
        if not user:
            self.cursor.execute("INSERT INTO users (user_id, username, balance) VALUES (?, ?, ?)", (user_id, u_name, 0.0))
            self.conn.commit()
            return {'user_id': user_id, 'username': u_name, 'balance': 0.0}
        return {'user_id': user[0], 'username': user[1], 'balance': user[2]}

    def update_balance(self, user_id, amount):
        self.cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        self.conn.commit()

    def add_profit(self, amount):
        self.cursor.execute("UPDATE stats SET total_profit = total_profit + ?", (amount,))
        self.conn.commit()

    def get_stats(self):
        self.cursor.execute("SELECT total_profit FROM stats WHERE id = 1")
        profit = self.cursor.fetchone()[0]
        self.cursor.execute("SELECT COUNT(*) FROM users")
        count = self.cursor.fetchone()[0]
        return profit, count

    def find_user_by_name(self, username):
        clean_name = username.replace('@', '').lower()
        self.cursor.execute("SELECT user_id FROM users WHERE LOWER(REPLACE(username, '@', '')) = ?", (clean_name,))
        res = self.cursor.fetchone()
        return res[0] if res else None

db = Database("casino_db.sqlite")
active_games = {} 
game_msg_map = {} 

# --- FSM СОСТОЯНИЯ ---
class AdminState(StatesGroup):
    waiting_for_username = State()
    waiting_for_amount = State()

# --- ФУНКЦИЯ ТЕКСТА ИГРЫ (ДИЗАЙН ИЗ СКРИНШОТОВ) ---
def get_game_text(game):
    if game['status'] == 'waiting':
        return (
            f"<b>FRK | CASINO</b> ♣️\n"
            f"{game['emoji']} {game['name']} {game['max_rolls']}TOTAL #{game['uuid']}\n\n"
            f"👤 <b>Создал</b> - {game['p1']['user']}\n\n"
            f"┕ <b>Нажмите присоединиться для того, чтобы сыграть</b>\n\n"
            f"⚡️ <b>Игра ведется до {game['max_rolls']}х бросков</b>\n\n"
            f"💰 <b>Ставка:</b> {game['bet']} RUB"
        )
    else:
        p2_info = f"{game['p2']['user']} <b>[{game['p2']['score']}]</b>" if game['p2'] else "Ожидание..."
        return (
            f"{game['emoji']} {game['name']} {game['max_rolls']}X №{game['uuid']}\n"
            f"📎 <a href='https://t.me/c/{str(GAME_CHAT_ID)[4:]}'>Наш чат</a>\n\n"
            f"— Отправьте {game['emoji']} в ответ на это сообщение\n\n"
            f"💰 <b>Ставка:</b> {game['bet']} RUB\n\n"
            f"⚡️ ⚡️ ⚡️ <b>Игра ведется до {game['max_rolls']}X побед</b>\n\n"
            f"👥 <b>Игроки:</b>\n"
            f"1️⃣ - {game['p1']['user']} <b>[{game['p1']['score']}]</b>\n"
            f"2️⃣ - {p2_info}"
        )

# --- КЛАВИАТУРЫ ---
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Активные игры", callback_data="active_list")],
        [InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit"),
         InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="📚 Правила", callback_data="instructions")]
    ])

def join_kb(gid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Присоединиться", callback_data=f"join_{gid}")]
    ])

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать баланс", callback_data="adm_give")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats")],
        [InlineKeyboardButton(text="💾 Скачать БД", callback_data="adm_db")]
    ])

# --- ОБРАБОТЧИКИ ---

@dp.message(Command("start"))
async def cmd_start(m: Message):
    db.get_user(m.from_user.id, m.from_user.username)
    await m.answer(f"👋 Добро пожаловать в <b>{CASINO_NAME}</b>", reply_markup=main_kb())

@dp.callback_query(F.data == "profile")
async def profile(cb: CallbackQuery):
    u = db.get_user(cb.from_user.id, cb.from_user.username)
    await cb.message.edit_text(f"👤 <b>Профиль</b>\n\n🆔 <code>{u['user_id']}</code>\n💰 Баланс: {u['balance']} RUB", 
                               reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back")]]))

@dp.callback_query(F.data == "back")
async def back(cb: CallbackQuery):
    await cb.message.edit_text(f"👋 Добро пожаловать в <b>{CASINO_NAME}</b>", reply_markup=main_kb())

@dp.callback_query(F.data == "active_list")
async def list_act(cb: CallbackQuery):
    if not active_games: return await cb.answer("Активных игр нет", show_alert=True)
    txt = "🎮 <b>Активные игры:</b>\n\n"
    for g in active_games.values():
        txt += f"🔹 {g['emoji']} {g['name']} | {g['bet']} RUB | #{g['uuid']}\n"
    await cb.message.answer(txt)
    await cb.answer()

# --- СОЗДАНИЕ ИГРЫ ---
GAME_TYPES = {'cub':('🎲','CUBE'), 'dar':('🎯','DARTS'), 'boul':('🎳','BOUL'), 'bas':('🏀','BASKET'), 'foot':('⚽','FOOT')}

@dp.message(F.text.regexp(r"^/([a-zA-Z0-9]+)\s+(\d+)$"))
async def start_game(m: Message):
    if m.chat.id != GAME_CHAT_ID: return
    match = re.match(r"^/([a-zA-Z0-9]+)\s+(\d+)$", m.text)
    cmd, bet = match.group(1).lower(), int(match.group(2))
    
    rolls, key = 1, cmd
    if "total" in cmd:
        last = cmd[-1]
        if last.isdigit(): rolls, key = int(last), cmd.replace(f"total{last}", "")
            
    if key not in GAME_TYPES: return
    
    u = db.get_user(m.from_user.id, m.from_user.username)
    if u['balance'] < bet: return await m.reply("❌ Недостаточно средств.")
    
    db.update_balance(m.from_user.id, -bet)
    gid = str(uuid.uuid4().int)[:6]
    
    game = {
        'uuid': gid, 'emoji': GAME_TYPES[key][0], 'name': GAME_TYPES[key][1],
        'bet': bet, 'max_rolls': rolls, 'status': 'waiting',
        'p1': {'id': m.from_user.id, 'user': u['username'], 'score': 0, 'done': 0},
        'p2': None, 'msg_id': None
    }
    
    sent = await m.answer(get_game_text(game), reply_markup=join_kb(gid))
    game['msg_id'] = sent.message_id
    active_games[gid] = game
    game_msg_map[sent.message_id] = gid

@dp.callback_query(F.data.startswith("join_"))
async def join(cb: CallbackQuery):
    gid = cb.data.split("_")[1]
    if gid not in active_games: return await cb.answer("Игра не найдена", show_alert=True)
    game = active_games[gid]
    
    if cb.from_user.id == game['p1']['id']:
        return await cb.answer("🚫 Нельзя играть с самим собой!", show_alert=True)
    
    u = db.get_user(cb.from_user.id, cb.from_user.username)
    if u['balance'] < game['bet']: return await cb.answer("Недостаточно RUB", show_alert=True)
    
    db.update_balance(cb.from_user.id, -game['bet'])
    game['p2'] = {'id': cb.from_user.id, 'user': u['username'], 'score': 0, 'done': 0}
    game['status'] = 'active'
    await cb.message.edit_text(get_game_text(game), reply_markup=None)

@dp.message(F.dice)
async def dice_handler(m: Message):
    if not m.reply_to_message or m.reply_to_message.message_id not in game_msg_map: return
    gid = game_msg_map[m.reply_to_message.message_id]
    game = active_games.get(gid)
    if not game or game['status'] != 'active' or m.dice.emoji != game['emoji']: return
    
    p = game['p1'] if m.from_user.id == game['p1']['id'] else game['p2'] if m.from_user.id == game['p2']['id'] else None
    if not p or p['done'] >= game['max_rolls']: return
        
    p['score'] += m.dice.value
    p['done'] += 1
    await bot.edit_message_text(chat_id=m.chat.id, message_id=game['msg_id'], text=get_game_text(game))
    
    if game['p1']['done'] >= game['max_rolls'] and game['p2']['done'] >= game['max_rolls']:
        await asyncio.sleep(4)
        await finish(gid, m.chat.id)

async def finish(gid, chat_id):
    game = active_games.get(gid)
    if not game: return
    p1, p2 = game['p1'], game['p2']
    win_amt = (game['bet'] * 2) * (1 - HOUSE_COMMISSION)
    
    res = f"🏁 <b>ИТОГ ИГРЫ №{gid}</b>\n\n👤 {p1['user']}: {p1['score']}\n👤 {p2['user']}: {p2['score']}\n\n"
    if p1['score'] > p2['score']:
        res += f"🏆 Победил: {p1['user']}\n💰 Приз: {win_amt} RUB"
        db.update_balance(p1['id'], win_amt); db.add_profit(game['bet']*2*HOUSE_COMMISSION)
    elif p2['score'] > p1['score']:
        res += f"🏆 Победил: {p2['user']}\n💰 Приз: {win_amt} RUB"
        db.update_balance(p2['id'], win_amt); db.add_profit(game['bet']*2*HOUSE_COMMISSION)
    else:
        res += "🤝 Ничья! Возврат ставок"
        db.update_balance(p1['id'], game['bet']); db.update_balance(p2['id'], game['bet'])
        
    await bot.send_message(chat_id, res)
    if gid in active_games: del active_games[gid]

# --- АДМИН ПАНЕЛЬ ---
@dp.message(Command("admin"))
async def adm(m: Message):
    if m.from_user.id == ADMIN_ID:
        await m.answer("👑 Админ-панель", reply_markup=admin_kb())

@dp.callback_query(F.data == "adm_stats")
async def adm_stats(cb: CallbackQuery):
    p, c = db.get_stats()
    await cb.message.answer(f"📊 Статистика:\n\n💰 Прибыль: {p} RUB\n👤 Юзеров: {c}")

@dp.callback_query(F.data == "adm_db")
async def adm_db(cb: CallbackQuery):
    await cb.message.answer_document(FSInputFile("casino_db.sqlite"))

@dp.callback_query(F.data == "adm_give")
async def adm_give(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("Введите @username пользователя:")
    await state.set_state(AdminState.waiting_for_username)

@dp.message(AdminState.waiting_for_username)
async def adm_u(m: Message, state: FSMContext):
    uid = db.find_user_by_name(m.text)
    if not uid: return await m.reply("Юзер не найден в БД")
    await state.update_data(target=uid)
    await m.answer("Введите сумму (например 100 или -100):")
    await state.set_state(AdminState.waiting_for_amount)

@dp.message(AdminState.waiting_for_amount)
async def adm_a(m: Message, state: FSMContext):
    try:
        amt = float(m.text)
        data = await state.get_data()
        db.update_balance(data['target'], amt)
        await m.answer("✅ Баланс обновлен")
        await state.clear()
    except: await m.answer("Ошибка. Введите число.")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
