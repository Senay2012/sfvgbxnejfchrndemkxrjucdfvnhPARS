"""
████████████████████████████████████████████████
██                                            ██
██      TELEGRAM PARSER PRO — v4.0            ██
██                                            ██
██  Два режима работы:                        ██
██  1. МОНИТОРИНГ — ловит новых юзеров        ██
██     в реальном времени, шлёт в чат         ██
██  2. СБОР БАЗЫ — парсит историю             ██
██     нескольких чатов параллельно           ██
██                                            ██
██  Управление: inline-кнопки в боте          ██
██                                            ██
██  pip install telethon==1.28.5              ██
████████████████████████████████████████████████
"""

import asyncio
import csv
import json
import os
from datetime import datetime

from telethon import TelegramClient, events, Button
from telethon.errors import FloodWaitError
from telethon.tl.types import User

# ╔══════════════════════════════════════════════╗
# ║              КОНФИГУРАЦИЯ                    ║
# ╚══════════════════════════════════════════════╝
API_ID    = 28183245
API_HASH  = '126fd744368c5045fc3f7dfd891cc5a9'
BOT_TOKEN = '7884094901:AAG4mKoeoYd5rL9ND2D18_Nj5RukdzNlvXM'
ADMIN_IDS = [7724292509]

CONFIG_FILE = 'bot_config.json'
CSV_FILE    = 'crypto_users.csv'

DEFAULT_CONFIG = {
    "monitoring_active":  True,
    "send_notifications": True,
    "only_with_username": False,
    "only_premium":       False,
    "target_chat_id":     "-1003300968090",
    "collect_chat_id":    "-1003300968090",
    "collect_limit":      1000,
    "monitored_channels": [
        "https://t.me/prchstikffr",
        "https://t.me/piarchatzaiii",
        "https://t.me/catrafff",
        "https://t.me/piaaarchaaatik",
        "https://t.me/chatkittx",
        "https://t.me/ezoterikov",
        "https://t.me/piarst09",
        "https://t.me/piarfreelancechat",
        "https://t.me/freelance5656",
        "https://t.me/avitotvdd",
        "https://t.me/yourfreelancework",
        "https://t.me/vzaimnopiart",
        "https://t.me/piarchatxsw",
        "https://t.me/poiarch",
        "https://t.me/PiarFactory",
        "https://t.me/piarfreereklama",
    ],
    "collect_channels": [
        "https://t.me/prchstikffr",
        "https://t.me/piarchatzaiii",
    ],
}

# ╔══════════════════════════════════════════════╗
# ║           СОСТОЯНИЕ ПРИЛОЖЕНИЯ               ║
# ╚══════════════════════════════════════════════╝
config: dict          = {}
processed_users: set  = set()
collect_running: bool = False
waiting_input: dict   = {}
user_client: TelegramClient = None


# ╔══════════════════════════════════════════════╗
# ║          КОНФИГ: ЗАГРУЗКА / СОХРАНЕНИЕ       ║
# ╚══════════════════════════════════════════════╝
def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding='utf-8') as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config():
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ╔══════════════════════════════════════════════╗
# ║                  УТИЛИТЫ                     ║
# ╚══════════════════════════════════════════════╝
def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def is_admin(uid: int) -> bool:
    return (not ADMIN_IDS) or (uid in ADMIN_IDS)

def on_off(v: bool) -> str:
    return "🟢 ВКЛ" if v else "🔴 ВЫКЛ"

def passes_filters(sender) -> bool:
    if config["only_with_username"] and not getattr(sender, 'username', None):
        return False
    if config["only_premium"] and not getattr(sender, 'premium', False):
        return False
    return True

def ch_short(url: str) -> str:
    return url.replace("https://t.me/", "@")

def load_processed_users():
    if os.path.exists(CSV_FILE):
        try:
            with open(CSV_FILE, encoding='utf-8') as f:
                r = csv.reader(f)
                next(r)
                for row in r:
                    if len(row) >= 5:
                        try:
                            processed_users.add(int(row[4]))
                        except ValueError:
                            pass
            print(f"📂 Загружено {len(processed_users)} юзеров из базы")
        except Exception as e:
            print(f"⚠️  Ошибка загрузки базы: {e}")

