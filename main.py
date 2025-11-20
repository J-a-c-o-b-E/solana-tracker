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
        
        NOTE: Dexscreener API only provides 5min and 1hour data, not 2-3min.
        We'll use 5min data as closest approximation.
        """
        try:
            # Get transaction data
            txns = pair.get('txns', {})
            m5 = txns.get('m5', {})  # 5 minute data (closest to 2-3 min)
            
            # Recent buys (using 5min window)
            buys_5min = m5.get('buys', 0)
            sells_5min = m5.get('sells', 0)
            
            # Calculate estimated 2-3 min values (scale down from 5min)
            # Assume 2.5 min average, so multiply by 0.5 (2.5/5)
            recent_buys = int(buys_5min * 0.5)
            
            # Volume in last 5 minutes
            volume_5min = float(pair.get('volume', {}).get('m5', 0))
            
            # Scale to 2-3 min estimate
            volume_2_3min = volume_5min * 0.5
            
            # Calculate average buy size
            avg_buy = volume_2_3min / recent_buys if recent_buys > 0 else 0
            
            return {
                'recent_buys': recent_buys,
                'volume': volume_2_3min,
                'avg_buy': avg_buy,
                'buys_5min': buys_5min,  # Keep original for reference
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
    def should_alert(pair_address):
        """Check if we should alert on this token (not already alerted)"""
        if pair_address in SmartMoneyTracker.alerted_tokens:
            return False
        
        # Add to alerted set
        SmartMoneyTracker.alerted_tokens.add(pair_address)
        
        # Keep only last 100 tokens to avoid memory issues
        if len(SmartMoneyTracker.alerted_tokens) > 100:
            # Remove oldest (first) item
            SmartMoneyTracker.alerted_tokens.pop()
        
        return True
    
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
            
            # Check pair age (prefer tokens deployed in last 48 hours)
            pair_created = pair.get('pairCreatedAt')
            if pair_created:
                age_hours = (datetime.now().timestamp() - pair_created / 1000) / 3600
                checks['age_ok'] = age_hours < 48
            
            return checks
        except Exception as e:
            print(f"Error in safety checks: {e}")
            return checks


async def scan_for_signals(context: ContextTypes.DEFAULT_TYPE):
    """Scan Solana tokens for volume spike signals"""
    try:
        # Get user chat IDs from context (users who have started the bot)
        if 'active_chats' not in context.bot_data:
            return
        
        active_chats = context.bot_data['active_chats']
        if not active_chats:
            return  # No one subscribed
        
        # Search for recent Solana tokens
        search_terms = ['pump', 'raydium', 'orca']
        
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
                            
                            for pair in solana_pairs[:15]:  # Check top 15
                                pair_address = pair.get('pairAddress')
                                
                                # Skip if already alerted
                                if not SmartMoneyTracker.should_alert(pair_address):
                                    continue
                                
                                # Calculate metrics
                                metrics = SmartMoneyTracker.calculate_metrics(pair)
                                if not metrics:
                                    continue
                                
                                # Determine tier
                                tier = SmartMoneyTracker.determine_tier(metrics)
                                if not tier:
                                    continue  # No signal
                                
                                # Perform safety checks
                                safety = await SmartMoneyTracker.perform_safety_checks(pair)
                                
                                # Only alert if passes liquidity check
                                if not safety['liquidity_ok']:
                                    continue
                                
                                # Format and send alert to all active chats
                                message = format_signal_alert(pair, tier, metrics, safety)
                                
                                for chat_id in active_chats:
                                    try:
                                        await context.bot.send_message(
                                            chat_id=chat_id,
                                            text=message,
                                            parse_mode='HTML',
                                            disable_web_page_preview=True
                                        )
                                    except Exception as e:
                                        print(f"Error sending to chat {chat_id}: {e}")
                                
                                print(f"📢 Alert sent: {tier} - {pair.get('baseToken', {}).get('symbol')}")
                                
                                # Don't spam - wait between alerts
                                await asyncio.sleep(1)
                
                except Exception as e:
                    print(f"Error scanning {term}: {e}")
                
                await asyncio.sleep(0.3)  # Rate limiting between searches
    
    except Exception as e:
        print(f"Error in scan_for_signals: {e}")


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
    
    # Get age
    pair_created = pair.get('pairCreatedAt')
    if pair_created:
        age_minutes = (datetime.now().timestamp() - pair_created / 1000) / 60
        if age_minutes < 60:
            age_str = f"{int(age_minutes)} minutes ago"
        else:
            age_hours = age_minutes / 60
            age_str = f"{age_hours:.1f} hours ago"
    else:
        age_str = "Unknown"
    
    # DEX links
    dex_url = pair.get('url', '#')
    pair_address = pair.get('pairAddress', 'N/A')
    
    # Build message
    message = f"<b>{tier_name}</b>\n\n"
    message += f"<b>🪙 {name} (${symbol})</b>\n\n"
    
    # Signal metrics (2-3 min window)
    message += f"<b>📊 Signal (2-3 min window):</b>\n"
    message += f"Recent Buys: <b>{metrics['recent_buys']}</b>\n"
    message += f"Volume: <b>${metrics['volume']:,.0f}</b>\n"
    message += f"Avg Buy: <b>${metrics['avg_buy']:.2f}</b>\n\n"
    
    # Token info
    message += f"💵 Price: ${price:.10f}\n"
    message += f"💰 Market Cap: ${mcap:,.0f}\n"
    message += f"💧 Liquidity: ${liquidity:,.0f}\n"
    message += f"⏰ Deployed: {age_str}\n\n"
    
    # Safety checks
    message += f"<b>🛡️ Safety:</b>\n"
    message += f"{'✅' if safety['liquidity_ok'] else '⚠️'} Liquidity: ${liquidity:,.0f}\n"
    message += f"{'✅' if safety['age_ok'] else '⚠️'} Age: {age_str}\n\n"
    
    # Links
    message += f"🔗 <a href='{dex_url}'>Dexscreener</a>\n"
    message += f"📍 <code>{pair_address}</code>"
    
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
