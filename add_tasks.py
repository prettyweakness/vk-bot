import sqlite3
from tasks_database import TASKS

def import_tasks_to_db():
    """Импортирует все задания из tasks_database.py в базу данных"""
    conn = sqlite3.connect('bot_db.sqlite')
    cursor = conn.cursor()
    
    added_count = 0
    skipped_count = 0
    
    for difficulty, tasks in TASKS.items():
        for task_text in tasks:
            try:
                # Проверяем, нет ли уже такого задания
                cursor.execute(
                    "SELECT id FROM tasks WHERE task_text = ? AND difficulty = ?",
                    (task_text, difficulty)
                )
                if cursor.fetchone() is None:
                    exp_reward = 10 if difficulty == 'easy' else 20 if difficulty == 'medium' else 30
                    cursor.execute(
                        "INSERT INTO tasks (task_text, difficulty, experience_reward) VALUES (?, ?, ?)",
                        (task_text, difficulty, exp_reward)
                    )
                    added_count += 1
                else:
                    skipped_count += 1
            except Exception as e:
                print(f"❌ Ошибка с заданием '{task_text}': {e}")
                skipped_count += 1
    
    conn.commit()
    conn.close()
    
    return added_count, skipped_count

def show_db_stats():
    """Показывает статистику базы данных"""
    conn = sqlite3.connect('bot_db.sqlite')
    cursor = conn.cursor()
    
    cursor.execute("SELECT difficulty, COUNT(*) FROM tasks GROUP BY difficulty")
    stats = cursor.fetchall()
    
    print("📊 База данных:")
    for difficulty, count in stats:
        level = "🟢 Патрульный" if difficulty == 'easy' else "🟡 Детектив" if difficulty == 'medium' else "🔴 Спецназ"
        print(f"{level}: {count} заданий")
    
    conn.close()

if __name__ == "__main__":
    print("📦 Импорт полицейских заданий")
    print("=" * 50)
    
    print(f"📝 В файле: {sum(len(tasks) for tasks in TASKS.values())} заданий")
    show_db_stats()
    
    confirm = input("\n✅ Импортировать задания? (y/n): ").lower().strip()
    
    if confirm == 'y':
        added, skipped = import_tasks_to_db()
        print(f"\n🎉 Результат:")
        print(f"✅ Добавлено: {added} новых заданий")
        print(f"⏭️ Пропущено: {skipped} (уже в базе)")
        
        print("\n📊 Обновленная статистика:")
        show_db_stats()
    else:
        print("❌ Импорт отменен")