def save_user_csv(u: dict):
    exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(['Канал', 'Username', 'Имя', 'Премиум', 'ID', 'Время'])
        w.writerow([u['channel'], u['username'], u['name'],
                    u['premium'], u['user_id'], u['time']])


# ╔══════════════════════════════════════════════╗
# ║          INLINE-КЛАВИАТУРЫ                   ║
# ╚══════════════════════════════════════════════╝
def kb_home():
    mon_icon = "🟢" if config["monitoring_active"] else "🔴"
    col_icon = "🔵" if collect_running else "⚪"
    return [
        [Button.inline(f"{mon_icon}  МОНИТОРИНГ", b"mode_monitor"),
         Button.inline(f"{col_icon}  СБОР БАЗЫ",  b"mode_collect")],
        [Button.inline("⚙️  Настройки фильтров",  b"filters"),
         Button.inline("📋  Каналы",               b"channels_menu")],
        [Button.inline("📊  Статистика",            b"stats"),
         Button.inline("💾  Экспорт базы",          b"export_menu")],
        [Button.inline("🔄  Обновить",              b"home")],
    ]

def kb_monitor_mode():
    active = config["monitoring_active"]
    notif  = config["send_notifications"]
    return [
        [Button.inline(
            "⏸  Поставить на паузу" if active else "▶️  Возобновить мониторинг",
            b"toggle_monitoring")],
        [Button.inline(f"🔔  Уведомления в чат: {on_off(notif)}", b"toggle_notif")],
        [Button.inline("📋  Каналы мониторинга", b"list_monitor")],
        [Button.inline("📊  Статистика",          b"stats"),
         Button.inline("◀️  Назад",               b"home")],
    ]

def kb_collect_mode():
    running = collect_running
    return [
        [Button.inline(
            "⏳  Сбор идёт... подождите" if running else "🚀  ЗАПУСТИТЬ СБОР БАЗЫ",
            b"noop" if running else b"start_collect")],
        [Button.inline("🗂  Каналы для сбора",             b"list_collect")],
        [Button.inline(f"🔢  Лимит: {config['collect_limit']} сообщ./канал", b"set_limit")],
        [Button.inline("📊  Статистика",                   b"stats"),
         Button.inline("◀️  Назад",                        b"home")],
    ]

def kb_filters():
    u = config["only_with_username"]
    p = config["only_premium"]
    return [
        [Button.inline(f"🔤  Только с @username: {on_off(u)}", b"toggle_username")],
        [Button.inline(f"⭐  Только Premium: {on_off(p)}",      b"toggle_premium")],
        [Button.inline("📤  Чат уведомлений",                   b"set_target"),
         Button.inline("📦  Чат базы",                          b"set_collect_chat")],
        [Button.inline("◀️  Назад", b"home")],
    ]

def kb_channels():
    return [
        [Button.inline("📡  Каналы МОНИТОРИНГА", b"list_monitor")],
        [Button.inline("🗂  Каналы СБОРА БАЗЫ",  b"list_collect")],
        [Button.inline("◀️  Назад",              b"home")],
    ]

def kb_export():
    return [
        [Button.inline("📄  Экспорт TXT (только @username)", b"export_txt")],
        [Button.inline("📊  Экспорт CSV (полная база)",       b"export_csv")],
        [Button.inline("🗑  Очистить базу",                   b"clear_ask"),
         Button.inline("◀️  Назад",                           b"home")],
    ]

def kb_monitor_list():
    chs = config["monitored_channels"]
    rows = []
    for i, ch in enumerate(chs):
        rows.append([Button.inline(f"❌  {ch_short(ch)}", f"del_mon_{i}".encode())])
    rows.append([Button.inline("➕  Добавить канал", b"add_monitor"),
                 Button.inline("◀️  Назад",          b"mode_monitor")])
    return rows

