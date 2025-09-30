import asyncio
import logging
import socket
import sys
import time
import json
import psutil
from asyncio.subprocess import PIPE
from logging.handlers import TimedRotatingFileHandler
from api import update_api_host
import os
from dynamic_config import DynamicConfigLoader
try:
    import aiohttp
except ImportError:
    print("Ошибка: модуль aiohttp не найден. Установите его: pip install aiohttp", file=sys.stderr)
    sys.exit(1)

from handlers import TelegramCommandHandler
config_loader = DynamicConfigLoader()

async def on_config_changed():
    """Обработчик изменения конфигурации"""
    global BOT_TOKEN, CHAT_ID, ALLOWED_USER_ID, API_TOKEN, API_DOMAIN
    global HEALTH_CHECK_INTERVAL_SECONDS, TUNNEL_HOST, TUNNEL_PORT
    global VPN_CONFIG, VK_TUNNEL_COMMAND
    
    # Перезагружаем переменные
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    CHAT_ID = os.getenv("CHAT_ID")
    ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID", "0"))
    API_TOKEN = os.getenv("API_TOKEN")
    API_DOMAIN = os.getenv("API_DOMAIN")
    HEALTH_CHECK_INTERVAL_SECONDS = int(os.getenv("HEALTH_CHECK_INTERVAL_SECONDS", "30"))
    TUNNEL_HOST = "127.0.0.1"  
    TUNNEL_PORT = int(os.getenv("TUNNEL_PORT", "10001"))
    
    # Обновляем конфигурацию VPN
    VPN_CONFIG["uuid"] = os.getenv("CONFIG_UUID", VPN_CONFIG["uuid"])
    VPN_CONFIG["inbound"]["configProfileUuid"] = os.getenv("CONFIG_PROFILE_UUID", "")
    VPN_CONFIG["inbound"]["configProfileInboundUuid"] = os.getenv("CONFIG_PROFILE_INBOUND_UUID", "")
    
    # Обновляем VK_TUNNEL_COMMAND с новыми значениями
    VK_TUNNEL_COMMAND = [
        "vk-tunnel", "--verbose", "--insecure=1", "--http-protocol=http", "--ws-protocol=ws",
        "--ws-origin=0", "--host", TUNNEL_HOST, "--port", str(TUNNEL_PORT),
        "--ws-ping-interval=30"
    ]
    
    log.info("Конфигурация перезагружена из .env")
    
    # Обновляем telegram handler
    if 'telegram_handler' in globals():
        telegram_handler.bot_token = BOT_TOKEN
        telegram_handler.owner_id = ALLOWED_USER_ID
        
    # Если нужно перезапустить туннель с новыми параметрами
    if STATE.get('notification_sent') and TUNNEL_PORT != int(os.getenv("TUNNEL_PORT", "10001")):
        log.info("Обнаружено изменение TUNNEL_PORT, требуется перезапуск туннеля")
        await send_telegram_message("⚙️ Конфигурация изменена. Перезапускаю туннель...")
        telegram_handler.manual_restart_event.set()

# Добавляем callback
config_loader.add_callback(on_config_changed)

VK_TUNNEL_COMMAND = [
    "vk-tunnel", "--verbose", "--insecure=1", "--http-protocol=http", "--ws-protocol=ws",
    "--ws-origin=0", "--host", TUNNEL_HOST, "--port", str(TUNNEL_PORT),
    "--ws-ping-interval=30"
]
VPN_CONFIG = {
    "uuid": "5c47363f-81b4-4e8e-88f1-852bb253acec",
    "inbound": {
        "configProfileUuid": os.getenv("CONFIG_PROFILE_UUID"),
        "configProfileInboundUuid": os.getenv("CONFIG_PROFILE_INBOUND_UUID")
    },
    "remark": "🔴 VK Tunnel",
    "address": "tunnel.vk-apps.com",
    "port": 443,
    "path": "/ws",
    "sni": "tunnel.vk-apps.com",
    "alpn": "h3,h2,http/1.1",
    "fingerprint": "chrome",
    "isDisabled": False,
    "securityLayer": "TLS",
    "xHttpExtraParams": None,
    "muxParams": None,
    "sockoptParams": None,
    "serverDescription": None,
    "tag": None,
    "isHidden": False,
    "overrideSniFromAddress": True,
    "vlessRouteId": None,
    "allowInsecure": False
}
# ----------------------------------------------------

# Проверка конфигурации при старте
# Проверка конфигурации при старте
if not all([BOT_TOKEN, CHAT_ID, os.getenv("ALLOWED_USER_ID")]):
    print("!!! КРИТИЧЕСКАЯ ОШИБКА !!!", file=sys.stderr)
    print("Пожалуйста, заполните переменные BOT_TOKEN, CHAT_ID и ALLOWED_USER_ID в .env файле.", file=sys.stderr)
    sys.exit(1)

