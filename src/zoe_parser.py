#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Parser for Zaporizhzhiaoblenergo (ZOE)

import asyncio
import re
import json
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
from playwright.async_api import async_playwright
import os

TZ = ZoneInfo("Europe/Kyiv")
URL = "https://www.zoe.com.ua/%D0%B3%D1%80%D0%B0%D1%84%D1%96%D0%BA%D0%B8-%D0%BF%D0%BE%D0%B3%D0%BE%D0%B4%D0%B8%D0%BD%D0%BD%D0%B8%D1%85-%D1%81%D1%82%D0%B0%D0%B1%D1%96%D0%BB%D1%96%D0%B7%D0%B0%D1%86%D1%96%D0%B9%D0%BD%D0%B8%D1%85/"
OUTPUT_FILE = "out/Zaporizhzhiaoblenergo.json"

LOG_DIR = "logs"
FULL_LOG_FILE = os.path.join(LOG_DIR, "full_log.log")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs("out", exist_ok=True)


def log(message: str):
    timestamp = datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")
    line = f"{timestamp} [zoe_parser] {message}"
    print(line)
    with open(FULL_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def time_to_hour(hhmm: str) -> float:
    hh, mm = map(int, hhmm.split(":"))
    return hh + (mm / 60.0)


async def fetch_text() -> str:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled"
            ]
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            # Спочатку завантажуємо сторінку
            await page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            
            # Чекаємо на основний контент
            await page.wait_for_selector("article", timeout=30000)
            
            # Отримуємо текст
            text = await page.inner_text("body")
            
        finally:
            await browser.close()
            
        return text


def put_interval(result: dict, group_id: str, t1: float, t2: float) -> None:
    for hour in range(1, 25):
        h_start = float(hour)
        h_mid = h_start + 0.5
        h_end = h_start + 1.0

        first_off = (t1 < h_mid and t2 > h_start)
        second_off = (t1 < h_end and t2 > h_mid)

        if not first_off and not second_off:
            continue

        key = str(hour + 1)

        if first_off and second_off:
            result[group_id][key] = "no"
        elif first_off:
            result[group_id][key] = "first"
        elif second_off:
            result[group_id][key] = "second"


def parse_date_from_header(text: str) -> str:
    """Витягує дату з заголовків типу '06 ГРУДНЯ ПО ЗАПОРІЗЬКІЙ ОБЛАСТІ'"""
    months = {
        'СІЧНЯ': '01', 'ЛЮТОГО': '02', 'БЕРЕЗНЯ': '03', 'КВІТНЯ': '04',
        'ТРАВНЯ': '05', 'ЧЕРВНЯ': '06', 'ЛИПНЯ': '07', 'СЕРПНЯ': '08',
        'ВЕРЕСНЯ': '09', 'ЖОВТНЯ': '10', 'ЛИСТОПАДА': '11', 'ГРУДНЯ': '12'
    }
    
    match = re.search(r'(\d{1,2})\s+(' + '|'.join(months.keys()) + r')', text)
    if match:
        day = match.group(1).zfill(2)
        month = months[match.group(2)]
        year = datetime.now(TZ).year
        return f"{day}.{month}.{year}"
    return None


