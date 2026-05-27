# Что это
Python-приложение для мониторинга истории вызовов домофона Fnet/Ufanet. При обнаружении нового звонка отправляет веб-хук.

Я отправляю хук в Home Assistant, где через эту интеграцию открываю дверь: https://github.com/Muxee4ka/ucams_home_assistant/

## Предыдущая версия
Альтернативный подход — [intercom_passthrough](https://github.com/Yundin/intercom_passthrough) — анализирует аудиопоток с камеры домофона в реальном времени, распознаёт звуки нажатий кнопок и сигнал вызова.

# Как использовать

### 1. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 2. Настройка
Конфигурация через `.env` файл в корне проекта:

```ini
# --- Учетные данные от приложения Fnet/Ufanet ---
UFA_USER=""
UFA_PASS=""

# --- URL для веб-хука ---
WEBHOOK_URL_CALL_HISTORY=""
```

### 3. Запуск
```bash
python main.py
```

# Развертывание в Docker

1. Создайте `.env` файл с настройками.
2. Запустите контейнер:
    ```bash
    docker compose up -d --build
    ```
