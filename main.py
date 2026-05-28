"""
Скрипт для мониторинга истории вызовов и отправки webhook при новых звонках.

Использование:
    python main.py

Требует .env файл с:
    UFA_USER - логин/контракт
    UFA_PASS - пароль
    WEBHOOK_URL_CALL_HISTORY - URL для webhook
"""

import os
import sys
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional

import requests
from dotenv import load_dotenv


def ts():
    """Возвращает текущий timestamp для логов."""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def parse_iso_timestamp(ts_str: str) -> datetime:
    """Parse ISO timestamp with timezone and convert to UTC."""
    # Format: 2026-05-26T22:22:17+05:00
    return datetime.fromisoformat(ts_str).astimezone(timezone.utc)


@dataclass
class CallHistoryResult:
    """Результат запроса истории вызовов."""
    data: Optional[dict] = None
    error_type: Optional[str] = None  # None="success", "server"=5xx, "network"=connection error

    @property
    def is_success(self) -> bool:
        return self.error_type is None


class UfanetAuth:
    """Аутентификация в сервисах Ufanet."""

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def get_access_token(self):
        """Шаг 1: Авторизация и получение JWT токена доступа."""
        print(f"[{ts()}] Авторизация...")
        url = "https://dom.ufanet.ru/api/v1/auth/auth_by_contract/"
        data = {"contract": self.username, "password": self.password}
        try:
            response = self.session.post(url, json=data)
            response.raise_for_status()
            print(f"[{ts()}] Авторизация успешна")
            return response.json()["token"]["access"]
        except requests.RequestException as e:
            print(f"[{ts()}] Ошибка получения access token: {e}")
            return None

    def get_call_history(self, access_token) -> CallHistoryResult:
        """Получение истории вызовов."""
        url = "https://dom.ufanet.ru/api/v1/skuds/call-history/"
        self.session.headers.update({"Authorization": f"JWT {access_token}"})

        try:
            response = self.session.get(url)
            if 400 <= response.status_code < 500:
                # 4xx errors likely mean expired token
                print(f"[{ts()}] Auth error: {response.status_code}")
                return CallHistoryResult(error_type="auth")
            if 500 <= response.status_code < 600:
                print(f"[{ts()}] Server error: {response.status_code}")
                return CallHistoryResult(error_type="server")
            return CallHistoryResult(data=response.json())
        except requests.RequestException as e:
            print(f"[{ts()}] Network error: {e}")
            return CallHistoryResult(error_type="network")


class CallHistoryWatcher:
    """Мониторит историю вызовов и отправляет webhook при новых."""

    def __init__(self, webhook_url, lookback_seconds=60):
        self.webhook_url = webhook_url
        self.lookback_seconds = lookback_seconds
        self.last_processed_time = datetime.now(timezone.utc) - timedelta(seconds=lookback_seconds)
        self.running = True
        self.request_count = 0
        self.last_no_calls_log_time = None

    def process_calls(self, calls):
        """Обработать список звонков, отправить webhook для новых."""
        # Находим все новые звонки (новее last_processed_time)
        new_calls = []
        max_called_at = None
        for call in calls:
            called_at = parse_iso_timestamp(call["called_at"])
            if called_at > self.last_processed_time:
                new_calls.append(call)
                if max_called_at is None or called_at > max_called_at:
                    max_called_at = called_at

        # Логируем количество звонков только раз в 5 минут или при новых звонках
        now = datetime.now()
        if len(new_calls) > 0 or self.last_no_calls_log_time is None or (now - self.last_no_calls_log_time).total_seconds() >= 300:
            print(f"[{ts()}] [Опрос #{self.request_count}] Получено звонков: {len(calls)}")

        # Отправляем webhook для всех новых звонков
        for call in new_calls:
            self._send_webhook(call)
            print(f"[{ts()}]   -> Новый звонок: {call.get('called_at')} | Кв. {call.get('flat')} | {call.get('address')}")

        # Сбрасываем таймер логирования при новых звонках
        if len(new_calls) > 0:
            self.last_no_calls_log_time = None

        # Обновляем last_processed_time на самый новый звонок (один раз)
        if max_called_at is not None:
            self.last_processed_time = max_called_at

        if len(new_calls) == 0:
            if self.last_no_calls_log_time is None or (now - self.last_no_calls_log_time).total_seconds() >= 300:
                print(f"[{ts()}] [Опрос #{self.request_count}] Новых звонков нет")
                self.last_no_calls_log_time = now

    def _send_webhook(self, call):
        """Отправить webhook (аналогично main.py)."""
        try:
            response = requests.post(self.webhook_url, timeout=5)
            if 200 <= response.status_code < 300:
                pass  # успех
            else:
                print(f"Ошибка webhook: Статус {response.status_code}")
        except requests.RequestException as e:
            print(f"Ошибка отправки webhook: {e}")

    def stop(self):
        self.running = False


def main():
    load_dotenv()

    username = os.getenv("UFA_USER")
    password = os.getenv("UFA_PASS")
    webhook_url = os.getenv("WEBHOOK_URL_CALL_HISTORY")

    if not username or not password:
        print("Ошибка: Убедитесь, что UFA_USER и UFA_PASS заданы в .env файле.")
        sys.exit(1)

    if not webhook_url:
        print("Ошибка: WEBHOOK_URL_CALL_HISTORY не задан в .env файле.")
        sys.exit(1)

    auth = UfanetAuth(username, password)
    watcher = CallHistoryWatcher(webhook_url)

    def signal_handler(sig, frame):
        print(f"\n[{ts()}] Остановка...")
        watcher.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    print(f"[{ts()}] Начинаю мониторинг call-history...")

    access_token = None
    poll_interval = 1.0

    print(f"[{ts()}] [Конфиг] Webhook URL: {webhook_url}")
    print(f"[{ts()}] [Конфиг] Lookback: {watcher.lookback_seconds} сек")
    print(f"[{ts()}] [Конфиг] Интервал опроса: {poll_interval} сек")

    while watcher.running:
        # Refresh token periodically (tokens expire ~8 hours)
        if access_token is None:
            print(f"[{ts()}] [Токен] Запрос нового токена...")
            access_token = auth.get_access_token()
            if not access_token:
                print(f"[{ts()}] [Токен] Не удалось получить токен, повтор через 5 сек...")
                time.sleep(5)
                continue
            print(f"[{ts()}] [Токен] Токен обновлён: {access_token[:20]}...")

        watcher.request_count += 1
        result = auth.get_call_history(access_token)

        if result.error_type == "auth":
            # 4xx - token likely expired, refresh
            print(f"[{ts()}] [Ошибка] Токен истёк, обновляю...")
            access_token = None
            time.sleep(poll_interval)
            continue

        if result.error_type in ("server", "network"):
            # Transient error - retry with same token
            time.sleep(poll_interval)
            continue

        calls = result.data.get("results", [])
        if isinstance(calls, list):
            watcher.process_calls(calls)

        time.sleep(poll_interval)

    print(f"[{ts()}] Мониторинг остановлен.")


if __name__ == "__main__":
    main()
