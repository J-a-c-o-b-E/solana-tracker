import os
import asyncio
import aiohttp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime, timedelta

# Dexscreener API endpoints
DEXSCREENER_PAIRS_API = "https://api.dexscreener.com/latest/dex/pairs/solana/"
DEXSCREENER_LATEST_API = "https://api.dexscreener.com/latest/dex/tokens/"

class TokenFilter:
    """Define filter criteria for different token categories"""
    
    VERY_DEGEN = {
        'name': 'Very Degen',
        'min_liquidity': 10000,
        'max_liquidity': 14900,
        'min_fdv': 100000,
        'max_fdv': 1000000,
        'min_pair_age_hours': 0,
        'max_pair_age_hours': 48,
        'min_txns_1h': 30,
        'max_txns_1h': 99,
    }
    
    DEGEN = {
        'name': 'Degen',
        'min_liquidity': 15000,
        'max_liquidity': 99900,
        'min_fdv': 100000,
        'max_fdv': 1000000,
        'min_pair_age_hours': 1,
        'max_pair_age_hours': 72,
        'min_txns_1h': 100,
        'max_txns_1h': 1000,
    }
    
    MID_CAPS = {
        'name': 'Mid-Caps',
        'min_liquidity': 100000,
        'max_liquidity': 199900,
        'min_fdv': 1000000,
        'max_fdv': float('inf'),
        'min_volume_24h': 1200000,
        'max_volume_24h': float('inf'),
        'min_txns_24h': 30,
        'max_txns_24h': float('inf'),
    }
    
    OLD_MID_CAPS = {
        'name': 'Old Mid-Caps',
        'min_liquidity': 100000,
        'max_liquidity': 199900,
        'min_fdv': 200000,
        'max_fdv': 100000000,
        'min_pair_age_hours': 720,
        'max_pair_age_hours': 2800,
        'min_volume_24h': 200000,
        'max_volume_24h': float('inf'),
        'min_txns_24h': 2000,
        'max_txns_24h': float('inf'),
    }
    
    LARGER_MID_CAPS = {
        'name': 'Larger Mid-Caps',
        'min_liquidity': 200000,
        'max_liquidity': float('inf'),
        'min_mcap': 1000000,
        'max_mcap': float('inf'),
        'min_volume_6h': 150000,
        'max_volume_6h': float('inf'),
    }


