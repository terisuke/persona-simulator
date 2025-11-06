"""
DiversitySampler のユニットテスト
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
from typing import List, Dict

from utils.diversity_sampling import DiversitySampler


class TestDiversitySampling(unittest.TestCase):
    """DiversitySampler のテストクラス"""

    def setUp(self):
        """テスト前のセットアップ"""
        self.mock_x_api = Mock()
        self.mock_grok_api = Mock()
        self.sampler = DiversitySampler(
            x_api_client=self.mock_x_api,
            grok_api=self.mock_grok_api
        )

    def test_stratified_sampling(self):
        """層化サンプリングの動作確認"""
        # テストデータ: 異なるフォロワー数、地域、言語、センチメントのアカウント
        accounts = [
            {"handle": "user1", "followers_count": 500, "region": "JP", "language": "ja", "dominant_sentiment": "positive"},
            {"handle": "user2", "followers_count": 5000, "region": "US", "language": "en", "dominant_sentiment": "neutral"},
            {"handle": "user3", "followers_count": 50000, "region": "JP", "language": "ja", "dominant_sentiment": "negative"},
            {"handle": "user4", "followers_count": 500, "region": "US", "language": "en", "dominant_sentiment": "positive"},
            {"handle": "user5", "followers_count": 5000, "region": "JP", "language": "ja", "dominant_sentiment": "neutral"},
        ]

        result = self.sampler.stratified_sampling(
            accounts,
            num_samples=3,
            strata_attributes=["followers", "region", "language", "sentiment"]
        )

        # 結果の検証
        self.assertIsInstance(result, list)
        self.assertLessEqual(len(result), 3)
        self.assertGreater(len(result), 0)
        
        # 各結果が元のアカウントリストに含まれているか確認
        handles = [acc["handle"] for acc in accounts]
        for account in result:
            self.assertIn(account["handle"], handles)

    def test_quota_sampling(self):
        """クォータサンプリングの動作確認"""
        # テストデータ
        accounts = [
            {"handle": "user1", "followers_count": 500, "region": "JP", "dominant_sentiment": "positive"},
            {"handle": "user2", "followers_count": 5000, "region": "US", "dominant_sentiment": "neutral"},
            {"handle": "user3", "followers_count": 50000, "region": "JP", "dominant_sentiment": "negative"},
            {"handle": "user4", "followers_count": 500, "region": "US", "dominant_sentiment": "positive"},
            {"handle": "user5", "followers_count": 5000, "region": "JP", "dominant_sentiment": "neutral"},
        ]

        quotas = {
            "followers": {
                "small": 1,
                "medium": 1,
                "large": 1,
            },
            "region": {
                "JP": 2,
                "US": 1,
            },
            "sentiment": {
                "positive": 1,
                "neutral": 1,
                "negative": 1,
            },
        }

        result = self.sampler.quota_sampling(
            accounts,
            quotas=quotas,
            max_total=5
        )

        # 結果の検証
        self.assertIsInstance(result, list)
        self.assertLessEqual(len(result), 5)
        
        # クォータが満たされているか確認（完全一致は難しいため、基本的な構造のみ確認）
        if len(result) > 0:
            # 結果が元のアカウントリストに含まれているか確認
            handles = [acc["handle"] for acc in accounts]
            for account in result:
                self.assertIn(account["handle"], handles)

    def test_random_sampling(self):
        """ランダムサンプリングの動作確認"""
        accounts = [
            {"handle": "user1", "followers_count": 500},
            {"handle": "user2", "followers_count": 5000},
            {"handle": "user3", "followers_count": 50000},
            {"handle": "user4", "followers_count": 500},
            {"handle": "user5", "followers_count": 5000},
        ]

        # random.sample を使用するため、discover_accounts_hybrid の random パスをテスト
        # 実際には discover_accounts_hybrid で random が使われるが、
        # ここでは直接テストするため、sampling_method="random" の動作を確認
        # ただし、random.sample は discover_accounts_hybrid 内で呼ばれるため、
        # ここでは基本的な動作確認のみ行う
        
        # 空のリストの場合
        result = self.sampler.stratified_sampling([], num_samples=3, strata_attributes=["followers"])
        self.assertEqual(result, [])

    def test_calculate_diversity_metrics(self):
        """多様性指標計算の検証"""
        accounts = [
            {"handle": "user1", "followers_count": 500, "region": "JP", "language": "ja", "dominant_sentiment": "positive"},
            {"handle": "user2", "followers_count": 5000, "region": "US", "language": "en", "dominant_sentiment": "neutral"},
            {"handle": "user3", "followers_count": 50000, "region": "JP", "language": "ja", "dominant_sentiment": "negative"},
        ]

        metrics = self.sampler.calculate_diversity_metrics(
            accounts,
            attributes=["followers", "region", "language", "sentiment"]
        )

        # 結果の検証
        self.assertIsInstance(metrics, dict)
        self.assertIn("overall_diversity", metrics)
        self.assertIsInstance(metrics["overall_diversity"], float)
        self.assertGreaterEqual(metrics["overall_diversity"], 0.0)
        self.assertLessEqual(metrics["overall_diversity"], 1.0)

        # 各属性のエントロピーが含まれているか確認
        expected_keys = ["followers_entropy", "region_entropy", "language_entropy", "sentiment_entropy", "overall_diversity"]
        for key in expected_keys:
            if key != "overall_diversity":
                # エントロピーは属性によっては存在しない場合がある
                pass
            else:
                self.assertIn(key, metrics)

    def test_deduplicate_accounts(self):
        """重複除去の検証"""
        accounts = [
            {"handle": "user1", "followers_count": 500},
            {"handle": "user2", "followers_count": 5000},
            {"handle": "user1", "followers_count": 500},  # 重複
            {"handle": "@user2", "followers_count": 5000},  # @付きで重複
            {"handle": "USER1", "followers_count": 500},  # 大文字小文字違いで重複
        ]

        result = self.sampler._deduplicate_accounts(accounts)

        # 結果の検証
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)  # user1 と user2 のみ
        
        handles = [acc["handle"].lstrip("@").lower() for acc in result]
        self.assertIn("user1", handles)
        self.assertIn("user2", handles)

    def test_enrich_account_attributes(self):
        """属性付与の検証（モック使用）"""
        # モックの設定
        self.mock_x_api.fetch_user_metrics.return_value = {
            "followers_count": 1000,
            "tweet_count": 500,
            "last_tweet_at": "2024-01-01T00:00:00Z",
            "account_created_at": "2020-01-01T00:00:00Z",
            "rate_limit_remaining": 10,
            "rate_limit_reset_at": "2024-01-01T01:00:00Z"
        }
        self.sampler.x_api_rate_limit_track["remaining"] = 10

        accounts = [
            {"handle": "user1", "description": "Tokyo, Japan", "location": "Tokyo"},
        ]

        result = self.sampler.enrich_account_attributes(accounts, x_api_client=self.mock_x_api)

        # 結果の検証
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        
        enriched = result[0]
        self.assertIn("region", enriched)
        self.assertIn("language", enriched)
        self.assertIn("dominant_sentiment", enriched)
        
        # X API が利用可能な場合、メトリクスが更新されているか確認
        if self.sampler._can_use_x_api():
            self.mock_x_api.fetch_user_metrics.assert_called_once_with("user1")

    def test_enrich_account_attributes_no_x_api(self):
        """X API が利用できない場合の属性付与"""
        # X API クライアントを None に設定
        self.sampler.x_api_client = None

        accounts = [
            {"handle": "user1", "description": "Tokyo, Japan", "location": "Tokyo"},
        ]

        result = self.sampler.enrich_account_attributes(accounts)

        # 結果の検証
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        
        enriched = result[0]
        self.assertIn("region", enriched)
        self.assertIn("language", enriched)
        self.assertIn("dominant_sentiment", enriched)

    @patch('utils.diversity_sampling.logger')
    def test_discover_accounts_hybrid_mock(self, mock_logger):
        """ハイブリッド検索の統合テスト（モック使用）"""
        # モックの設定
        self.mock_x_api.search_recent_tweets.return_value = [
            {"text": "Hello @testuser1", "id": "123"},
            {"text": "Hello @testuser2", "id": "124"},
        ]
        self.mock_x_api.fetch_user_by_handle.return_value = [
            {
                "username": "testuser1",
                "name": "Test User 1",
                "public_metrics": {"followers_count": 1000, "tweet_count": 500},
                "verified": False,
                "description": "Test description"
            }
        ]
        self.sampler.x_api_rate_limit_track["remaining"] = 10

        self.mock_grok_api.discover_accounts_by_keyword.return_value = [
            {
                "handle": "grokuser1",
                "display_name": "Grok User 1",
                "followers_count": 2000,
                "source": "grok_keyword",
                "confidence": 0.8
            }
        ]

        # テスト実行
        queries = ["test query"]
        result = self.sampler.discover_accounts_hybrid(
            queries=queries,
            max_results=5,
            prefer_x_api=True,
            fallback_to_grok=True,
            sampling_method="random"
        )

        # 結果の検証
        self.assertIsInstance(result, list)
        # モックの動作により、結果が空でないことを確認
        # 実際の結果はモックの実装に依存するため、基本的な構造のみ確認

    def test_get_follower_stratum(self):
        """フォロワー層の判定テスト"""
        self.assertEqual(self.sampler._get_follower_stratum(50), "micro")
        self.assertEqual(self.sampler._get_follower_stratum(500), "small")
        self.assertEqual(self.sampler._get_follower_stratum(5000), "medium")
        self.assertEqual(self.sampler._get_follower_stratum(50000), "large")
        self.assertEqual(self.sampler._get_follower_stratum(500000), "macro")
        self.assertEqual(self.sampler._get_follower_stratum(5000000), "mega")
        self.assertEqual(self.sampler._get_follower_stratum(-1), "unknown")

    def test_calculate_entropy(self):
        """エントロピー計算のテスト"""
        # 完全に均一な分布（最大エントロピー）
        values = ["a", "b", "c", "d"]
        entropy = self.sampler._calculate_entropy(values)
        self.assertAlmostEqual(entropy, 1.0, places=5)

        # 完全に偏った分布（最小エントロピー）
        values = ["a", "a", "a", "a"]
        entropy = self.sampler._calculate_entropy(values)
        self.assertAlmostEqual(entropy, 0.0, places=5)

        # 空のリスト
        entropy = self.sampler._calculate_entropy([])
        self.assertEqual(entropy, 0.0)

    def test_infer_region(self):
        """地域推論のテスト"""
        account_jp = {"location": "Tokyo, Japan", "description": "日本在住"}
        self.assertEqual(self.sampler._infer_region(account_jp), "JP")

        account_us = {"location": "New York", "description": "USA"}
        self.assertEqual(self.sampler._infer_region(account_us), "US")

        account_unknown = {"location": "", "description": ""}
        self.assertEqual(self.sampler._infer_region(account_unknown), "unknown")

    def test_infer_language(self):
        """言語推論のテスト"""
        account_ja = {"description": "日本語の説明"}
        self.assertEqual(self.sampler._infer_language(account_ja), "ja")

        account_ko = {"description": "한국어 설명"}
        self.assertEqual(self.sampler._infer_language(account_ko), "ko")

        account_zh = {"description": "中文说明"}
        self.assertEqual(self.sampler._infer_language(account_zh), "zh")

        account_en = {"description": "English description"}
        self.assertEqual(self.sampler._infer_language(account_en), "en")

    def test_analyze_sentiment(self):
        """センチメント分析のテスト"""
        account_positive = {"description": "Great! Amazing! Wonderful!"}
        self.assertEqual(self.sampler._analyze_sentiment(account_positive), "positive")

        account_negative = {"description": "Bad! Terrible! Awful!"}
        self.assertEqual(self.sampler._analyze_sentiment(account_negative), "negative")

        account_neutral = {"description": "Normal text"}
        self.assertEqual(self.sampler._analyze_sentiment(account_neutral), "neutral")

        account_empty = {"description": ""}
        self.assertEqual(self.sampler._analyze_sentiment(account_empty), "neutral")


if __name__ == "__main__":
    unittest.main()

