import vk_api
from vk_api.utils import get_random_id
import sqlite3
import datetime
import time
import random
import json
from tasks_database import TASKS

# КОНФИГУРАЦИЯ
GROUP_TOKEN = 'vk1.a.U55bi2V1xVgwCZDsXAWPiC_6grS-v98AgwmjCrUAD0-QrxXOkR_eG2-Dub2XnEQCJ7d_zn5q2KM_R_tusJwuo_EeIyh71U2bGuytK5x5gtzFuteho0HAG7-62rVzmHMm20sRryQn2JY9sbDFalf-ksqpGA2dCXF3Jq6gwbuA6Parud9Q8Xvw_GO67KqwN2IUDnM8nMHMFCU1pckQiV90mQ'
ADMIN_IDS = [424837142]  # ID администраторов

# Опыт за задания в зависимости от отдела
TASK_EXPERIENCE = {
    'Патрульный': 25,
    'Детектив': 50,
    'Спецназ': 75
}

# Система рулетки
ROULETTE_PRIZES = {
    'experience': [10, 25, 50, 100],
    'bonus_tasks': [1, 2, 3],
    'special': ["2x опыт на след. задание", "Мгновенное задание", "Повышение ранга (малое)"]
}

# Инициализация VK API
vk_session = vk_api.VkApi(token=GROUP_TOKEN)
vk = vk_session.get_api()

