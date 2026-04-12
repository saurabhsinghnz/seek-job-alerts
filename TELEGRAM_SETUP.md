# Telegram Bot Setup Guide

## Getting Your Credentials

### Step 1: Create a Bot with @BotFather

1. Open Telegram
2. Search for **@BotFather** (official Telegram bot creator)
3. Send: `/newbot`
4. Follow the prompts:
   - Enter a name (e.g., "Seek Job Alert")
   - Enter a username (e.g., `seek_job_alert_bot`) - must end with `_bot`
5. **Copy your Bot Token** - looks like: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`

### Step 2: Get Your User ID

1. Search for **@userinfobot**
2. Send any message (e.g., "hello")
3. It replies with your User ID (a number like `987654321`)

### Step 3: IMPORTANT - Start Conversation with Your Bot

⚠️ **This is the crucial step many people miss:**

1. Search for your bot username (the one you created, e.g., `@seek_job_alert_bot`)
2. **Click "Start"** to send the `/start` command
3. The bot should reply (even if just with an empty message)
4. Now the bot has permission to send you messages!

### Step 4: Configure Environment Variables

Create `.env` file (use KEY=VALUE format preferred by `./run.sh`):

```bash
SEEK_TELEGRAM_TOKEN=your_bot_token_here
SEEK_CHAT_ID=your_user_id_here
SEEK_CHECK_INTERVAL=10
```

Or run with inline variables:

```bash
export SEEK_TELEGRAM_TOKEN="123456:ABC-DEF1234..."
export SEEK_CHAT_ID="987654321"
python seek_job_alert.py
```

## Troubleshooting

### Error: "Forbidden: bot can't initiate conversation with a user"

**Solution:** You haven't started a conversation with the bot yet!

1. Go to Telegram
2. Search for your bot name
3. Click **Start**
4. Then run the job alert bot again

### Error: "Unauthorized" or token doesn't work

**Solution:** Double-check your bot token from @BotFather

### No messages received

1. Check `job_alert.log` for errors
2. Verify both `SEEK_TELEGRAM_TOKEN` and `SEEK_CHAT_ID` are set correctly
3. Make sure you clicked "Start" on your bot in Telegram

## Testing

Send a test message:

```bash
curl -X POST https://api.telegram.org/bot{YOUR_TOKEN}/sendMessage \
  -H 'Content-Type: application/json' \
  -d '{"chat_id": {YOUR_CHAT_ID}, "text": "Test message"}'
```

If it returns `"ok":true`, your credentials are correct!
