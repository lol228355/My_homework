import asyncio
import logging
import re
import uuid
import sqlite3 # Добавляем библиотеку для работы с БД

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.default import DefaultBotProperties
from aiocryptopay import AioCryptoPay, Networks

# --- ⚙️ НАСТРОЙКИ ---
BOT_TOKEN = "8315937988:AAHaKhMNy0t-uXQjSumvkDk3nf2vyTHf63U"
CRYPTO_BOT_TOKEN = "505642:AATEFAUIQ3OE9ihgalDaLzhI4u7uH2CY0X5"
GAME_CHAT_ID = -1003582415216 
ADMIN_ID = 7323981601          

CASINO_NAME = "🎰 ANDRON"
MIN_DEPOSIT_RUB = 100.0
MIN_WITHDRAW_RUB = 150.0
USD_TO_RUB_RATE = 100.0
HOUSE_COMMISSION = 0.10

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())
crypto = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)

# --- 🗄 РАБОТА С БАЗОЙ ДАННЫХ (ФАЙЛ) ---
class Database:
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        # Таблица пользователей
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 0.0
            )
        """)
        # Таблица статистики (для прибыли)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                id INTEGER PRIMARY KEY,
                total_profit REAL DEFAULT 0.0
            )
        """)
        self.cursor.execute("INSERT OR IGNORE INTO stats (id, total_profit) VALUES (1, 0.0)")
        self.conn.commit()

    def get_user(self, user_id, username=None):
        self.cursor.execute("SELECT user_id, username, balance FROM users WHERE user_id = ?", (user_id,))
        user = self.cursor.fetchone()
        if not user:
            u_name = f"@{username}" if username else f"ID_{user_id}"
            self.cursor.execute("INSERT INTO users (user_id, username, balance) VALUES (?, ?, ?)", (user_id, u_name, 0.0))
            self.conn.commit()
            return {'user_id': user_id, 'username': u_name, 'balance': 0.0}
        
        # Обновляем юзернейм если изменился
        if username and user[1] != f"@{username}":
            self.cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (f"@{username}", user_id))
            self.conn.commit()
            
        return {'user_id': user[0], 'username': user[1], 'balance': user[2]}

    def update_balance(self, user_id, amount):
        self.cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        self.conn.commit()

    def get_total_users(self):
        self.cursor.execute("SELECT COUNT(*) FROM users")
        return self.cursor.fetchone()[0]

    def add_profit(self, amount):
        self.cursor.execute("UPDATE stats SET total_profit = total_profit + ? WHERE id = 1", (amount,))
        self.conn.commit()

    def get_profit(self):
        self.cursor.execute("SELECT total_profit FROM stats WHERE id = 1")
        return self.cursor.fetchone()[0]

    def find_user_by_name(self, username):
        clean_name = username.replace('@', '').lower()
        self.cursor.execute("SELECT user_id FROM users WHERE LOWER(REPLACE(username, '@', '')) = ?", (clean_name,))
        res = self.cursor.fetchone()
        return res[0] if res else None

db = Database("casino_db.sqlite")

# --- ПЕРЕМЕННЫЕ В ПАМЯТИ (ТОЛЬКО ДЛЯ АКТИВНЫХ ИГР) ---
# Игры не храним в БД, так как при перезагрузке бота "реплаи" на сообщения все равно теряют смысл
active_games = {} 
game_msg_map = {} 
withdrawal_requests = {} 

# --- FSM (СОСТОЯНИЯ) ---
class AdminState(StatesGroup):
    waiting_for_username = State()
    waiting_for_amount = State()

class UserState(StatesGroup):
    waiting_deposit_amount = State()
    waiting_withdraw_amount = State()

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---
def format_money(amount):
    return f"{amount:.0f} RUB"

def get_game_text(game):
    header_num = f"№{game['uuid']}"
    p1_score = f"[{game['p1']['score']}]"
    p2_score = f"[{game['p2']['score']}]" if game['p2'] else "[0]"
    p2_name = game['p2']['user'] if game['p2'] else "Ожидание..."
    
    text = (
        f"{game['emoji']} <b>{game['name'].upper()} {header_num}</b>\n"
        f"📎 <a href='https://t.me/your_chat_link'>Наш чат</a>\n\n"
        f"— Отправьте {game['emoji']} в ответ на это сообщение\n\n"
        f"💰 <b>Ставка:</b> {game['bet']} RUB\n\n"
        f"⚡️ ⚡️ ⚡️ <b>Игра ведется до {game['max_rolls']} побед</b>\n\n"
        f"👥 <b>Игроки:</b>\n"
        f"1️⃣ - {game['p1']['user']} <b>{p1_score}</b>\n"
        f"2️⃣ - {p2_name} <b>{p2_score}</b>"
    )
    return text

# --- КЛАВИАТУРЫ ---
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit"),
         InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="📚 Правила", callback_data="instructions")]
    ])

def join_kb(game_uuid):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Присоединиться ↗️", callback_data=f"join_{game_uuid}")]
    ])

def admin_kb():
    req_count = len(withdrawal_requests)
    req_text = f"🔔 Заявки ({req_count})" if req_count > 0 else "🔕 Заявки"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать деньги", callback_data="admin_give_money")],
        [InlineKeyboardButton(text=req_text, callback_data="admin_requests")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_admin")]
    ])

# --- ОБРАБОТЧИКИ ---

@dp.callback_query(F.data == "instructions")
async def show_rules(cb: CallbackQuery):
    txt = f"<b>ℹ️ ИНСТРУКЦИЯ {CASINO_NAME}</b>\n\n🎲 <code>/cub 100</code>\n🏀 <code>/bas 100</code>\n⚽️ <code>/foot 100</code>\n\nДо 2-х побед: <code>/foottotal2 100</code>"
    await cb.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]]))