# Преобразуем ALLOWED_USER_ID в int после проверки
try:
    ALLOWED_USER_ID = int(os.getenv("ALLOWED_USER_ID"))
except (ValueError, TypeError):
    print("!!! КРИТИЧЕСКАЯ ОШИБКА !!!", file=sys.stderr)
    print("ALLOWED_USER_ID должен быть числом.", file=sys.stderr)
    sys.exit(1)

if not all([API_TOKEN, VPN_CONFIG["uuid"], VPN_CONFIG["inbound"]["configProfileUuid"], VPN_CONFIG["inbound"]["configProfileInboundUuid"]]):
    print("!!! КРИТИЧЕСКАЯ ОШИБКА !!!", file=sys.stderr)
    print("Пожалуйста, заполните API_TOKEN и параметры VPN_CONFIG.", file=sys.stderr)
    sys.exit(1)
# --- КОНФИГУРАЦИЯ ЛОГОВ С АВТОМАТИЧЕСКОЙ РОТАЦИЕЙ ---
log_formatter = logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(console_handler)

log = logging.getLogger("manager")
log_vktunnel = logging.getLogger("vk-tunnel")
log_telegram = logging.getLogger("telegram")

# --- ГЛОБАЛЬНОЕ СОСТОЯНИЕ ---
STATE = {
    'notification_sent': False,
    'process_start_time': None,
    'last_output_time': None,
    'process_pid': None,
    'last_health_check_time': None,
    'current_wss_url': None,
    'current_host': None,
    'consecutive_failures': 0,
    'total_crashes': 0, 
    'is_stopped': False,
    'auth_url': None,          
    'waiting_for_auth': False,  
    'vk_process': None
}

def get_server_info():
    try:
        hostname = socket.getfqdn()
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip_address = s.getsockname()[0]
        return ip_address, hostname
    except Exception:
        return "127.0.0.1", "localhost"

SERVER_IP, SERVER_HOSTNAME = get_server_info()

# Создаем обработчик команд
telegram_handler = TelegramCommandHandler(BOT_TOKEN, ALLOWED_USER_ID, STATE)

async def send_telegram_message(text: str, chat_id=None):
    """Отправка сообщения в Telegram"""
    target_chat_id = chat_id or CHAT_ID
    await telegram_handler.send_message(text, target_chat_id)



async def monitor_stream(stream: asyncio.StreamReader, stream_name: str = "unknown"):
    """Мониторинг вывода процесса"""
    while True:
        try:
            line_bytes = await stream.readline()
            if not line_bytes:
                log.warning(f"Поток {stream_name} процесса был закрыт.")
                break

            STATE['last_output_time'] = time.time()
            line = line_bytes.decode('utf-8', errors='ignore').strip()
            
            # Логируем все строки для отладки
            log_vktunnel.info(f"[{stream_name}] {line}")

            # Ищем ссылку авторизации VK в любом потоке
            if "oauth.vk.ru" in line or "Please open the following link" in line:
                log.info(f"Обнаружена строка авторизации в {stream_name}: {line}")
                
                # Если это строка с URL
                if "https://oauth.vk.ru" in line:
                    import re
                    url_match = re.search(r'https://oauth\.vk\.ru/[^\s]*', line)
                    if url_match:
                        auth_url = url_match.group(0)
                        STATE['auth_url'] = auth_url
                        STATE['waiting_for_auth'] = True
                        
                        message = (f"🔐 *Требуется авторизация VK*\n\n"
                                  f"Откройте ссылку в браузере:\n"
                                  f"`{auth_url}`\n\n"
                                  f"После авторизации нажмите /accept")
                        
                        await send_telegram_message(message)
                        log.info(f"Отправлена ссылка авторизации VK: {auth_url}")
                # Если это просто упоминание о ссылке, ждем следующую строку
                elif "Please open the following link" in line:
                    STATE['waiting_for_auth'] = True
                    log.info("Ожидаем ссылку авторизации в следующих строках...")
                continue

            # Проверяем на WSS URL для успешного подключения
            if not STATE['notification_sent'] and line.startswith("wss:"):
                try:
                    wss_url = line.split(maxsplit=1)[1] if len(line.split()) > 1 else line
                    STATE['current_wss_url'] = wss_url
                    STATE['waiting_for_auth'] = False
                    
                    # Извлекаем host из WSS URL
                    import re
                    match = re.search(r'wss://([^/]+)', wss_url)
                    if match:
                        host = match.group(1)
                        STATE['current_host'] = host
                        
                        # Обновляем API
                        from api import update_api_host
                        api_updated = await update_api_host(host, API_DOMAIN, API_TOKEN, VPN_CONFIG)
                        
                        log.info(f"Обнаружен WSS адрес: {wss_url}. Host: {host}")
                        
                        message = (f"✅ *VK Tunnel запущен*\n\n"
                                   f"🖥️ *Сервер:* `{SERVER_HOSTNAME}`\n"
                                   f"🌐 *IP:* `{SERVER_IP}`\n"
                                   f"🔗 *Host:* `{host}`\n\n")
                        
                        if api_updated:
                            message += "✅ *API обновлен успешно*\n\n"
                        else:
                            message += "❌ *Ошибка обновления API*\n\n"
                        
                        message += "📱 *Обновите подписку в вашем VPN клиенте*"
                        
                        await send_telegram_message(message)
                        STATE['notification_sent'] = True
                        STATE['consecutive_failures'] = 0
                except Exception as e:
                    log.error(f"Ошибка при обработке WSS URL: {e}")
                    
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.error(f"Ошибка в monitor_stream ({stream_name}): {e}")

