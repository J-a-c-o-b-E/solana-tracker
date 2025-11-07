# Solana Gem Finder Telegram Bot 🔍💎

A Telegram bot that finds hidden gems on the Solana network using Dexscreener data with customizable filters.

## Features

- **Multiple Filter Presets**: 
  - 🔥 Very Degen (0-48h old pairs)
  - 💎 Degen (1-72h old pairs)  
  - 📈 Mid-Caps (established tokens)
  - 🏛️ Old Mid-Caps (mature projects)
  - 💰 Larger Mid-Caps (high liquidity)

- **Real-time Data**: Fetches live data from Dexscreener API
- **Detailed Metrics**: Shows liquidity, FDV, volume, transactions, pair age
- **Easy to Use**: Simple inline keyboard interface

## Setup Instructions

### 1. Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` command
3. Follow the prompts to create your bot
4. Copy the bot token (looks like: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

Or install manually:
```bash
pip install python-telegram-bot==20.7 aiohttp==3.9.1
```

### 3. Set Your Bot Token

**On Linux/Mac:**
```bash
export TELEGRAM_BOT_TOKEN='your_bot_token_here'
```

**On Windows (CMD):**
```cmd
set TELEGRAM_BOT_TOKEN=your_bot_token_here
```

**On Windows (PowerShell):**
```powershell
$env:TELEGRAM_BOT_TOKEN='your_bot_token_here'
```

### 4. Run the Bot

```bash
python solana_gem_bot.py
```

### 5. Use the Bot

1. Open your bot in Telegram
2. Send `/start` command
3. Click on a filter button to search for tokens
4. View the results!

## Filter Configurations

### Very Degen 🔥
- Liquidity: $10k+
- Min FDV: $100k
- Pair Age: 0-48 hours
- 1H Transactions: 30+

### Degen 💎
- Min Liquidity: $15k
- Min FDV: $100k
- Pair Age: 1-72 hours
- 1H Transactions: 100+

### Mid-Caps 📈
- Liquidity: $100k+
- Min FDV: $1M
- 24H Volume: $1.2M+
- 24H Transactions: 30+

### Old Mid-Caps 🏛️
- Liquidity: $100k+
- FDV: $200k-$100M
- Pair Age: 720-2800 hours
- 24H Volume: $200k+
- 24H Transactions: 2000+

### Larger Mid-Caps 💰
- Liquidity: $200k+
- Min MCap: $1M
- 6H Volume: $150k+

## Customization

You can modify the filter criteria by editing the `TokenFilter` class in `solana_gem_bot.py`:

```python
VERY_DEGEN = {
    'name': 'Very Degen',
    'min_liquidity': 10000,  # Change this value
    'max_liquidity': float('inf'),
    'min_fdv': 100000,       # Change this value
    # ... more parameters
}
```

## API Rate Limits

- Dexscreener API has rate limits
- The bot includes a 0.5-second delay between messages to avoid Telegram rate limits
- Consider implementing caching for production use

## Advanced Usage

### Running as a Service (Linux)

Create a systemd service file `/etc/systemd/system/solana-gem-bot.service`:

```ini
[Unit]
Description=Solana Gem Finder Bot
After=network.target

[Service]
Type=simple
User=your_username
WorkingDirectory=/path/to/bot
Environment="TELEGRAM_BOT_TOKEN=your_token_here"
ExecStart=/usr/bin/python3 /path/to/bot/solana_gem_bot.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Then enable and start:
```bash
sudo systemctl enable solana-gem-bot
sudo systemctl start solana-gem-bot
```

### Using Docker

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY solana_gem_bot.py .

CMD ["python", "solana_gem_bot.py"]
```

Build and run:
```bash
docker build -t solana-gem-bot .
docker run -e TELEGRAM_BOT_TOKEN='your_token' solana-gem-bot
```

## Troubleshooting

**Bot doesn't respond:**
- Check if the bot token is set correctly
- Verify the bot is running (`python solana_gem_bot.py`)
- Check for error messages in the console

**No tokens found:**
- The filters might be too strict
- Try a different filter preset
- Check if Dexscreener API is accessible

**Rate limit errors:**
- Wait a few minutes before trying again
- Consider implementing request caching

## Data Sources

- **Dexscreener API**: https://api.dexscreener.com/
- All data is fetched in real-time from public DEX aggregators

## Disclaimer

⚠️ **IMPORTANT**: This bot is for informational purposes only. Always do your own research (DYOR) before investing in any cryptocurrency. The crypto market is highly volatile and risky.

## Contributing

Feel free to fork this project and customize it for your needs. Suggestions and improvements are welcome!

## License

MIT License - Feel free to use and modify as needed.
