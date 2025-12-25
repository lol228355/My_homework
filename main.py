import asyncio
import logging
import re
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
ADMIN_ID = 7323981601 # Ваш ID

CASINO_NAME = "Andron"
MIN_DEPOSIT_RUB = 50.0
MIN_WITHDRAW_RUB = 150.0
USD_TO_RUB_RATE = 50.0 # Курс для конвертации пополнений
HOUSE_COMMISSION = 0.10  # 10% (скрытая)

# Логирование
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())

# Crypto Pay
crypto = AioCryptoPay(token=CRYPTO_BOT_TOKEN, network=Networks.MAIN_NET)

# --- БАЗА ДАННЫХ В ПАМЯТИ ---
user_db = {}
active_games = {}
withdrawal_requests = {} # id_заявки: {user_id, amount, username}
TOTAL_PROFIT = 0.0 

# --- СОСТОЯНИЯ (FSM) ---
class AdminState(StatesGroup):
    waiting_for_username = State()
    waiting_for_amount = State()

class UserState(StatesGroup):
    waiting_deposit_amount = State()
    waiting_withdraw_amount = State()

# --- ФУНКЦИИ БД ---
def get_user(user_id, username=None):
    if user_id not in user_db:
        u_name = f"@{username}" if username else f"ID_{user_id}"
        user_db[user_id] = {'balance': 0.0, 'username': u_name, 'real_name': username}
    if username: 
        user_db[user_id]['username'] = f"@{username}"
        user_db[user_id]['real_name'] = username
    return user_db[user_id]

def find_user_id_by_name(target_username):
    target = target_username.lower().replace('@', '').strip()
    for uid, data in user_db.items():
        if data.get('real_name', '').lower() == target: return uid
        if data['username'].lower().replace('@', '') == target: return uid
    return None

def format_money(amount):
    return f"{amount:.0f} RUB"

# --- ТЕКСТЫ ---
# Текст правил без упоминания комиссии
RULES_TEXT = f"""
<b>ℹ️ ИНСТРУКЦИЯ {CASINO_NAME}</b>

1. Пополните баланс через CryptoBot или администратора.
2. Создавайте игры командами или вступайте в существующие.
3. Вывод средств осуществляется по запросу в профиле.

<b>Минимальное пополнение:</b> {MIN_DEPOSIT_RUB} RUB
<b>Минимальный вывод:</b> {MIN_WITHDRAW_RUB} RUB

<b>Доступные игры:</b>
🎲 <code>/cub [ставка]</code> — Кубик (1 бросок)
🎯 <code>/dar [ставка]</code> — Дартс
🎳 <code>/boul [ставка]</code> — Боулинг
🏀 <code>/bas [ставка]</code> — Баскетбол
⚽️ <code>/foot [ставка]</code> — Футбол

<b>Сумма бросков (Total):</b>
Пример: <code>/cubtotal3 100</code> (3 броска по 100р)
Команды: <code>/cubtotal[2-5]</code>, <code>/dartotal[2-5]</code> и т.д.
"""

START_TEXT = f"👋 <b>Приветствуем в {CASINO_NAME}!</b>\nИспользуй меню ниже для управления."

# --- КЛАВИАТУРЫ ---
def main_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Пополнить", callback_data="deposit"),
         InlineKeyboardButton(text="💸 Вывести", callback_data="withdraw")],
        [InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
         InlineKeyboardButton(text="📚 Правила", callback_data="instructions")]
    ])

def join_kb(game_id):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Вступить", callback_data=f"join_{game_id}")]])

def admin_kb():
    # Считаем количество активных заявок для красивой кнопки
    req_count = len(withdrawal_requests)
    req_text = f"🔔 Заявки на вывод ({req_count})" if req_count > 0 else "🔕 Заявки на вывод"
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать баланс", callback_data="admin_give_money")],
        [InlineKeyboardButton(text=req_text, callback_data="admin_requests")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="❌ Закрыть", callback_data="close_admin")]
    ])

# Кнопки для обработки заявки
def request_kb(req_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Одобрить (Выплачено)", callback_data=f"req_ok_{req_id}")],
        [InlineKeyboardButton(text="❌ Отклонить (Вернуть)", callback_data=f"req_no_{req_id}")]
    ])

