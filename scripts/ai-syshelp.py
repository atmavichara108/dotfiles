
#!/usr/bin/env python3
"""
AI System Helper для Manjaro на ThinkPad P51
Использует локальную Ollama + Mistral-7B с контекстом системы
"""

import requests
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime
import signal

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "mistral:7b"
TIMEOUT_SYSTEM_CHECK = 5  # секунд на сбор контекста

def timeout_handler(signum, frame):
    """Обработчик timeout для долгих команд"""
    raise TimeoutError("Команда заняла слишком много времени")

def run_cmd_safe(cmd, timeout=3):
    """Безопасное выполнение команды с timeout"""
    try:
        signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        signal.alarm(0)  # отменяем alarm
        return result.stdout.strip() if result.returncode == 0 else None
    except (subprocess.TimeoutExpired, TimeoutError):
        return None
    except Exception as e:
        return None

def get_system_context():
    """Собирает актуальное состояние системы БЕЗ зависаний"""
    context = {
        "timestamp": datetime.now().isoformat(),
        "system_state": {},
    }
    
    # # 1. Критичные конфиги (только существующие файлы)
    # config_files = [
    #     "~/dotfiles/qtile/.config/qtile/config.py",
    #     "~/dotfiles/qtile/.config/qtile/autostart.sh",
    #     "~/dotfiles/tmux/.tmux.conf"
    #     "~/.config/i3/config",
    #     "~/.config/alacritty/alacritty.toml",
    #     "/etc/pacman.conf",
    #     "~/.bashrc",
    # ]
    #
    # for cfg in config_files:
    #     expanded = os.path.expanduser(cfg)
    #     if os.path.exists(expanded):
    #         try:
    #             with open(expanded, 'r', encoding='utf-8', errors='ignore') as f:
    #                 content = f.read()
    #                 # Берём первые 2500 символов + metadata
    #                 context["configs"][cfg] = content[:2500]
    #         except Exception as e:
    #             context["configs"][cfg] = f"[Ошибка чтения: {str(e)[:50]}]"
    
    # 2. Состояние системы (с защитой от зависания)
    
    # Btop snapshot (самое важное)
    btop_raw = run_cmd_safe("btop | head -50", timeout=3)
    if btop_raw:
        context["system_state"]["btop_snapshot"] = btop_raw
    # CPU температура (исправленная версия)
    # temp = None
    # if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
    #     temp_raw = run_cmd_safe("cat /sys/class/thermal/thermal_zone0/temp", timeout=1)
    #     if temp_raw:
    #         try:
    #             temp = f"{int(temp_raw) // 1000}°C"
    #         except:
    #             pass
    #
    # if not temp:
    #     # Fallback на sensors если тепловая зона не доступна
    #     sensors_out = run_cmd_safe("sensors 2>/dev/null | grep -i 'core\\|package' | head -2", timeout=2)
    #     if sensors_out:
    #         temp = sensors_out
    #     else:
    #         temp = "N/A"
    #
    # context["system_state"]["cpu_temp"] = temp
    
    # Память
    # free_raw = run_cmd_safe("free -h | awk 'NR==2 {print $3 \" / \" $2}'", timeout=1)
    # context["system_state"]["memory"] = free_raw or "N/A"
    #
    # # Диск
    # disk_raw = run_cmd_safe("df -h / | awk 'NR==2 {print $3 \" / \" $2 \" (\" $5 \")\"}'", timeout=1)
    # context["system_state"]["disk"] = disk_raw or "N/A"
    #
    # # NVIDIA GPU (если доступна)
    # nvidia_raw = run_cmd_safe("nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.total "
    #                          "--format=csv,noheader,nounits 2>/dev/null", timeout=2)
    # if nvidia_raw:
    #     context["system_state"]["nvidia"] = nvidia_raw
    # else:
    #     context["system_state"]["nvidia"] = "Not available or not installed"
    
    # Активный WM
    # wm = run_cmd_safe("echo $DESKTOP_SESSION", timeout=1)
    # context["system_state"]["window_manager"] = wm or os.environ.get("DESKTOP_SESSION", "Unknown")
    #
    # # Статус сервисов
    # services_to_check = ["tor", "bluetooth", "networking"]
    # for svc in services_to_check:
    #     status = run_cmd_safe(f"systemctl is-active {svc} 2>/dev/null", timeout=1)
    #     context["system_state"][f"{svc}_status"] = status or "inactive/unknown"
    
    # 3. История изменений в dotfiles (если Git инициализирован)
    dotfiles_path = os.path.expanduser("~/dotfiles")
    if os.path.exists(dotfiles_path) and os.path.exists(os.path.join(dotfiles_path, ".git")):
        git_log = run_cmd_safe(f"cd {dotfiles_path} && git log --oneline -5 2>/dev/null", timeout=2)
        if git_log:
            context["recent_changes"] = git_log.split('\n')
    
    return context

