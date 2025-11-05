"""
多様性を担保したアカウントサンプリングモジュール（X API + Grok Web Search ハイブリッド）
"""

import logging
import random
import math
import time
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from textblob import TextBlob

logger = logging.getLogger(__name__)


class DiversitySampler:
    """
    多様性を担保したアカウントサンプリング（X API + Grok Web Search ハイブリッド）
    
    このクラスは以下の2段階アプローチを実装しています：
    1. データソースのハイブリッド: X APIとGrok Web Searchから候補を収集・統合
    2. サンプリング手法の適用: 確率サンプリング（層化/ランダム）または非確率サンプリング（クォータ）を選択
    
    注意: 「ハイブリッド」はデータソースの組み合わせを指し、サンプリング手法の組み合わせではありません。
    """

    FOLLOWER_STRATA = [
        (0, 100, "micro"),
        (100, 1000, "small"),
        (1000, 10000, "medium"),
        (10000, 100000, "large"),
        (100000, 1000000, "macro"),
        (1000000, float("inf"), "mega"),
    ]

    REGIONS = {
        "JP": "日本",
        "US": "アメリカ",
        "GB": "イギリス",
        "IN": "インド",
        "BR": "ブラジル",
        "KR": "韓国",
        "CN": "中国",
        "DE": "ドイツ",
        "FR": "フランス",
        "CA": "カナダ",
    }

    LANGUAGES = ["ja", "en", "ko", "zh", "es", "fr", "de", "pt"]

    def __init__(self, x_api_client=None, grok_api=None):
        """
        Args:
            x_api_client: XAPIClient インスタンス（オプション）
            grok_api: GrokAPI インスタンス（必須）
        """
        self.x_api_client = x_api_client
        self.grok_api = grok_api
        self.x_api_rate_limit_track: Dict[str, Optional[datetime]] = {
            "remaining": None,
            "reset_at": None,
            "last_check": None,
        }

    def discover_accounts_hybrid(
        self,
        queries: List[str],
        max_results: int = 50,
        prefer_x_api: bool = True,
        fallback_to_grok: bool = True,
        sampling_method: str = "stratified",
    ) -> List[Dict]:
        """
        X API + Grok Web Search のハイブリッドでアカウントを発見し、多様性を担保する。
        
        2段階アプローチ:
        1. データソースのハイブリッド: X APIとGrok Web Searchから候補を収集・統合
        2. サンプリング手法の適用: 選択した手法（stratified/quota/random）を適用
        
        Args:
            queries: 検索クエリのリスト
            max_results: 最大取得件数
            prefer_x_api: X APIを優先するか
            fallback_to_grok: Grok Web Searchにフォールバックするか
            sampling_method: サンプリング手法（"stratified", "quota", "random"）
                - "stratified": 確率サンプリング（層化サンプリング）
                - "quota": 非確率サンプリング（クォータサンプリング）
                - "random": 確率サンプリング（ランダムサンプリング）
        
        Returns:
            多様性指標付きのアカウントリスト
        """
        all_candidates: List[Dict] = []
        x_api_success_count = 0
        grok_success_count = 0
        x_api_failures = 0

        logger.info(
            f"🔍 ハイブリッドアカウント発見開始: {len(queries)}件のクエリ "
            f"(目標: {max_results}件, 手法: {sampling_method})"
        )

        for query in queries:
            if len(all_candidates) >= max_results * 2:
                break

            account_batch: List[Dict] = []

            if prefer_x_api and self.x_api_client and self._can_use_x_api():
                try:
                    account_batch = self._discover_via_x_api(query, max_results=20)
                    if account_batch:
                        x_api_success_count += 1
                        logger.info(f"✅ X API成功: '{query}' → {len(account_batch)}件")
                    else:
                        x_api_failures += 1
                except Exception as error:  # noqa: BLE001
                    logger.warning(f"⚠️ X API検索失敗: '{query}' - {error}")
                    x_api_failures += 1
                    account_batch = []

            if (not account_batch or len(account_batch) < 5) and fallback_to_grok and self.grok_api:
                try:
                    grok_batch = self._discover_via_grok(query, max_results=20)
                    if grok_batch:
                        grok_success_count += 1
                        existing_handles = {acc.get("handle", "").lstrip("@") for acc in account_batch}
                        for candidate in grok_batch:
                            handle = candidate.get("handle", "").lstrip("@")
                            if handle and handle not in existing_handles:
                                account_batch.append(candidate)
                        logger.info(f"✅ Grok成功: '{query}' → {len(grok_batch)}件追加")
                except Exception as error:  # noqa: BLE001
                    logger.warning(f"⚠️ Grok Web Search検索失敗: '{query}' - {error}")

            all_candidates.extend(account_batch)

        logger.info(
            f"候補収集完了: 総{len(all_candidates)}件 "
            f"(X API成功: {x_api_success_count}, Grok成功: {grok_success_count}, "
            f"X API失敗: {x_api_failures})"
        )

        unique_candidates = self._deduplicate_accounts(all_candidates)
        logger.info(f"重複除去後: {len(unique_candidates)}件")

        enriched_candidates = self.enrich_account_attributes(
            unique_candidates,
            x_api_client=self.x_api_client if self._can_use_x_api() else None,
        )

        if sampling_method == "stratified":
            sampled = self.stratified_sampling(
                enriched_candidates,
                num_samples=max_results,
                strata_attributes=["followers", "region", "language", "sentiment"],
            )
        elif sampling_method == "quota":
            quotas = self._generate_default_quotas(max_results)
            sampled = self.quota_sampling(
                enriched_candidates,
                quotas=quotas,
                max_total=max_results,
            )
        else:
            sampled = random.sample(
                enriched_candidates,
                min(max_results, len(enriched_candidates)),
            )

        diversity_metrics = self.calculate_diversity_metrics(
            sampled,
            attributes=["followers", "region", "language", "sentiment"],
        )
        logger.info(f"📊 多様性指標: {diversity_metrics}")

        overall_score = diversity_metrics.get("overall_diversity", 0.0)
        for account in sampled:
            account["diversity_score"] = overall_score
            account.setdefault("source", "hybrid")

        logger.info(f"✅ ハイブリッドサンプリング完了: {len(sampled)}件")
        return sampled

    def _discover_via_x_api(self, query: str, max_results: int = 20) -> List[Dict]:
        """X API v2でアカウントを検索。"""
        if not self.x_api_client:
            return []

        tweets = self.x_api_client.search_recent_tweets(
            query=query,
            max_results=min(max_results * 2, 100),
            max_wait_seconds=0,
        )
        if not tweets:
            return []

        user_handles = set()
        accounts: List[Dict] = []

        for tweet in tweets:
            text = tweet.get("text", "")
            mentions = re.findall(r"@(\w+)", text)
            for mention in mentions:
                if mention in user_handles:
                    continue
                user_handles.add(mention)
                try:
                    users = self.x_api_client.fetch_user_by_handle([mention])
                except Exception as error:  # noqa: BLE001
                    logger.debug(f"ユーザー情報取得失敗: @{mention} - {error}")
                    continue

                if not users:
                    continue

                user = users[0]
                accounts.append(
                    {
                        "handle": user.get("username", mention),
                        "display_name": user.get("name", mention),
                        "followers_count": user.get("public_metrics", {}).get("followers_count", 0),
                        "tweet_count": user.get("public_metrics", {}).get("tweet_count", 0),
                        "verified": user.get("verified", False),
                        "description": user.get("description", ""),
                        "source": "x_api",
                        "confidence": 0.9,
                    }
                )

        return accounts[:max_results]

    def _discover_via_grok(self, query: str, max_results: int = 20) -> List[Dict]:
        """Grok Web Searchでアカウントを検索。"""
        if not self.grok_api:
            return []

        accounts = self.grok_api.discover_accounts_by_keyword(
            keyword=query,
            max_results=max_results,
            dry_run=False,
            x_api_client=self.x_api_client if self._can_use_x_api() else None,
        )
        for account in accounts:
            if account.get("source") == "grok_keyword":
                account["source"] = "grok_web_search"
        return accounts

    def _can_use_x_api(self) -> bool:
        """X APIが利用可能かチェック（簡易実装）。"""
        if not self.x_api_client:
            return False

        remaining = self.x_api_rate_limit_track.get("remaining")
        reset_at = self.x_api_rate_limit_track.get("reset_at")
        if remaining is not None and remaining == 0:
            if reset_at and isinstance(reset_at, datetime):
                return datetime.now() >= reset_at
            return False
        return True

    def _deduplicate_accounts(self, accounts: List[Dict]) -> List[Dict]:
        """アカウントの重複を除去。"""
        seen_handles = set()
        unique: List[Dict] = []
        for account in accounts:
            handle = account.get("handle", "").lstrip("@").lower()
            if handle and handle not in seen_handles:
                seen_handles.add(handle)
                unique.append(account)
        return unique

    def _generate_default_quotas(self, max_total: int) -> Dict[str, Dict[str, int]]:
        """クォータのデフォルト値を生成。"""
        return {
            "followers": {
                "micro": max_total // 6,
                "small": max_total // 6,
                "medium": max_total // 3,
                "large": max_total // 4,
                "macro": max_total // 12,
                "mega": max_total // 12,
            },
            "region": {
                "JP": max_total // 2,
                "US": max_total // 4,
                "GB": max_total // 8,
                "KR": max_total // 8,
            },
            "sentiment": {
                "positive": max_total // 3,
                "neutral": max_total // 3,
                "negative": max_total // 3,
            },
        }

    def stratified_sampling(
        self,
        accounts: List[Dict],
        num_samples: int,
        strata_attributes: List[str],
    ) -> List[Dict]:
        """
        層化サンプリング（確率サンプリング）。
        
        複数属性（followers, region, language, sentiment）で層化し、
        各層から比例的にランダムサンプリング（random.sample使用）。
        
        Args:
            accounts: アカウント候補リスト
            num_samples: サンプル数
            strata_attributes: 層化に使用する属性のリスト
        
        Returns:
            サンプリングされたアカウントリスト
        """
        if not accounts:
            return []

        strata: Dict[str, List[Dict]] = defaultdict(list)

        for account in accounts:
            key_parts: List[str] = []
            if "followers" in strata_attributes:
                key_parts.append(self._get_follower_stratum(account.get("followers_count", 0)))
            if "region" in strata_attributes:
                key_parts.append(f"region_{account.get('region', 'unknown')}")
            if "language" in strata_attributes:
                key_parts.append(f"lang_{account.get('language', 'unknown')}")
            if "sentiment" in strata_attributes:
                key_parts.append(f"sentiment_{account.get('dominant_sentiment', 'neutral')}")

            strata["_".join(key_parts)].append(account)

        sampled: List[Dict] = []
        total_accounts = len(accounts)

        for stratum_accounts in strata.values():
            stratum_size = len(stratum_accounts)
            sample_size = max(1, int(num_samples * stratum_size / total_accounts))
            sampled.extend(random.sample(stratum_accounts, min(sample_size, stratum_size)))

        if len(sampled) > num_samples:
            sampled = random.sample(sampled, num_samples)

        return sampled

    def quota_sampling(
        self,
        accounts: List[Dict],
        quotas: Dict[str, Dict[str, int]],
        max_total: int,
    ) -> List[Dict]:
        """
        クォータサンプリング（非確率サンプリング）。
        
        指定されたクォータに従ってサンプリング（便利サンプリングに近い）。
        シャッフル済みリストを順次処理し、クォータを満たすものを選択。
        
        Args:
            accounts: アカウント候補リスト
            quotas: クォータ設定（属性ごとの目標数）
            max_total: 最大サンプル数
        
        Returns:
            サンプリングされたアカウントリスト
        """
        sampled: List[Dict] = []
        quota_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        shuffled = accounts.copy()
        random.shuffle(shuffled)

        for account in shuffled:
            if len(sampled) >= max_total:
                break

            fits = True

            for attribute, quota in quotas.items():
                if attribute == "followers":
                    stratum = self._get_follower_stratum(account.get("followers_count", 0))
                    if quota_counts[attribute][stratum] >= quota.get(stratum, 0):
                        fits = False
                        break
                elif attribute == "region":
                    region = account.get("region", "unknown")
                    if quota_counts[attribute][region] >= quota.get(region, 0):
                        fits = False
                        break
                elif attribute == "sentiment":
                    sentiment = account.get("dominant_sentiment", "neutral")
                    if quota_counts[attribute][sentiment] >= quota.get(sentiment, 0):
                        fits = False
                        break

            if fits:
                sampled.append(account)
                for attribute, quota in quotas.items():
                    if attribute == "followers":
                        stratum = self._get_follower_stratum(account.get("followers_count", 0))
                        quota_counts[attribute][stratum] += 1
                    elif attribute == "region":
                        region = account.get("region", "unknown")
                        quota_counts[attribute][region] += 1
                    elif attribute == "sentiment":
                        sentiment = account.get("dominant_sentiment", "neutral")
                        quota_counts[attribute][sentiment] += 1

        return sampled

    def calculate_diversity_metrics(
        self,
        accounts: List[Dict],
        attributes: List[str],
    ) -> Dict[str, float]:
        """多様性指標（正規化エントロピー）を計算。"""
        metrics: Dict[str, float] = {}

        for attribute in attributes:
            if attribute == "followers":
                values = [self._get_follower_stratum(acc.get("followers_count", 0)) for acc in accounts]
            else:
                key = {
                    "region": "region",
                    "language": "language",
                    "sentiment": "dominant_sentiment",
                }.get(attribute)
                if not key:
                    continue
                values = [acc.get(key, "unknown") for acc in accounts]

            entropy = self._calculate_entropy(values)
            metrics[f"{attribute}_entropy"] = entropy

        if metrics:
            metrics["overall_diversity"] = sum(metrics.values()) / len(metrics)

        return metrics

    def enrich_account_attributes(
        self,
        accounts: List[Dict],
        x_api_client=None,
    ) -> List[Dict]:
        """アカウントに追加属性を付与。"""
        enriched: List[Dict] = []
        client = x_api_client or self.x_api_client

        for account in accounts:
            handle = account.get("handle", "").lstrip("@")
            enriched_account = account.copy()

            if client and self._can_use_x_api():
                try:
                    metrics = client.fetch_user_metrics(handle)
                    if metrics:
                        enriched_account["followers_count"] = metrics.get("followers_count", 0)
                        enriched_account["tweet_count"] = metrics.get("tweet_count", 0)
                        enriched_account["last_tweet_at"] = metrics.get("last_tweet_at")
                        enriched_account["account_created_at"] = metrics.get("account_created_at")
                        # レートリミットトラックを更新（簡易）
                        remaining = metrics.get("rate_limit_remaining")
                        reset_at = metrics.get("rate_limit_reset_at")
                        if remaining is not None:
                            self.x_api_rate_limit_track["remaining"] = remaining
                        if reset_at:
                            try:
                                self.x_api_rate_limit_track["reset_at"] = datetime.fromisoformat(reset_at)
                            except ValueError:
                                pass
                except Exception as error:  # noqa: BLE001
                    logger.debug(f"メトリクス取得失敗: @{handle} - {error}")

            enriched_account["region"] = self._infer_region(enriched_account)
            enriched_account["language"] = self._infer_language(enriched_account)
            enriched_account["dominant_sentiment"] = self._analyze_sentiment(enriched_account)
            enriched.append(enriched_account)

        return enriched

    def _get_follower_stratum(self, followers: int) -> str:
        for low, high, label in self.FOLLOWER_STRATA:
            if low <= followers < high:
                return label
        return "unknown"

    def _calculate_entropy(self, values: List[str]) -> float:
        if not values:
            return 0.0

        counter = Counter(values)
        total = len(values)
        if total == 0:
            return 0.0

        entropy = 0.0
        for count in counter.values():
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)

        max_entropy = math.log2(len(counter)) if len(counter) > 1 else 1.0
        return entropy / max_entropy if max_entropy > 0 else 0.0

    def _infer_region(self, account: Dict) -> str:
        text = f"{account.get('location', '')} {account.get('description', '')}".lower()
        if any(keyword in text for keyword in ["japan", "tokyo", "osaka", "日本", "東京"]):
            return "JP"
        if any(keyword in text for keyword in ["usa", "united states", "america", "new york", "california"]):
            return "US"
        if any(keyword in text for keyword in ["uk", "united kingdom", "london", "england"]):
            return "GB"
        if any(keyword in text for keyword in ["korea", "seoul", "대한민국", "한국"]):
            return "KR"
        return "unknown"

    def _infer_language(self, account: Dict) -> str:
        description = account.get("description", "")
        if any("\u3040" <= ch <= "\u309f" or "\u30a0" <= ch <= "\u30ff" for ch in description):
            return "ja"
        if any("\uac00" <= ch <= "\ud7a3" for ch in description):
            return "ko"
        if any("\u4e00" <= ch <= "\u9fff" for ch in description):
            return "zh"
        return "en"

    def _analyze_sentiment(self, account: Dict) -> str:
        description = account.get("description", "")
        if not description:
            return "neutral"
        try:
            polarity = TextBlob(description).sentiment.polarity
        except Exception:  # noqa: BLE001
            return "neutral"
        if polarity > 0.1:
            return "positive"
        if polarity < -0.1:
            return "negative"
        return "neutral"