def kb_collect_list():
    chs = config["collect_channels"]
    rows = []
    for i, ch in enumerate(chs):
        rows.append([Button.inline(f"❌  {ch_short(ch)}", f"del_col_{i}".encode())])
    rows.append([Button.inline("➕  Добавить канал", b"add_collect"),
                 Button.inline("◀️  Назад",          b"mode_collect")])
    return rows

def kb_back(dest: bytes):
    return [[Button.inline("◀️  Назад", dest)]]

def kb_confirm_clear():
    return [
        [Button.inline("✅  Да, удалить всё", b"clear_confirm"),
         Button.inline("❌  Отмена",           b"home")],
    ]


# ╔══════════════════════════════════════════════╗
# ║             ТЕКСТЫ ЭКРАНОВ                   ║
# ╚══════════════════════════════════════════════╝
def txt_home() -> str:
    mon_s = "🟢 Активен" if config["monitoring_active"] else "🔴 На паузе"
    col_s = "🔵 Идёт сбор..." if collect_running else "⚪ Не запущен"
    return (
        "┌─────────────────────────────┐\n"
        "│   🤖  ПАРСЕР PRO — МЕНЮ     │\n"
        "└─────────────────────────────┘\n\n"
        f"📡  <b>Мониторинг:</b>  {mon_s}\n"
        f"🗂  <b>Сбор базы:</b>   {col_s}\n\n"
        f"👥  Юзеров в базе:  <b>{len(processed_users)}</b>\n"
        f"📋  Каналов (мон.): <b>{len(config['monitored_channels'])}</b>\n"
        f"🗂  Каналов (сбор): <b>{len(config['collect_channels'])}</b>\n\n"
        f"🕐  {now()}\n\n"
        "▼  Выберите режим или раздел:"
    )

def txt_monitor_mode() -> str:
    active = config["monitoring_active"]
    notif  = config["send_notifications"]
    filters = []
    if config["only_with_username"]: filters.append("@username")
    if config["only_premium"]:       filters.append("Premium")
    flt = ", ".join(filters) if filters else "нет"
    return (
        "📡  <b>РЕЖИМ: МОНИТОРИНГ</b>\n\n"
        "Слушает каналы в реальном времени.\n"
        "Каждый новый уникальный пользователь\n"
        "сохраняется и отправляется в чат.\n\n"
        f"▸  Статус:       {'🟢 Активен' if active else '🔴 На паузе'}\n"
        f"▸  Уведомления:  {'✅ Включены' if notif else '❌ Выключены'}\n"
        f"▸  Каналов:      {len(config['monitored_channels'])}\n"
        f"▸  Собрано:      {len(processed_users)} юзеров\n"
        f"▸  Чат:          <code>{config['target_chat_id']}</code>\n"
        f"▸  Фильтры:      {flt}"
    )

def txt_collect_mode() -> str:
    return (
        "🗂  <b>РЕЖИМ: СБОР БАЗЫ</b>\n\n"
        "Парсит историю сообщений из выбранных\n"
        "каналов <b>параллельно</b>.\n\n"
        "Результат — TXT файл:\n"
        "одна строка = один @username\n\n"
        f"▸  Каналов:  {len(config['collect_channels'])}\n"
        f"▸  Лимит:    {config['collect_limit']} сообщ. на канал\n"
        f"▸  Чат:      <code>{config['collect_chat_id']}</code>\n"
        f"▸  Статус:   {'🔵 Сбор идёт...' if collect_running else '⚪ Готов к запуску'}"
    )

def txt_stats() -> str:
    return (
        "📊  <b>СТАТИСТИКА</b>\n\n"
        f"👥  Юзеров в базе:         <b>{len(processed_users)}</b>\n"
        f"📡  Каналов (мониторинг):  <b>{len(config['monitored_channels'])}</b>\n"
        f"🗂  Каналов (сбор):        <b>{len(config['collect_channels'])}</b>\n\n"
        f"📡  Мониторинг:    {on_off(config['monitoring_active'])}\n"
        f"🔔  Уведомления:   {on_off(config['send_notifications'])}\n"
        f"🔤  Фильтр @user:  {on_off(config['only_with_username'])}\n"
        f"⭐  Фильтр Prem:   {on_off(config['only_premium'])}\n\n"
        f"📤  Чат уведомл.:  <code>{config['target_chat_id']}</code>\n"
        f"📦  Чат базы:      <code>{config['collect_chat_id']}</code>"
    )


