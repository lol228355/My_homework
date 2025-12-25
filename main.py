import asyncio
import logging
import re
import uuid
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties

# --- ⚙️ НАСТРОЙКИ ---
BOT_TOKEN = "8315937988:AAHaKhMNy0t-uXQjSumvkDk3nf2vyTHf63U"
GAME_CHAT_ID = -1003582415216 
ADMIN_ID = 7323981601           

CASINO_NAME = "🎰 ANDRON" # Можешь поменять на FRK | CASINO
HOUSE_COMMISSION = 0.10

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())

# --- 🗄 РАБОТА С БАЗОЙ ДАННЫХ ---
class Database:
    def __init__(self, db_file):
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, balance REAL DEFAULT 0.0)")
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

db = Database("casino_db.sqlite")
active_games = {} 
game_msg_map = {} 

# --- КЛАВИАТУРЫ ---
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Активные игры", callback_data="active_list")],
        [InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit"),
         InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="📚 Правила", callback_data="instructions")]
    ])

# --- 🔥 ОФОРМЛЕНИЕ КАК НА СКРИНШОТЕ ---
def get_game_text(game):
    # Статус игры
    if game['status'] == 'waiting':
        action_text = "💾 <b>Нажмите присоединиться для того, чтобы сыграть</b>"
    else:
        action_text = "▶️ <b>Игра началась! Кидайте кубик в ответ.</b>"

    # Формируем текст
    text = (
        f"<b>{CASINO_NAME} ♣️</b>\n"
        f"{game['emoji']} <b>{game['name']} #{game['uuid']}</b>\n\n"
        f"👤 <b>Создал -</b> {game['p1']['user']}\n\n"
        f"{action_text}\n\n"
        f"⚡ <b>Игра ведется до {game['max_rolls']}х бросков</b>\n\n"
        f"💰 <b>Ставка: {game['bet']} RUB</b>"
    )

    # Если игра уже идет, добавляем табло очков снизу
    if game['status'] == 'active':
        text += f"\n\n➖➖➖➖➖➖➖➖➖\n"
        text += f"1️⃣ {game['p1']['user']}: <b>{game['p1']['score']}</b>\n"
        text += f"2️⃣ {game['p2']['user']}: <b>{game['p2']['score']}</b>"

    return text

# --- ОБРАБОТЧИКИ ---

@dp.callback_query(F.data == "active_list")
async def show_active_games(cb: CallbackQuery):
    if not active_games:
        return await cb.answer("Сейчас нет активных игр", show_alert=True)
    
    text = "🎮 <b>Список активных игр:</b>\n\n"
    for gid, g in active_games.items():
        status = "⏳ Ожидание" if g['status'] == 'waiting' else "🎲 В игре"
        text += f"🔹 {g['emoji']} {g['name']} #{gid} | {g['bet']} RUB | {status}\n"
    
    await cb.message.answer(text)
    await cb.answer()

@dp.message(F.text.regexp(r"^/([a-zA-Z0-9]+)\s+(\d+)$"))
async def create_game(m: Message):
    if m.chat.id != GAME_CHAT_ID: return
    match = re.match(r"^/([a-zA-Z0-9]+)\s+(\d+)$", m.text)
    cmd, bet = match.group(1).lower(), int(match.group(2))
    
    rolls, key = 1, cmd
    # Логика для total2, total3 и т.д.
    if "total" in cmd:
        last = cmd[-1]
        if last.isdigit(): 
            rolls = int(last)
            key = cmd.replace(f"total{rolls}", "") # Исправлено удаление цифры
            
    game_types = {
        'cube': ('🎲', 'CUBE'), 
        'dar': ('🎯', 'DARTS'), 
        'boul': ('🎳', 'BOWLING'), 
        'bas': ('🏀', 'BASKET'), 
        'foot': ('⚽', 'FOOTBALL')
    }
    
    # Пытаемся найти ключ, даже если юзер написал cube4total
    clean_key = key.replace("total", "")
    if clean_key not in game_types: 
        # Если не нашли по точному совпадению, пробуем сокращения как у вас были
        if 'cub' in key: clean_key = 'cube'
        elif 'dar' in key: clean_key = 'dar'
        elif 'boul' in key: clean_key = 'boul'
        elif 'bas' in key: clean_key = 'bas'
        elif 'foot' in key: clean_key = 'foot'
        else: return

    game_info = game_types[clean_key]
    
    u = db.get_user(m.from_user.id, m.from_user.username)
    if u['balance'] < bet: return await m.reply("❌ Недостаточно средств.")
    
    db.update_balance(m.from_user.id, -bet)
    gid = str(uuid.uuid4().int)[:6]
    
    game = {
        'uuid': gid, 'emoji': game_info[0], 'name': game_info[1] + (f" {rolls}TOTAL" if rolls > 1 else ""),
        'bet': bet, 'max_rolls': rolls, 'status': 'waiting',
        'p1': {'id': m.from_user.id, 'user': u['username'], 'score': 0, 'done': 0},
        'p2': None, 'msg_id': None
    }
    
    # Кнопка зеленая галочка
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Присоединиться", callback_data=f"join_{gid}")]])
    sent = await m.answer(get_game_text(game), reply_markup=kb)
    game['msg_id'] = sent.message_id
    active_games[gid] = game
    game_msg_map[sent.message_id] = gid

