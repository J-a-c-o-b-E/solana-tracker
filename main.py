import os
import asyncio
import aiohttp
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# Dexscreener API
DEXSCREENER_API = "https://api.dexscreener.com/latest/dex/search?q="

class SmartMoneyTracker:
    """Tracks volume spikes and buying pressure on Solana tokens"""
    
    # Track tokens we've already alerted on
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


async def scan_for_signals(context: ContextTypes.DEFAULT_TYPE):
    """Scan Solana tokens for volume spike signals - find ONE best signal per cycle"""
    try:
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
            
            # Keep only last 100 tokens
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
        "Use /stop to unsubscribe from alerts.",
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


def main():
    """Main function"""
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