# ╔══════════════════════════════════════════════╗
# ║      ОБРАБОТЧИКИ КОМАНД И КНОПОК БОТА        ║
# ╚══════════════════════════════════════════════╝
async def setup_bot(bot: TelegramClient):
    global collect_running

    @bot.on(events.NewMessage(pattern=r'^/(start|menu)$'))
    async def cmd_start(event):
        if not is_admin(event.sender_id): return
        await event.respond(txt_home(), buttons=kb_home(), parse_mode='html')
        raise events.StopPropagation

    @bot.on(events.NewMessage)
    async def handle_text(event):
        uid = event.sender_id
        if not is_admin(uid): return
        if uid not in waiting_input: return
        if not event.text or event.text.startswith('/'): return

        action = waiting_input.pop(uid)
        text   = event.text.strip()

        if action == "add_monitor":
            url = text if text.startswith("http") else f"https://t.me/{text.lstrip('@')}"
            if url in config["monitored_channels"]:
                await event.respond("⚠️  Канал уже есть в мониторинге.", buttons=kb_back(b"list_monitor"))
                return
            config["monitored_channels"].append(url)
            save_config()
            try:
                entity = await user_client.get_entity(url)
                user_client.add_event_handler(make_monitor_handler(bot), events.NewMessage(chats=entity))
                await event.respond(f"✅  Канал добавлен и подключён:\n<code>{url}</code>",
                                    buttons=kb_back(b"list_monitor"), parse_mode='html')
            except Exception as ex:
                await event.respond(f"⚠️  Сохранён, но подключить не удалось: {ex}",
                                    buttons=kb_back(b"list_monitor"))

        elif action == "add_collect":
            url = text if text.startswith("http") else f"https://t.me/{text.lstrip('@')}"
            if url in config["collect_channels"]:
                await event.respond("⚠️  Канал уже есть в списке сбора.", buttons=kb_back(b"list_collect"))
                return
            config["collect_channels"].append(url)
            save_config()
            await event.respond(f"✅  Добавлен в список сбора:\n<code>{url}</code>",
                                buttons=kb_back(b"list_collect"), parse_mode='html')

        elif action == "set_limit":
            try:
                val = int(text)
                if val < 10: raise ValueError
                config["collect_limit"] = val
                save_config()
                await event.respond(f"✅  Лимит: <b>{val}</b> сообщений на канал",
                                    buttons=kb_back(b"mode_collect"), parse_mode='html')
            except ValueError:
                await event.respond("⚠️  Введите число больше 10", buttons=kb_back(b"mode_collect"))

        elif action == "set_target":
            config["target_chat_id"] = text
            save_config()
            await event.respond(f"✅  Чат уведомлений: <code>{text}</code>",
                                buttons=kb_back(b"filters"), parse_mode='html')

        elif action == "set_collect_chat":
            config["collect_chat_id"] = text
            save_config()
            await event.respond(f"✅  Чат для базы: <code>{text}</code>",
                                buttons=kb_back(b"filters"), parse_mode='html')

    @bot.on(events.CallbackQuery)
    async def handle_cb(event):
        global collect_running
        if not is_admin(event.sender_id): return
        uid  = event.sender_id
        data = event.data

        if data == b"home":
            await event.edit(txt_home(), buttons=kb_home(), parse_mode='html')

        elif data == b"mode_monitor":
            await event.edit(txt_monitor_mode(), buttons=kb_monitor_mode(), parse_mode='html')

        elif data == b"mode_collect":
            await event.edit(txt_collect_mode(), buttons=kb_collect_mode(), parse_mode='html')

        elif data == b"toggle_monitoring":
            config["monitoring_active"] = not config["monitoring_active"]
            save_config()
            await event.edit(txt_monitor_mode(), buttons=kb_monitor_mode(), parse_mode='html')

        elif data == b"toggle_notif":
            config["send_notifications"] = not config["send_notifications"]
            save_config()
            await event.edit(txt_monitor_mode(), buttons=kb_monitor_mode(), parse_mode='html')

        elif data == b"filters":
            await event.edit(
                "⚙️  <b>НАСТРОЙКИ ФИЛЬТРОВ</b>\n\n"
                "Фильтры применяются к обоим режимам.\n"
                "Здесь же можно сменить целевые чаты.",
                buttons=kb_filters(), parse_mode='html')

        elif data == b"toggle_username":
            config["only_with_username"] = not config["only_with_username"]
            save_config()
            await event.edit(
                "⚙️  <b>НАСТРОЙКИ ФИЛЬТРОВ</b>\n\n"
                "Фильтры применяются к обоим режимам.",
                buttons=kb_filters(), parse_mode='html')

        elif data == b"toggle_premium":
            config["only_premium"] = not config["only_premium"]
            save_config()
            await event.edit(
                "⚙️  <b>НАСТРОЙКИ ФИЛЬТРОВ</b>\n\n"
                "Фильтры применяются к обоим режимам.",
                buttons=kb_filters(), parse_mode='html')

        elif data == b"set_target":
            waiting_input[uid] = "set_target"
            await event.edit(
                f"📤  <b>Чат для уведомлений</b>\n\n"
                f"Текущий: <code>{config['target_chat_id']}</code>\n\n"
                "Отправьте ID чата:\n<code>-1001234567890</code>",
                buttons=kb_back(b"filters"), parse_mode='html')

        elif data == b"set_collect_chat":
            waiting_input[uid] = "set_collect_chat"
            await event.edit(
                f"📦  <b>Чат для базы данных</b>\n\n"
                f"Текущий: <code>{config['collect_chat_id']}</code>\n\n"
                "Отправьте ID чата или @юзернейм:",
                buttons=kb_back(b"filters"), parse_mode='html')

        elif data == b"channels_menu":
            await event.edit(
                "📋  <b>УПРАВЛЕНИЕ КАНАЛАМИ</b>\n\n"
                "Выберите список для управления:",
                buttons=kb_channels(), parse_mode='html')

        elif data == b"list_monitor":
            chs   = config["monitored_channels"]
            lines = "\n".join(f"  {i+1}. {ch_short(c)}" for i, c in enumerate(chs))
            await event.edit(
                f"📡  <b>Каналы мониторинга ({len(chs)}):</b>\n\n"
                f"{lines if lines else '  — список пуст —'}\n\n"
                "Нажмите ❌ на канале чтобы удалить:",
                buttons=kb_monitor_list(), parse_mode='html')

        elif data == b"add_monitor":
            waiting_input[uid] = "add_monitor"
            await event.edit(
                "📡  <b>Добавить канал в мониторинг</b>\n\n"
                "Отправьте ссылку или @юзернейм:\n"
                "<code>https://t.me/channel</code>",
                buttons=kb_back(b"list_monitor"), parse_mode='html')

        elif data == b"list_collect":
            chs   = config["collect_channels"]
            lines = "\n".join(f"  {i+1}. {ch_short(c)}" for i, c in enumerate(chs))
            await event.edit(
                f"🗂  <b>Каналы сбора базы ({len(chs)}):</b>\n\n"
                f"{lines if lines else '  — список пуст —'}\n\n"
                "Нажмите ❌ на канале чтобы удалить:",
                buttons=kb_collect_list(), parse_mode='html')

        elif data == b"add_collect":
            waiting_input[uid] = "add_collect"
            await event.edit(
                "🗂  <b>Добавить канал в сбор базы</b>\n\n"
                "Отправьте ссылку или @юзернейм:\n"
                "<code>https://t.me/channel</code>",
                buttons=kb_back(b"list_collect"), parse_mode='html')

        elif data.startswith(b"del_mon_"):
            try:
                idx = int(data.split(b"_")[-1])
                chs = config["monitored_channels"]
                if 0 <= idx < len(chs):
                    removed = chs.pop(idx)
                    save_config()
                    await event.answer(f"Удалён: {ch_short(removed)}")
            except Exception:
                pass
            chs   = config["monitored_channels"]
            lines = "\n".join(f"  {i+1}. {ch_short(c)}" for i, c in enumerate(chs))
            await event.edit(
                f"📡  <b>Каналы мониторинга ({len(chs)}):</b>\n\n"
                f"{lines if lines else '  — список пуст —'}\n\n"
                "Нажмите ❌ на канале чтобы удалить:",
                buttons=kb_monitor_list(), parse_mode='html')

        elif data.startswith(b"del_col_"):
            try:
                idx = int(data.split(b"_")[-1])
                chs = config["collect_channels"]
                if 0 <= idx < len(chs):
                    removed = chs.pop(idx)
                    save_config()
                    await event.answer(f"Удалён: {ch_short(removed)}")
            except Exception:
                pass
            chs   = config["collect_channels"]
            lines = "\n".join(f"  {i+1}. {ch_short(c)}" for i, c in enumerate(chs))
            await event.edit(
                f"🗂  <b>Каналы сбора базы ({len(chs)}):</b>\n\n"
                f"{lines if lines else '  — список пуст —'}\n\n"
                "Нажмите ❌ на канале чтобы удалить:",
                buttons=kb_collect_list(), parse_mode='html')

        elif data == b"set_limit":
            waiting_input[uid] = "set_limit"
            await event.edit(
                f"🔢  <b>Лимит сообщений на канал</b>\n\n"
                f"Текущий: <b>{config['collect_limit']}</b>\n\n"
                "Отправьте число (например: 500, 1000, 5000):",
                buttons=kb_back(b"mode_collect"), parse_mode='html')

        elif data == b"start_collect":
            if collect_running:
                await event.answer("⚠️ Сбор уже идёт!", alert=True); return
            if not config["collect_channels"]:
                await event.answer("⚠️ Добавьте каналы для сбора!", alert=True); return
            collect_running = True
            await event.edit(
                f"🚀  <b>Сбор базы запущен!</b>\n\n"
                f"📋  Каналов: <b>{len(config['collect_channels'])}</b>\n"
                f"🔢  Лимит: <b>{config['collect_limit']}</b> сообщ./канал\n\n"
                "⏳  Каналы парсятся <b>параллельно</b>.\n"
                f"Результат придёт сюда и в <code>{config['collect_chat_id']}</code>",
                parse_mode='html')
            asyncio.create_task(run_collect(bot, uid))

        elif data == b"noop":
            await event.answer("⏳ Сбор идёт, подождите...", alert=True); return

        elif data == b"stats":
            await event.edit(txt_stats(),
                             buttons=[[Button.inline("◀️  Назад", b"home")]],
                             parse_mode='html')

        elif data == b"export_menu":
            await event.edit(
                f"💾  <b>ЭКСПОРТ БАЗЫ</b>\n\n"
                f"👥  Юзеров в базе: <b>{len(processed_users)}</b>\n\n"
                "Выберите формат:",
                buttons=kb_export(), parse_mode='html')

        elif data == b"export_txt":
            if not os.path.exists(CSV_FILE) or not processed_users:
                await event.answer("😔 База пуста!", alert=True); return
            await event.answer("📄 Формирую TXT...")
            asyncio.create_task(do_export_txt(bot, uid))

        elif data == b"export_csv":
            if not os.path.exists(CSV_FILE) or not processed_users:
                await event.answer("😔 База пуста!", alert=True); return
            await event.answer("📊 Отправляю CSV...")
            asyncio.create_task(do_export_csv(bot, uid))

        elif data == b"clear_ask":
            await event.edit(
                f"⚠️  <b>УДАЛЕНИЕ БАЗЫ</b>\n\n"
                f"Будет удалено: <b>{len(processed_users)}</b> пользователей.\n"
                "Действие <b>необратимо</b>!\n\nПродолжить?",
                buttons=kb_confirm_clear(), parse_mode='html')

        elif data == b"clear_confirm":
            processed_users.clear()
            if os.path.exists(CSV_FILE):
                os.remove(CSV_FILE)
            await event.edit(
                "✅  <b>База очищена.</b>\n\n"
                "Все записи удалены. Мониторинг продолжается.",
                buttons=[[Button.inline("◀️  Главное меню", b"home")]],
                parse_mode='html')

        try:
            await event.answer()
        except Exception:
            pass


