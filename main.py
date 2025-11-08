import os
import asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime, timedelta

# Dexscreener API endpoint
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/tokens/"
SEARCH_API = "https://api.dexscreener.com/latest/dex/search"

class TokenFilter:
    """Define filter criteria for different token categories"""
    
    VERY_DEGEN = {
        'name': 'Very Degen',
        'min_liquidity': 5000,  # Lowered from 10k
        'max_liquidity': float('inf'),
        'min_fdv': 50000,  # Lowered from 100k
        'max_fdv': float('inf'),
        'min_pair_age_hours': 0,
        'max_pair_age_hours': 48,
        'min_txns_1h': 10,  # Lowered from 30
        'max_txns_1h': float('inf'),
    }
    
    DEGEN = {
        'name': 'Degen',
        'min_liquidity': 8000,  # Lowered from 15k
        'max_liquidity': float('inf'),
        'min_fdv': 50000,  # Lowered from 100k
        'max_fdv': float('inf'),
        'min_pair_age_hours': 1,
        'max_pair_age_hours': 72,
        'min_txns_1h': 20,  # Lowered from 100
        'max_txns_1h': float('inf'),
    }
    
    MID_CAPS = {
        'name': 'Mid-Caps',
        'min_liquidity': 50000,  # Lowered from 100k
        'max_liquidity': float('inf'),
        'min_fdv': 500000,  # Lowered from 1M
        'max_fdv': float('inf'),
        'min_volume_24h': 100000,  # Lowered from 1.2M
        'max_volume_24h': float('inf'),
        'min_txns_24h': 20,  # Lowered from 30
        'max_txns_24h': float('inf'),
    }
    
    OLD_MID_CAPS = {
        'name': 'Old Mid-Caps',
        'min_liquidity': 50000,  # Lowered from 100k
        'max_liquidity': float('inf'),
        'min_fdv': 100000,  # Lowered from 200k
        'max_fdv': 100000000,
        'min_pair_age_hours': 720,
        'max_pair_age_hours': 2800,
        'min_volume_24h': 50000,  # Lowered from 200k
        'max_volume_24h': float('inf'),
        'min_txns_24h': 100,  # Lowered from 2000
        'max_txns_24h': float('inf'),
    }
    
    LARGER_MID_CAPS = {
        'name': 'Larger Mid-Caps',
        'min_liquidity': 100000,  # Lowered from 200k
        'max_liquidity': float('inf'),
        'min_mcap': 500000,  # Lowered from 1M
        'max_mcap': float('inf'),
        'min_volume_6h': 50000,  # Lowered from 150k
        'max_volume_6h': float('inf'),
    }


async def fetch_solana_tokens(session, limit=50):
    """Fetch latest Solana tokens from Dexscreener"""
    try:
        url = f"{SEARCH_API}?q=solana"
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                # Filter for Solana chain only
                pairs = data.get('pairs', [])
                solana_pairs = [p for p in pairs if p.get('chainId') == 'solana']
                return solana_pairs[:limit]
    except Exception as e:
        print(f"Error fetching tokens: {e}")
    return []


def calculate_pair_age_hours(pair_created_at):
    """Calculate pair age in hours"""
    try:
        created_time = datetime.fromtimestamp(pair_created_at / 1000)
        now = datetime.now()
        age_hours = (now - created_time).total_seconds() / 3600
        return age_hours
    except:
        return None


