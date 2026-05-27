"""
Скрипт для получения истории вызовов SKUD в цикле.

Использование:
    python poll_skud.py

Требует .env файл с:
    UFA_USER - логин/контракт
    UFA_PASS - пароль
"""

import time
import sys
import json
import re
from datetime import datetime
from urllib.parse import urljoin
import requests
from dotenv import load_dotenv
import os


class UfanetAuth:
    """Аутентификация в сервисах Ufanet."""

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def get_access_token(self):
        """Шаг 1: Авторизация и получение JWT токена доступа."""
        print("Получение JWT токена...")
        url = "https://dom.ufanet.ru/api/v1/auth/auth_by_contract/"
        data = {"contract": self.username, "password": self.password}
        try:
            response = self.session.post(url, json=data)
            response.raise_for_status()
            return response.json()["token"]["access"]
        except requests.RequestException as e:
            print(f"Ошибка получения access token: {e}")
            return None

    def get_cam_server_url(self, access_token):
        """Шаг 2: Получение URL сервера камер."""
        print("Получение URL сервера камер...")
        url = "https://dom.ufanet.ru/api/v0/contract/"
        self.session.headers.update({"Authorization": f"JWT {access_token}"})
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()[0]["isp_org"]["cams_server"]["url"]
        except (requests.RequestException, IndexError, KeyError) as e:
            print(f"Ошибка получения cam server URL: {e}")
            return None

    def get_skud_call_history(self, cam_server_url, access_token):
        """Получение истории вызовов SKUD."""
        # Этот endpoint может быть на основном домене или cam_server
        # Пробуем основной домен
        base_url = "https://dom.ufanet.ru"

        url = f"{base_url}/api/v1/skuds/call-history/"

        # Используем JWT токен для авторизации
        self.session.headers.update({
            "Content-Type": "application/json",
            "Authorization": f"JWT {access_token}"
        })

        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"Ошибка получения истории вызовов: {e}")
            return None


class ColoredJSONFormatter:
    """Форматирование JSON с подсветкой синтаксиса."""

    COLORS = {
        'key': '\033[96m',      # cyan
        'string': '\033[93m',   # yellow
        'number': '\033[92m',    # green
        'boolean': '\033[95m',  # magenta
        'null': '\033[90m',     # gray
        'bracket': '\033[97m',  # white
        'reset': '\033[0m',
    }

    @classmethod
    def format(cls, data):
        """Форматирует JSON со цветовой подсветкой."""
        formatted = json.dumps(data, indent=2, ensure_ascii=False)

        # Подсветка ключей
        formatted = cls.COLORS['key'] + formatted
        formatted = formatted.replace('"', cls.COLORS['reset'] + '"')
        formatted = formatted.replace('":', '"' + cls.COLORS['key'] + ':')
        formatted = formatted.replace('": ', '": ' + cls.COLORS['reset'] + '"')

        # Подсветка значений
        formatted = re.sub(
            r'(?<=: )\042[^\042]*\042',
            cls.COLORS['string'] + r'\g<0>' + cls.COLORS['reset'],
            formatted
        )
        formatted = re.sub(
            r'(?<=: )(?<![\042])\d+\.?\d*(?!\w)',
            cls.COLORS['number'] + r'\g<0>' + cls.COLORS['reset'],
            formatted
        )
        formatted = re.sub(
            r'(?<=: )(true|false)',
            cls.COLORS['boolean'] + r'\g<0>' + cls.COLORS['reset'],
            formatted
        )
        formatted = re.sub(
            r'(?<=: )null',
            cls.COLORS['null'] + r'\g<0>' + cls.COLORS['reset'],
            formatted
        )

        return formatted


def main():
    load_dotenv()

    username = os.getenv("UFA_USER")
    password = os.getenv("UFA_PASS")

    if not username or not password:
        print("Ошибка: Убедитесь, что UFA_USER и UFA_PASS заданы в .env файле.")
        sys.exit(1)

    auth = UfanetAuth(username, password)

    print("\033[1m\033[94m" + "=" * 60)
    print("  Получение токенов...")
    print("=" * 60 + "\033[0m")

    access_token = auth.get_access_token()
    if not access_token:
        print("Не удалось получить access token.")
        sys.exit(1)
    print(f"\033[92m✓\033[0m JWT Token получен: {access_token[:20]}...")

    cam_server_url = auth.get_cam_server_url(access_token)
    if cam_server_url:
        print(f"\033[92m✓\033[0m Cam Server URL: {cam_server_url}")
    else:
        print("Не удалось получить cam server URL (не критично)")

    print("\033[1m\033[94m" + "=" * 60)
    print("  Начинаю опрос api/v1/skuds/call-history/")
    print("  Нажмите Ctrl+C для остановки")
    print("=" * 60 + "\033[0m")

    timeout_seconds = 1
    call_count = 0

    try:
        while True:
            call_count += 1
            print(f"\r\033[K\033[1m\033[94m--- Запрос #{call_count} ---\033[0m", end='', flush=True)

            result = auth.get_skud_call_history(cam_server_url, access_token)

            if result is not None:
                results = result.get("results", [])
                if isinstance(results, list):
                    if len(results) == 0:
                        print(f"\r\033[K\033[90mНет новых вызовов\033[0m", end='', flush=True)
                    else:
                        # Сортировка по called_at (новые первыми)
                        sorted_calls = sorted(results, key=lambda x: x.get("called_at", ""), reverse=True)
                        call = sorted_calls[0]
                        called_at = call.get("called_at", "")
                        flat = call.get("flat", "")
                        address = call.get("address", "")
                        print(f"\r\033[K\033[96m{called_at}\033[0m | \033[93mКв. {flat}\033[0m | {address}", end='', flush=True)
                else:
                    print(f"\r\033[K{ColoredJSONFormatter.format(result)}", end='', flush=True)
            else:
                print(f"\r\033[K\033[91mОшибка\033[0m", end='', flush=True)

            time.sleep(timeout_seconds)

    except KeyboardInterrupt:
        print(f"\n\n\033[93mОстановлено после {call_count} запросов.\033[0m")
        sys.exit(0)


if __name__ == "__main__":
    main()