@dp.callback_query(F.data == "back_to_menu")
async def back_menu(cb: CallbackQuery):
    await cb.message.edit_text(f"👋 <b>Меню {CASINO_NAME}</b>", reply_markup=main_kb())

@dp.callback_query(F.data == "profile")
async def show_profile(cb: CallbackQuery):
    u = db.get_user(cb.from_user.id, cb.from_user.username)
    txt = f"👤 <b>Твой профиль:</b>\n\n🆔 <code>{cb.from_user.id}</code>\n💰 Баланс: {format_money(u['balance'])}"
    await cb.message.edit_text(txt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]]))

# --- АДМИНКА ---
@dp.message(Command("admin"))
async def admin_panel(m: Message):
    if m.from_user.id == ADMIN_ID:
        await m.answer("👑 <b>Админ-панель</b>", reply_markup=admin_kb())

@dp.callback_query(F.data == "admin_stats")
async def adm_stats(cb: CallbackQuery):
    txt = f"📊 <b>Статистика</b>\n\n💰 Прибыль: {format_money(db.get_profit())}\n👤 Юзеров: {db.get_total_users()}"
    await cb.message.edit_text(txt, reply_markup=admin_kb())

@dp.callback_query(F.data == "admin_give_money")
async def adm_give(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("✍️ Введите @username:")
    await state.set_state(AdminState.waiting_for_username)

@dp.message(AdminState.waiting_for_username)
async def adm_proc_user(m: Message, state: FSMContext):
    uid = db.find_user_by_name(m.text)
    if not uid: return await m.reply("❌ Не найден.")
    await state.update_data(target_id=uid)
    await m.reply("💰 Сумма:")
    await state.set_state(AdminState.waiting_for_amount)

@dp.message(AdminState.waiting_for_amount)
async def adm_proc_amount(m: Message, state: FSMContext):
    try:
        amt = float(m.text)
        data = await state.get_data()
        db.update_balance(data['target_id'], amt)
        await m.reply("✅ Баланс изменен.")
        await state.clear()
    except: pass

# --- ИГРОВОЙ ДВИЖОК ---

@dp.message(F.text.regexp(r"^/([a-zA-Z0-9]+)\s+(\d+)$"))
async def create_game(m: Message):
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
    
    db.update_balance(m.from_user.id, -bet) # Списываем из БД
    gid = str(uuid.uuid4().int)[:6]
    
    game = {
        'uuid': gid, 'emoji': GAME_TYPES[key]['emoji'], 'name': GAME_TYPES[key]['name'],
        'bet': bet, 'max_rolls': rolls, 'status': 'waiting',
        'p1': {'id': m.from_user.id, 'user': u['username'], 'score': 0, 'done': 0},
        'p2': None, 'msg_id': None
    }
    
    sent = await m.answer(get_game_text(game), reply_markup=join_kb(gid))
    game['msg_id'] = sent.message_id
    active_games[gid] = game
    game_msg_map[sent.message_id] = gid

@dp.callback_query(F.data.startswith("join_"))
async def join_game(cb: CallbackQuery):
    gid = cb.data.split("_")[1]
    if gid not in active_games: return await cb.answer("Игра не найдена", show_alert=True)
    game = active_games[gid]
    if game['status'] != 'waiting': return
    
    u = db.get_user(cb.from_user.id, cb.from_user.username)
    if u['balance'] < game['bet']: return await cb.answer("Нет денег", show_alert=True)
    
    db.update_balance(cb.from_user.id, -game['bet']) # Списываем из БД
    game['p2'] = {'id': cb.from_user.id, 'user': u['username'], 'score': 0, 'done': 0}
    game['status'] = 'active'
    await cb.message.edit_text(get_game_text(game), reply_markup=None)

@dp.message(F.dice)
async def process_dice(m: Message):
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
        await finish_game(gid, m.chat.id)

async def finish_game(gid, chat_id):
    game = active_games[gid]
    p1, p2 = game['p1'], game['p2']
    bank = game['bet'] * 2
    fee = bank * HOUSE_COMMISSION
    win = bank - fee
    
    res_text = f"🏁 <b>ИГРА ОКОНЧЕНА №{gid}</b>\n\n👤 {p1['user']}: {p1['score']}\n👤 {p2['user']}: {p2['score']}\n\n"
    
    if p1['score'] > p2['score']:
        res_text += f"🏆 Победил: {p1['user']}\n💰 Выигрыш: {format_money(win)}"
        db.update_balance(p1['id'], win) # Начисляем в БД
        db.add_profit(fee)
    elif p2['score'] > p1['score']:
        res_text += f"🏆 Победил: {p2['user']}\n💰 Выигрыш: {format_money(win)}"
        db.update_balance(p2['id'], win) # Начисляем в БД
        db.add_profit(fee)
    else:
        res_text += "🤝 Ничья! Ставки возвращены."
        db.update_balance(p1['id'], game['bet'])
        db.update_balance(p2['id'], game['bet'])
        
    await bot.send_message(chat_id, res_text)
    del active_games[gid]

GAME_TYPES = {
    'cub': {'emoji': '🎲', 'name': 'DICE'},
    'dar': {'emoji': '🎯', 'name': 'DARTS'},
    'boul': {'emoji': '🎳', 'name': 'BOWLING'},
    'bas': {'emoji': '🏀', 'name': 'BASKET'},
    'foot': {'emoji': '⚽', 'name': 'FOOTBALL'}
}

@dp.message(Command("start"))
async def start(m: Message):
    db.get_user(m.from_user.id, m.from_user.username)
    await m.answer(f"👋 <b>Добро пожаловать</b>", reply_markup=main_kb())

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
