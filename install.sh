#!/bin/bash
# Остановить скрипт немедленно, если любая команда завершится с ошибкой.
set -e

# --- Переменные для удобства ---
VENV_DIR=".venv"
# !!! ГЛАВНОЕ ИЗМЕНЕНИЕ: Указываем правильное имя файла !!!
MAIN_PYTHON_FILE="vk-tun.py"

# --- Функция для вывода красивых заголовков ---
print_header() {
    echo ""
    echo "================================================================="
    echo " $1"
    echo "================================================================="
    sleep 1
}

# --- ШАГ 1: НАСТРОЙКА ОКРУЖЕНИЯ ---
print_header "⚙️  ШАГ 1: Настройка окружения"

if [ ! -d "$VENV_DIR" ]; then
    echo "🐍 Создаю виртуальное окружение Python в '$VENV_DIR'..."
    python3 -m venv "$VENV_DIR"
fi

echo "📦 Устанавливаю необходимые Python-зависимости..."
# ЯВНО используем pip из нашего venv и ПОКАЗЫВАЕМ ВЫВОД.
"$VENV_DIR/bin/pip" install aiohttp pycryptodome websockets
echo "✅ Python-зависимости успешно установлены."

echo "📦 Устанавливаю npm-пакет '@vkontakte/vk-tunnel'..."
npm i -g @vkontakte/vk-tunnel
echo "✅ npm-пакет установлен."


# --- ШАГ 2: НАСТРОЙКА КОНФИГУРАЦИОННОГО ФАЙЛА ---
print_header "✍️  ШАГ 2: Настройка конфигурационного файла"

# Проверяем, что наш главный файл существует
if [ ! -f "$MAIN_PYTHON_FILE" ]; then
    echo "❌ Ошибка: Главный файл '$MAIN_PYTHON_FILE' не найден. Не могу продолжить."
    exit 1
fi

# --- Сначала запрашиваем все данные у пользователя ---
echo ""
echo "Пожалуйста, введите данные для Telegram (они будут записаны в $MAIN_PYTHON_FILE):"
read -p "   - Telegram BOT_TOKEN: " BOT_TOKEN
read -p "   - Telegram CHAT_ID: " CHAT_ID
read -p "   - Ваш личный Telegram User ID (для команды /restart-tunnel): " ALLOWED_USER_ID

# --- Записываем данные в vk-tun.py ---
echo "✍️  Обновляю файл '$MAIN_PYTHON_FILE'..."
# Используем надежные команды sed, которые заменят значения, даже если они уже были установлены
sed -i.bak \
    -e "s/BOT_TOKEN = \".*\"/BOT_TOKEN = \"$BOT_TOKEN\"/" \
    -e "s/CHAT_ID = \".*\"/CHAT_ID = \"$CHAT_ID\"/" \
    -e "s/ALLOWED_USER_ID = .*/ALLOWED_USER_ID = $ALLOWED_USER_ID/" \
    "$MAIN_PYTHON_FILE"

echo "✅ Файл '$MAIN_PYTHON_FILE' успешно настроен."


# --- ШАГ 3: ЗАПУСК ПРИЛОЖЕНИЯ ---
print_header "🚀 ШАГ 3: Запуск приложения"
read -p "Хотите запустить сервер сейчас в фоновом режиме? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "⏳ Запускаю $MAIN_PYTHON_FILE..."
    
    # ЯВНО используем python3 из нашего venv
    nohup "$VENV_DIR/bin/python3" "$MAIN_PYTHON_FILE" > server.log 2>&1 &
    
    sleep 2 # Даем процессу время запуститься

    if ps -p $! > /dev/null; then
        echo "✅ Процесс '$MAIN_PYTHON_FILE' успешно запущен."
        echo "   - Логи можно посмотреть командой: tail -f server.log"
    else
        echo "❌ Ошибка при запуске '$MAIN_PYTHON_FILE'. Проверьте лог 'server.log'."
    fi
else
    echo "ℹ️  Запуск отменен. Вы можете запустить скрипт позже командой:"
    echo "   nohup ./.venv/bin/python3 $MAIN_PYTHON_FILE > server.log 2>&1 &"
fi

echo ""
echo "🎉 Настройка завершена!"