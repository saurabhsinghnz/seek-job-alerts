# Seek.com.au Job Alert Bot

Automated Python bot that monitors Seek.com.au for new TypeScript IT jobs (remote, $150K+) and sends Telegram notifications every 10 minutes.

## Features

✅ Continuous monitoring of Seek.com.au job listings  
✅ Automatic new job detection using local JSON tracking  
✅ Real-time Telegram notifications  
✅ Configurable check intervals (default: 10 minutes)  
✅ Comprehensive logging (console + file)  
✅ Graceful shutdown with Ctrl+C

## Prerequisites

- Python 3.8+
- Telegram Bot and Chat ID (see [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md))

## Quick Setup

### 1. Clone or Download the Project

### 2. Create Virtual Environment & Install Dependencies

```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
pip install -r requirements.txt
```

### 3. Get Telegram Credentials

See **[TELEGRAM_SETUP.md](TELEGRAM_SETUP.md)** for detailed instructions on:

- Creating a Telegram bot with @BotFather
- Getting your Chat ID from @userinfobot
- Starting a conversation with your bot (important!)

### 4. Configure Environment

Create a `.env` file in the project root:

```bash
SEEK_TELEGRAM_TOKEN=your_bot_token_here
SEEK_CHAT_ID=your_chat_id_here
SEEK_CHECK_INTERVAL=10  # Optional, defaults to 10 minutes
```

Or set them directly in your terminal for a single run:

```bash
export SEEK_TELEGRAM_TOKEN="your_bot_token_here"
export SEEK_CHAT_ID="your_chat_id_here"
```

### 5. Run the Bot

```bash
./run.sh
```

Expected output:

```
2026-04-11 10:00:00,000 - __main__ - INFO - Scheduler is running. Press Ctrl+C to exit.
```

## How It Works

1. **Initial Scan**: Runs immediately on startup
2. **Periodic Checks**: Runs every 10 minutes (configurable)
3. **Job Detection**: Compares new listings against `seen_jobs.json`
4. **Notifications**: Sends Telegram message for each new job
5. **Tracking**: Saves job IDs to `seen_jobs.json` to avoid duplicates

## Troubleshooting

### Bot not sending messages?

See the **[TELEGRAM_SETUP.md](TELEGRAM_SETUP.md#troubleshooting)** troubleshooting section for Telegram-specific issues, including:

- "Forbidden: bot can't initiate conversation with a user"
- "Unauthorized" or token errors
- No messages received

### Not finding jobs?

- Verify the search URL is still valid
- Check website HTML structure hasn't changed (may need to update selectors)
- Ensure you have internet connection

### Syntax/Import errors?

```bash
pip install --upgrade -r requirements.txt
```

## Keep It Running 24/7 (Optional)

### On Mac with `screen`:

```bash
source venv/bin/activate
screen -S seek_alert python seek_job_alert.py
# Press Ctrl+A then D to detach
# Use "screen -r seek_alert" to reattach
```

### On Mac with `nohup`:

```bash
nohup python seek_job_alert.py > seek_alert.log 2>&1 &
```

## Logs

- **Console**: Real-time output in terminal
- **File**: `job_alert.log` for historical records

## Files in Project

- `seek_job_alert.py` - Main bot script
- `requirements.txt` - Python dependencies
- `seen_jobs.json` - Tracks seen job IDs (auto-generated)
- `job_alert.log` - Log file (auto-generated)
- `README.md` - This file