# ╔══════════════════════════════════════════════╗
# ║         ПАРАЛЛЕЛЬНЫЙ СБОР БАЗЫ               ║
# ╚══════════════════════════════════════════════╝
async def collect_one(url: str) -> tuple:
    usernames: set = set()
    count = 0
    try:
        entity = await user_client.get_entity(url)
        async for msg in user_client.iter_messages(entity, limit=config["collect_limit"]):
            count += 1
            if not msg.sender_id: continue
            try:
                sender = await user_client.get_entity(msg.sender_id)
                if isinstance(sender, User) and not sender.bot:
                    if sender.username:
                        usernames.add(f"@{sender.username.lower()}")
                    elif not config["only_with_username"]:
                        usernames.add(f"tg://user?id={sender.id}")
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)
            except Exception:
                pass
        return url, usernames, count, None
    except Exception as ex:
        return url, usernames, count, str(ex)


async def run_collect(bot: TelegramClient, admin_id: int):
    global collect_running
    try:
        channels = list(config["collect_channels"])
        tasks    = [collect_one(url) for url in channels]
        results  = await asyncio.gather(*tasks)

        all_unames: set = set()
        total = 0
        lines = []

        for url, unames, count, err in results:
            all_unames |= unames
            total += count
            if err:
                lines.append(f"❌  {ch_short(url)}: {err[:60]}")
            else:
                lines.append(f"✅  {ch_short(url)}: {count} сообщ., {len(unames)} юзеров")

        report = "\n".join(lines)

        if not all_unames:
            await bot.send_message(admin_id,
                f"😔  <b>Сбор завершён — юзеров не найдено.</b>\n\n{report}",
                buttons=[[Button.inline("◀️  Меню", b"home")]], parse_mode='html')
            return

        txt_path = 'collected_base.txt'
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(sorted(all_unames)))

        summary = (
            f"✅  <b>БАЗА СОБРАНА!</b>\n\n"
            f"👥  Уникальных: <b>{len(all_unames)}</b>\n"
            f"📨  Сообщений:  <b>{total}</b>\n"
            f"📋  Каналов:    <b>{len(channels)}</b>\n\n"
            f"{report}"
        )

        target = config["collect_chat_id"]
        try:
            await bot.send_file(target, txt_path, caption=summary, parse_mode='html')
        except Exception:
            pass

        await bot.send_file(
            admin_id, txt_path, caption=summary,
            buttons=[[Button.inline("◀️  Главное меню", b"home")]],
            parse_mode='html')

    except Exception as ex:
        await bot.send_message(admin_id, f"❌  Ошибка сбора: {ex}")
    finally:
        collect_running = False