async def check_tunnel_health():
    """Проверка здоровья туннеля через HTTP запрос"""
    log.info(f"Проверка здоровья туннеля запущена. Интервал: {HEALTH_CHECK_INTERVAL_SECONDS}с.")
    await asyncio.sleep(20)  # Даем время на запуск

    while True:
        try:
            # Пробуем сделать HTTP запрос к туннелю
            url = f"http://{TUNNEL_HOST}:{TUNNEL_PORT}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as response:
                    # Любой ответ означает, что туннель работает
                    STATE['last_health_check_time'] = time.time()
                    STATE['consecutive_failures'] = 0
                    log.info(f"Health check: туннель отвечает (статус: {response.status})")

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            STATE['consecutive_failures'] += 1
            log.warning(f"Health check failed ({STATE['consecutive_failures']}): {type(e).__name__}")
            
            # Если 3 неудачные проверки подряд - перезапускаем
            if STATE['consecutive_failures'] >= 3:
                log.error("Туннель не отвечает после 3 проверок. Инициирую перезапуск.")
                await send_telegram_message("⚠️ *Туннель не отвечает*\n\nИнициирую перезапуск...")
                telegram_handler.manual_restart_event.set()
                break
                
        except asyncio.CancelledError:
            log.info("Проверка здоровья остановлена.")
            break
        except Exception as e:
            log.error(f"Неизвестная ошибка при проверке здоровья: {e}")

        await asyncio.sleep(HEALTH_CHECK_INTERVAL_SECONDS)

