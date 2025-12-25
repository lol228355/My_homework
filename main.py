import asyncio
import logging
import re
import uuid

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
GAME_CHAT_ID = -1003582415216  # ID вашего чата
ADMIN_ID = 7323981601  # Ваш ID

CASINO_NAME = "🎰 ANDRON CASINO"
MIN_DEPOSIT_RUB = 100.0
MIN_WITHDRAW_RUB = 150.0
USD_TO_RUB_RATE = 100.0
HOUSE_COMMISSION = 0.10

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())
crypto = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)

# --- БАЗА ДАННЫХ ---
user_db = {}
active_games = {} # Key: game_uuid, Value: dict
game_msg_map = {} # Key: bot_message_id, Value: game_uuid
withdrawal_requests = {} 
TOTAL_PROFIT = 0.0

# --- СОСТОЯНИЯ ---
class AdminState(StatesGroup):
    waiting_for_username = State()
    waiting_for_amount = State()

class UserState(StatesGroup):
    waiting_deposit_amount = State()
    waiting_withdraw_amount = State()

# --- ФУНКЦИИ ---
def get_user(user_id, username=None):
    if user_id not in user_db:
        u_name = f"@{username}" if username else f"ID_{user_id}"
        user_db[user_id] = {'balance': 0.0, 'username': u_name, 'real_name': username}
    if username:
        user_db[user_id]['username'] = f"@{username}"
    return user_db[user_id]

def format_money(amount):
    return f"<b>{amount:.0f} RUB</b>"

# --- ТЕКСТЫ И МЕНЮ ---
RULES_TEXT = f"""
<b>ℹ️ ИНСТРУКЦИЯ {CASINO_NAME}</b>

<b>1. Пополнение:</b> Через CryptoBot или Админа.
<b>2. Вывод:</b> От {MIN_WITHDRAW_RUB} RUB в профиле.

👇 <b>Нажми на команду, чтобы скопировать:</b>

🎲 Кубик:
<code>/cub 100</code> (1 бросок)
<code>/cubtotal3 100</code> (3 броска)

🎯 Дартс:
<code>/dar 100</code>

🎳 Боулинг:
<code>/boul 100</code>

🏀 Баскетбол:
<code>/bas 100</code>

⚽️ Футбол:
<code>/foot 100</code>
"""

START_TEXT = f"👋 <b>Приветствуем в {CASINO_NAME}!</b>\n\nЗдесь честные игры, быстрые выплаты и живые эмоции.\nИспользуй меню для навигации."

def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 Активные игры", callback_data="active_list")],
        [InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit"),
         InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="📚 Как играть?", callback_data="instructions")]
    ])

def join_kb(game_id):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⚔️ Принять вызов", callback_data=f"join_{game_id}")]])

# --- ОБРАБОТЧИКИ МЕНЮ ---

@dp.callback_query(F.data == "back_to_menu")
async def back_menu(cb: CallbackQuery):
    await cb.message.edit_text(START_TEXT, reply_markup=main_kb())

@dp.callback_query(F.data == "instructions")
async def show_rules(cb: CallbackQuery):
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]])
    await cb.message.edit_text(RULES_TEXT, reply_markup=back_kb)

@dp.callback_query(F.data == "profile")
async def show_profile(cb: CallbackQuery):
    u = get_user(cb.from_user.id, cb.from_user.username)
    txt = (f"👤 <b>Личный кабинет</b>\n"
           f"➖➖➖➖➖➖➖➖\n"
           f"🆔 ID: <code>{cb.from_user.id}</code>\n"
           f"💰 Баланс: {format_money(u['balance'])}\n"
           f"➖➖➖➖➖➖➖➖")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 В меню", callback_data="back_to_menu")]])
    await cb.message.edit_text(txt, reply_markup=kb)