# ╔══════════════════════════════════════════════╗
# ║              ЭКСПОРТ ФАЙЛОВ                  ║
# ╚══════════════════════════════════════════════╝
async def do_export_txt(bot: TelegramClient, admin_id: int):
    try:
        unames = []
        with open(CSV_FILE, encoding='utf-8') as f:
            r = csv.reader(f)
            next(r)
            for row in r:
                if len(row) >= 2 and row[1] and row[1] != 'Без username':
                    unames.append(row[1])
        if not unames:
            await bot.send_message(admin_id, "😔 В базе нет юзеров с @username")
            return
        txt_path = 'export_usernames.txt'
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(sorted(set(unames))))
        cap = f"📄  <b>Экспорт @username</b>\n👥  {len(set(unames))} юзеров\n📅  {now()}"
        try:
            await bot.send_file(config["collect_chat_id"], txt_path, caption=cap, parse_mode='html')
        except Exception:
            pass
        await bot.send_file(admin_id, txt_path, caption=cap,
                            buttons=[[Button.inline("◀️  Меню", b"home")]], parse_mode='html')
    except Exception as ex:
        await bot.send_message(admin_id, f"❌ Ошибка экспорта TXT: {ex}")


async def do_export_csv(bot: TelegramClient, admin_id: int):
    try:
        cap = f"📊  <b>Полная база (CSV)</b>\n👥  {len(processed_users)} юзеров\n📅  {now()}"
        try:
            await bot.send_file(config["collect_chat_id"], CSV_FILE, caption=cap, parse_mode='html')
        except Exception:
            pass
        await bot.send_file(admin_id, CSV_FILE, caption=cap,
                            buttons=[[Button.inline("◀️  Меню", b"home")]], parse_mode='html')
    except Exception as ex:
        await bot.send_message(admin_id, f"❌ Ошибка экспорта CSV: {ex}")