async def manage_vk_tunnel_lifecycle():
    """Основной цикл управления жизненным циклом vk-tunnel"""
    while True:
        # Проверяем, остановлен ли процесс
        if STATE['is_stopped']:
            await asyncio.sleep(5)
            continue
            
        # Проверяем количество падений (увеличим лимит до 5 для большей устойчивости)
        if STATE['total_crashes'] >= 5:
            await send_telegram_message(
                "❌ *Туннель упал 5 раз*\n\n"
                "Автоматический перезапуск отключен.\n"
                "Используйте /start для запуска вручную."
            )
            STATE['is_stopped'] = True
            continue
            
        log.info("Запуск нового цикла vk-tunnel.")
        STATE.update({
            'notification_sent': False,
            'process_start_time': time.time(),
            'last_output_time': time.time(),
            'process_pid': None,
            'last_health_check_time': time.time(),
            'current_wss_url': None,
            'current_host': None,
            'consecutive_failures': 0
        })
        telegram_handler.manual_restart_event.clear()

        try:
            process = await asyncio.create_subprocess_exec(
                *VK_TUNNEL_COMMAND,
                stdout=PIPE,
                stderr=PIPE,
                stdin=PIPE
            )
            STATE['process_pid'] = process.pid
            STATE['vk_process'] = process
            log.info(f"Процесс vk-tunnel запущен с PID: {process.pid}")
        except FileNotFoundError:
            log.critical("Команда 'vk-tunnel' не найдена! Повтор через 30с...")
            await asyncio.sleep(30)
            continue
        except Exception as e:
            log.critical(f"Не удалось запустить процесс vk-tunnel: {e}. Повтор через 30с...")
            await asyncio.sleep(30)
            continue

        # Создаем задачи мониторинга
        monitor_stdout_task = asyncio.create_task(monitor_stream(process.stdout, "stdout"))
        monitor_stderr_task = asyncio.create_task(monitor_stream(process.stderr, "stderr"))
        health_check_task = asyncio.create_task(check_tunnel_health())

        # Создаем задачи ожидания событий (ЭТО ИСПРАВЛЕНИЕ: задачи определяются здесь, перед asyncio.wait)
        wait_process_task = asyncio.create_task(process.wait())
        wait_command_task = asyncio.create_task(telegram_handler.manual_restart_event.wait())
        wait_start_task = asyncio.create_task(telegram_handler.start_event.wait())

        # Ждем первое событие
        done, pending = await asyncio.wait(
            [wait_process_task, wait_command_task, wait_start_task, health_check_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        # Определяем причину остановки
        reason = "неизвестная причина"
        if wait_process_task in done:
            STATE['total_crashes'] += 1
            reason = f"процесс завершился сам с кодом {process.returncode} (падение {STATE['total_crashes']}/5)"
            await send_telegram_message(f"⚠️ *Туннель упал*\n\nПричина: {reason}\nПерезапускаю...")
        elif wait_command_task in done:
            reason = "получена команда перезапуска"
            STATE['total_crashes'] = 0  # Сбрасываем счетчик при ручном перезапуске
        elif wait_start_task in done:
            reason = "получена команда запуска"
            STATE['total_crashes'] = 0  # Сбрасываем счетчик при ручном запуске
        elif health_check_task in done:
            STATE['total_crashes'] += 1
            reason = f"health check обнаружил проблему (падение {STATE['total_crashes']}/5)"

        log.warning(f"Инициирован перезапуск vk-tunnel (PID: {process.pid}). Причина: {reason}.")

        # Отменяем все незавершенные задачи
        for task in pending:
            task.cancel()

        monitor_stdout_task.cancel()
        monitor_stderr_task.cancel()
        health_check_task.cancel()

        await asyncio.gather(
            monitor_stdout_task,
            monitor_stderr_task,
            health_check_task,
            return_exceptions=True
        )

        # Улучшенный раздел убийства процесса
        if process.returncode is None:
            log.warning(f"Пытаюсь убить процесс {process.pid}...")
            try:
                # Сначала SIGTERM
                process.terminate()
                await asyncio.wait_for(process.wait(), timeout=5)
                log.info(f"Процесс {process.pid} успешно завершен (SIGTERM).")
            except asyncio.TimeoutError:
                log.warning(f"Процесс {process.pid} не ответил на SIGTERM. Пытаюсь SIGKILL...")
                process.kill()
                await asyncio.wait_for(process.wait(), timeout=5)
                log.info(f"Процесс {process.pid} успешно убит (SIGKILL).")
            except Exception as e:
                log.error(f"Ошибка при убийстве процесса {process.pid}: {e}. Принудительное убийство через psutil...")
                # Fallback через psutil для надёжности
                try:
                    p = psutil.Process(process.pid)
                    p.terminate()
                    p.wait(timeout=5)
                except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                    log.info(f"Процесс {process.pid} уже не существует.")
                except Exception as kill_e:
                    log.critical(f"Не удалось убить процесс {process.pid}: {kill_e}. Возможно, требуется ручное вмешательство.")

            # Дополнительная проверка: убедимся, что PID мёртв
            await asyncio.sleep(2)  # Задержка для ОС
            if psutil.pid_exists(process.pid):
                log.error(f"Процесс {process.pid} всё ещё жив! Принудительное убийство через psutil...")
                try:
                    p = psutil.Process(process.pid)
                    p.kill()  # Эквивалент SIGKILL
                    p.wait(timeout=5)  # Ждём завершения
                    log.info(f"Процесс {process.pid} успешно убит через psutil.")
                except psutil.NoSuchProcess:
                    log.info(f"Процесс {process.pid} уже не существует.")
                except psutil.TimeoutExpired:
                    log.warning(f"Таймаут при ожидании завершения {process.pid}.")
                except Exception as e:
                    log.error(f"Ошибка при убийстве через psutil: {e}")

        log.info("Пауза 10 секунд перед перезапуском...")
        await asyncio.sleep(10)

async def main():
    """Главная функция"""
    log.info("Запуск менеджера vk-tunnel с управлением через Telegram.")
    log.info(f"Конфигурация: BOT_TOKEN={'*' * 10}, CHAT_ID={CHAT_ID}, ALLOWED_USER_ID={ALLOWED_USER_ID}")
    log.info(f"API: {API_DOMAIN}")
    config_loader.start_watching()
    # Запускаем обе задачи параллельно
    await asyncio.gather(
        manage_vk_tunnel_lifecycle(),
        telegram_handler.listen_for_commands()
    )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Менеджер остановлен пользователем.")
    except Exception as e:
        log.critical(f"Критическая ошибка: {e}", exc_info=True)
        sys.exit(1)