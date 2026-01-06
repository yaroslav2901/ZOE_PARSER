#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os, json, asyncio
from zoneinfo import ZoneInfo
from datetime import datetime
from telegram_notify import send_error, send_message, send_photo
import gener_im_1_G
import gener_im_full
import upload_to_github
import zoe_parser
from utils import clean_log, clean_old_files, delete_json

LOG_DIR = "logs"
FULL_LOG_FILE = os.path.join(LOG_DIR, "full_log.log")
os.makedirs(LOG_DIR, exist_ok=True)


def log(message):
    timestamp = datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} [main] {message}"
    print(line)
    with open(FULL_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def send_schedule_photo(json_path: str, base_image_path: str = "out/images") -> None:
    """
    Визначає яке фото відправляти (сьогодні або завтра) на основі кількості дат у JSON.
    Якщо є 2+ дати - відправляє графік на завтра, інакше - на сьогодні.
    
    Args:
        json_path: Шлях до JSON файлу з графіком
        base_image_path: Базовий шлях до папки з зображеннями
    """
    try:
        # Перевіряємо чи існує JSON файл
        if not os.path.exists(json_path):
            log(f"⚠️ JSON файл не існує: {json_path}, пропускаю відправку фото")
            return
        
        # Читаємо JSON для перевірки дат
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Отримуємо всі дати з графіками
        #dates = list(data.get("date", {}).keys())
        dates = list(data.get("fact", {}).get("data", {}).keys())
        date_count = len(dates)
        
        log(f"📊 Знайдено {date_count} дат у графіку: {dates}")
        
        # Визначаємо яке фото відправляти
        if date_count >= 2:
            # Є дві і більше дати (сьогодні + завтра)
            photo_path = os.path.join(base_image_path, "gpv-all-tomorrow.png")
            caption = "🔄 <b>Запоріжжяобленерго</b>\nГрафік на завтра\n#Запоріжжяобленерго"
            log("📸 Відправляю графік на ЗАВТРА (є 2+ дати)")
        else:
            # Тільки одна дата (сьогодні) або немає дат
            photo_path = os.path.join(base_image_path, "gpv-all-today.png")
            caption = "🔄 <b>Запоріжжяобленерго</b>\nГрафік на сьогодні\n#Запоріжжяобленерго"
            log("📸 Відправляю графік на СЬОГОДНІ (1 дата)")
        
        # Перевіряємо чи файл існує
        if os.path.exists(photo_path):
            send_photo(photo_path, caption)
            log(f"✔️ Фото відправлено: {photo_path}")
        else:
            error_msg = f"⚠️ Файл не знайдено: {photo_path}"
            log(error_msg)
            send_error(error_msg)
            
    except json.JSONDecodeError as e:
        error_msg = f"❌ Помилка читання JSON: {e}"
        log(error_msg)
        send_error(error_msg)
    except Exception as e:
        error_msg = f"❌ Помилка при відправці фото: {e}"
        log(error_msg)
        send_error(error_msg)


def main():
    # Чистимо лог від даних старше 3 днів
    removed = clean_log(FULL_LOG_FILE, days=3)
    if removed is not None:
        if removed > 0:
            log(f"🧹 Логи очищено — видалено {removed} старих рядків")
    else:
        log("⚠️ Файла логів ще не існує — очищення пропущено")

    json_path = "out/Zaporizhzhiaoblenergo.json"

    log("⚡ Запуск парсера…") 
    # Run the parser   
    try:
        updated = asyncio.run(zoe_parser.main())
    except Exception as e:
        log(f"❌ Помилка парсера: {e}")
        send_error(f"❌ Помилка парсера: {e}")
        return
    
    if not updated:
        log("ℹ️ Дані ті ж самі — оновлення не потрібне")
        return
   
    log("🔴 Дані змінились — запускаю оновлення PNG та GitHub")

    try:
        log(f"🖼 Генерація PNG по групах із {json_path}")
        gener_im_1_G.generate_from_json(json_path)
        log("✔️ PNG по групах — OK")
    except Exception as e:
        log(f"❌ Помилка PNG по групах: {e}")
        send_error(f"❌ Помилка PNG по групах: {e}")
        if delete_json(json_path):
            log(f"🗑 Видалено JSON файл {json_path} через помилку генерації PNG по групах")
        return

    try:
        log(f"🖼 Генерація загального gpv-all-today.png із {json_path}")
        gener_im_full.generate_from_json(json_path)
        log("✔️ gpv-all-today — OK")
    except Exception as e:
        log(f"❌ Помилка створення all-image: {e}")
        send_error(f"❌ Помилка створення all-image: {e}")
        if delete_json(json_path):
            log(f"🗑 Видалено JSON файл {json_path} через помилку генерації загального PNG")
        return

    try:
        log("⬆️ Завантажую нові файли в GitHub…")
        upload_to_github.run_upload()
        log("✔️ GitHub OK")
    except Exception as e:
        log(f"❌ Помилка GitHub upload: {e}")
        send_error(f"❌ Помилка GitHub upload: {e}")
        if delete_json(json_path):
            log(f"🗑 Видалено JSON файл {json_path} через помилку завантаження в GitHub")
        return

    # Відправка фото з автоматичним вибором (сьогодні або завтра)
    send_schedule_photo(json_path)
    
    log("🎉 УСПІХ")


if __name__ == "__main__":
    main()