# ╔══════════════════════════════════════════════╗
# ║          МОНИТОРИНГ НОВЫХ СООБЩЕНИЙ          ║
# ╚══════════════════════════════════════════════╝
def make_monitor_handler(bot: TelegramClient):
    async def handler(event):
        if not config["monitoring_active"]: return
        try:
            if not event.sender_id or event.sender_id in processed_users: return
            sender = await event.get_sender()
            if not sender or not isinstance(sender, User) or getattr(sender, 'bot', False): return
            if not passes_filters(sender): return

            chat   = await event.get_chat()
            ch_url = f"https://t.me/{chat.username}" if getattr(chat, 'username', None) else str(chat.id)

            username = f"@{sender.username}" if getattr(sender, 'username', None) else "Без username"
            fname    = getattr(sender, 'first_name', '') or ''
            lname    = getattr(sender, 'last_name', '') or ''
            name     = f"{fname} {lname}".strip() or "Без имени"
            premium  = getattr(sender, 'premium', False)
            uid      = sender.id
            ts       = now()

            u = {
                'username': username, 'name': name, 'channel': ch_url,
                'link': f"tg://user?id={uid}",
                'premium': "Да" if premium else "Нет",
                'user_id': uid, 'time': ts,
            }
            processed_users.add(uid)
            save_user_csv(u)

            if config["send_notifications"]:
                prem_tag = " ⭐" if premium else ""
                msg = (
                    f"👤  <b>{name}</b>{prem_tag}\n"
                    f"🔗  {username}\n"
                    f"📍  {ch_url}\n"
                    f"🕐  {ts}"
                )
                try:
                    target = int(config["target_chat_id"])
                except ValueError:
                    target = config["target_chat_id"]
                await bot.send_message(target, msg, parse_mode='html')

            print(f"🆕 {username} | {ch_url}")

        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)
        except Exception as e:
            print(f"⚠️  monitor: {e}")
    return handler