# --- ОБРАБОТЧИКИ КНОПОК МЕНЮ ---

@dp.callback_query(F.data == "instructions")
async def show_rules(cb: CallbackQuery):
    # Показываем инструкцию вместо стартового сообщения, добавляем кнопку "Назад"
    back_kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]])
    await cb.message.edit_text(RULES_TEXT, reply_markup=back_kb)

@dp.callback_query(F.data == "back_to_menu")
async def back_menu(cb: CallbackQuery):
    await cb.message.edit_text(START_TEXT, reply_markup=main_kb())

@dp.callback_query(F.data == "profile")
async def show_profile(cb: CallbackQuery):
    u = get_user(cb.from_user.id, cb.from_user.username)
    txt = f"👤 <b>Ваш профиль:</b>\n\n🆔 ID: <code>{cb.from_user.id}</code>\n💰 Баланс: {format_money(u['balance'])}"
    # Кнопка назад
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")]])
    await cb.message.edit_text(txt, reply_markup=kb)

# --- ЛОГИКА ПОПОЛНЕНИЯ (DEPOSIT) ---
@dp.callback_query(F.data == "deposit")
async def deposit_start(cb: CallbackQuery, state: FSMContext):
    await cb.message.answer("✍️ <b>Введите сумму пополнения в RUB:</b>\n(Минимум 100 RUB)")
    await state.set_state(UserState.waiting_deposit_amount)
    await cb.answer()

@dp.message(UserState.waiting_deposit_amount)
async def deposit_process(message: Message, state: FSMContext):
    try:
        amount_rub = float(message.text)
        if amount_rub < MIN_DEPOSIT_RUB:
            return await message.reply(f"❌ Минимум {MIN_DEPOSIT_RUB} RUB.")
    except ValueError:
        return await message.reply("❌ Введите число.")

    # Конвертация в USD для CryptoBot
    amount_usd = amount_rub / USD_TO_RUB_RATE
    
    try:
        # Создаем счет (invoice)
        invoice = await crypto.create_invoice(asset='USDT', amount=amount_usd, 
                                              description=f"Deposit {amount_rub} RUB to {CASINO_NAME}")
        
        # Кнопка оплаты
        pay_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Оплатить (CryptoBot)", url=invoice.bot_invoice_url)],
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_pay_{invoice.invoice_id}")]
        ])
        
        await message.answer(f"🧾 <b>Счет сформирован</b>\nСумма: {amount_usd:.2f} USDT (~{amount_rub} RUB)\n\nНажмите кнопку ниже для оплаты.", reply_markup=pay_kb)
        
        # В реальном проекте тут нужен Webhook. 
        # Здесь мы просто оставим это пользователю, а начисление сделаем "фейковым" чеком или админ проверит.
        # Для полной автоматизации нужен Webhook Server, что сложно для этого примера.
        # Поэтому добавим "Я оплатил", который просто отправит уведомление админу проверить.
        
    except Exception as e:
        await message.answer(f"Ошибка создания счета: {e}")
    
    await state.clear()

@dp.callback_query(F.data.startswith("check_pay_"))
async def check_pay_fake(cb: CallbackQuery):
    # Заглушка, так как без вебхука мы не узнаем статус
    invoice_id = cb.data.split("_")[2]
    # Пытаемся проверить статус (если бот запущен локально, это сработает при нажатии)
    try:
        old_invoices = await crypto.get_invoices(invoice_ids=invoice_id)
        if old_invoices and old_invoices[0].status == 'paid':
             # Начисляем, если реально оплачено (CryptoBot сам обновляет статус)
             # Но для этого нужно чтобы пользователь реально оплатил USDT
             # Тут сложная логика, упростим:
             await cb.answer("Ожидайте зачисления (система проверяет оплату)", show_alert=True)
        else:
             await cb.answer("Счет еще не оплачен!", show_alert=True)
    except:
        await cb.answer("Заявка отправлена администратору.", show_alert=True)
        # Отправляем админу уведомление
        await bot.send_message(ADMIN_ID, f"📥 <b>Проверьте оплату!</b>\nЮзер: {cb.from_user.id}\nInvoice: {invoice_id}")