# def build_system_prompt_with_context(system_context):
#     """Строит системный промпт с контекстом"""
#
#     prompt = """Ты Linux системный консультант на ThinkPad P51.
# Характеристики: i7-7820HQ, 16GB DDR4, Quadro M2200, SSD NVMe 500GB, Manjaro Linux.
#
# ТЕКУЩЕЕ СОСТОЯНИЕ СИСТЕМЫ (прямо сейчас):
# """
#
#     # Добавляем состояние системы
#     if system_context["system_state"]:
#         prompt += "\n[СОСТОЯНИЕ]\n"
#         for key, val in system_context["system_state"].items():
#             prompt += f"  {key}: {val}\n"
#
#     # Добавляем активные конфиги
#     if system_context["configs"]:
#         prompt += "\n[АКТИВНЫЕ КОНФИГИ]\n"
#         for cfg_name, cfg_content in system_context["configs"].items():
#             prompt += f"  {cfg_name}:\n"
#             lines = cfg_content.split('\n')[:8]
#             for i, line in enumerate(lines, 1):
#                 if line.strip():
#                     prompt += f"    {i}: {line[:80]}\n"
#
#     # История изменений
#     if system_context["recent_changes"]:
#         prompt += "\n[ПОСЛЕДНИЕ ИЗМЕНЕНИЯ]\n"
#         for change in system_context["recent_changes"][:3]:
#             if change.strip():
#                 prompt += f"  {change}\n"
#
#     prompt += """
#
# ПРАВИЛА ОТВЕТА:
# 1. Использовать АКТУАЛЬНЫЕ данные из контекста выше
# 2. Перед редактированием конфига — показать текущее содержимое с номерами строк
# 3. Объяснять ЧТО и ПОЧЕМУ, не только КАК
# 4. Если не уверен — начать с "⚠️ ВНИМАНИЕ:"
# 5. Команды для Manjaro (pacman, paru, systemctl)
# 6. Никогда не предлагать команды типа "rm -rf /" или опасные опции
#
# ФОРМАТЫ ОТВЕТА (используй эти метки):
# [ACTION] command: твоя-команда-здесь
# [SHOW] file: /path/to/file (показать содержимое перед редактом)
# [EDIT] file: /path/to/file
#     строка 5: старое → новое
#     или полный новый контент
# [EXPLAIN] текст объяснения
# [WARNING] ⚠️ важное предупреждение
# [SUCCESS] ✅ что получилось сделать
# """
#
#     return prompt

def build_system_prompt_with_context(system_context):
    """Компактный системный промпт"""
    
    state = system_context["system_state"]
    
    prompt = f"""Ты Linux консультант на ThinkPad P51 (Manjaro, i7-7820HQ, 16GB, Quadro M2200).


ПРАВИЛА:
1. Отвечай кратко и конкретно
2. Команды для Manjaro (pacman/yay/systemctl)
3. Если нужен конфиг — попроси пользователя показать его
4. Объясняй ЧТО и ПОЧЕМУ
5. Если не уверен → начни с "⚠️"

ФОРМАТЫ:
[ACTION] command: твоя-команда
[EXPLAIN] текст объяснения
[WARNING] ⚠️ предупреждение
[ASK] запрос: "покажи конфиг X"
"""
    
    # Добавляем btop только если есть
    if state.get('btop_snapshot'):
        prompt += f"\nBTOP SNAPSHOT:\n{state['btop_snapshot'][:800]}\n"
    
    return prompt

