import os
import asyncio
import aiohttp
import sqlite3
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Dexscreener API
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/search?q="

# Database setup
DB_FILE = 'call_history.db'

def init_database():
    """Initialize SQLite database for persistent call tracking"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_address TEXT NOT NULL,
            pair_address TEXT NOT NULL,
            symbol TEXT NOT NULL,
            name TEXT NOT NULL,
            initial_price REAL NOT NULL,
            peak_price REAL NOT NULL,
            call_time TIMESTAMP NOT NULL,
            tier TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create index for faster lookups
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_pair_address ON calls(pair_address)
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")


def was_recently_called(pair_address, hours=24):
    """Check if token was called in last X hours"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT COUNT(*) FROM calls
        WHERE pair_address = ? 
        AND datetime(call_time) > datetime('now', '-' || ? || ' hours')
    ''', (pair_address, hours))
    
    count = cursor.fetchone()[0]
    conn.close()
    
    return count > 0


def save_call(token_address, pair_address, symbol, name, initial_price, tier):
    """Save a new call to database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO calls (token_address, pair_address, symbol, name, initial_price, peak_price, call_time, tier)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (token_address, pair_address, symbol, name, initial_price, initial_price, datetime.now(), tier))
    
    conn.commit()
    conn.close()


def update_peak_price(pair_address, new_peak):
    """Update peak price if higher than current peak"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE calls 
        SET peak_price = ?
        WHERE pair_address = ? AND peak_price < ?
    ''', (new_peak, pair_address, new_peak))
    
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    
    return affected > 0


