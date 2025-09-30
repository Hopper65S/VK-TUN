import asyncio
import json
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import aiohttp
from aiohttp import web
import aiofiles
from dotenv import dotenv_values, set_key

log = logging.getLogger("web_ui")

class ConfigManager:
    def __init__(self, env_path: str = ".env"):
        self.env_path = env_path
        self.api_domain = os.getenv("API_DOMAIN")
        self.api_token = os.getenv("API_TOKEN")
        
    async def get_hosts(self) -> list:
        """Получение списка хостов из API"""
        if not self.api_domain or not self.api_token:
            raise ValueError("API_DOMAIN или API_TOKEN не настроены")
            
        url = f"{self.api_domain}/api/hosts"
        headers = {"Authorization": f"Bearer {self.api_token}"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        # Извлекаем только нужные поля
                        hosts = []
                        for item in data:
                            hosts.append({
                                "uuid": item.get("uuid"),
                                "remark": item.get("remark", "Unknown"),
                                "address": item.get("address", ""),
                                "port": item.get("port", 443),
                                "inbound": item.get("inbound", {}),
                                "isDisabled": item.get("isDisabled", False)
                            })
                        return hosts
                    else:
                        log.error(f"Ошибка API: {response.status}")
                        return []
        except Exception as e:
            log.error(f"Ошибка при получении хостов: {e}")
            return []
    
    async def get_current_config(self) -> Dict[str, str]:
        """Получение текущей конфигурации из .env"""
        return dotenv_values(self.env_path)
    
    async def update_env_config(self, host_data: Dict[str, Any]) -> bool:
        """Обновление .env файла с данными выбранного хоста"""
        try:
            # Обновляем значения в .env файле
            set_key(self.env_path, "CONFIG_UUID", host_data.get("uuid", ""))
            
            inbound = host_data.get("inbound", {})
            set_key(self.env_path, "CONFIG_PROFILE_UUID", 
                   inbound.get("configProfileUuid", ""))
            set_key(self.env_path, "CONFIG_PROFILE_INBOUND_UUID", 
                   inbound.get("configProfileInboundUuid", ""))
            
            # Сохраняем информацию о выбранном хосте
            set_key(self.env_path, "SELECTED_HOST_REMARK", 
                   host_data.get("remark", ""))
            set_key(self.env_path, "SELECTED_HOST_ADDRESS", 
                   host_data.get("address", ""))
            
            log.info(f"Конфигурация обновлена для хоста: {host_data.get('remark')}")
            return True
        except Exception as e:
            log.error(f"Ошибка при обновлении .env: {e}")
            return False
    
    async def update_env_field(self, key: str, value: str) -> bool:
        """Обновление отдельного поля в .env"""
        try:
            set_key(self.env_path, key, value)
            return True
        except Exception as e:
            log.error(f"Ошибка при обновлении поля {key}: {e}")
            return False

class WebUI:
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.app = web.Application()
        self.setup_routes()
        
    def setup_routes(self):
        """Настройка маршрутов"""
        self.app.router.add_get('/', self.index_handler)
        self.app.router.add_get('/api/hosts', self.get_hosts_handler)
        self.app.router.add_get('/api/config', self.get_config_handler)
        self.app.router.add_post('/api/config/apply-host', self.apply_host_handler)
        self.app.router.add_post('/api/config/update', self.update_config_handler)
        self.app.router.add_static('/', path='static', name='static')
        
    async def index_handler(self, request):
        """Главная страница"""
        html_path = Path(__file__).parent / 'templates' / 'index.html'
        async with aiofiles.open(html_path, 'r', encoding='utf-8') as f:
            html_content = await f.read()
        return web.Response(text=html_content, content_type='text/html')
    
    async def get_hosts_handler(self, request):
        """API endpoint для получения хостов"""
        hosts = await self.config_manager.get_hosts()
        return web.json_response(hosts)
    
    async def get_config_handler(self, request):
        """API endpoint для получения текущей конфигурации"""
        config = await self.config_manager.get_current_config()
        return web.json_response(config)
    
    async def apply_host_handler(self, request):
        """API endpoint для применения конфигурации хоста"""
        try:
            data = await request.json()
            success = await self.config_manager.update_env_config(data)
            
            if success:
                return web.json_response({
                    "success": True, 
                    "message": "Конфигурация успешно применена"
                })
            else:
                return web.json_response({
                    "success": False, 
                    "message": "Ошибка при применении конфигурации"
                }, status=500)
        except Exception as e:
            return web.json_response({
                "success": False, 
                "message": str(e)
            }, status=400)
    
    async def update_config_handler(self, request):
        """API endpoint для обновления отдельных полей конфигурации"""
        try:
            data = await request.json()
            
            # Обновляем каждое поле
            for key, value in data.items():
                if key in ["BOT_TOKEN", "CHAT_ID", "ALLOWED_USER_ID", 
                          "API_TOKEN", "API_DOMAIN", "HEALTH_CHECK_INTERVAL_SECONDS", 
                          "TUNNEL_PORT"]:
                    await self.config_manager.update_env_field(key, str(value))
            
            return web.json_response({
                "success": True, 
                "message": "Конфигурация обновлена"
            })
        except Exception as e:
            return web.json_response({
                "success": False, 
                "message": str(e)
            }, status=400)
    
    def run(self, host='127.0.0.1', port=4001):
        """Запуск веб-сервера"""
        web.run_app(self.app, host=host, port=port)

async def main():
    """Главная функция"""
    logging.basicConfig(level=logging.INFO)
    
    # Создаем менеджер конфигурации
    config_manager = ConfigManager()
    
    # Создаем и запускаем веб-интерфейс
    web_ui = WebUI(config_manager)
    
    log.info("Запуск веб-интерфейса на http://127.0.0.1:4001")
    web_ui.run()

if __name__ == "__main__":
    asyncio.run(main())