def call_ollama_with_context(user_prompt, system_context):
    """Запрос к Ollama с контекстом системы"""
    
    system_prompt = build_system_prompt_with_context(system_context)
    
    payload = {
        "model": MODEL,
        "prompt": user_prompt,
        "system": system_prompt,
        "stream": False,
        "temperature": 0.2,  # низкая температура для точности
        "top_p": 0.9,
        "top_k": 40,
    }
    
    try:
        print("🔄 Собираю контекст системы...\n")
        response = requests.post(OLLAMA_URL, json=payload, timeout=90)
        
        if response.status_code == 200:
            return response.json()['response']
        elif response.status_code == 404:
            return "❌ Модель не найдена. Запусти: ollama pull mistral:7b"
        elif response.status_code == 503:
            return "❌ Ollama недоступна. Запусти: ollama serve"
        else:
            return f"❌ Ошибка Ollama ({response.status_code}): {response.text[:200]}"
            
    except requests.exceptions.ConnectionError:
        return "❌ Не могу подключиться к Ollama на localhost:11434.\nЗапусти в отдельном терминале: ollama serve"
    except requests.exceptions.Timeout:
        return "❌ Ollama не ответила за 90 секунд. Может быть загружена?"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

def parse_response(response):
    """Парсит и показывает ответ агента"""
    
    print("\n" + "="*60)
    print("🤖 ОТВЕТ АГЕНТА:")
    print("="*60 + "\n")
    
    lines = response.split('\n')
    
    for line in lines:
        line = line.rstrip()
        
        if line.startswith('[ACTION]'):
            cmd = line.replace('[ACTION]', '').replace('command:', '').strip()
            print(f"\n🔧 ВЫПОЛНИТЬ КОМАНДУ:\n")
            print(f"  {cmd}\n")
            
        elif line.startswith('[SHOW]'):
            print(f"\n📖 {line}\n")
            
        elif line.startswith('[EDIT]'):
            print(f"\n✏️  {line}\n")
            
        elif line.startswith('[EXPLAIN]'):
            text = line.replace('[EXPLAIN]', '').strip()
            print(f"\n💡 {text}\n")
            
        elif line.startswith('[WARNING]'):
            text = line.replace('[WARNING]', '').strip()
            print(f"\n⚠️  {text}\n")
            
        elif line.startswith('[SUCCESS]'):
            text = line.replace('[SUCCESS]', '').strip()
            print(f"\n✅ {text}\n")
            
        elif line.strip():
            print(line)
    
    print("\n" + "="*60 + "\n")

def main():
    if len(sys.argv) < 2:
        print("""
╔═══════════════════════════════════════════════════════════════╗
║         AI System Helper для Manjaro на ThinkPad P51          ║
║              Локальный agеnt с Ollama + Mistral-7B            ║
╚═══════════════════════════════════════════════════════════════╝

📖 Использование: ai 'твой запрос'

🎯 Примеры:
  ai 'почему не загружается Qtile?'
  ai 'помоги оптимизировать батарею'
  ai 'проверь что сейчас работает'

⚡ Агент:
  - Читает текущее состояние системы
  - Знает все активные конфиги
  - Учитывает историю изменений (Git)
  - Работает полностью локально (приватно)

⚠️  Убедись что запущен демон: ollama serve
        """)
        sys.exit(0)
    
    user_prompt = ' '.join(sys.argv[1:])
    
    print(f"\n🚀 Запрос: {user_prompt}")
    print("⏳ Обработка...\n")
    
    # Собираем контекст системы
    system_context = get_system_context()
    
    # Запрашиваем ответ с контекстом
    response = call_ollama_with_context(user_prompt, system_context)
    
    # Парсим и показываем результат
    parse_response(response)

if __name__ == "__main__":
    main()