async def fetch_solana_tokens(session, limit=2000):
    """Fetch latest Solana tokens from Dexscreener using multiple endpoints"""
    all_pairs = []
    seen_addresses = set()  # Avoid duplicates
    
    try:
        # Method 1: Search by DEXes
        dexes = ['raydium', 'orca', 'meteora', 'pump', 'jupiter', 'lifinity', 'phoenix', 'openbook']
        
        for dex in dexes:
            try:
                url = f"https://api.dexscreener.com/latest/dex/search?q={dex}"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        pairs = data.get('pairs', [])
                        for pair in pairs:
                            pair_address = pair.get('pairAddress')
                            if (pair.get('chainId') == 'solana' and 
                                pair.get('liquidity', {}).get('usd', 0) > 0 and
                                pair_address and pair_address not in seen_addresses):
                                all_pairs.append(pair)
                                seen_addresses.add(pair_address)
                await asyncio.sleep(0.15)
            except Exception as e:
                print(f"Error fetching from {dex}: {e}")
        
        # Method 2: Search by popular terms and categories
        search_terms = [
            'solana', 'meme', 'coin', 'token', 'new', 'ai', 'dao', 'nft',
            'pepe', 'doge', 'cat', 'dog', 'frog', 'baby', 'moon', 'safe',
            'elon', 'trump', 'chad', 'wojak', 'bonk', 'inu', 'shib'
        ]
        for term in search_terms:
            try:
                url = f"https://api.dexscreener.com/latest/dex/search?q={term}"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        pairs = data.get('pairs', [])
                        for pair in pairs:
                            pair_address = pair.get('pairAddress')
                            if (pair.get('chainId') == 'solana' and 
                                pair.get('liquidity', {}).get('usd', 0) > 0 and
                                pair_address and pair_address not in seen_addresses):
                                all_pairs.append(pair)
                                seen_addresses.add(pair_address)
                await asyncio.sleep(0.15)
            except Exception as e:
                print(f"Error fetching for {term}: {e}")
        
        # Method 3: Alphabet search for maximum coverage
        letters = ['a', 'b', 'c', 'd', 'e', 'sol']
        for letter in letters:
            try:
                url = f"https://api.dexscreener.com/latest/dex/search?q={letter}"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        pairs = data.get('pairs', [])
                        for pair in pairs:
                            pair_address = pair.get('pairAddress')
                            if (pair.get('chainId') == 'solana' and 
                                pair.get('liquidity', {}).get('usd', 0) > 0 and
                                pair_address and pair_address not in seen_addresses):
                                all_pairs.append(pair)
                                seen_addresses.add(pair_address)
                await asyncio.sleep(0.15)
            except:
                pass
        
        # Method 4: Get trending/boosted tokens
        try:
            url = "https://api.dexscreener.com/token-boosts/top/v1"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    for item in data:
                        if isinstance(item, dict):
                            pair_address = item.get('pairAddress')
                            if (item.get('chainId') == 'solana' and
                                pair_address and pair_address not in seen_addresses):
                                all_pairs.append(item)
                                seen_addresses.add(pair_address)
        except:
            pass
                
        print(f"📊 Total unique pairs fetched: {len(all_pairs)}")
        
        if all_pairs:
            # Sort by most recent first (to catch new gems)
            all_pairs.sort(key=lambda x: x.get('pairCreatedAt', 0), reverse=True)
            
            first = all_pairs[0]
            print(f"📝 Sample token: {first.get('baseToken', {}).get('symbol')} - "
                  f"Liq: ${first.get('liquidity', {}).get('usd', 0):,.0f}, "
                  f"FDV: ${first.get('fdv', 0):,.0f}, "
                  f"DEX: {first.get('dexId')}")
            
            # Show age range
            newest_age = calculate_pair_age_hours(all_pairs[0].get('pairCreatedAt'))
            oldest_age = calculate_pair_age_hours(all_pairs[-1].get('pairCreatedAt'))
            if newest_age and oldest_age:
                print(f"📈 Age range: newest={newest_age:.1f}h, oldest={oldest_age:.1f}h")
        else:
            print("⚠️ No Solana pairs found")
        
        return all_pairs[:limit]
        
    except Exception as e:
        print(f"❌ Error fetching tokens: {e}")
        import traceback
        traceback.print_exc()
    
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
        [InlineKeyboardButton("Very Degen 🔥", callback_data='very_degen')],
        [InlineKeyboardButton("Degen 💎", callback_data='degen')],
        [InlineKeyboardButton("Mid-Caps 📈", callback_data='mid_caps')],
        [InlineKeyboardButton("Old Mid-Caps 🏛️", callback_data='old_mid_caps')],
        [InlineKeyboardButton("Larger Mid-Caps 💰", callback_data='larger_mid_caps')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Select a filter:",
        reply_markup=reply_markup
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
    
    # Get or initialize shown tokens set for this user
    user_id = update.effective_user.id
    if 'shown_tokens' not in context.user_data:
        context.user_data['shown_tokens'] = set()
    
    shown_tokens = context.user_data['shown_tokens']
    
    # Fetch and filter tokens
    async with aiohttp.ClientSession() as session:
        pairs = await fetch_solana_tokens(session, limit=2000)
        
        print(f"🔍 Checking {len(pairs)} pairs against {filter_config['name']} filter")
        
        # First try to find perfect matches (excluding already shown)
        perfect_matches = []
        checked_count = 0
        
        for pair in pairs:
            pair_address = pair.get('pairAddress')
            # Skip if already shown to this user
            if pair_address in shown_tokens:
                continue
                
            checked_count += 1
            if matches_filter(pair, filter_config):
                perfect_matches.append(pair)
                print(f"✅ Perfect match found: {pair.get('baseToken', {}).get('symbol')}")
                break  # Stop after finding 1 perfect match
        
        print(f"📊 Checked {checked_count} pairs, found {len(perfect_matches)} perfect matches")
        
        # If no perfect match, find the BEST token that's closest to criteria
        if not perfect_matches:
            print("⚠️ No perfect match, finding best alternative...")
            
            # Score all tokens and pick the best one (excluding already shown)
            scored_pairs = []
            for pair in pairs:
                pair_address = pair.get('pairAddress')
                # Skip if already shown to this user
                if pair_address in shown_tokens:
                    continue
                    
                score = 0
                liquidity = float(pair.get('liquidity', {}).get('usd', 0))
                fdv = float(pair.get('fdv', 0))
                
                # Skip tokens with no data
                if liquidity < 1000:
                    continue
                
                # Score based on how close to target liquidity range
                target_liq_min = filter_config.get('min_liquidity', 0)
                target_liq_max = filter_config.get('max_liquidity', float('inf'))
                
                if target_liq_min <= liquidity <= target_liq_max:
                    score += 100  # Perfect liquidity range
                else:
                    # Calculate distance from range
                    if liquidity < target_liq_min:
                        diff_pct = abs(liquidity - target_liq_min) / target_liq_min
                    else:
                        diff_pct = abs(liquidity - target_liq_max) / target_liq_max
                    score += max(0, 50 - diff_pct * 50)
                
                # Score FDV if applicable
                if 'min_fdv' in filter_config:
                    target_fdv_min = filter_config.get('min_fdv', 0)
                    target_fdv_max = filter_config.get('max_fdv', float('inf'))
                    if target_fdv_min <= fdv <= target_fdv_max:
                        score += 50
                
                # Score age if applicable
                if 'min_pair_age_hours' in filter_config:
                    pair_created = pair.get('pairCreatedAt')
                    if pair_created:
                        age_hours = calculate_pair_age_hours(pair_created)
                        if age_hours:
                            target_age_min = filter_config.get('min_pair_age_hours', 0)
                            target_age_max = filter_config.get('max_pair_age_hours', float('inf'))
                            if target_age_min <= age_hours <= target_age_max:
                                score += 50
                
                # Score transactions if applicable
                if 'min_txns_1h' in filter_config:
                    txns_1h = pair.get('txns', {}).get('h1', {})
                    txns_total = txns_1h.get('buys', 0) + txns_1h.get('sells', 0)
                    target_min = filter_config.get('min_txns_1h', 0)
                    if txns_total >= target_min:
                        score += 30
                
                if score > 0:
                    scored_pairs.append((score, pair))
            
            # Sort by score and pick the best
            scored_pairs.sort(reverse=True, key=lambda x: x[0])
            
            if scored_pairs:
                best_score, best_pair = scored_pairs[0]
                perfect_matches = [best_pair]
                print(f"✅ Best alternative found (score: {best_score:.0f}): {best_pair.get('baseToken', {}).get('symbol')}")
            else:
                # Last resort: just pick the first token with good liquidity (not already shown)
                for pair in pairs:
                    pair_address = pair.get('pairAddress')
                    if pair_address not in shown_tokens and float(pair.get('liquidity', {}).get('usd', 0)) > 5000:
                        perfect_matches = [pair]
                        print(f"✅ Fallback token: {pair.get('baseToken', {}).get('symbol')}")
                        break
        
        # Send the token (we WILL have one at this point)
        if perfect_matches:
            pair = perfect_matches[0]
            pair_address = pair.get('pairAddress')
            
            # Mark this token as shown to this user
            shown_tokens.add(pair_address)
            
            # Keep only last 50 shown tokens to avoid memory issues
            if len(shown_tokens) > 50:
                shown_tokens.pop()
            
            message = format_token_message(pair)
            await query.message.reply_text(message, parse_mode='Markdown', disable_web_page_preview=True)
        else:
            # This should never happen now, but just in case
            await query.message.reply_text(
                f"❌ Unable to find any tokens. Please try again in a moment.",
                parse_mode='Markdown'
            )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle any text message - just show the buttons again"""
    keyboard = [
        [InlineKeyboardButton("Very Degen 🔥", callback_data='very_degen')],
        [InlineKeyboardButton("Degen 💎", callback_data='degen')],
        [InlineKeyboardButton("Mid-Caps 📈", callback_data='mid_caps')],
        [InlineKeyboardButton("Old Mid-Caps 🏛️", callback_data='old_mid_caps')],
        [InlineKeyboardButton("Larger Mid-Caps 💰", callback_data='larger_mid_caps')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Select a filter:",
        reply_markup=reply_markup
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
            pairs = await fetch_solana_tokens(session, limit=2000)
            
            matching_pairs = []
            for pair in pairs:
                if matches_filter(pair, TokenFilter.VERY_DEGEN):
                    matching_pairs.append(pair)
                    break  # Only get 1 token
            
            if matching_pairs:
                pair = matching_pairs[0]
                message = format_token_message(pair)
                await context.bot.send_message(
                    chat_id=group_chat_id,
                    text=f"🔥 **Auto Scan Alert - Very Degen Gem Found!**\n\n{message}",
                    parse_mode='Markdown',
                    disable_web_page_preview=True
                )
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
    
    # Handle all other text messages - just show buttons
    from telegram.ext import MessageHandler, filters
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    
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