# --- АКТИВНЫЕ ИГРЫ ---
@dp.callback_query(F.data == "active_list")
async def show_active_games(cb: CallbackQuery):
    # Фильтруем игры, где статус 'waiting'
    waiting_games = [g for g in active_games.values() if g['status'] == 'waiting']
    
    if not waiting_games:
        await cb.answer("😔 Сейчас нет активных игр. Создай свою!", show_alert=True)
        return

    txt = "🎮 <b>СПИСОК АКТИВНЫХ ИГР:</b>\n\n"
    kb_list = []
    
    # Показываем последние 5 игр
    for game in waiting_games[-5:]:
        txt += f"{game['emoji']} <b>{game['bet']} RUB</b> от {game['p1']['user']} (Бросков: {game['max_rolls']})\n"
        # Добавляем кнопку прямого перехода (если бот админ канала) или просто инфо
        kb_list.append([InlineKeyboardButton(text=f"⚔️ Играть на {game['bet']} RUB", url=f"https://t.me/{cb.message.chat.username}/{game['msg_id']}")])

    # Если бот в группе, ссылка на сообщение (msg_id) может не работать корректно без публичного юзернейма группы. 
    # Поэтому просто даем кнопку "Назад" и обновляем текст.
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]])
    await cb.message.edit_text(txt + "\n<i>Зайдите в чат, чтобы принять игру!</i>", reply_markup=kb)

# --- ФИНАНСЫ (Упрощено для краткости) ---
@dp.callback_query(F.data == "deposit")
async def deposit_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("📥 <b>Введите сумму пополнения (RUB):</b>")
    await state.set_state(UserState.waiting_deposit_amount)
    await cb.answer()

@dp.message(UserState.waiting_deposit_amount)
async def deposit_process(message: Message, state: FSMContext):
    try:
        val = float(message.text)
        if val < MIN_DEPOSIT_RUB: return await message.reply(f"Минимум {MIN_DEPOSIT_RUB} RUB")
        # Тут создание инвойса CryptoBot
        await message.answer(f"🧾 Создан счет на {val} RUB. (Симуляция: нажмите 'Я оплатил')")
        # Симуляция зачисления для теста:
        get_user(message.from_user.id)['balance'] += val
        await message.answer(f"✅ Баланс пополнен! Теперь у вас {get_user(message.from_user.id)['balance']} RUB")
    except: await message.reply("Введите число.")
    await state.clear()

@dp.callback_query(F.data == "withdraw")
async def withdraw_start(cb: CallbackQuery, state: FSMContext):
    u = get_user(cb.from_user.id)
    await cb.message.answer(f"📤 <b>Вывод средств</b>\nДоступно: {u['balance']} RUB\nВведите сумму:")
    await state.set_state(UserState.waiting_withdraw_amount)
    await cb.answer()

@dp.message(UserState.waiting_withdraw_amount)
async def withdraw_process(message: Message, state: FSMContext):
    try:
        val = float(message.text)
    except: return await message.reply("Введите число")
    
    u = get_user(message.from_user.id)
    if val > u['balance'] or val < MIN_WITHDRAW_RUB:
        return await message.reply("❌ Ошибка баланса или лимита.")
    
    u['balance'] -= val
    rid = str(message.message_id)
    withdrawal_requests[rid] = {'user_id': message.from_user.id, 'amount': val, 'username': u['username']}
    await message.answer("✅ <b>Заявка создана!</b> Ожидайте подтверждения.")
    await bot.send_message(ADMIN_ID, f"🔔 <b>ВЫВОД:</b> {val} RUB от {u['username']}\n/admin")
    await state.clear()

# --- АДМИНКА ---
@dp.message(Command("admin"))
async def admin_panel(m: Message):
    if m.from_user.id == ADMIN_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"Заявки ({len(withdrawal_requests)})", callback_data="admin_requests")],
            [InlineKeyboardButton(text="Закрыть", callback_data="close_admin")]
        ])
        await m.answer("👑 Админ-панель", reply_markup=kb)

@dp.callback_query(F.data == "admin_requests")
async def admin_req(cb: CallbackQuery):
    if not withdrawal_requests: return await cb.answer("Пусто", show_alert=True)
    for rid, info in list(withdrawal_requests.items()):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да", callback_data=f"ok_{rid}"), InlineKeyboardButton(text="❌ Нет", callback_data=f"no_{rid}")]
        ])
        await cb.message.answer(f"Заявка #{rid}\n👤 {info['username']}\n💰 {info['amount']}", reply_markup=kb)

@dp.callback_query(F.data.startswith("ok_"))
async def ok_req(cb: CallbackQuery):
    rid = cb.data.split("_")[1]
    if rid in withdrawal_requests:
        del withdrawal_requests[rid]
        await cb.message.edit_text("✅ Выплачено")