async def main():
    log("⏳ Отримую HTML...")
    html_text = await fetch_text()
    log("✔️ HTML отримано!")

    today = datetime.now(TZ).date()
    tomorrow = today + timedelta(days=1)
    today_str = today.strftime("%d.%m.%Y")
    tomorrow_str = tomorrow.strftime("%d.%m.%Y")     

    results_for_all_dates = {}
    updates_for_dates = {}

    # Розбиваємо текст на блоки по датах (шукаємо заголовки з датами)
    date_pattern = r'(\d{1,2})\s+(СІЧНЯ|ЛЮТОГО|БЕРЕЗНЯ|КВІТНЯ|ТРАВНЯ|ЧЕРВНЯ|ЛИПНЯ|СЕРПНЯ|ВЕРЕСНЯ|ЖОВТНЯ|ЛИСТОПАДА|ГРУДНЯ)\s+ПО\s+ЗАПОРІЗЬКІЙ\s+ОБЛАСТІ'
    
    # Знаходимо всі блоки з датами
    blocks = re.split(date_pattern, html_text, flags=re.IGNORECASE)
    
    # Обробляємо кожен блок
    for i in range(1, len(blocks), 3):
        if i + 2 >= len(blocks):
            break
            
        day = blocks[i]
        month = blocks[i + 1]
        chunk = blocks[i + 2]
        
        # Перетворюємо місяць на номер
        months = {
            'СІЧНЯ': '01', 'ЛЮТОГО': '02', 'БЕРЕЗНЯ': '03', 'КВІТНЯ': '04',
            'ТРАВНЯ': '05', 'ЧЕРВНЯ': '06', 'ЛИПНЯ': '07', 'СЕРПНЯ': '08',
            'ВЕРЕСНЯ': '09', 'ЖОВТНЯ': '10', 'ЛИСТОПАДА': '11', 'ГРУДНЯ': '12'
        }
        
        month_num = months.get(month.upper())
        if not month_num:
            continue
            
        date_str = f"{day.zfill(2)}.{month_num}.{datetime.now(TZ).year}"
        
        if date_str not in (today_str, tomorrow_str):
            #log(f"⏭️ Пропускаю {date_str} — не today/tomorrow")            
            continue

        log(f"➡️ Обробляю дату: {date_str}")

        # Шукаємо оновлення в цьому блоці з датою
        # Формат: "ОНОВЛЕНО ГПВ НА 05 ГРУДНЯ (оновлено о 18:31)"
        update_pattern = r'ОНОВЛЕНО\s+ГПВ\s+НА\s+(\d{1,2})\s+(' + '|'.join(months.keys()) + r').*?оновлено\s+о?\s*(\d{1,2})[:\-](\d{2})'
        update_match = re.search(update_pattern, chunk, re.IGNORECASE | re.DOTALL)
        
        if update_match:
            update_day = update_match.group(1).zfill(2)
            update_month = months.get(update_match.group(2).upper())
            update_time = f"{update_match.group(3).zfill(2)}:{update_match.group(4)}"
            
            if update_month:
                update_date_str = f"{update_day}.{update_month}.{datetime.now(TZ).year}"
                
                # Якщо дата оновлення в межах today/tomorrow - використовуємо її
                if update_date_str in (today_str, tomorrow_str):
                    if update_date_str not in updates_for_dates:
                        updates_for_dates[update_date_str] = f"{update_time} {update_date_str}"
                        log(f"🕒 Update для {update_date_str}: {update_time}")
                    else:
                        # Порівнюємо часи і беремо новіший
                        existing_time = updates_for_dates[update_date_str].split()[0]
                        if update_time > existing_time:
                            updates_for_dates[update_date_str] = f"{update_time} {update_date_str}"
                            log(f"🕒 Update для {update_date_str}: {update_time} (оновлено)")
        else:
            # Якщо не знайдено оновлення, встановлюємо поточний час і поточну дату
            if date_str not in updates_for_dates:
                current_datetime = datetime.now(TZ)
                current_time = current_datetime.strftime("%H:%M")
                current_date = current_datetime.strftime("%d.%m.%Y")
                updates_for_dates[date_str] = f"{current_time} {current_date}"
                log(f"🕒 Update для {date_str}: {current_time} {current_date} (поточний час і дата, без оновлення)")
        
        # Створюємо timestamp
        day_int, month_int, year_int = map(int, date_str.split("."))
        date_dt = datetime(year_int, month_int, day_int, tzinfo=TZ)
        date_ts = int(date_dt.timestamp())

        result = {}

        # Шукаємо графіки у форматі "1.1: 05:30 – 10:30" або "1.1: не вимикається"
        lines = chunk.split('\n')
        for line in lines:
            line = line.strip()
            
            # Шукаємо формат "1.1: 05:30 – 10:30"
            match = re.match(r'(\d)\.(\d)\s*:\s*(.+)', line)
            if not match:
                continue
                
            group_num = f"{match.group(1)}.{match.group(2)}"
            group_id = "GPV" + group_num
            text = match.group(3)
            
            # Перевіряємо чи не вимикається
            if 'не вимикається' in text.lower() or 'не вимикаються' in text.lower():
                continue
            
            if group_id not in result:
                result[group_id] = {str(h): "yes" for h in range(1, 25)}

            # Шукаємо інтервали відключень
            # Формат: 05:30 – 10:30 або 05:30-10:30 або 05:30 - 10:30
            intervals = re.findall(r'(\d{1,2}:\d{2})\s*[–\-—]\s*(\d{1,2}:\d{2})', text)
            
            for t1_str, t2_str in intervals:
                try:
                    t1 = time_to_hour(t1_str)
                    t2 = time_to_hour(t2_str)
                    put_interval(result, group_id, t1, t2)
                except:
                    continue
            
            if intervals:
                log(f"✔️ {group_id} — знайдено {len(intervals)} інтервалів")

        if result:
            results_for_all_dates[str(date_ts)] = result

    if not results_for_all_dates:
        log("⚠️ Не знайдено жодних графіків відключень!")
        return False

    # Перевіряємо DIFF
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            old_json = json.load(f)
        old_data = old_json.get("fact", {}).get("data", {})

        if json.dumps(old_data, sort_keys=True) == json.dumps(results_for_all_dates, sort_keys=True):
            log("ℹ️ Дані не змінилися — JSON не оновлюємо")
            return False

    # Вибираємо найновіше оновлення
    if updates_for_dates:
        latest_update_value = max(updates_for_dates.values())
        latest_update_formatted = datetime.strptime(
            latest_update_value, "%H:%M %d.%m.%Y"
        ).strftime("%d.%m.%Y %H:%M")
    else:
        latest_update_formatted = datetime.now(TZ).strftime("%d.%m.%Y %H:%M")
    
    log(f"🕑 Обрано фінальне оновлення: {latest_update_formatted}")

    # Формуємо JSON
    new_json = {
        "regionId": "Zaporizhzhia",
        "lastUpdated": datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
        "fact": {
            "data": results_for_all_dates,
            "update": latest_update_formatted,
            "today": int(datetime(today.year, today.month, today.day, tzinfo=TZ).timestamp())
        },
        "preset": {
            "time_zone": {
                str(i): [f"{i - 1:02d}-{i:02d}", f"{i - 1:02d}:00", f"{i:02d}:00"]
                for i in range(1, 25)
            },
            "time_type": {
                "yes": "Світло є",
                "maybe": "Можливе відключення",
                "no": "Світла немає",
                "first": "Світла не буде перші 30 хв.",
                "second": "Світла не буде другі 30 хв"
            }
        }
    }

    # Записуємо JSON
    log(f"💾 Записую JSON → {OUTPUT_FILE}")
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(new_json, f, ensure_ascii=False, indent=2)

    log("✔️ JSON оновлено")
    return True


if __name__ == "__main__":
    asyncio.run(main())