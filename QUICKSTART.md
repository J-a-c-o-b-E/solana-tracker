# Quick Start Guide 🚀

Get your Solana Gem Finder bot running in 5 minutes!

## Option 1: Direct Python (Easiest)

### Step 1: Get Your Bot Token
1. Open Telegram, search for `@BotFather`
2. Send `/newbot` and follow instructions
3. Copy your bot token (e.g., `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Step 2: Install Python Requirements
```bash
pip install python-telegram-bot aiohttp
```

### Step 3: Set Token and Run
```bash
# Linux/Mac
export TELEGRAM_BOT_TOKEN='YOUR_TOKEN_HERE'
python solana_gem_bot.py

# Windows CMD
set TELEGRAM_BOT_TOKEN=YOUR_TOKEN_HERE
python solana_gem_bot.py

# Windows PowerShell
$env:TELEGRAM_BOT_TOKEN='YOUR_TOKEN_HERE'
python solana_gem_bot.py
```

### Step 4: Test Your Bot
1. Open Telegram
2. Search for your bot by username
3. Send `/start`
4. Click a filter button!

---

## Option 2: Docker (For Deployment)

### Step 1: Create .env File
```bash
cp .env.example .env
# Edit .env and add your bot token
```

### Step 2: Build and Run
```bash
docker-compose up -d
```

### Step 3: Check Logs
```bash
docker-compose logs -f
```

---

## Troubleshooting

### "Bot doesn't respond"
- ✅ Make sure bot is running (check console/logs)
- ✅ Verify token is correct
- ✅ Try `/start` command in bot chat

### "No tokens found"
- ✅ Filters might be strict, try different preset
- ✅ Solana market might be quiet
- ✅ Check Dexscreener API status

### "Import errors"
```bash
# Make sure you have Python 3.8+
python --version

# Reinstall dependencies
pip install --upgrade -r requirements.txt
```

---

## What the Filters Mean

| Filter | Best For |
|--------|----------|
| **Very Degen** 🔥 | Brand new launches (0-48h), high risk/reward |
| **Degen** 💎 | New but active (1-3 days), good transaction volume |
| **Mid-Caps** 📈 | Established projects with solid metrics |
| **Old Mid-Caps** 🏛️ | Mature projects (30-117 days old) |
| **Larger Mid-Caps** 💰 | Higher liquidity, lower risk |

---

## Next Steps

1. ⭐ Star the repo if you find it useful
2. 🔧 Customize filters in `solana_gem_bot.py`
3. 📱 Add more features (price alerts, favorites, etc.)
4. 🤝 Share with friends who trade Solana

---

## Need Help?

- Check the full README.md for detailed docs
- Review the code comments
- Test with different filters

Happy hunting! 💎🚀
