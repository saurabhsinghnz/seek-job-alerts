# 🚀 Quick Start Guide

Get your Seek Job Alert Bot running in 5 minutes!

## Step 1: Install Python Dependencies

```bash
cd /Users/saurabhsingh/Workspace/Source/Personal/seek-job-alert
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Or use the automated setup script:

```bash
./setup.sh
```

---

## Step 2: Get Telegram Credentials

### 2a. Create a Telegram Bot (Get Bot Token)

1. Open Telegram app
2. Search for **@BotFather**
3. Send: `/newbot`
4. Follow instructions to name your bot
5. **Copy the Bot Token** (example: `123456:ABC-DEF123...`)

### 2b. Get Your Chat ID (Get Chat ID)

1. Open Telegram app
2. Search for **@userinfobot**
3. Send any message
4. **Copy your User ID** (5-10 digit number)

### 2c. ⚠️ START CONVERSATION WITH YOUR BOT (Required!)

This is the most important step! Without it, you won't receive messages:

1. In Telegram, search for your bot by the name you created
2. **Click "Start"** to send `/start` command
3. The bot now has permission to message you

---

## Step 3: Configure Environment

Create `.env` file with your credentials:

```bash
# On macOS/Linux, run this in the terminal:
cat > .env << EOF
SEEK_TELEGRAM_TOKEN=paste_your_bot_token_here
SEEK_CHAT_ID=paste_your_chat_id_here
EOF
```

Or manually edit `.env`:

```
SEEK_TELEGRAM_TOKEN=your_bot_token_here
SEEK_CHAT_ID=your_chat_id_here
```

---

## Step 4: Start the Bot

```bash
# Activate virtual environment (if not already active)
source venv/bin/activate

# Run the bot
python seek_job_alert.py
```

If you use `./run.sh`, it will source `.env` but does not activate the virtualenv for you. Activate the venv first:

```bash
source venv/bin/activate && ./run.sh
```

You should see:

```
2026-04-11 21:55:00,000 - __main__ - INFO - Scheduler is running. Press Ctrl+C to exit.
```

---

## Step 5: Test It Out

1. The bot will scan immediately and every 10 minutes
2. When new TypeScript jobs are found, you'll receive **Telegram notifications**
3. Check `job_alert.log` for detailed logs

---

## Troubleshooting

| Problem                      | Solution                                                               |
| ---------------------------- | ---------------------------------------------------------------------- |
| **Module not found errors**  | Run `pip install -r requirements.txt` again                            |
| **Bot not sending messages** | Verify token & chat ID are correct                                     |
| **No jobs found**            | Check your internet connection, Seek.com.au might be blocking requests |
| **Can't find .env file**     | Create it in the project root: `cp .env.example .env`                  |

---

## Keep It Running 24/7 (Optional)

### On Mac with `screen`:

```bash
screen -S seek_alert python seek_job_alert.py
# Press Ctrl+A then D to detach
# Use "screen -r seek_alert" to reattach
```

### On Mac with `nohup`:

```bash
nohup python seek_job_alert.py > seek_alert.log 2>&1 &
```

### Using systemd (Linux only):

Create `/etc/systemd/system/seek-alert.service`:

```ini
[Unit]
Description=Seek Job Alert Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/seek-job-alert
Environment="SEEK_TELEGRAM_TOKEN=your_token"
Environment="SEEK_CHAT_ID=your_chat_id"
ExecStart=/path/to/venv/bin/python seek_job_alert.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl enable seek-alert
sudo systemctl start seek-alert
```

---

## That's it! 🎉

Your bot should now be monitoring Seek.com.au for TypeScript jobs every 10 minutes!

For more info, see [README.md](README.md)
