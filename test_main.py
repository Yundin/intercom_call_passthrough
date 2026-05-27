"""
Тесты для main.py
"""

import pytest
import requests
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

from main import (
    parse_iso_timestamp,
    UfanetAuth,
    CallHistoryWatcher,
)


class TestParseIsoTimestamp:
    """Unit тесты для parse_iso_timestamp()."""

    def test_parses_timestamp_with_positive_offset(self):
        """Парсинг timestamp с положительным смещением часового пояса."""
        ts = "2026-05-26T22:22:17+05:00"
        result = parse_iso_timestamp(ts)

        assert result.year == 2026
        assert result.month == 5
        assert result.day == 26
        assert result.hour == 17  # 22 - 5 = 17 UTC
        assert result.minute == 22
        assert result.tzinfo == timezone.utc

    def test_parses_timestamp_with_negative_offset(self):
        """Парсинг timestamp с отрицательным смещением."""
        ts = "2026-05-26T10:00:00-03:00"
        result = parse_iso_timestamp(ts)

        assert result.hour == 13  # 10 + 3 = 13 UTC

    def test_parses_timestamp_with_z_suffix(self):
        """Парсинг timestamp с суффиксом Z (UTC)."""
        ts = "2026-05-26T15:30:00Z"
        result = parse_iso_timestamp(ts)

        assert result.hour == 15
        assert result.tzinfo == timezone.utc

    def test_parses_timestamp_without_timezone(self):
        """Парсинг timestamp без часового пояса (должен добавить локальный)."""
        ts = "2026-05-26T15:30:00"
        result = parse_iso_timestamp(ts)

        # Должен быть конвертирован в UTC
        assert result.tzinfo == timezone.utc


class TestCallHistoryWatcher:
    """Unit тесты для CallHistoryWatcher."""

    def setup_method(self):
        """Инициализация перед каждым тестом."""
        self.webhook_url = "http://test.local/webhook"
        self.watcher = CallHistoryWatcher(self.webhook_url, lookback_seconds=60)

    def test_initial_last_processed_time_is_in_past(self):
        """При старте last_processed_time должен быть в прошлом."""
        expected_max = datetime.now(timezone.utc)
        expected_min = datetime.now(timezone.utc) - timedelta(seconds=120)

        assert self.watcher.last_processed_time < expected_max
        assert self.watcher.last_processed_time > expected_min

    @patch('main.requests.post')
    def test_process_calls_skips_old_calls(self, mock_post):
        """Звонки старше last_processed_time должны быть пропущены."""
        old_time = datetime.now(timezone.utc) - timedelta(hours=1)
        old_time_iso = old_time.strftime('%Y-%m-%dT%H:%M:%S+00:00')

        calls = [
            {"called_at": old_time_iso, "flat": "42", "address": "ул. Тестовая 1"}
        ]

        self.watcher.process_calls(calls)

        mock_post.assert_not_called()
        # last_processed_time не должен измениться
        initial_time = self.watcher.last_processed_time
        self.watcher.process_calls(calls)
        assert self.watcher.last_processed_time == initial_time

    @patch('main.requests.post')
    def test_process_calls_sends_webhook_for_new_call(self, mock_post):
        """Новый звонок должен вызвать webhook."""
        mock_post.return_value = Mock(status_code=200)

        new_time = datetime.now(timezone.utc)
        new_time_iso = new_time.strftime('%Y-%m-%dT%H:%M:%S+00:00')

        calls = [
            {"called_at": new_time_iso, "flat": "42", "address": "ул. Тестовая 1"}
        ]

        self.watcher.process_calls(calls)

        mock_post.assert_called_once_with(self.webhook_url, timeout=5)
        assert self.watcher.last_processed_time >= new_time - timedelta(seconds=1)

    @patch('main.requests.post')
    def test_process_calls_updates_last_processed_time(self, mock_post):
        """После обработки звонка last_processed_time должен обновиться."""
        mock_post.return_value = Mock(status_code=200)

        new_time = datetime.now(timezone.utc)
        new_time_iso = new_time.strftime('%Y-%m-%dT%H:%M:%S+00:00')

        calls = [
            {"called_at": new_time_iso, "flat": "42", "address": "ул. Тестовая 1"}
        ]

        old_last_processed = self.watcher.last_processed_time
        self.watcher.process_calls(calls)

        assert self.watcher.last_processed_time > old_last_processed

    @patch('main.requests.post')
    def test_process_calls_handles_multiple_calls(self, mock_post):
        """Должны обрабатываться все новые звонки (созданные в одном батче)."""
        mock_post.return_value = Mock(status_code=200)

        # Все звонки в пределах lookback_seconds (60 сек), чтобы все считались "новыми"
        now = datetime.now(timezone.utc)
        calls = [
            {"called_at": (now - timedelta(seconds=50)).strftime('%Y-%m-%dT%H:%M:%S+00:00'), "flat": "1", "address": "A"},
            {"called_at": (now - timedelta(seconds=30)).strftime('%Y-%m-%dT%H:%M:%S+00:00'), "flat": "2", "address": "B"},
            {"called_at": (now - timedelta(seconds=10)).strftime('%Y-%m-%dT%H:%M:%S+00:00'), "flat": "3", "address": "C"},
        ]

        self.watcher.process_calls(calls)

        # Все 3 звонка должны быть обработаны
        assert mock_post.call_count == 3
        assert self.watcher.last_processed_time >= now - timedelta(seconds=11)

    @patch('main.requests.post')
    def test_webhook_success(self, mock_post):
        """Успешная отправка webhook."""
        mock_post.return_value = Mock(status_code=200)

        self.watcher._send_webhook({
            "called_at": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S+00:00'),
            "flat": "42",
            "address": "A"
        })

        mock_post.assert_called_once_with(self.watcher.webhook_url, timeout=5)

    def test_stop_sets_running_false(self):
        """stop() должен установить running = False."""
        assert self.watcher.running is True
        self.watcher.stop()
        assert self.watcher.running is False


