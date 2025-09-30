#!/usr/bin/env python3
import asyncio
import sys
import os
from pathlib import Path

# Добавляем текущую директорию в путь
sys.path.insert(0, str(Path(__file__).parent))

# Загружаем переменные окружения
from dotenv import load_dotenv
load_dotenv()

# Импортируем и запускаем веб-интерфейс
from web_ui import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nВеб-интерфейс остановлен")
    except Exception as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)