def matches_filter(pair, filter_config):
    """Check if a pair matches the filter criteria"""
    try:
        # Get liquidity
        liquidity = float(pair.get('liquidity', {}).get('usd', 0))
        if liquidity < filter_config['min_liquidity'] or liquidity > filter_config.get('max_liquidity', float('inf')):
            return False
        
        # Get FDV (Fully Diluted Valuation)
        fdv = float(pair.get('fdv', 0))
        if 'min_fdv' in filter_config:
            if fdv < filter_config['min_fdv'] or fdv > filter_config.get('max_fdv', float('inf')):
                return False
        
        # Get Market Cap
        mcap = float(pair.get('marketCap', 0))
        if 'min_mcap' in filter_config:
            if mcap < filter_config['min_mcap'] or mcap > filter_config.get('max_mcap', float('inf')):
                return False
        
        # Check pair age
        if 'min_pair_age_hours' in filter_config:
            pair_created = pair.get('pairCreatedAt')
            if pair_created:
                age_hours = calculate_pair_age_hours(pair_created)
                if age_hours is None:
                    return False
                if age_hours < filter_config['min_pair_age_hours'] or age_hours > filter_config['max_pair_age_hours']:
                    return False
        
        # Check 1H transactions
        if 'min_txns_1h' in filter_config:
            txns_1h_buys = pair.get('txns', {}).get('h1', {}).get('buys', 0)
            txns_1h_sells = pair.get('txns', {}).get('h1', {}).get('sells', 0)
            txns_1h = txns_1h_buys + txns_1h_sells
            if txns_1h < filter_config['min_txns_1h'] or txns_1h > filter_config.get('max_txns_1h', float('inf')):
                return False
        
        # Check 24H transactions
        if 'min_txns_24h' in filter_config:
            txns_24h_buys = pair.get('txns', {}).get('h24', {}).get('buys', 0)
            txns_24h_sells = pair.get('txns', {}).get('h24', {}).get('sells', 0)
            txns_24h = txns_24h_buys + txns_24h_sells
            if txns_24h < filter_config['min_txns_24h'] or txns_24h > filter_config.get('max_txns_24h', float('inf')):
                return False
        
        # Check 24H volume
        if 'min_volume_24h' in filter_config:
            volume_24h = float(pair.get('volume', {}).get('h24', 0))
            if volume_24h < filter_config['min_volume_24h'] or volume_24h > filter_config.get('max_volume_24h', float('inf')):
                return False
        
        # Check 6H volume
        if 'min_volume_6h' in filter_config:
            volume_6h = float(pair.get('volume', {}).get('h6', 0))
            if volume_6h < filter_config['min_volume_6h'] or volume_6h > filter_config.get('max_volume_6h', float('inf')):
                return False
        
        return True
    except Exception as e:
        print(f"Error matching filter: {e}")
        return False