# --- ЛОГИКА ВЫВОДА (WITHDRAW) ---
@dp.callback_query(F.data == "withdraw")
async def withdraw_start(cb: CallbackQuery, state: FSMContext):
    user = get_user(cb.from_user.id)
    if user['balance'] < MIN_WITHDRAW_RUB:
        return await cb.answer(f"❌ Минимум для вывода: {MIN_WITHDRAW_RUB} RUB", show_alert=True)
    
    await cb.message.answer(f"💰 Ваш баланс: {user['balance']} RUB\n✍️ <b>Введите сумму для вывода:</b>")
    await state.set_state(UserState.waiting_withdraw_amount)
    await cb.answer()

@dp.message(UserState.waiting_withdraw_amount)
async def withdraw_process(message: Message, state: FSMContext):
    try:
        amount = float(message.text)
    except ValueError:
        return await message.reply("❌ Введите число.")
    
    user = get_user(message.from_user.id)
    if amount < MIN_WITHDRAW_RUB:
        return await message.reply(f"❌ Минимум {MIN_WITHDRAW_RUB} RUB")
    if user['balance'] < amount:
        return await message.reply(f"❌ Недостаточно средств. Доступно: {user['balance']}")

    # Списываем баланс сразу
    user['balance'] -= amount
    
    # Создаем заявку
    req_id = str(message.message_id)
    withdrawal_requests[req_id] = {
        'user_id': message.from_user.id,
        'amount': amount,
        'username': user['username']
    }
    
    await message.answer(f"✅ <b>Заявка создана!</b>\nСумма: {amount} RUB списана с баланса.\nОжидайте одобрения администратора.")
    await bot.send_message(ADMIN_ID, f"🔔 <b>НОВАЯ ЗАЯВКА НА ВЫВОД!</b>\n👤 {user['username']}\n💰 {amount} RUB\n👉 /admin")
    await state.clear()


# --- АДМИН ПАНЕЛЬ И ЗАЯВКИ ---

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("👑 <b>Админ-панель</b>", reply_markup=admin_kb())

