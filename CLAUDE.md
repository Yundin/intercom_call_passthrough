# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Python application for monitoring intercom (domophone) call history from Fnet/Ufanet. When new calls are detected, sends a webhook to Home Assistant for door opening integration.

## Common Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run main monitoring script
python main.py

# Run tests
pytest test_main.py -v

# Run with Docker
docker compose up -d --build
```

## Environment Configuration

Create `.env` file with:
```ini
UFA_USER=        # Fnet/Ufanet login/contract
UFA_PASS=        # Fnet/Ufanet password
WEBHOOK_URL_CALL_HISTORY=  # Webhook URL for Home Assistant
```

## Architecture

**main.py** - Production monitoring script
- `UfanetAuth` class: JWT authentication with `get_access_token()` and `get_call_history()`
- `CallHistoryWatcher` class: Polls call history, detects new calls, sends webhooks
- 1-second polling interval with automatic token refresh on expiry (~8 hours)

**poll_skud.py** - Debug/interactive polling script
- Similar `UfanetAuth` class (duplicated logic)
- Real-time display of call history with colored JSON output
- Interactive one-shot polling

## API Endpoints

- Auth: `https://dom.ufanet.ru/api/v1/auth/auth_by_contract/`
- Call History: `https://dom.ufanet.ru/api/v1/skuds/call-history/`

## Testing

Tests use pytest with mocks for network calls. Key test classes:
- `TestParseIsoTimestamp` - timezone conversion tests
- `TestCallHistoryWatcher` - core monitoring logic
- `TestUfanetAuth` - authentication tests
- `TestIntegration` - full flow tests
