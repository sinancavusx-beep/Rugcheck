import aiohttp
import asyncio
from datetime import datetime, timezone


class TokenAnalyzer:
    def __init__(self, helius_api_key: str):
        self.helius_key = helius_api_key
        self.helius_rpc = f"https://mainnet.helius-rpc.com/?api-key={helius_api_key}"
        self.helius_api = f"https://api.helius.xyz/v0"

    async def analyze(self, ca: str) -> dict:
        """Ana analiz fonksiyonu - CA alır, risk skoru döner"""
        async with aiohttp.ClientSession() as session:
            # 1. Token metadata al
            token_info = await self._get_token_metadata(session, ca)

            # 2. Dev wallet bul
            dev_wallet = await self._get_dev_wallet(session, ca)

            # 3. Dev wallet geçmişini analiz et
            dev_history = await self._analyze_dev_wallet(session, dev_wallet)

            # 4. Pump.fun verisi
            pumpfun_data = await self._get_pumpfun_data(session, ca)

            # 5. Twitter analizi (metadata'dan)
            twitter_data = await self._analyze_twitter(session, pumpfun_data)

            # 6. Risk skoru hesapla
            scores = self._calculate_risk_score(dev_history, pumpfun_data, twitter_data)

            return {
                "ca": ca,
                "token_name": token_info.get("name", "Bilinmiyor"),
                "token_symbol": token_info.get("symbol", "?"),
                "dev_wallet": dev_wallet,
                "total_tokens_created": dev_history.get("total_tokens", 0),
                "rug_count": dev_history.get("rug_count", 0),
                "liquidity_pulls": dev_history.get("liquidity_pulls", 0),
                "twitter_handle": pumpfun_data.get("twitter", ""),
                "twitter_age": twitter_data.get("account_age", "?"),
                "deleted_posts": twitter_data.get("deleted_posts", 0),
                "risk_score": scores["total"],
                "rug_score": scores["rug"],
                "liquidity_score": scores["liquidity"],
                "social_score": scores["social"],
                "pattern_score": scores["pattern"],
            }

    async def _get_token_metadata(self, session: aiohttp.ClientSession, ca: str) -> dict:
        """Helius'tan token metadata al"""
        try:
            url = f"{self.helius_api}/token-metadata?api-key={self.helius_key}"
            payload = {"mintAccounts": [ca]}
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and len(data) > 0:
                        meta = data[0]
                        on_chain = meta.get("onChainMetadata", {}).get("metadata", {}).get("data", {})
                        return {
                            "name": on_chain.get("name", "Bilinmiyor"),
                            "symbol": on_chain.get("symbol", "?"),
                        }
        except Exception:
            pass
        return {"name": "Bilinmiyor", "symbol": "?"}

    async def _get_dev_wallet(self, session: aiohttp.ClientSession, ca: str) -> str:
        """Token mint işleminden dev wallet'ı bul"""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [ca, {"limit": 1, "commitment": "confirmed"}]
            }
            async with session.post(self.helius_rpc, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                signatures = data.get("result", [])
                if not signatures:
                    return "unknown"

                # İlk tx'i al (mint tx)
                sig = signatures[-1]["signature"] if len(signatures) > 0 else signatures[0]["signature"]

                tx_payload = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "getTransaction",
                    "params": [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}]
                }
                async with session.post(self.helius_rpc, json=tx_payload, timeout=aiohttp.ClientTimeout(total=10)) as tx_resp:
                    tx_data = await tx_resp.json()
                    tx = tx_data.get("result", {})
                    if tx:
                        account_keys = tx.get("transaction", {}).get("message", {}).get("accountKeys", [])
                        if account_keys:
                            # İlk signer = fee payer = dev
                            for acc in account_keys:
                                if isinstance(acc, dict) and acc.get("signer"):
                                    return acc["pubkey"]
                            if isinstance(account_keys[0], dict):
                                return account_keys[0].get("pubkey", "unknown")
                            return account_keys[0] if isinstance(account_keys[0], str) else "unknown"
        except Exception as e:
            pass
        return "unknown"

    async def _analyze_dev_wallet(self, session: aiohttp.ClientSession, dev_wallet: str) -> dict:
        """Dev wallet'ın geçmiş token'larını analiz et"""
        if dev_wallet == "unknown":
            return {"total_tokens": 0, "rug_count": 0, "liquidity_pulls": 0}

        try:
            # Helius enhanced transactions
            url = f"{self.helius_api}/addresses/{dev_wallet}/transactions?api-key={self.helius_key}&limit=100&type=TOKEN_MINT"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    # Fallback: tüm tx'leri al
                    return await self._analyze_dev_wallet_fallback(session, dev_wallet)
                
                txs = await resp.json()
                
                total_tokens = len(txs)
                rug_count = 0
                liquidity_pulls = 0

                # Her token için likidite çekme kontrolü
                for tx in txs[:20]:  # İlk 20 token
                    token_transfers = tx.get("tokenTransfers", [])
                    for transfer in token_transfers:
                        # Büyük miktarda token transferi = potansiyel rug
                        if transfer.get("fromUserAccount") == dev_wallet:
                            amount = transfer.get("tokenAmount", 0)
                            if isinstance(amount, (int, float)) and amount > 1000000:
                                liquidity_pulls += 1

                # Pump.fun üzerinden rug tespiti
                pumpfun_rugs = await self._check_pumpfun_rugs(session, dev_wallet)
                rug_count = pumpfun_rugs

                return {
                    "total_tokens": total_tokens,
                    "rug_count": rug_count,
                    "liquidity_pulls": liquidity_pulls
                }

        except Exception as e:
            return await self._analyze_dev_wallet_fallback(session, dev_wallet)

    async def _analyze_dev_wallet_fallback(self, session: aiohttp.ClientSession, dev_wallet: str) -> dict:
        """Fallback: Basit tx analizi"""
        try:
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getSignaturesForAddress",
                "params": [dev_wallet, {"limit": 50}]
            }
            async with session.post(self.helius_rpc, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                sigs = data.get("result", [])
                return {
                    "total_tokens": max(0, len(sigs) // 5),
                    "rug_count": 0,
                    "liquidity_pulls": 0
                }
        except Exception:
            return {"total_tokens": 0, "rug_count": 0, "liquidity_pulls": 0}

    async def _check_pumpfun_rugs(self, session: aiohttp.ClientSession, dev_wallet: str) -> int:
        """Pump.fun API'sinden dev'in rug geçmişini kontrol et"""
        try:
            url = f"https://frontend-api.pump.fun/coins/user-created-coins/{dev_wallet}?offset=0&limit=50&includeNsfw=true"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    return 0
                data = await resp.json()
                
                rug_count = 0
                coins = data if isinstance(data, list) else data.get("coins", [])
                
                for coin in coins:
                    market_cap = coin.get("usd_market_cap", 0) or 0
                    complete = coin.get("complete", False)
                    
                    # Tamamlanmamış ve market cap çok düşük = muhtemel rug
                    if not complete and market_cap < 100:
                        rug_count += 1

                return rug_count
        except Exception:
            return 0

    async def _get_pumpfun_data(self, session: aiohttp.ClientSession, ca: str) -> dict:
        """Pump.fun'dan token verisi al"""
        try:
            url = f"https://frontend-api.pump.fun/coins/{ca}"
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "twitter": data.get("twitter", ""),
                        "telegram": data.get("telegram", ""),
                        "website": data.get("website", ""),
                        "created_timestamp": data.get("created_timestamp", 0),
                        "market_cap": data.get("usd_market_cap", 0),
                        "complete": data.get("complete", False),
                        "reply_count": data.get("reply_count", 0),
                    }
        except Exception:
            pass
        return {}

    async def _analyze_twitter(self, session: aiohttp.ClientSession, pumpfun_data: dict) -> dict:
        """Twitter/X hesabını analiz et (API gerektirmeden)"""
        twitter_handle = pumpfun_data.get("twitter", "")
        
        if not twitter_handle:
            return {"account_age": "Yok", "deleted_posts": 0, "score": 10}

        # Twitter handle temizle
        handle = twitter_handle.replace("https://twitter.com/", "").replace("https://x.com/", "").replace("@", "").strip()
        
        try:
            # Nitter üzerinden kontrol (public scraping)
            nitter_instances = [
                f"https://nitter.net/{handle}",
                f"https://nitter.privacydev.net/{handle}",
            ]
            
            for nitter_url in nitter_instances:
                try:
                    async with session.get(nitter_url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            
                            # Hesap yaşını bul
                            age = "Bilinmiyor"
                            if "Joined" in html or "Katıldı" in html:
                                import re
                                match = re.search(r'Joined ([A-Za-z]+ \d{4})', html)
                                if match:
                                    age = match.group(1)

                            # Tweet sayısını bul
                            tweet_count = 0
                            match = re.search(r'(\d+)\s*Tweet', html)
                            if match:
                                tweet_count = int(match.group(1))

                            return {
                                "account_age": age,
                                "deleted_posts": 0,  # Silinen tweet tespiti zor
                                "tweet_count": tweet_count,
                                "exists": True
                            }
                except Exception:
                    continue
            
            # Nitter çalışmıyorsa basit skor
            return {"account_age": "Kontrol edilemedi", "deleted_posts": 0, "exists": None}
            
        except Exception:
            return {"account_age": "Hata", "deleted_posts": 0, "exists": None}

    def _calculate_risk_score(self, dev_history: dict, pumpfun_data: dict, twitter_data: dict) -> dict:
        """Risk skoru hesapla (0-100, yüksek = tehlikeli)"""
        
        # 1. RUG GEÇMİŞİ SKORU (0-40 puan)
        rug_score = 0
        rug_count = dev_history.get("rug_count", 0)
        if rug_count == 1:
            rug_score = 20
        elif rug_count == 2:
            rug_score = 35
        elif rug_count >= 3:
            rug_score = 40

        # 2. LİKİDİTE RİSKİ (0-25 puan)
        liquidity_score = 0
        pulls = dev_history.get("liquidity_pulls", 0)
        if pulls > 0:
            liquidity_score = min(25, pulls * 8)

        total_tokens = dev_history.get("total_tokens", 0)
        if total_tokens > 10:
            liquidity_score = min(25, liquidity_score + 5)
        if total_tokens > 20:
            liquidity_score = min(25, liquidity_score + 5)

        # 3. SOSYAL MEDYA SKORU (0-20 puan)
        social_score = 0
        if not pumpfun_data.get("twitter"):
            social_score += 10  # Twitter yok = şüpheli
        if not pumpfun_data.get("website"):
            social_score += 5
        if twitter_data.get("exists") is False:
            social_score += 5  # Twitter silinmiş

        social_score = min(20, social_score)

        # 4. PATTERN SKORU (0-15 puan)
        pattern_score = 0
        if total_tokens > 5:
            pattern_score += 5   # Çok fazla token açmış
        if total_tokens > 15:
            pattern_score += 5
        if pumpfun_data.get("reply_count", 0) < 5:
            pattern_score += 5   # Çok az etkileşim

        pattern_score = min(15, pattern_score)

        total = rug_score + liquidity_score + social_score + pattern_score

        return {
            "total": min(100, total),
            "rug": rug_score,
            "liquidity": liquidity_score,
            "social": social_score,
            "pattern": pattern_score,
        }
