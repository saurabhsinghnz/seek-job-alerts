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
- Telegram Bot Token (from [@BotFather](https://t.me/botfather))
- Telegram Chat ID (your personal chat ID with the bot)

## Setup Instructions

### 1. Clone or Download the Project

```bash
cd /Users/saurabhsingh/Workspace/Source/Personal/seek-job-alert
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Get Telegram Credentials

**4a. Create a Telegram Bot:**

1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/start` then `/newbot`
3. Follow the prompts to create your bot
4. Copy the **Bot Token** (looks like: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)

**4b. Get Your Chat ID:**

1. Open Telegram and search for [@userinfobot](https://t.me/userinfobot)
2. Send any message and it will reply with your **User ID**

**4c. ⚠️ IMPORTANT - Start Conversation with Your Bot:**

This is required for Telegram to allow the bot to send you messages:

1. Search for your bot by username (the name you created in step 4a)
2. **Click "Start"** to initiate the conversation
3. Done! The bot now has permission to message you

Create a `.env` file in the project root (use KEY=VALUE format):

```bash
# Copy this template to .env (no `export` keywords)
SEEK_TELEGRAM_TOKEN=your_bot_token_here
SEEK_CHAT_ID=your_chat_id_here
SEEK_CHECK_INTERVAL=10  # Optional, defaults to 10 minutes
```

Or set them directly in your terminal for a single session:

```bash
export SEEK_TELEGRAM_TOKEN="your_bot_token_here"
export SEEK_CHAT_ID="your_chat_id_here"
```

### 6. Run the Bot

```bash
python seek_job_alert.py
```

If you prefer to use the helper script `./run.sh`, note that it reads the `.env` file but does not activate the project's virtual environment. Activate the venv first, for example:

```bash
source venv/bin/activate
./run.sh
```

You should see:

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

### Error: "Forbidden: bot can't initiate conversation with a user"

**Solution:** You haven't started a conversation with the bot yet!

1. Open Telegram
2. Search for your bot by name
3. Click **Start**
4. Then run the job alert bot again

### Bot not sending messages?

- Verify Telegram token is correct
- Check Chat ID is correct
- Make sure you clicked **Start** on your bot (see error above)
- Check `job_alert.log` for detailed errors
- Check firewall/VPN isn't blocking Telegram API

### Not finding jobs?

- Verify the search URL is still valid
- Check website HTML structure hasn't changed (may need to update selectors)
- Ensure you have internet connection

### Syntax/Import errors?

```bash
pip install --upgrade -r requirements.txt
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

## Notes

- The bot uses web scraping (BeautifulSoup) - not an official API
- Seek.com.au's HTML structure may change; if no jobs are found, check selectors
- The bot respects rate limits by checking every 10 minutes
- Seen jobs are permanently tracked to avoid duplicate alerts

## Next Steps (Optional Enhancements)

- [ ] Add database storage instead of JSON
- [ ] Create dashboard to view job history
- [ ] Add filtering by keywords in job description
- [ ] Deploy to cloud (AWS Lambda, DigitalOcean, etc.)
- [ ] Add job statistics and analytics
