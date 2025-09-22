#!/bin/bash
# Этот флаг остановит скрипт, если любая команда завершится с ошибкой
set -e

# --- Переменные для удобства ---
VENV_DIR=".venv"
AES_CONFIG_FILE="config_light.py"
MAIN_PYTHON_FILE="server.py"

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

# Создание виртуального окружения, если его нет
if [ ! -d "$VENV_DIR" ]; then
    echo "🐍 Создаю виртуальное окружение Python в '$VENV_DIR'..."
    python3 -m venv "$VENV_DIR"
fi

# Создаем requirements.txt для чистоты
echo "📝 Создаю requirements.txt..."
cat << EOF > requirements.txt
aiohttp
pycryptodome
websockets
EOF

echo "📦 Устанавливаю Python-зависимости из requirements.txt..."
# ЯВНО используем pip из нашего venv и ПОКАЗЫВАЕМ вывод
"$VENV_DIR/bin/pip" install -r requirements.txt
echo "✅ Python-зависимости установлены."

echo "📦 Проверяю и устанавливаю npm-пакет '@vkontakte/vk-tunnel'..."
# Устанавливаем глобально, как и требовалось
npm i -g @vkontakte/vk-tunnel
echo "✅ npm-пакет установлен."

# --- ШАГ 2: НАСТРОЙКА КОНФИГУРАЦИОННЫХ ФАЙЛОВ ---
print_header "✍️  ШАГ 2: Настройка конфигурационных файлов"

# Настройка config_light.py
if [ ! -f "$AES_CONFIG_FILE" ]; then
    echo "⚠️  Предупреждение: Файл '$AES_CONFIG_FILE' не найден. Пропускаю настройку AES ключа."
else
    echo "🔑 Генерирую новый AES ключ..."
    AES_KEY=$(openssl rand -hex 16)
    # Более надежный sed, который заменит ключ, даже если он уже был установлен
    sed -i.bak "s/\"aes_key_hex\": \".*\"/\"aes_key_hex\": \"$AES_KEY\"/" "$AES_CONFIG_FILE"
    echo "✅ Новый AES ключ успешно записан в $AES_CONFIG_FILE."
fi

# Настройка server.py
if [ ! -f "$MAIN_PYTHON_FILE" ]; then
    echo "❌ Ошибка: Главный файл '$MAIN_PYTHON_FILE' не найден. Не могу продолжить."
    exit 1
fi

echo ""
echo "Пожалуйста, введите данные для Telegram:"
read -p "   - Telegram BOT_TOKEN: " BOT_TOKEN
read -p "   - Telegram CHAT_ID (для групп/каналов начинается с -100): " CHAT_ID
read -p "   - Ваш личный Telegram User ID (для команды /restart-tunnel): " ALLOWED_USER_ID

# Используем более надежные команды sed для замены
sed -i.bak \
    -e "s/BOT_TOKEN = \".*\"/BOT_TOKEN = \"$BOT_TOKEN\"/" \
    -e "s/CHAT_ID = \".*\"/CHAT_ID = \"$CHAT_ID\"/" \
    -e "s/ALLOWED_USER_ID = .*/ALLOWED_USER_ID = $ALLOWED_USER_ID/" \
    "$MAIN_PYTHON_FILE"

echo "✅ Настройки Telegram успешно обновлены в файле '$MAIN_PYTHON_FILE'."


# --- ШАГ 3: ЗАПУСК ПРИЛОЖЕНИЯ ---
print_header "🚀 ШАГ 3: Запуск приложения"
read -p "Хотите запустить VK-TUNNEL сейчас в фоновом режиме? (y/n) " -n 1 -r
echo ""

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "⏳ Запускаю server.py через 3 секунды..."
    sleep 3

    # ЯВНО используем python3 из нашего venv
    nohup "$VENV_DIR/bin/python3" "$MAIN_PYTHON_FILE" > server.log 2>&1 &
    
    # Проверяем PID, чтобы убедиться, что процесс запустился
    if ps -p $! > /dev/null; then
        echo "✅ Процесс '$MAIN_PYTHON_FILE' успешно запущен в фоновом режиме."
        echo "   - Логи можно посмотреть командой: tail -f server.log"
        echo "   - Чтобы остановить, найдите PID командой 'pgrep -f server.py' и выполните 'kill <PID>'"
    else
        echo "❌ Ошибка при запуске '$MAIN_PYTHON_FILE'. Проверьте лог 'server.log' на наличие ошибок."
    fi
else
    echo "ℹ️  Запуск отменен. Вы можете запустить скрипт позже командой:"
    echo "   nohup ./.venv/bin/python3 $MAIN_PYTHON_FILE > server.log 2>&1 &"
fi

echo ""
echo "🎉 Настройка завершена!"