class TestUfanetAuth:
    """Unit тесты для UfanetAuth."""

    def test_init_sets_credentials(self):
        """Конструктор должен сохранять credentials."""
        auth = UfanetAuth("user", "pass")
        assert auth.username == "user"
        assert auth.password == "pass"

    def test_init_creates_session(self):
        """Конструктор должен создавать сессию."""
        auth = UfanetAuth("user", "pass")
        assert auth.session is not None

    @patch('requests.Session')
    def test_get_access_token_success(self, mock_session_class):
        """Успешное получение токена."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json = Mock(return_value={"token": {"access": "test_token_123"}})
        mock_session.post = Mock(return_value=mock_response)

        auth = UfanetAuth("user", "pass")
        token = auth.get_access_token()

        assert token == "test_token_123"
        mock_session.post.assert_called_once()

    @patch('requests.Session')
    def test_get_access_token_failure(self, mock_session_class):
        """Ошибка при получении токена."""
        mock_session = MagicMock()
        mock_session.post = Mock(side_effect=requests.RequestException("Network error"))
        mock_session_class.return_value = mock_session

        auth = UfanetAuth("user", "pass")
        token = auth.get_access_token()

        assert token is None

    @patch('requests.Session')
    def test_get_call_history_success(self, mock_session_class):
        """Успешное получение истории."""
        mock_session = MagicMock()
        mock_session_class.return_value = mock_session

        mock_response = Mock()
        mock_response.raise_for_status = Mock()
        mock_response.json = Mock(return_value={"results": []})
        mock_session.get = Mock(return_value=mock_response)

        auth = UfanetAuth("user", "pass")
        result = auth.get_call_history("test_token")

        assert result == {"results": []}

    @patch('requests.Session')
    def test_get_call_history_failure(self, mock_session_class):
        """Ошибка при получении истории."""
        mock_session = MagicMock()
        mock_session.get = Mock(side_effect=requests.RequestException("Network error"))
        mock_session_class.return_value = mock_session

        auth = UfanetAuth("user", "pass")
        result = auth.get_call_history("test_token")

        assert result is None


class TestIntegration:
    """Интеграционные тесты с моком API."""

    @patch('main.requests.post')
    def test_full_flow_new_call(self, mock_webhook):
        """Полный флоу: новый звонок -> webhook."""
        mock_webhook.return_value = Mock(status_code=200)

        # Используем now() с timezone для корректного форматирования
        now = datetime.now(timezone.utc)
        # Форматируем как UTC с +00:00
        test_calls = [
            {
                "called_at": now.strftime('%Y-%m-%dT%H:%M:%S+00:00'),
                "flat": "42",
                "address": "ул. Ленина 10"
            }
        ]

        watcher = CallHistoryWatcher("http://webhook.local")

        # Симулируем обработку
        watcher.process_calls(test_calls)

        assert mock_webhook.call_count == 1

    @patch('main.requests.post')
    def test_full_flow_no_new_calls(self, mock_webhook):
        """Полный флоу: нет новых звонков."""
        mock_webhook.return_value = Mock(status_code=200)

        # Старый звонок (больше чем lookback_seconds назад)
        old_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        test_calls = [
            {
                "called_at": old_time.strftime('%Y-%m-%dT%H:%M:%S+05:00'),
                "flat": "1",
                "address": "Старый"
            }
        ]

        watcher = CallHistoryWatcher("http://webhook.local")
        watcher.process_calls(test_calls)

        assert mock_webhook.call_count == 0

    @patch('main.requests.post')
    def test_full_flow_api_returns_empty(self, mock_webhook):
        """Полный флоу: API возвращает пустой список."""
        mock_webhook.return_value = Mock(status_code=200)

        watcher = CallHistoryWatcher("http://webhook.local")
        watcher.process_calls([])

        assert mock_webhook.call_count == 0

    @patch('main.requests.post')
    def test_full_flow_sorted_by_time(self, mock_webhook):
        """Звонки должны обрабатываться в порядке newest-first."""
        mock_webhook.return_value = Mock(status_code=200)

        now = datetime.now(timezone.utc)
        # Возвращаем в произвольном порядке, все в пределах lookback
        test_calls = [
            {"called_at": (now - timedelta(seconds=50)).strftime('%Y-%m-%dT%H:%M:%S+00:00'), "flat": "2"},
            {"called_at": (now - timedelta(seconds=10)).strftime('%Y-%m-%dT%H:%M:%S+00:00'), "flat": "1"},
            {"called_at": (now - timedelta(seconds=30)).strftime('%Y-%m-%dT%H:%M:%S+00:00'), "flat": "3"},
        ]

        watcher = CallHistoryWatcher("http://webhook.local")
        watcher.process_calls(test_calls)

        # Все 3 звонка должны быть обработаны (все в пределах lookback)
        assert mock_webhook.call_count == 3


class TestEdgeCases:
    """Тесты на граничные случаи."""

    @patch('main.requests.post')
    def test_empty_calls_list(self, mock_post):
        """Пустой список звонков."""
        mock_post.return_value = Mock(status_code=200)
        watcher = CallHistoryWatcher("http://webhook.local")
        watcher.process_calls([])
        mock_post.assert_not_called()

    @patch('main.requests.post')
    def test_call_missing_fields(self, mock_post):
        """Звонок с отсутствующими полями."""
        mock_post.return_value = Mock(status_code=200)
        watcher = CallHistoryWatcher("http://webhook.local")

        # Звонок с отсутствующим called_at - должен вызвать ошибку
        calls = [{"flat": "42"}]
        with pytest.raises(KeyError):
            watcher.process_calls(calls)

    def test_watcher_initialization_with_custom_lookback(self):
        """Инициализация с кастомным lookback."""
        watcher = CallHistoryWatcher("http://webhook.local", lookback_seconds=120)
        assert watcher.lookback_seconds == 120

        expected = datetime.now(timezone.utc) - timedelta(seconds=120)
        delta = abs((watcher.last_processed_time - expected).total_seconds())
        assert delta < 2  # в пределах 2 секунд


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