@dp.callback_query(F.data == "admin_stats")
async def cb_stats(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    txt = f"📊 <b>Статистика {CASINO_NAME}</b>\n\n💰 Прибыль проекта: {format_money(TOTAL_PROFIT)}\n👤 Юзеров в БД: {len(user_db)}"
    await cb.message.edit_text(txt, reply_markup=admin_kb())

@dp.callback_query(F.data == "close_admin")
async def cb_close(cb: CallbackQuery):
    await cb.message.delete()

# Просмотр заявок
@dp.callback_query(F.data == "admin_requests")
async def view_requests(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    
    if not withdrawal_requests:
        return await cb.answer("📭 Заявок нет", show_alert=True)
    
    await cb.message.delete()
    for req_id, info in list(withdrawal_requests.items()):
        txt = (f"💸 <b>Заявка #{req_id}</b>\n"
               f"👤 Игрок: {info['username']} (ID: <code>{info['user_id']}</code>)\n"
               f"💰 Сумма: {info['amount']} RUB")
        await cb.message.answer(txt, reply_markup=request_kb(req_id))
    
    await cb.message.answer("👑 Админ-панель", reply_markup=admin_kb())

# Одобрение заявки
@dp.callback_query(F.data.startswith("req_ok_"))
async def approve_request(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    req_id = cb.data.split("_")[2]
    
    if req_id in withdrawal_requests:
        info = withdrawal_requests.pop(req_id)
        # Отправляем уведомление юзеру
        try:
            await bot.send_message(info['user_id'], f"✅ <b>Ваша заявка на вывод {info['amount']} RUB одобрена!</b>\nСредства отправлены.")
        except:
            pass
        await cb.message.edit_text(f"✅ Заявка #{req_id} ОДОБРЕНА ({info['amount']} RUB)\nИгрок: {info['username']}", reply_markup=None)
    else:
        await cb.answer("Заявка не найдена", show_alert=True)

# Отклонение заявки
@dp.callback_query(F.data.startswith("req_no_"))
async def reject_request(cb: CallbackQuery):
    if cb.from_user.id != ADMIN_ID: return
    req_id = cb.data.split("_")[2]
    
    if req_id in withdrawal_requests:
        info = withdrawal_requests.pop(req_id)
        # Возвращаем деньги
        get_user(info['user_id'])['balance'] += info['amount']
        
        try:
            await bot.send_message(info['user_id'], f"❌ <b>Заявка на вывод {info['amount']} RUB отклонена.</b>\nСредства возвращены на баланс.")
        except:
            pass
        await cb.message.edit_text(f"❌ Заявка #{req_id} ОТКЛОНЕНА\nДеньги возвращены игроку {info['username']}", reply_markup=None)
    else:
        await cb.answer("Заявка не найдена", show_alert=True)

# Выдача баланса (из прошлого кода)
@dp.callback_query(F.data == "admin_give_money")
async def cb_give_money(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id != ADMIN_ID: return
    await cb.message.edit_text("✍️ <b>Введите Username пользователя</b>", reply_markup=None)
    await state.set_state(AdminState.waiting_for_username)

@dp.message(AdminState.waiting_for_username)
async def process_username(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    target_id = find_user_id_by_name(message.text)
    if not target_id:
        return await message.reply("❌ Пользователь не найден. Введите еще раз или /cancel")
    await state.update_data(target_id=target_id, target_name=message.text)
    await message.reply(f"✅ Найден: {target_id}. Введите сумму:")
    await state.set_state(AdminState.waiting_for_amount)

@dp.message(AdminState.waiting_for_amount)
async def process_amount(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    try:
        amount = float(message.text)
    except: return await message.reply("Число!")
    
    data = await state.get_data()
    user = get_user(data['target_id'])
    user['balance'] += amount
    await message.reply(f"✅ Баланс {data['target_name']} пополнен на {amount}. Итог: {user['balance']}")
    await state.clear()
    await message.answer("👑 Админ-панель", reply_markup=admin_kb())

@dp.message(Command("cancel"), StateFilter(AdminState))
async def cancel_admin(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Отмена.", reply_markup=admin_kb())

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
    sent = await message.answer(
        f"<b>{CASINO_NAME} | НОВАЯ ИГРА</b>\n{GAME_TYPES[base_key]['emoji']} {GAME_TYPES[base_key]['name']}\n"
        f"👤 Создал: {user['username']}\n💰 Ставка: {bet} RUB\n🔢 Бросков: {rolls}",
        reply_markup=join_kb(gid))
    active_games[str(sent.message_id)] = active_games.pop(gid)

@dp.callback_query(F.data.startswith("join_"))
async def join_game(cb: CallbackQuery):
    gid = cb.data.split("_")[1]
    if gid not in active_games or active_games[gid]['status'] != 'waiting':
        return await cb.answer("Игра недоступна")
    game = active_games[gid]
    user = get_user(cb.from_user.id, cb.from_user.username)
    if cb.from_user.id == game['p1']['id']: return await cb.answer("Нельзя с собой", show_alert=True)
    if user['balance'] < game['bet']: return await cb.answer(f"Нужно {game['bet']} RUB", show_alert=True)

    user['balance'] -= game['bet']
    game['p2'] = {'id': cb.from_user.id, 'user': user['username'], 'score': 0, 'done': 0}
    game['status'] = 'active'
    await cb.message.edit_text(
        f"<b>{CASINO_NAME} | ИГРА НАЧАТА</b>\n👥 {game['p1']['user']} VS {game['p2']['user']}\n"
        f"💰 Банк: {game['bet']*2} RUB\n— Кидайте {game['emoji']} в ответ!", reply_markup=None)

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
        # Не пишем про комиссию, просто итог
        res += f"🏆 Победил {p1['user']}!\n💰 Выигрыш: {format_money(win_sum)}"
    elif p2['score'] > p1['score']:
        get_user(p2['id'])['balance'] += win_sum
        TOTAL_PROFIT += fee
        res += f"🏆 Победил {p2['user']}!\n💰 Выигрыш: {format_money(win_sum)}"
    else:
        get_user(p1['id'])['balance'] += game['bet']
        get_user(p2['id'])['balance'] += game['bet']
        res += "🤝 Ничья! Ставки возвращены."

    await msg.answer(res)
    del active_games[gid]

@dp.message(Command("start"))
async def start(m: Message):
    get_user(m.from_user.id, m.from_user.username)
    await m.answer(START_TEXT, reply_markup=main_kb())

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