@dp.callback_query(F.data.startswith("no_"))
async def no_req(cb: CallbackQuery):
    rid = cb.data.split("_")[1]
    if rid in withdrawal_requests:
        info = withdrawal_requests.pop(rid)
        get_user(info['user_id'])['balance'] += info['amount']
        await cb.message.edit_text("❌ Отклонено (возврат)")

@dp.callback_query(F.data == "close_admin")
async def close_admin(cb: CallbackQuery):
    await cb.message.delete()

# --- 🎲 ЛОГИКА ИГРЫ (ИСПРАВЛЕНА) ---

GAME_TYPES = {
    'cub': {'emoji': '🎲', 'name': 'Кубик'},
    'dar': {'emoji': '🎯', 'name': 'Дартс'},
    'boul': {'emoji': '🎳', 'name': 'Боулинг'},
    'bas': {'emoji': '🏀', 'name': 'Баскетбол'},
    'foot': {'emoji': '⚽', 'name': 'Футбол'}
}

@dp.message(F.text.regexp(r"^/([a-zA-Z0-9]+)\s+(\d+)$"))
async def create_game_handler(message: Message):
    if message.chat.id != GAME_CHAT_ID: return
    
    # Парсинг команды
    match = re.match(r"^/([a-zA-Z0-9]+)\s+(\d+)$", message.text)
    cmd_raw = match.group(1).lower()
    bet = int(match.group(2))
    
    rolls = 1
    g_key = cmd_raw
    if "total" in cmd_raw:
        # Пытаемся достать цифру количества бросков
        last_char = cmd_raw[-1]
        if last_char.isdigit() and '2' <= last_char <= '5':
            rolls = int(last_char)
            g_key = cmd_raw.replace(f"total{last_char}", "")
    
    if g_key not in GAME_TYPES: return
    
    user = get_user(message.from_user.id, message.from_user.username)
    if user['balance'] < bet:
        return await message.reply(f"❌ <b>Недостаточно средств!</b>\nВаш баланс: {format_money(user['balance'])}")

    # Списание и создание
    user['balance'] -= bet
    game_uuid = str(uuid.uuid4())[:8] # Генерируем уникальный ID игры
    
    game_data = {
        'uuid': game_uuid,
        'emoji': GAME_TYPES[g_key]['emoji'],
        'name': GAME_TYPES[g_key]['name'],
        'bet': bet,
        'max_rolls': rolls,
        'status': 'waiting',
        'p1': {'id': message.from_user.id, 'user': user['username'], 'score': 0, 'done': 0},
        'p2': None,
        'msg_id': None # Заполним после отправки сообщения
    }
    
    # Красивое сообщение
    txt = (f"🎰 <b>НОВАЯ ИГРА | {CASINO_NAME}</b>\n\n"
           f"{game_data['emoji']} <b>Игра:</b> {game_data['name']}\n"
           f"👤 <b>Игрок:</b> {user['username']}\n"
           f"💵 <b>Ставка:</b> {bet} RUB\n"
           f"🔢 <b>Бросков:</b> {rolls}\n\n"
           f"👇 <i>Нажми кнопку, чтобы вступить!</i>")
    
    sent_msg = await message.answer(txt, reply_markup=join_kb(game_uuid))
    
    # Сохраняем
    game_data['msg_id'] = sent_msg.message_id
    active_games[game_uuid] = game_data
    game_msg_map[sent_msg.message_id] = game_uuid # Связываем ID сообщения бота с игрой

@dp.callback_query(F.data.startswith("join_"))
async def join_game_handler(cb: CallbackQuery):
    game_uuid = cb.data.split("_")[1]
    
    if game_uuid not in active_games:
        return await cb.answer("❌ Игра не найдена или завершена", show_alert=True)
    
    game = active_games[game_uuid]
    
    if game['status'] != 'waiting':
        return await cb.answer("🔒 Игра уже идет!", show_alert=True)
    
    if cb.from_user.id == game['p1']['id']:
        return await cb.answer("🤡 Нельзя играть самим с собой!", show_alert=True)
        
    user = get_user(cb.from_user.id, cb.from_user.username)
    if user['balance'] < game['bet']:
        return await cb.answer(f"❌ Не хватает денег! Нужно {game['bet']} RUB", show_alert=True)

    # Старт игры
    user['balance'] -= game['bet']
    game['p2'] = {'id': cb.from_user.id, 'user': user['username'], 'score': 0, 'done': 0}
    game['status'] = 'active'
    
    txt = (f"🔥 <b>ИГРА НАЧАЛАСЬ!</b>\n\n"
           f"🔴 <b>{game['p1']['user']}</b> VS 🔵 <b>{game['p2']['user']}</b>\n"
           f"💰 <b>Банк:</b> {game['bet']*2} RUB\n"
           f"🎮 <b>Задача:</b> Кидайте {game['emoji']} в ответ на это сообщение!")
    
    await cb.message.edit_text(txt, reply_markup=None)