# ╔══════════════════════════════════════════════╗
# ║                    ЗАПУСК                    ║
# ╚══════════════════════════════════════════════╝
async def main():
    global user_client
    config.update(load_config())
    load_processed_users()

    user_client = TelegramClient('session_name', API_ID, API_HASH)
    await user_client.start()
    print("✅  UserClient запущен")

    bot = TelegramClient('bot_session', API_ID, API_HASH)
    await bot.start(bot_token=BOT_TOKEN)
    print("✅  BotClient запущен")

    await setup_bot(bot)

    handler   = make_monitor_handler(bot)
    connected = 0
    for url in config["monitored_channels"]:
        try:
            entity = await user_client.get_entity(url)
            user_client.add_event_handler(handler, events.NewMessage(chats=entity))
            connected += 1
            print(f"   📡 {url}")
        except Exception as ex:
            print(f"   ❌ {url}: {ex}")

    print(f"\n🚀  Запущено! Каналов: {connected}/{len(config['monitored_channels'])}")
    print("📱  Напишите боту /menu\n")

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"🚀  <b>Парсер запущен!</b>\n\n"
                f"📡  Каналов: <b>{connected}</b>\n"
                f"👥  Юзеров в базе: <b>{len(processed_users)}</b>\n\n"
                "Напишите /menu для управления",
                parse_mode='html')
        except Exception:
            pass

    await asyncio.gather(
        user_client.run_until_disconnected(),
        bot.run_until_disconnected(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑  Остановлено")
    except Exception as e:
        print(f"❌  Критическая ошибка: {e}")
