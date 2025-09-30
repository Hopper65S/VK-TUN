import os
import asyncio
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

log = logging.getLogger("dynamic_config")

class EnvFileHandler(FileSystemEventHandler):
    """Обработчик изменений .env файла"""
    
    def __init__(self, callback):
        self.callback = callback
        self.last_modified = 0
        
    def on_modified(self, event):
        if event.src_path.endswith('.env'):
            # Защита от множественных событий
            current_time = asyncio.get_event_loop().time()
            if current_time - self.last_modified < 1:
                return
            self.last_modified = current_time
            
            log.info("Обнаружено изменение .env файла")
            asyncio.create_task(self.callback())

class DynamicConfigLoader:
    """Загрузчик конфигурации с поддержкой горячей перезагрузки"""
    
    def __init__(self, env_path: str = ".env"):
        self.env_path = Path(env_path)
        self.observer = None
        self.config_callbacks = []
        
    def add_callback(self, callback):
        """Добавить callback для уведомления об изменениях"""
        self.config_callbacks.append(callback)
        
    async def reload_config(self):
        """Перезагрузить конфигурацию"""
        log.info("Перезагрузка конфигурации...")
        load_dotenv(self.env_path, override=True)
        
        # Уведомляем все callbacks
        for callback in self.config_callbacks:
            try:
                await callback()
            except Exception as e:
                log.error(f"Ошибка в callback: {e}")
                
    def start_watching(self):
        """Начать отслеживание изменений файла"""
        if self.observer:
            return
            
        self.observer = Observer()
        handler = EnvFileHandler(self.reload_config)
        self.observer.schedule(handler, str(self.env_path.parent), recursive=False)
        self.observer.start()
        log.info(f"Начато отслеживание изменений {self.env_path}")
        
    def stop_watching(self):
        """Остановить отслеживание"""
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None