def format_token_message(pair):
    """Format token data into a readable message"""
    try:
        base_token = pair.get('baseToken', {})
        quote_token = pair.get('quoteToken', {})
        
        name = base_token.get('name', 'Unknown')
        symbol = base_token.get('symbol', 'Unknown')
        price_usd = float(pair.get('priceUsd', 0))
        
        liquidity = float(pair.get('liquidity', {}).get('usd', 0))
        fdv = float(pair.get('fdv', 0))
        mcap = float(pair.get('marketCap', 0))
        
        volume_24h = float(pair.get('volume', {}).get('h24', 0))
        
        txns_1h = pair.get('txns', {}).get('h1', {})
        txns_1h_total = txns_1h.get('buys', 0) + txns_1h.get('sells', 0)
        
        txns_24h = pair.get('txns', {}).get('h24', {})
        txns_24h_total = txns_24h.get('buys', 0) + txns_24h.get('sells', 0)
        
        pair_created = pair.get('pairCreatedAt')
        age_hours = calculate_pair_age_hours(pair_created) if pair_created else None
        
        price_change_24h = pair.get('priceChange', {}).get('h24', 0)
        
        dex_url = pair.get('url', '#')
        pair_address = pair.get('pairAddress', 'N/A')
        
        message = f"🪙 **{name}** (${symbol})\n\n"
        message += f"💵 Price: ${price_usd:.8f}\n"
        message += f"💧 Liquidity: ${liquidity:,.0f}\n"
        message += f"📊 FDV: ${fdv:,.0f}\n"
        message += f"🏦 MCap: ${mcap:,.0f}\n"
        message += f"📈 24h Volume: ${volume_24h:,.0f}\n"
        message += f"🔄 24h Change: {price_change_24h:.2f}%\n\n"
        
        message += f"⏱️ Pair Age: {age_hours:.1f} hours\n" if age_hours else ""
        message += f"🔥 1H Txns: {txns_1h_total}\n"
        message += f"🔥 24H Txns: {txns_24h_total}\n\n"
        
        message += f"🔗 [View on Dexscreener]({dex_url})\n"
        message += f"📍 Pair: `{pair_address}`"
        
        return message
    except Exception as e:
        print(f"Error formatting message: {e}")
        return "Error formatting token data"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    keyboard = [
        [
            InlineKeyboardButton("Very Degen 🔥", callback_data='very_degen'),
            InlineKeyboardButton("Degen 💎", callback_data='degen'),
        ],
        [
            InlineKeyboardButton("Mid-Caps 📈", callback_data='mid_caps'),
            InlineKeyboardButton("Old Mid-Caps 🏛️", callback_data='old_mid_caps'),
        ],
        [
            InlineKeyboardButton("Larger Mid-Caps 💰", callback_data='larger_mid_caps'),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔍 **Solana Gem Finder Bot**\n\n"
        "Select a filter to find hidden gems on Solana:\n\n"
        "🔥 Very Degen - Fresh pairs, 0-48h old\n"
        "💎 Degen - Young pairs, 1-72h old\n"
        "📈 Mid-Caps - Established tokens\n"
        "🏛️ Old Mid-Caps - Mature projects\n"
        "💰 Larger Mid-Caps - Higher liquidity",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks"""
    query = update.callback_query
    await query.answer()
    
    filter_map = {
        'very_degen': TokenFilter.VERY_DEGEN,
        'degen': TokenFilter.DEGEN,
        'mid_caps': TokenFilter.MID_CAPS,
        'old_mid_caps': TokenFilter.OLD_MID_CAPS,
        'larger_mid_caps': TokenFilter.LARGER_MID_CAPS,
    }
    
    filter_config = filter_map.get(query.data)
    if not filter_config:
        await query.message.reply_text("Invalid filter selected.")
        return
    
    await query.message.reply_text(
        f"🔍 Searching for **{filter_config['name']}** tokens...\n"
        "This may take a few moments.",
        parse_mode='Markdown'
    )
    
    # Fetch and filter tokens
    async with aiohttp.ClientSession() as session:
        pairs = await fetch_solana_tokens(session, limit=100)
        
        matching_pairs = []
        for pair in pairs:
            if matches_filter(pair, filter_config):
                matching_pairs.append(pair)
                if len(matching_pairs) >= 10:  # Limit to 10 results
                    break
        
        if matching_pairs:
            await query.message.reply_text(
                f"✅ Found {len(matching_pairs)} tokens matching **{filter_config['name']}** criteria:",
                parse_mode='Markdown'
            )
            
            for pair in matching_pairs:
                message = format_token_message(pair)
                await query.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
                await asyncio.sleep(0.5)  # Avoid rate limiting
        else:
            await query.message.reply_text(
                f"❌ No tokens found matching **{filter_config['name']}** criteria.\n"
                "Try again later or select a different filter.",
                parse_mode='Markdown'
            )


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manual scan command for groups"""
    keyboard = [
        [
            InlineKeyboardButton("Very Degen 🔥", callback_data='very_degen'),
            InlineKeyboardButton("Degen 💎", callback_data='degen'),
        ],
        [
            InlineKeyboardButton("Mid-Caps 📈", callback_data='mid_caps'),
            InlineKeyboardButton("Old Mid-Caps 🏛️", callback_data='old_mid_caps'),
        ],
        [
            InlineKeyboardButton("Larger Mid-Caps 💰", callback_data='larger_mid_caps'),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔍 **Select a filter to scan Solana tokens:**",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def auto_scan(context: ContextTypes.DEFAULT_TYPE):
    """Automatic scan job that runs periodically"""
    try:
        # Get the group chat ID from environment or use default
        group_chat_id = os.environ.get('TELEGRAM_GROUP_ID', '3229530404')
        
        # Convert to negative ID for groups (Telegram API requirement)
        if not group_chat_id.startswith('-'):
            group_chat_id = f'-{group_chat_id}'
        
        # Scan with Very Degen filter (most aggressive for new gems)
        async with aiohttp.ClientSession() as session:
            pairs = await fetch_solana_tokens(session, limit=100)
            
            matching_pairs = []
            for pair in pairs:
                if matches_filter(pair, TokenFilter.VERY_DEGEN):
                    matching_pairs.append(pair)
                    if len(matching_pairs) >= 5:  # Limit to top 5 gems
                        break
            
            if matching_pairs:
                await context.bot.send_message(
                    chat_id=group_chat_id,
                    text=f"🔥 **Auto Scan Alert!**\n\nFound {len(matching_pairs)} Very Degen tokens:",
                    parse_mode='Markdown'
                )
                
                for pair in matching_pairs:
                    message = format_token_message(pair)
                    await context.bot.send_message(
                        chat_id=group_chat_id,
                        text=message,
                        parse_mode='Markdown',
                        disable_web_page_preview=True
                    )
                    await asyncio.sleep(1)
    except Exception as e:
        print(f"Error in auto_scan: {e}")


def main():
    """Main function to run the bot"""
    # Get bot token from environment variable
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    
    if not bot_token:
        print("❌ Error: TELEGRAM_BOT_TOKEN environment variable not set!")
        print("\nTo set it:")
        print("  export TELEGRAM_BOT_TOKEN='your_token_here'")
        return
    
    print(f"🤖 Bot Token: {bot_token[:10]}...{bot_token[-5:]}")
    
    # Get group ID
    group_id = os.environ.get('TELEGRAM_GROUP_ID', '3229530404')
    print(f"📢 Group ID: {group_id}")
    
    # Create application
    application = Application.builder().token(bot_token).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("scan", scan_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add auto-scan job (runs every 30 minutes)
    job_queue = application.job_queue
    job_queue.run_repeating(auto_scan, interval=1800, first=10)  # 1800 seconds = 30 minutes
    
    # Start the bot
    print("🤖 Bot is starting...")
    print("🔄 Auto-scan enabled: Every 30 minutes")
    print("💎 Ready to find Solana gems!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