@dp.message(F.dice)
async def process_dice(message: Message):
    # Проверка, что это ответ на сообщение (реплай)
    if not message.reply_to_message: return
    
    bot_msg_id = message.reply_to_message.message_id
    
    # Ищем игру по ID сообщения бота
    if bot_msg_id not in game_msg_map: return
    game_uuid = game_msg_map[bot_msg_id]
    game = active_games.get(game_uuid)
    
    if not game or game['status'] != 'active': return
    if message.dice.emoji != game['emoji']: return # Проверка, что кинули правильный смайл

    # Определяем игрока
    player = None
    if message.from_user.id == game['p1']['id']: player = game['p1']
    elif message.from_user.id == game['p2']['id']: player = game['p2']
    
    if not player: return # Чужой кинул кубик
    if player['done'] >= game['max_rolls']: 
        await message.reply("🛑 Ваши попытки кончились!")
        return

    # Засчитываем
    dice_val = message.dice.value
    # Для баскетбола и футбола value работает иначе (1-5), для кубика (1-6)
    # Можно добавить логику подсчета очков (например, в баскетболе 5 это 3 очка), но пока оставим value
    
    player['score'] += dice_val
    player['done'] += 1
    
    score_txt = f"🎲 <b>{player['user']}</b> выбросил <b>{dice_val}</b>!"
    if game['max_rolls'] > 1:
        score_txt += f"\nСумма: {player['score']} (Бросок {player['done']}/{game['max_rolls']})"
    
    msg = await message.reply(score_txt)
    await asyncio.sleep(2) # Пауза для драматизма
    
    # Проверка конца игры
    if game['p1']['done'] >= game['max_rolls'] and game['p2']['done'] >= game['max_rolls']:
        await finish_game(game_uuid, message.chat.id)

async def finish_game(game_uuid, chat_id):
    global TOTAL_PROFIT
    game = active_games[game_uuid]
    p1 = game['p1']
    p2 = game['p2']
    
    bank = game['bet'] * 2
    fee = bank * HOUSE_COMMISSION
    win_sum = bank - fee
    
    text = (f"🏁 <b>ИГРА ОКОНЧЕНА!</b>\n"
            f"➖➖➖➖➖➖➖➖\n"
            f"🔴 {p1['user']}: <b>{p1['score']}</b>\n"
            f"🔵 {p2['user']}: <b>{p2['score']}</b>\n"
            f"➖➖➖➖➖➖➖➖\n")
            
    if p1['score'] > p2['score']:
        text += f"🏆 <b>Победитель:</b> {p1['user']}\n💰 <b>Выигрыш:</b> {format_money(win_sum)}"
        get_user(p1['id'])['balance'] += win_sum
        TOTAL_PROFIT += fee
    elif p2['score'] > p1['score']:
        text += f"🏆 <b>Победитель:</b> {p2['user']}\n💰 <b>Выигрыш:</b> {format_money(win_sum)}"
        get_user(p2['id'])['balance'] += win_sum
        TOTAL_PROFIT += fee
    else:
        text += "🤝 <b>НИЧЬЯ!</b>\nВозврат средств."
        get_user(p1['id'])['balance'] += game['bet']
        get_user(p2['id'])['balance'] += game['bet']

    await bot.send_message(chat_id, text)
    
    # Чистим память
    del active_games[game_uuid]
    # Удаляем из маппинга (можно не удалять сразу, но лучше чистить)
    keys_to_remove = [k for k, v in game_msg_map.items() if v == game_uuid]
    for k in keys_to_remove: del game_msg_map[k]

# --- ЗАПУСК ---
@dp.message(Command("start"))
async def start(m: Message):
    get_user(m.from_user.id, m.from_user.username)
    await m.answer(START_TEXT, reply_markup=main_kb())

async def main():
    print("Бот запущен...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