@dp.callback_query(F.data.startswith("join_"))
async def join_game(cb: CallbackQuery):
    gid = cb.data.split("_")[1]
    if gid not in active_games: return await cb.answer("Игра не найдена", show_alert=True)
    game = active_games[gid]
    
    # --- 🛑 ЗАПРЕТ ИГРЫ С САМИМ СОБОЙ ---
    if game['p1']['id'] == cb.from_user.id:
        return await cb.answer("❌ Вы не можете играть сами с собой!", show_alert=True)
    
    if game['status'] != 'waiting': return await cb.answer("Игра уже идет!", show_alert=True)
    
    u = db.get_user(cb.from_user.id, cb.from_user.username)
    if u['balance'] < game['bet']: return await cb.answer("Нет денег", show_alert=True)
    
    db.update_balance(cb.from_user.id, -game['bet'])
    game['p2'] = {'id': cb.from_user.id, 'user': u['username'], 'score': 0, 'done': 0}
    game['status'] = 'active'
    
    # Убираем кнопку после старта
    await cb.message.edit_text(get_game_text(game), reply_markup=None)

@dp.message(F.dice)
async def process_dice(m: Message):
    if not m.reply_to_message or m.reply_to_message.message_id not in game_msg_map: return
    gid = game_msg_map[m.reply_to_message.message_id]
    game = active_games.get(gid)
    if not game or game['status'] != 'active' or m.dice.emoji != game['emoji']: return
    
    p = None
    if m.from_user.id == game['p1']['id']: p = game['p1']
    elif m.from_user.id == game['p2']['id']: p = game['p2']
    
    if not p or p['done'] >= game['max_rolls']: return
        
    p['score'] += m.dice.value
    p['done'] += 1
    
    # Обновляем текст сообщения
    await bot.edit_message_text(chat_id=m.chat.id, message_id=game['msg_id'], text=get_game_text(game))
    
    if game['p1']['done'] >= game['max_rolls'] and game['p2']['done'] >= game['max_rolls']:
        await finish_game(gid, m.chat.id)

async def finish_game(gid, chat_id):
    game = active_games[gid]
    p1, p2 = game['p1'], game['p2']
    win_amount = (game['bet'] * 2) * (1 - HOUSE_COMMISSION)
    
    res = f"🏁 <b>ИТОГ ИГРЫ #{gid}</b>\n\n👤 {p1['user']}: <b>{p1['score']}</b>\n👤 {p2['user']}: <b>{p2['score']}</b>\n\n"
    
    if p1['score'] > p2['score']:
        res += f"🏆 Победил: {p1['user']}\n💰 Выигрыш: {win_amount:.2f} RUB"
        db.update_balance(p1['id'], win_amount)
    elif p2['score'] > p1['score']:
        res += f"🏆 Победил: {p2['user']}\n💰 Выигрыш: {win_amount:.2f} RUB"
        db.update_balance(p2['id'], win_amount)
    else:
        res += "🤝 <b>Ничья! Возврат ставок</b>"
        db.update_balance(p1['id'], game['bet'])
        db.update_balance(p2['id'], game['bet'])
        
    await bot.send_message(chat_id, res)
    del active_games[gid]

@dp.message(Command("start"))
async def start(m: Message):
    db.get_user(m.from_user.id, m.from_user.username)
    await m.answer(f"👋 Привет в {CASINO_NAME}", reply_markup=main_kb())

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