def get_all_calls():
    """Get all calls from database"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT token_address, pair_address, symbol, name, initial_price, peak_price, call_time, tier
        FROM calls
        ORDER BY call_time DESC
    ''')
    
    rows = cursor.fetchall()
    conn.close()
    
    calls = []
    for row in rows:
        calls.append({
            'token_address': row[0],
            'pair_address': row[1],
            'symbol': row[2],
            'name': row[3],
            'initial_price': row[4],
            'peak_price': row[5],
            'call_time': datetime.fromisoformat(row[6]) if isinstance(row[6], str) else row[6],
            'tier': row[7],
        })
    
    return calls


def get_recent_calls(limit=20):
    """Get most recent calls for peak tracking"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT pair_address, symbol, peak_price
        FROM calls
        ORDER BY call_time DESC
        LIMIT ?
    ''', (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return [{'pair_address': r[0], 'symbol': r[1], 'peak_price': r[2]} for r in rows]

class SmartMoneyTracker:
    """Tracks volume spikes and buying pressure on Solana tokens"""
    
    # Track tokens we've already alerted on (in-memory for duplicate prevention)
    alerted_tokens = set()
    
    # Signal strength tiers based on your images
    TIERS = {
        'FIRST_CALL': {
            'name': '🔔 FIRST CALL',
            'recent_buys': 20,
            'volume': 3000,
            'avg_buy': 50,
        },
        'MEDIUM': {
            'name': '💎 MEDIUM',
            'recent_buys': 30,
            'volume': 6000,
            'avg_buy': 75,
        },
        'STRONG': {
            'name': '💎 STRONG',
            'recent_buys': 45,
            'volume': 10000,
            'avg_buy': 100,
        },
        'VERY_STRONG': {
            'name': '💎 VERY STRONG 💎',
            'recent_buys': 80,
            'volume': 20000,
            'avg_buy': 0,  # No minimum
        },
    }
    
    @staticmethod
    def calculate_metrics(pair):
        """Calculate recent buys, volume, and average buy from pair data
        
        Uses 5min data scaled to approximate 2-3 min window.
        Also validates with 1h data to ensure real activity.
        """
        try:
            # Get transaction data
            txns = pair.get('txns', {})
            m5 = txns.get('m5', {})  # 5 minute data
            h1 = txns.get('h1', {})  # 1 hour data
            
            # Get 5min buys
            buys_5min = m5.get('buys', 0)
            
            # Validate with 1h data - token must have sustained activity
            buys_1h = h1.get('buys', 0)
            if buys_1h < 5:  # Very minimal threshold - just checking for activity
                return None
            
            # Calculate estimated 2-3 min values
            # Use 2.5 min as target (halfway between 2-3)
            # Scale factor: 2.5/5 = 0.5
            recent_buys = int(buys_5min * 0.5)
            
            # Get volume data
            volume_5min = float(pair.get('volume', {}).get('m5', 0))
            
            # Scale to 2-3 min estimate
            volume_2_3min = volume_5min * 0.5
            
            # Calculate average buy size
            avg_buy = volume_2_3min / recent_buys if recent_buys > 0 else 0
            
            # Additional validation - check if numbers make sense
            if recent_buys < 1 or volume_2_3min < 50:
                return None
            
            return {
                'recent_buys': recent_buys,
                'volume': volume_2_3min,
                'avg_buy': avg_buy,
                'buys_5min': buys_5min,
                'buys_1h': buys_1h,
                'volume_5min': volume_5min,
            }
        except Exception as e:
            print(f"Error calculating metrics: {e}")
            return None
    
    @staticmethod
    def determine_tier(metrics):
        """Determine signal tier based on metrics"""
        if not metrics:
            return None
        
        recent_buys = metrics['recent_buys']
        volume = metrics['volume']
        avg_buy = metrics['avg_buy']
        
        # Check VERY_STRONG first (either 80 buys OR $20k volume)
        if recent_buys >= 80 or volume >= 20000:
            return 'VERY_STRONG'
        
        # Check STRONG (ALL conditions must be met)
        if recent_buys >= 45 and volume >= 10000 and avg_buy >= 100:
            return 'STRONG'
        
        # Check MEDIUM (ALL conditions must be met)
        if recent_buys >= 30 and volume >= 6000 and avg_buy >= 75:
            return 'MEDIUM'
        
        # Check FIRST_CALL (ALL conditions must be met)
        if recent_buys >= 20 and volume >= 3000 and avg_buy >= 50:
            return 'FIRST_CALL'
        
        return None
    
    @staticmethod
    async def perform_safety_checks(pair):
        """Perform basic safety checks on the token"""
        checks = {
            'liquidity_ok': False,
            'age_ok': False,
            'holder_concentration': 'Unknown',
        }
        
        try:
            # Check liquidity (should be > $5k)
            liquidity = float(pair.get('liquidity', {}).get('usd', 0))
            checks['liquidity_ok'] = liquidity > 5000
            
            # Check pair age (accept tokens deployed in last 240 hours = 10 days)
            pair_created = pair.get('pairCreatedAt')
            if pair_created:
                age_hours = (datetime.now().timestamp() - pair_created / 1000) / 3600
                checks['age_ok'] = age_hours < 240
            
            return checks
        except Exception as e:
            print(f"Error in safety checks: {e}")
            return checks


async def update_peak_prices():
    """Update peak prices for recent calls - runs every scan cycle"""
    recent_calls = get_recent_calls(limit=20)  # Only track last 20 for performance
    
    if not recent_calls:
        return
    
    try:
        async with aiohttp.ClientSession() as session:
            for call in recent_calls:
                pair_address = call.get('pair_address')
                if not pair_address:
                    continue
                
                try:
                    # Fetch current price
                    url = f"https://api.dexscreener.com/latest/dex/pairs/solana/{pair_address}"
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            if data and 'pair' in data:
                                current_price = float(data['pair'].get('priceUsd', 0))
                                
                                # Update peak if current is higher
                                if current_price > call.get('peak_price', 0):
                                    if update_peak_price(pair_address, current_price):
                                        print(f"  🚀 New peak for ${call['symbol']}: ${current_price:.10f}")
                    
                    await asyncio.sleep(0.1)  # Quick rate limiting
                    
                except Exception as e:
                    print(f"Error updating peak for {call.get('symbol')}: {e}")
    
    except Exception as e:
        print(f"Error in update_peak_prices: {e}")


async def scan_for_signals(context: ContextTypes.DEFAULT_TYPE):
    """Scan Solana tokens for volume spike signals - find ONE best signal per cycle"""
    try:
        # First, update peak prices for previous calls (runs in background)
        asyncio.create_task(update_peak_prices())
        
        # Get user chat IDs from context (users who have started the bot)
        if 'active_chats' not in context.bot_data:
            print("⚠️ No active_chats in bot_data")
            return
        
        active_chats = context.bot_data['active_chats']
        if not active_chats:
            print("⚠️ No active chats subscribed")
            return
        
        print(f"\n🔍 Starting scan cycle at {datetime.now().strftime('%H:%M:%S')}")
        
        # Collect all valid signals first
        all_signals = []
        tokens_checked = 0
        
        # Search for recent Solana tokens
        search_terms = ['pump', 'raydium', 'orca', 'meteora']
        
        async with aiohttp.ClientSession() as session:
            for term in search_terms:
                try:
                    url = f"{DEXSCREENER_API}{term}"
                    async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            pairs = data.get('pairs', [])
                            
                            # Filter for Solana
                            solana_pairs = [p for p in pairs if p.get('chainId') == 'solana']
                            print(f"  📊 Found {len(solana_pairs)} Solana pairs for '{term}'")
                            
                            for pair in solana_pairs[:20]:  # Check top 20
                                tokens_checked += 1
                                pair_address = pair.get('pairAddress')
                                symbol = pair.get('baseToken', {}).get('symbol', 'Unknown')
                                
                                # Skip if already alerted
                                if pair_address in SmartMoneyTracker.alerted_tokens:
                                    print(f"  ⏭️ Skipping ${symbol} - already alerted")
                                    continue
                                
                                # Calculate metrics
                                metrics = SmartMoneyTracker.calculate_metrics(pair)
                                if not metrics:
                                    print(f"  ❌ ${symbol} - No valid metrics")
                                    continue
                                
                                # Log metrics for debugging
                                print(f"  📈 ${symbol}: {metrics['recent_buys']} buys, ${metrics['volume']:,.0f} vol, ${metrics['avg_buy']:.2f} avg")
                                
                                # Determine tier
                                tier = SmartMoneyTracker.determine_tier(metrics)
                                if not tier:
                                    print(f"  ⏭️ ${symbol} - Doesn't meet any tier requirements")
                                    continue
                                
                                print(f"  ✅ ${symbol} - Meets {tier} tier!")
                                
                                # Perform safety checks
                                safety = await SmartMoneyTracker.perform_safety_checks(pair)
                                
                                # Log safety checks
                                liquidity = float(pair.get('liquidity', {}).get('usd', 0))
                                pair_created = pair.get('pairCreatedAt')
                                if pair_created:
                                    age_hours = (datetime.now().timestamp() - pair_created / 1000) / 3600
                                    print(f"     ⏰ Age: {age_hours:.1f}h - {'PASS' if safety['age_ok'] else 'FAIL (>10 days)'}")
                                print(f"     💧 Liquidity: ${liquidity:,.0f} - {'PASS' if safety['liquidity_ok'] else 'FAIL'}")
                                
                                # Only include if passes BOTH liquidity AND age checks
                                if not safety['liquidity_ok']:
                                    print(f"     ❌ Skipping - Low liquidity")
                                    continue
                                
                                if not safety['age_ok']:
                                    print(f"     ❌ Skipping - Too old (>10 days)")
                                    continue
                                
                                # Add to valid signals with tier priority
                                tier_priority = {
                                    'VERY_STRONG': 4,
                                    'STRONG': 3,
                                    'MEDIUM': 2,
                                    'FIRST_CALL': 1,
                                }
                                
                                all_signals.append({
                                    'pair': pair,
                                    'tier': tier,
                                    'metrics': metrics,
                                    'safety': safety,
                                    'priority': tier_priority.get(tier, 0),
                                    'volume': metrics['volume'],
                                })
                
                except Exception as e:
                    print(f"❌ Error scanning {term}: {e}")
                    import traceback
                    traceback.print_exc()
                
                await asyncio.sleep(0.2)  # Rate limiting
        
        print(f"\n📊 Scan complete: Checked {tokens_checked} tokens, found {len(all_signals)} valid signals")
        
        # Sort by priority (tier) then by volume
        all_signals.sort(key=lambda x: (x['priority'], x['volume']), reverse=True)
        
        # Send ONLY the best signal (if any)
        if all_signals:
            best_signal = all_signals[0]
            pair = best_signal['pair']
            tier = best_signal['tier']
            metrics = best_signal['metrics']
            safety = best_signal['safety']
            pair_address = pair.get('pairAddress')
            
            # Mark as alerted
            SmartMoneyTracker.alerted_tokens.add(pair_address)
            
            # Optional: Skip if token was called in last 24h (uncomment to enable)
            # if was_recently_called(pair_address, hours=24):
            #     print(f"⏭️ Skipping ${symbol} - already called in last 24h")
            #     continue
            
            # Save call to database
            symbol = best_signal['pair'].get('baseToken', {}).get('symbol')
            name = best_signal['pair'].get('baseToken', {}).get('name')
            token_address = best_signal['pair'].get('baseToken', {}).get('address')
            initial_price = float(best_signal['pair'].get('priceUsd', 0))
            
            save_call(token_address, pair_address, symbol, name, initial_price, tier)
            print(f"💾 Call saved to database: ${symbol}")
            
            # Keep only last 100 tokens in memory for duplicate prevention
            if len(SmartMoneyTracker.alerted_tokens) > 100:
                # Convert to list, remove first, convert back
                temp = list(SmartMoneyTracker.alerted_tokens)
                temp.pop(0)
                SmartMoneyTracker.alerted_tokens = set(temp)
            
            # Format message
            message = format_signal_alert(pair, tier, metrics, safety)
            
            # Send to all active chats
            for chat_id in active_chats:
                try:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=message,
                        parse_mode='HTML',
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    print(f"❌ Error sending to chat {chat_id}: {e}")
            
            symbol = pair.get('baseToken', {}).get('symbol', 'Unknown')
            print(f"✅ Alert sent: {tier} - ${symbol} (Vol: ${metrics['volume']:,.0f})")
        else:
            print(f"⏭️ No valid signals found this cycle - skipping")
    
    except Exception as e:
        print(f"❌ Error in scan_for_signals: {e}")
        import traceback
        traceback.print_exc()


def format_signal_alert(pair, tier, metrics, safety):
    """Format the signal alert message"""
    tier_config = SmartMoneyTracker.TIERS[tier]
    tier_name = tier_config['name']
    
    base_token = pair.get('baseToken', {})
    name = base_token.get('name', 'Unknown')
    symbol = base_token.get('symbol', 'Unknown')
    
    # Get pair data
    liquidity = float(pair.get('liquidity', {}).get('usd', 0))
    mcap = float(pair.get('marketCap', 0))
    price = float(pair.get('priceUsd', 0))
    
    # Get transaction data
    txns_5min = pair.get('txns', {}).get('m5', {})
    txns_1h = pair.get('txns', {}).get('h1', {})
    buys_5min = txns_5min.get('buys', 0)
    sells_5min = txns_5min.get('sells', 0)
    
    # Get age
    pair_created = pair.get('pairCreatedAt')
    if pair_created:
        age_minutes = (datetime.now().timestamp() - pair_created / 1000) / 60
        if age_minutes < 60:
            age_str = f"{int(age_minutes)} minutes ago"
        elif age_minutes < 1440:  # Less than 24 hours
            age_hours = age_minutes / 60
            age_str = f"{age_hours:.1f} hours ago"
        else:
            age_days = age_minutes / 1440
            age_str = f"{age_days:.1f} days ago"
    else:
        age_str = "Unknown"
    
    # Determine if Fourmeme/known origin (we don't have this data, so skip)
    # Get quote token
    quote_token = pair.get('quoteToken', {})
    quote_symbol = quote_token.get('symbol', 'USD')
    
    # DEX links
    dex_url = pair.get('url', '#')
    pair_address = pair.get('pairAddress', 'N/A')
    base_address = base_token.get('address', 'N/A')
    
    # Build message
    message = f"<b>{tier_name}</b>\n\n"
    
    # Token name
    message += f"<b>{name} (${symbol})</b>\n\n"
    
    # Recent buys info
    message += f"Recent buys: <b>{metrics['recent_buys']}</b> | "
    message += f"Vol: <b>{metrics['volume']:,.2f} {quote_symbol}</b> | "
    message += f"Average: <b>{metrics['avg_buy']:.2f}</b>\n"
    message += f"FR: <b>{buys_5min}</b> | TR: <b>{buys_5min + sells_5min}</b>\n\n"
    
    # Market cap
    message += f"💰 Market cap: <b>{mcap:,.0f} $</b>\n"
    
    # Links
    message += f"<a href='{dex_url}'>DexScreener</a>\n"
    
    # Contract address
    message += f"CA: <code>{base_address}</code>\n\n"
    
    # Additional info
    message += f"💧 Liquidity: <b>${liquidity:,.0f}</b>\n"
    message += f"💵 Price: <b>${price:.10f}</b>\n\n"
    
    # Deployed time
    message += f"⏰ Token deployed: <b>{age_str}</b>"
    
    return message


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - registers user to receive alerts"""
    chat_id = update.effective_chat.id
    
    # Initialize active chats set if not exists
    if 'active_chats' not in context.bot_data:
        context.bot_data['active_chats'] = set()
    
    # Add this chat to active chats
    context.bot_data['active_chats'].add(chat_id)
    
    await update.message.reply_text(
        "🤖 <b>Smart Money Tracker Bot</b>\n\n"
        "✅ You're now subscribed to real-time alerts!\n\n"
        "I automatically scan for volume spikes and smart money activity on Solana.\n\n"
        "<b>Signal Tiers:</b>\n"
        "🔔 First Call - 20+ buys, $3K+ volume\n"
        "💎 Medium - 30+ buys, $6K+ volume\n"
        "💎 Strong - 45+ buys, $10K+ volume\n"
        "💎 Very Strong - 80+ buys OR $20K+ volume\n\n"
        "Scanning every 15 seconds...\n\n"
        "<b>Commands:</b>\n"
        "/stats - View top 25 performers\n"
        "/export - Download database file\n"
        "/stop - Unsubscribe from alerts",
        parse_mode='HTML'
    )
    
    print(f"✅ Chat {chat_id} subscribed to alerts")


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop command - unsubscribes user from alerts"""
    chat_id = update.effective_chat.id
    
    if 'active_chats' in context.bot_data:
        context.bot_data['active_chats'].discard(chat_id)
    
    await update.message.reply_text(
        "🛑 <b>Alerts Stopped</b>\n\n"
        "You've been unsubscribed from alerts.\n\n"
        "Use /start to subscribe again.",
        parse_mode='HTML'
    )
    
    print(f"❌ Chat {chat_id} unsubscribed from alerts")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stats command - shows ALL call performance from database"""
    
    # Delete previous stats message if exists
    if 'last_stats_message' in context.user_data:
        try:
            await context.user_data['last_stats_message'].delete()
        except:
            pass  # Message might already be deleted
    
    loading_msg = await update.message.reply_text("📊 Loading call history from database...", parse_mode='HTML')
    
    all_calls = get_all_calls()
    
    if not all_calls:
        await loading_msg.edit_text(
            "📊 <b>No Calls Yet</b>\n\n"
            "No calls have been made yet. Wait for the bot to detect signals!",
            parse_mode='HTML'
        )
        context.user_data['last_stats_message'] = loading_msg
        return
    
    # Calculate gains using peak prices
    results = []
    
    for call in all_calls:
        initial_price = call.get('initial_price', 0)
        peak_price = call.get('peak_price', 0)
        
        if peak_price > 0 and initial_price > 0:
            # Calculate MAX % gain (using peak)
            max_gain_pct = ((peak_price - initial_price) / initial_price) * 100
            
            results.append({
                'symbol': call['symbol'],
                'name': call['name'],
                'tier': call['tier'],
                'initial_price': initial_price,
                'peak_price': peak_price,
                'max_gain_pct': max_gain_pct,
                'call_time': call['call_time'],
            })
    
    if not results:
        await loading_msg.edit_text(
            "❌ <b>No Valid Data</b>\n\n"
            "No price data available for tracked calls.",
            parse_mode='HTML'
        )
        context.user_data['last_stats_message'] = loading_msg
        return
    
    # Sort by highest gain
    results.sort(key=lambda x: x['max_gain_pct'], reverse=True)
    
    # Calculate statistics
    avg_max_gain = sum(r['max_gain_pct'] for r in results) / len(results) if results else 0
    profitable = sum(1 for r in results if r['max_gain_pct'] > 0)
    win_rate = (profitable / len(results) * 100) if results else 0
    
    # Find best call
    best_call = results[0] if results else None
    
    # Build message
    message = "<b>📊 ALL-TIME CALL PERFORMANCE</b>\n\n"
    message += f"<b>Total Calls:</b> {len(results)}\n"
    message += f"<b>Win Rate:</b> {win_rate:.1f}% ({profitable}/{len(results)})\n"
    message += f"<b>Average Max Gain:</b> {avg_max_gain:+.2f}%\n"
    
    if best_call:
        message += f"<b>Best Call:</b> ${best_call['symbol']} ({best_call['max_gain_pct']:+.1f}%)\n"
    
    message += f"\n<b>Top 25 Performers:</b>\n\n"
    
    # Show top 25
    for i, result in enumerate(results[:25], 1):
        elapsed = datetime.now() - result['call_time']
        hours = elapsed.total_seconds() / 3600
        
        if hours < 24:
            time_str = f"{hours:.1f}h ago"
        else:
            days = hours / 24
            time_str = f"{days:.1f}d ago"
        
        emoji = "🟢" if result['max_gain_pct'] > 0 else "🔴"
        
        message += f"{i}. {emoji} <b>{result['symbol']}</b> - {result['tier']}\n"
        message += f"   Max: <b>{result['max_gain_pct']:+.2f}%</b> | {time_str}\n\n"
    
    # Delete loading message and send final stats
    await loading_msg.delete()
    stats_msg = await update.message.reply_text(message, parse_mode='HTML')
    
    # Store this message to delete it next time
    context.user_data['last_stats_message'] = stats_msg


async def performance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check performance of all calls made"""
    await update.message.reply_text(
        "📊 Analyzing call performance...\n"
        "Fetching current prices from Dexscreener...",
        parse_mode='HTML'
    )
    
    if not SmartMoneyTracker.call_history:
        await update.message.reply_text(
            "❌ No calls have been made yet!\n\n"
            "Start the bot with /start to receive signals.",
            parse_mode='HTML'
        )
        return
    
    # Fetch current prices for all tracked calls
    results = []
    
    async with aiohttp.ClientSession() as session:
        for call in SmartMoneyTracker.call_history:
            try:
                token_address = call['token_address']
                
                # Fetch current data from Dexscreener
                url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        pairs = data.get('pairs', [])
                        
                        if pairs:
                            # Get Solana pair
                            solana_pair = next((p for p in pairs if p.get('chainId') == 'solana'), None)
                            
                            if solana_pair:
                                current_price = float(solana_pair.get('priceUsd', 0))
                                initial_price = call['initial_price']
                                
                                if initial_price > 0:
                                    price_change = ((current_price - initial_price) / initial_price) * 100
                                    
                                    # Calculate time since call
                                    time_diff = datetime.now() - call['call_time']
                                    hours = time_diff.total_seconds() / 3600
                                    
                                    results.append({
                                        'symbol': call['symbol'],
                                        'name': call['name'],
                                        'tier': call['tier'],
                                        'price_change': price_change,
                                        'hours_ago': hours,
                                        'initial_price': initial_price,
                                        'current_price': current_price,
                                    })
                
                await asyncio.sleep(0.3)  # Rate limiting
            
            except Exception as e:
                print(f"Error fetching price for {call['symbol']}: {e}")
    
    if not results:
        await update.message.reply_text(
            "❌ Could not fetch current prices for tracked calls.",
            parse_mode='HTML'
        )
        return
    
    # Sort by price change (best to worst)
    results.sort(key=lambda x: x['price_change'], reverse=True)
    
    # Calculate statistics
    total_calls = len(results)
    profitable_calls = len([r for r in results if r['price_change'] > 0])
    avg_gain = sum(r['price_change'] for r in results) / total_calls
    max_gain = max(r['price_change'] for r in results)
    max_loss = min(r['price_change'] for r in results)
    
    # Build message
    message = "<b>📊 CALL PERFORMANCE REPORT</b>\n\n"
    message += f"<b>Statistics:</b>\n"
    message += f"Total Calls: <b>{total_calls}</b>\n"
    message += f"Profitable: <b>{profitable_calls}/{total_calls}</b> ({(profitable_calls/total_calls*100):.1f}%)\n"
    message += f"Avg Change: <b>{avg_gain:+.2f}%</b>\n"
    message += f"Best: <b>{max_gain:+.2f}%</b>\n"
    message += f"Worst: <b>{max_loss:+.2f}%</b>\n\n"
    
    message += "<b>Recent Calls:</b>\n"
    
    # Show top 10 calls
    for i, result in enumerate(results[:10], 1):
        emoji = "🟢" if result['price_change'] > 0 else "🔴"
        message += f"\n{i}. {emoji} <b>{result['symbol']}</b>\n"
        message += f"   {result['tier']}\n"
        message += f"   Change: <b>{result['price_change']:+.2f}%</b>\n"
        message += f"   Called: {result['hours_ago']:.1f}h ago\n"
        message += f"   ${result['initial_price']:.8f} → ${result['current_price']:.8f}\n"
    
    if len(results) > 10:
        message += f"\n<i>... and {len(results) - 10} more calls</i>"
    
    await update.message.reply_text(message, parse_mode='HTML')
    
    print(f"📊 Performance report sent to user")


async def export_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export command - sends database file"""
    try:
        if os.path.exists(DB_FILE):
            await update.message.reply_document(
                document=open(DB_FILE, 'rb'),
                filename='call_history.db',
                caption='📊 <b>Call History Database</b>\n\nOpen with SQLite browser to view all data.',
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text("❌ Database file not found.", parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}", parse_mode='HTML')


def main():
    """Main function"""
    # Initialize database
    init_database()
    
    bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
    
    if not bot_token:
        print("❌ Error: TELEGRAM_BOT_TOKEN environment variable not set!")
        return
    
    print(f"🤖 Bot Token: {bot_token[:10]}...{bot_token[-5:]}")
    
    # Create application
    application = Application.builder().token(bot_token).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("stats", stats))
    application.add_handler(CommandHandler("export", export_db))
    application.add_handler(CommandHandler("performance", performance))
    application.add_handler(CommandHandler("stats", performance))  # Alias
    
    # Add scanning job (every 15 seconds)
    job_queue = application.job_queue
    job_queue.run_repeating(scan_for_signals, interval=15, first=10)
    
    # Start the bot
    print("🤖 Smart Money Tracker starting...")
    print("🔍 Scanning for volume spikes every 15 seconds")
    print("💬 Alerts will be sent to users who /start the bot")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