# База данных
conn = sqlite3.connect('bot_db.sqlite', check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц
cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY, 
    rank TEXT DEFAULT 'Рядовой',
    experience INTEGER DEFAULT 0,
    last_task_time TEXT,
    current_task TEXT,
    join_date TEXT,
    department TEXT DEFAULT 'Патрульный',
    attempts INTEGER DEFAULT 3,              -- Попытки для рулетки
    last_attempt_time TEXT,                  -- Время последней попытки
    bonus_tasks INTEGER DEFAULT 0,           -- Дополнительные задания
    daily_attempts_reset TEXT                -- Дата последнего сброса попыток
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    task_text TEXT NOT NULL,
    difficulty TEXT NOT NULL
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS experience_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    amount INTEGER,
    reason TEXT,
    admin_id INTEGER,
    timestamp TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS attempts_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    amount INTEGER,
    reason TEXT,
    admin_id INTEGER,
    timestamp TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS bonus_tasks_log (
    id INTEGER PRIMARY KEY,
    user_id INTEGER,
    amount INTEGER,
    action TEXT,
    reason TEXT,
    timestamp TEXT
)
''')
conn.commit()

# Соответствие рангов и отделов
RANK_TO_DEPARTMENT = {
    'Рядовой': 'Патрульный',
    'Сержант': 'Детектив', 
    'Лейтенант': 'Спецназ',
    'Капитан': 'Спецназ',
    'Майор': 'Спецназ',
    'Подполковник': 'Спецназ',
    'Полковник': 'Спецназ'
}

DEPARTMENT_INFO = {
    'Патрульный': {'emoji': '🟢', 'min_rank': 'Рядовой'},
    'Детектив': {'emoji': '🟡', 'min_rank': 'Сержант'},
    'Спецназ': {'emoji': '🔴', 'min_rank': 'Лейтенант'}
}

def create_keyboard(buttons):
    """Создает инлайн-клавиатуру"""
    keyboard = {
        "inline": True,
        "buttons": buttons
    }
    return keyboard

def get_main_keyboard():
    """Основная клавиатура"""
    buttons = [
        [
            {"action": {"type": "text", "label": "🎯 Задание", "payload": "{\"command\":\"task\"}"}, "color": "primary"},
            {"action": {"type": "text", "label": "⭐ Статус", "payload": "{\"command\":\"status\"}"}, "color": "secondary"}
        ],
        [
            {"action": {"type": "text", "label": "🎰 Рулетка", "payload": "{\"command\":\"roulette\"}"}, "color": "positive"},
            {"action": {"type": "text", "label": "👮 Служба", "payload": "{\"command\":\"service\"}"}, "color": "primary"}
        ]
    ]
    return create_keyboard(buttons)

def upload_photo_to_vk(image_type=None):
    """Загружает картинку на VK сервера и возвращает attachment строку"""
    try:
        import requests
        import os

        # Определяем имя файла картинки в зависимости от типа
        if image_type == 'task':
            filename = 'task.png'
        elif image_type == 'roulette':
            filename = 'generated-icon.png'  # Используем основную картинку
        elif image_type == 'service':
            filename = 'status.png'
        elif image_type == 'welcome':
            filename = 'welcome.png'
        else:
            filename = 'generated-icon.png'  # По умолчанию

        # Проверяем существование файла, если нет - используем основной
        if not os.path.exists(filename):
            filename = 'generated-icon.png'

        # Получаем сервер для загрузки
        upload_url = vk.photos.getMessagesUploadServer()['upload_url']

        # Загружаем файл
        with open(filename, 'rb') as photo_file:
            response = requests.post(upload_url, files={'photo': photo_file}).json()

        # Сохраняем фото
        photo = vk.photos.saveMessagesPhoto(
            photo=response['photo'],
            server=response['server'],
            hash=response['hash']
        )[0]

        # Возвращаем attachment строку
        return f"photo{photo['owner_id']}_{photo['id']}"
    except Exception as e:
        print(f"⚠️ Ошибка загрузки фото: {e}")
        return None

def send_message(user_id, message, keyboard=None, image_type=None):
    """Отправка сообщения с возможностью добавления клавиатуры и картинки"""
    try:
        # Для новых пользователей не отправляем клавиатуру
        cursor.execute("SELECT COUNT(*) FROM users WHERE user_id=?", (user_id,))
        user_exists = cursor.fetchone()[0] > 0

        if not user_exists and keyboard:
            print("⚠️  Пропускаем клавиатуру для нового пользователя")
            keyboard = None

        # Загружаем картинку
        photo_attachment = upload_photo_to_vk(image_type)

        params = {
            'user_id': user_id,
            'message': message,
            'random_id': get_random_id()
        }

        if keyboard:
            params['keyboard'] = json.dumps(keyboard)

        if photo_attachment:
            params['attachment'] = photo_attachment

        vk.messages.send(**params)
        print(f"✓ Отправлено пользователю {user_id} {'с картинкой' if photo_attachment else ''}")
        return True
    except vk_api.exceptions.ApiError as e:
        if e.code == 912:
            print(f"⚠️ VK API Ошибка 912: Отправляем без клавиатуры")
            # Повторяем без клавиатуры
            try:
                photo_attachment = upload_photo_to_vk(image_type)
                params = {
                    'user_id': user_id,
                    'message': message,
                    'random_id': get_random_id()
                }
                if photo_attachment:
                    params['attachment'] = photo_attachment

                vk.messages.send(**params)
                print(f"✓ Отправлено без клавиатуры пользователю {user_id} {'с картинкой' if photo_attachment else ''}")
                return True
            except Exception as e2:
                print(f"✗ Критическая ошибка отправки: {e2}")
                return False
        else:
            print(f"✗ VK API ошибка: {e}")
            return False
    except Exception as e:
        print(f"✗ Ошибка отправки: {e}")
        return False

def is_admin(user_id):
    """Проверяет, является ли пользователь администратором"""
    return user_id in ADMIN_IDS

def add_experience(user_id, amount, reason, admin_id):
    """Добавляет опыт пользователю (ручное начисление)"""
    cursor.execute("UPDATE users SET experience = experience + ? WHERE user_id=?", (amount, user_id))
    conn.commit()

    # Логируем начисление
    cursor.execute(
        "INSERT INTO experience_log (user_id, amount, reason, admin_id, timestamp) VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, reason, admin_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()

    # Проверяем повышение ранга
    cursor.execute("SELECT experience, rank FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    if not result:
        return None
    exp, current_rank = result

    ranks = {
        0: "Рядовой",
        100: "Сержант", 
        300: "Лейтенант",
        600: "Капитан",
        1000: "Майор",
        1500: "Подполковник",
        2000: "Полковник"
    }

    new_rank = "Рядовой"
    for threshold, rank in sorted(ranks.items(), reverse=True):
        if exp >= threshold:
            new_rank = rank
            break

    if current_rank != new_rank:
        cursor.execute("UPDATE users SET rank=? WHERE user_id=?", (new_rank, user_id))
        conn.commit()

        # Обновляем отдел при повышении
        new_department = RANK_TO_DEPARTMENT.get(new_rank, 'Патрульный')
        cursor.execute("UPDATE users SET department=? WHERE user_id=?", (new_department, user_id))
        conn.commit()

        return new_rank
    return None

def add_attempts(user_id, amount, reason, admin_id):
    """Добавляет попытки пользователю"""
    cursor.execute("UPDATE users SET attempts = attempts + ? WHERE user_id=?", (amount, user_id))
    conn.commit()

    # Логируем начисление
    cursor.execute(
        "INSERT INTO attempts_log (user_id, amount, reason, admin_id, timestamp) VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, reason, admin_id, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()

    # Получаем обновленное количество попыток
    cursor.execute("SELECT attempts FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else amount

def add_bonus_tasks(user_id, amount, reason):
    """Добавляет бонусные задания пользователю"""
    cursor.execute("UPDATE users SET bonus_tasks = bonus_tasks + ? WHERE user_id=?", (amount, user_id))
    conn.commit()

    # Логируем начисление
    cursor.execute(
        "INSERT INTO bonus_tasks_log (user_id, amount, action, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
        (user_id, amount, 'add', reason, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()

    # Получаем обновленное количество бонусных заданий
    cursor.execute("SELECT bonus_tasks FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else amount

def use_bonus_task(user_id, reason):
    """Использует одно бонусное задание"""
    cursor.execute("UPDATE users SET bonus_tasks = bonus_tasks - 1 WHERE user_id=?", (user_id,))
    conn.commit()

    # Логируем использование
    cursor.execute(
        "INSERT INTO bonus_tasks_log (user_id, amount, action, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
        (user_id, 1, 'use', reason, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()

    # Получаем обновленное количество бонусных заданий
    cursor.execute("SELECT bonus_tasks FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 0

def can_get_new_task(user_id):
    """Проверяет, может ли пользователь получить новое задание"""
    cursor.execute("SELECT last_task_time, bonus_tasks FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()

    if not result:
        return True, None, False

    last_task_time, bonus_tasks = result

    # Если никогда не получал задание
    if not last_task_time:
        return True, None, False

    # Проверяем время с последнего задания
    last_task_time = datetime.datetime.strptime(last_task_time, "%Y-%m-%d %H:%M:%S")
    now = datetime.datetime.now()
    time_diff = now - last_task_time

    # Если есть бонусные задания, можно получить сразу
    if bonus_tasks > 0:
        return True, "bonus", True

    # Стандартная проверка времени
    if time_diff.total_seconds() >= 24 * 3600:
        return True, None, False
    else:
        remaining = 24 * 3600 - time_diff.total_seconds()
        hours = int(remaining // 3600)
        minutes = int((remaining % 3600) // 60)
        return False, f"{hours}ч {minutes}м", False

def get_user_info(user_id):
    """Получает информацию о пользователе"""
    cursor.execute("SELECT rank, experience, current_task, last_task_time, department, attempts, last_attempt_time, bonus_tasks FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()

    if result:
        rank, exp, current_task, last_task_time, department, attempts, last_attempt_time, bonus_tasks = result
        return {
            'rank': rank,
            'experience': exp,
            'department': department,
            'current_task': current_task,
            'last_task_time': last_task_time,
            'attempts': attempts,
            'last_attempt_time': last_attempt_time,
            'bonus_tasks': bonus_tasks
        }
    return None

def ensure_user_exists(user_id):
    """Создает запись пользователя если не существует"""
    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, rank, experience, join_date, department, attempts, daily_attempts_reset) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, 'Рядовой', 0, datetime.datetime.now().strftime("%Y-%m-%d"), 'Патрульный', 3, datetime.datetime.now().strftime("%Y-%m-%d"))
        )
        conn.commit()
        return True
    return False

def spin_roulette(user_id):
    """Крутка рулетки"""
    user_info = get_user_info(user_id)

    if user_info['attempts'] <= 0:
        return False, "❌ У вас нет попыток для рулетки"

    # Проверяем время (максимум 1 раз в день)
    if user_info['last_attempt_time']:
        last_spin = datetime.datetime.strptime(user_info['last_attempt_time'], "%Y-%m-%d %H:%M:%S")
        if (datetime.datetime.now() - last_spin).total_seconds() < 24 * 3600:
            return False, "⏰ Рулетку можно крутить раз в день"

    # Выбираем случайный тип приза
    prize_types = ['experience'] * 50 + ['bonus_tasks'] * 30 + ['special'] * 20
    prize_type = random.choice(prize_types)
    prize = random.choice(ROULETTE_PRIZES[prize_type])

    # Обновляем попытки и время
    cursor.execute("UPDATE users SET attempts = attempts - 1, last_attempt_time = ? WHERE user_id = ?",
                  (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    conn.commit()

    # Выдаем приз
    if prize_type == 'experience':
        add_experience(user_id, prize, "Выигрыш в рулетке", 0)
        return True, f"🎉 Вы выиграли {prize} опыта!"

    elif prize_type == 'bonus_tasks':
        new_bonus_count = add_bonus_tasks(user_id, prize, "Выигрыш в рулетке")
        return True, f"🎉 Вы выиграли {prize} дополниных заданий! Теперь у вас {new_bonus_count} бонусных заданий."

    else:
        # Для специальных призов
        if prize == "Мгновенное задание":
            # Сбрасываем таймер задания
            cursor.execute("UPDATE users SET last_task_time = NULL WHERE user_id = ?", (user_id,))
            conn.commit()
            return True, f"🎉 Вы выиграли: {prize}! Можете получить новое задание сразу."

        elif prize == "2x опыт на след. задание":
            # Временный бонус (можно реализовать через отдельную таблицу временных бонусов)
            return True, f"🎉 Вы выиграли: {prize}! Обратитесь к администратору для активации."

        else:
            return True, f"🎉 Вы выиграли: {prize}!"

def reset_daily_attempts():
    """Ежедневный сброс попыток"""
    now = datetime.datetime.now()
    today = now.strftime("%Y-%m-%d")

    # Сбрасываем попытки только для тех, у кого дата сброса не сегодня
    cursor.execute("""
        UPDATE users 
        SET attempts = 3, 
            daily_attempts_reset = ?
        WHERE daily_attempts_reset != ? OR daily_attempts_reset IS NULL
    """, (today, today))

    updated = cursor.rowcount
    conn.commit()

    if updated > 0:
        print(f"✅ Сброшены попытки для {updated} пользователей")
    else:
        print("ℹ️ Попытки уже сброшены сегодня")

def handle_admin_command(user_id, text):
    """Обработка команд администратора"""
    parts = text.split()
    command = parts[0].lower()

    if command == '/add_exp':
        if len(parts) < 3:
            send_message(user_id, "❌ Формат команды: /add_exp [user_id] [amount] [reason]")
            return

        try:
            target_user_id = int(parts[1])
            amount = int(parts[2])
            reason = ' '.join(parts[3:]) if len(parts) > 3 else "Награда за задание"

            if amount <= 0:
                send_message(user_id, "❌ Сумма опыта должна быть положительной")
                return

            # Проверяем существование пользователя
            ensure_user_exists(target_user_id)

            # Начисляем опыт
            new_rank = add_experience(target_user_id, amount, reason, user_id)

            # Получаем информацию о пользователе после начисления
            target_info = get_user_info(target_user_id)

            response = (
                f"✅ Начислено {amount} опыта пользователю {target_user_id}\n"
                f"📝 Причина: {reason}\n"
                f"⭐ Текущий опыт: {target_info['experience']}\n"
                f"👮 Звание: {target_info['rank']}"
            )

            if new_rank:
                response += f"\n🎉 Новое звание: {new_rank}"

            send_message(user_id, response)

            # Уведомляем пользователя
            send_message(target_user_id, 
                f"🎉 Вам начислено {amount} опыта!\n"
                f"📝 Причина: {reason}\n"
                f"⭐ Текущий опыт: {target_info['experience']}\n"
                f"👮 Звание: {target_info['rank']}"
            )

        except ValueError:
            send_message(user_id, "❌ Неверный формат. Используйте: /add_exp [user_id] [amount] [reason]")
        except Exception as e:
            send_message(user_id, f"❌ Ошибка: {e}")

    elif command == '/add_attempts':
        if len(parts) < 3:
            send_message(user_id, "❌ Формат команды: /add_attempts [user_id] [amount] [reason]")
            return

        try:
            target_user_id = int(parts[1])
            amount = int(parts[2])
            reason = ' '.join(parts[3:]) if len(parts) > 3 else "Награда за активность"

            if amount <= 0:
                send_message(user_id, "❌ Количество попыток должно быть положительным")
                return

            # Проверяем существование пользователя
            ensure_user_exists(target_user_id)

            # Начисляем попытки
            new_attempts = add_attempts(target_user_id, amount, reason, user_id)

            response = (
                f"✅ Начислено {amount} попыток пользователю {target_user_id}\n"
                f"📝 Причина: {reason}\n"
                f"🎰 Теперь попыток: {new_attempts}"
            )

            send_message(user_id, response)

            # Уведомляем пользователя
            send_message(target_user_id, 
                f"🎉 Вам начислено {amount} попыток для рулетки!\n"
                f"📝 Причина: {reason}\n"
                f"🎰 Теперь попыток: {new_attempts}"
            )

        except ValueError:
            send_message(user_id, "❌ Неверный формат. Используйте: /add_attempts [user_id] [amount] [reason]")
        except Exception as e:
            send_message(user_id, f"❌ Ошибка: {e}")

    elif command == '/add_bonus_tasks':
        if len(parts) < 3:
            send_message(user_id, "❌ Формат команды: /add_bonus_tasks [user_id] [amount] [reason]")
            return

        try:
            target_user_id = int(parts[1])
            amount = int(parts[2])
            reason = ' '.join(parts[3:]) if len(parts) > 3 else "Награда за активность"

            if amount <= 0:
                send_message(user_id, "❌ Количество бонусных заданий должно быть положительным")
                return

            # Проверяем существование пользователя
            ensure_user_exists(target_user_id)

            # Начисляем бонусные задания
            new_bonus_count = add_bonus_tasks(target_user_id, amount, reason)

            response = (
                f"✅ Начислено {amount} бонусных заданий пользователю {target_user_id}\n"
                f"📝 Причина: {reason}\n"
                f"🎁 Теперь бонусных заданий: {new_bonus_count}"
            )

            send_message(user_id, response)

            # Уведомляем пользователя
            send_message(target_user_id, 
                f"🎉 Вам начислено {amount} бонусных заданий!\n"
                f"📝 Причина: {reason}\n"
                f"🎁 Теперь бонусных заданий: {new_bonus_count}\n\n"
                f"💡 Бонусные задания позволяют получать новые задания без ожидания 24 часов!"
            )

        except ValueError:
            send_message(user_id, "❌ Неверный формат. Используйте: /add_bonus_tasks [user_id] [amount] [reason]")
        except Exception as e:
            send_message(user_id, f"❌ Ошибка: {e}")

    elif command == '/complete_task':
        if len(parts) < 2:
            send_message(user_id, "❌ Формат команды: /complete_task [user_id]")
            return

        try:
            target_user_id = int(parts[1])

            # Проверяем существование пользователя
            ensure_user_exists(target_user_id)
            user_info = get_user_info(target_user_id)

            if not user_info['current_task']:
                send_message(user_id, "❌ У пользователя нет активного задания")
                return

            # Начисляем опыт за задание
            experience_amount = TASK_EXPERIENCE.get(user_info['department'], 25)
            new_rank = add_experience(target_user_id, experience_amount, "Выполнение задания", user_id)

            # Сбрасываем текущее задание и обновляем время получения задания
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("UPDATE users SET current_task=NULL, last_task_time=? WHERE user_id=?", (now, target_user_id))
            conn.commit()

            # Получаем обновленную информацию о пользователе
            updated_info = get_user_info(target_user_id)

            response = (
                f"✅ Задание пользователя {target_user_id} завершено!\n"
                f"🎯 Задание: {user_info['current_task']}\n"
                f"⭐ Начислено опыта: {experience_amount}\n"
                f"📊 Текущий опыт: {updated_info['experience']}\n"
                f"👮 Звание: {updated_info['rank']}"
            )

            if new_rank:
                response += f"\n🎉 Новое звание: {new_rank}"

            send_message(user_id, response)

            # Уведомляем пользователя
            send_message(target_user_id,
                f"🎉 Ваше задание выполнено!\n"
                f"🎯 Задание: {user_info['current_task']}\n"
                f"⭐ Награда: {experience_amount} опыта\n"
                f"📊 Текущий опыт: {updated_info['experience']}\n"
                f"👮 Звание: {updated_info['rank']}\n\n"
                f"⏳ Следующее задание будет доступно через 24 часа"
            )

        except ValueError:
            send_message(user_id, "❌ Неверный формат. Используйте: /complete_task [user_id]")
        except Exception as e:
            send_message(user_id, f"❌ Ошибка: {e}")

    else:
        send_message(user_id,
            "👮 Команды администратора:\n\n"
            "➕ /add_exp [user_id] [amount] [reason] - начислить опыт\n"
            "🎰 /add_attempts [user_id] [amount] [reason] - начислить попытки\n"
            "🎁 /add_bonus_tasks [user_id] [amount] [reason] - начислить бонусные задания\n"
            "✅ /complete_task [user_id] - завершить задание пользователя"
        )

def show_user_status(user_id):
    """Показывает статус пользователя"""
    user_info = get_user_info(user_id)
    if not user_info:
        send_message(user_id, "❌ Вы не зарегистрированы. Напишите 'Служба' чтобы начать.")
        return

    department = user_info['department']
    dept_info = DEPARTMENT_INFO[department]

    # Следующее звание
    exp = user_info['experience']
    next_rank_exp = 100 - (exp % 100) if exp < 2000 else 0

    status_msg = (
        f"{dept_info['emoji']} Статус сотрудника:\n\n"
        f"👮 Отдел: {department}\n"
        f"⭐ Звание: {user_info['rank']}\n"
        f"🎯 Опыт: {exp} очков\n"
        f"🎰 Попытки рулетки: {user_info['attempts']}\n"
        f"🎁 Доп. задания: {user_info['bonus_tasks']}\n"
    )

    if next_rank_exp > 0:
        status_msg += f"📈 До следующего звания: {next_rank_exp} очков\n"

    # Следующий отдел
    ranks_order = ["Рядовой", "Сержант", "Лейтенант", "Капитан", "Майор", "Подполковник", "Полковник"]
    current_index = ranks_order.index(user_info['rank'])

    if current_index < len(ranks_order) - 1:
        next_rank = ranks_order[current_index + 1]
        next_dept = RANK_TO_DEPARTMENT.get(next_rank, 'Спецназ')
        if next_dept != department:
            status_msg += f"🔓 Следующий отдел: {next_dept} (звание {next_rank})\n"

    # Активное задание или время ожидания
    if user_info['current_task']:
        status_msg += f"\n📋 Активное задание:\n{user_info['current_task']}"
    else:
        # Проверяем время до следующего задания
        can_get, time_remaining, has_bonus = can_get_new_task(user_id)
        if not can_get and not has_bonus:
            status_msg += f"\n⏳ Ожидание следующего задания: {time_remaining}"
        elif has_bonus:
            status_msg += f"\n🎁 Можете получить задание сейчас (используя бонусное задание)"
        else:
            status_msg += f"\n✅ Готов к получению нового задания!"

    send_message(user_id, status_msg, get_main_keyboard(), 'service')

def send_task_to_user(user_id):
    """Отправляет задание пользователю (без автоматического начисления опыта)"""
    user_info = get_user_info(user_id)
    if not user_info:
        send_message(user_id, "❌ Сначала напишите 'Служба' чтобы начать!")
        return

    # Проверяем возможность получения задания
    can_get, time_remaining, has_bonus = can_get_new_task(user_id)

    if not can_get and not has_bonus:
        send_message(user_id, 
            f"⏰ Вы уже выполнили задание. Следующее будет доступно через {time_remaining}\n\n"
            f"💡 Используйте бонусные задания для получения заданий без ожидания!",
            get_main_keyboard()
        )
        return

    # Если используем бонусное задание
    using_bonus = False
    if has_bonus:
        # Предлагаем использовать бонусное задание
        remaining_bonus = use_bonus_task(user_id, "Получение задания без ожидания")
        using_bonus = True

    # Получаем новое задание
    department = user_info['department']
    task = get_random_task(department)

    # Сохраняем время получения задания
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("UPDATE users SET last_task_time=?, current_task=? WHERE user_id=?", (now, task, user_id))
    conn.commit()

    dept_info = DEPARTMENT_INFO[department]
    experience_amount = TASK_EXPERIENCE[department]

    message = (
        f"{dept_info['emoji']} Служебное задание ({department}):\n\n"
        f"🎯 {task}\n\n"
        f"💰 Награда: {experience_amount} опыта\n"
        f"👮 Звание: {user_info['rank']}\n"
    )

    if using_bonus:
        message += f"🎁 Использовано бонусное задание. Осталось: {remaining_bonus}\n"

    message += "💫 Выполните задание и обратитесь к командиру для награды!"

    if not using_bonus:
        message += "\n\n⏳ Следующее задание через 24 часа"
    else:
        message += "\n\n💡 Можете получить следующее задание сразу, если у вас есть бонусные задания!"

    send_message(user_id, message, get_main_keyboard(), 'task')

def get_random_task(department):
    """Возвращает случайное задание для отдела"""
    difficulty = 'easy' if department == 'Патрульный' else 'medium' if department == 'Детектив' else 'hard'
    try:
        cursor.execute(
            "SELECT task_text FROM tasks WHERE difficulty=? ORDER BY RANDOM() LIMIT 1", 
            (difficulty,)
        )
        task = cursor.fetchone()
        return task[0] if task else random.choice(TASKS[difficulty])
    except:
        return random.choice(TASKS[difficulty])

def handle_message(user_id, text, payload=None):
    """Обработка входящих сообщений с поддержкой payload"""
    # Обработка payload от кнопок
    if payload:
        try:
            payload_data = json.loads(payload)
            if 'command' in payload_data:
                text = payload_data['command']
        except:
            pass

    text = text.lower().strip()
    print(f"📩 Сообщение от {user_id}: '{text}' (payload: {payload})")

    # Команды администратора
    if is_admin(user_id) and (text.startswith('/add_exp') or text.startswith('/add_attempts') or 
                             text.startswith('/add_bonus_tasks') or text.startswith('/complete_task')):
        handle_admin_command(user_id, text)
        return

    # Гарантируем что пользователь существует в базе
    is_new_user = ensure_user_exists(user_id)
    user_info = get_user_info(user_id)

    if text in ['начать', 'служба', 'старт', 'service']:
        department = user_info['department']
        dept_info = DEPARTMENT_INFO[department]

        welcome_msg = (
            f"{dept_info['emoji']} Добро пожаловать в полицейский департамент!\n\n"
            f"👮 Ваш отдел: {department}\n"
            f"⭐ Звание: {user_info['rank']}\n"
            f"🎯 Опыт: {user_info['experience']} очков\n"
            f"🎰 Попытки рулетки: {user_info['attempts']}\n"
            f"🎁 Бонусные задания: {user_info['bonus_tasks']}\n\n"
        )

        if is_new_user:
            welcome_msg += "🎉 Вы приняты на службу! Обратитесь к командиру для получения задания."
        else:
            welcome_msg += "💫 Ожидайте задания от командира!"

        send_message(user_id, welcome_msg, get_main_keyboard(), 'welcome')

    elif text in ['задание', 'рапорт', 'task']:
        send_task_to_user(user_id)

    elif text in ['статус', 'ранг', 'звание', 'status']:
        show_user_status(user_id)

    elif text in ['рулетка', 'колесо', 'spin', 'roulette']:
        success, message = spin_roulette(user_id)
        send_message(user_id, message, get_main_keyboard(), 'roulette')

    else:
        send_message(user_id, 
            "👮 Полицейский бот\n\n"
            "🎯 'Служба' - начать работу\n"
            "📝 'Задание' - получить задание\n"  
            "⭐ 'Статус' - узнать свой ранг\n"
            "🎰 'Рулетка' - испытать удачу\n\n"
            "💡 Бонусные задания позволяют получать задания без ожидания 24 часов!",
            get_main_keyboard()
        )

def check_new_messages():
    """Проверяет новые сообщения с поддержкой payload"""
    try:
        response = vk.messages.getConversations(
            count=20,
            filter='unread',
            extended=0
        )

        processed = 0
        for item in response['items']:
            message = item['last_message']
            user_id = message['from_id']
            text = message['text']
            payload = message.get('payload')

            print(f"📩 Сообщение от {user_id}: '{text}', payload: {payload}")
            handle_message(user_id, text, payload)

            vk.messages.markAsRead(peer_id=user_id)
            processed += 1

        if processed > 0:
            print(f"✅ Обработано сообщений: {processed}")

        return processed

    except Exception as e:
        print(f"❌ Ошибка проверки сообщений: {e}")
        return 0

def daily_attempts_job():
    """Ежедневный сброс попыток"""
    while True:
        now = datetime.datetime.now()
        if now.hour == 0 and now.minute == 0:  # В полночь
            reset_daily_attempts()
            time.sleep(60)  # Ждем минуту чтобы не повторять
        time.sleep(60)

# Главный цикл
print("👮 Полицейский бот запущен!")
print("🔁 Проверяю сообщения каждые 5 секунд...")
print("🎰 Система попыток активирована (3 попытки в день)")
print("🎁 Система бонусных заданий активирована")
print("⌨️  Инлайн-кнопки активированы")

# Инициализация базы заданий
try:
    for difficulty, tasks in TASKS.items():
        for task in tasks:
            cursor.execute(
                "INSERT OR IGNORE INTO tasks (task_text, difficulty) VALUES (?, ?)",
                (task, difficulty)
            )
    conn.commit()
    print("✅ Задания инициализированы")
except Exception as e:
    print(f"ℹ️ Ошибка инициализации заданий: {e}")

# Запуск ежедневного сброса попыток в отдельном потоке
import threading
threading.Thread(target=daily_attempts_job, daemon=True).start()

while True:
    try:
        check_new_messages()
        time.sleep(5)

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        time.sleep(60)