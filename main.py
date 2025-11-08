import asyncio
import aiohttp
from datetime import datetime

async def test_dexscreener():
    """Simple test to fetch and display Solana tokens"""
    
    print("🔍 Testing Dexscreener API...")
    print("=" * 50)
    
    url = "https://api.dexscreener.com/latest/dex/search?q=solana"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                print(f"📡 API Status: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    pairs = data.get('pairs', [])
                    
                    print(f"✅ Total pairs fetched: {len(pairs)}")
                    
                    # Filter for Solana only
                    solana_pairs = [p for p in pairs if p.get('chainId') == 'solana']
                    print(f"🔗 Solana pairs: {len(solana_pairs)}")
                    
                    if solana_pairs:
                        print("\n" + "=" * 50)
                        print("📊 FIRST 10 SOLANA TOKENS:")
                        print("=" * 50 + "\n")
                        
                        for i, pair in enumerate(solana_pairs[:10], 1):
                            base_token = pair.get('baseToken', {})
                            symbol = base_token.get('symbol', 'Unknown')
                            name = base_token.get('name', 'Unknown')
                            
                            liquidity = pair.get('liquidity', {}).get('usd', 0)
                            fdv = pair.get('fdv', 0)
                            mcap = pair.get('marketCap', 0)
                            
                            volume_24h = pair.get('volume', {}).get('h24', 0)
                            
                            txns_1h = pair.get('txns', {}).get('h1', {})
                            txns_1h_total = txns_1h.get('buys', 0) + txns_1h.get('sells', 0)
                            
                            txns_24h = pair.get('txns', {}).get('h24', {})
                            txns_24h_total = txns_24h.get('buys', 0) + txns_24h.get('sells', 0)
                            
                            # Calculate age
                            pair_created = pair.get('pairCreatedAt')
                            if pair_created:
                                created_time = datetime.fromtimestamp(pair_created / 1000)
                                age_hours = (datetime.now() - created_time).total_seconds() / 3600
                                age_str = f"{age_hours:.1f} hours"
                            else:
                                age_str = "Unknown"
                            
                            print(f"#{i} {name} (${symbol})")
                            print(f"   💧 Liquidity: ${liquidity:,.0f}")
                            print(f"   📊 FDV: ${fdv:,.0f}")
                            print(f"   🏦 MCap: ${mcap:,.0f}")
                            print(f"   📈 24h Volume: ${volume_24h:,.0f}")
                            print(f"   🔥 1H Txns: {txns_1h_total}")
                            print(f"   🔥 24H Txns: {txns_24h_total}")
                            print(f"   ⏱️  Age: {age_str}")
                            print()
                        
                        print("=" * 50)
                        print("✅ TEST SUCCESSFUL - API is working!")
                        print("=" * 50)
                        
                    else:
                        print("⚠️ No Solana pairs found in response")
                        
                else:
                    print(f"❌ API returned error status: {response.status}")
                    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_dexscreener())
