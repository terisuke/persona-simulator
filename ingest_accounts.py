#!/usr/bin/env python3
"""
アカウント一括インポートとキャッシュ前処理 CLI

使用例:
    # CSVファイルから一括取得
    python ingest_accounts.py accounts.csv --batch-size 5

    # テキストファイルから取得
    python ingest_accounts.py accounts.txt --batch-size 10

    # 既存キャッシュを強制再取得
    python ingest_accounts.py accounts.csv --force-refresh

    # Web検索を無効化して高速化
    python ingest_accounts.py accounts.csv --no-web-enrichment
"""

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from enum import Enum

from utils.bootstrap import (
    ensure_cache_dir,
    cache_data,
    load_cache,
    load_grok_api_from_env,
    load_x_api_from_env,
    load_secrets_from_toml,
    read_accounts_from_file,
    DEFAULT_POST_LIMIT
)
from utils.grok_api import GrokAPI
from utils.x_api import XAPIClient

# キャッシュディレクトリを事前に作成（ログ初期化前に必須）
ensure_cache_dir()

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('.cache/ingest.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class FetchStatus(Enum):
    """取得ステータス"""
    SUCCESS = "success"  # 新規取得成功
    CACHED = "cached"    # キャッシュ使用
    FAILED = "failed"    # 失敗


@dataclass
class FetchResult:
    """取得結果"""
    posts: List[Dict]
    persona: Dict
    status: FetchStatus
    source: str  # "twitter" | "web_search" | "generated"


class RateLimitManager:
    """X API レートリミット管理"""

    def __init__(self):
        self.remaining_calls = 15  # X API v2 の初期値
        self.reset_time = None
        self.last_response_headers = {}

    def update_from_headers(self, headers: Dict[str, str]):
        """
        レスポンスヘッダーからレートリミット情報を更新

        Args:
            headers: API レスポンスヘッダー
        """
        if 'x-rate-limit-remaining' in headers:
            self.remaining_calls = int(headers['x-rate-limit-remaining'])
            logger.debug(f"レートリミット残り: {self.remaining_calls}")

        if 'x-rate-limit-reset' in headers:
            reset_timestamp = int(headers['x-rate-limit-reset'])
            self.reset_time = datetime.fromtimestamp(reset_timestamp)
            logger.debug(f"レートリミットリセット: {self.reset_time}")

        self.last_response_headers = headers

    def should_wait(self, threshold: int = 3) -> bool:
        """
        待機が必要かチェック

        Args:
            threshold: 残り呼び出し数の閾値

        Returns:
            待機が必要な場合 True
        """
        return self.remaining_calls <= threshold

    def wait_if_needed(self, threshold: int = 3):
        """
        必要に応じてレートリミットリセットまで待機

        Args:
            threshold: 残り呼び出し数の閾値
        """
        if self.should_wait(threshold):
            if self.reset_time:
                wait_seconds = (self.reset_time - datetime.now()).total_seconds()
                if wait_seconds > 0:
                    logger.warning(
                        f"⏳ レートリミット接近 (残り{self.remaining_calls}回)。"
                        f"{int(wait_seconds)}秒待機します..."
                    )
                    time.sleep(wait_seconds + 5)  # 余裕を持って5秒追加
                    self.remaining_calls = 15  # リセット
                    logger.info("✅ レートリミットリセット完了")
            else:
                # reset_time が不明な場合は安全に15分待機
                logger.warning("⏳ レートリミット接近。安全のため15分待機します...")
                time.sleep(900)
                self.remaining_calls = 15

    def decrement(self):
        """呼び出し回数をデクリメント"""
        if self.remaining_calls > 0:
            self.remaining_calls -= 1


def fetch_account_data(
    grok_api: GrokAPI,
    x_api: Optional[XAPIClient],
    account: str,
    enable_web_enrichment: bool,
    rate_limiter: RateLimitManager,
    force_refresh: bool = False
) -> FetchResult:
    """
    単一アカウントのデータを取得

    Args:
        grok_api: Grok API インスタンス
        x_api: X API インスタンス (オプション)
        account: アカウント名
        enable_web_enrichment: Web検索で情報を強化するか
        rate_limiter: レートリミットマネージャー
        force_refresh: 強制再取得フラグ

    Returns:
        FetchResult: 取得結果（posts, persona, status）
    """
    account_clean = account.lstrip('@')
    cache_key = f"posts_{account_clean}"

    # 既存キャッシュチェック
    if not force_refresh:
        cached = load_cache(cache_key)
        if cached:
            logger.info(f"📦 @{account_clean}: キャッシュから読み込み (スキップ)")
            # キャッシュに保存されたsourceを使用（なければ"unknown"）
            cached_source = cached.get('source', 'unknown')
            return FetchResult(
                posts=cached['posts'],
                persona=cached['persona'],
                status=FetchStatus.CACHED,
                source=cached_source
            )

    # レートリミットチェック
    rate_limiter.wait_if_needed()

    try:
        # 投稿取得
        logger.info(f"📡 @{account_clean}: 投稿取得中...")
        posts = grok_api.fetch_posts(
            account_clean,
            limit=DEFAULT_POST_LIMIT,
            since_date="2024-01-01",
            x_api_client=x_api
        )

        # レートリミット更新 (X API 使用時)
        if x_api and hasattr(grok_api, '_last_response_headers'):
            rate_limiter.update_from_headers(grok_api._last_response_headers)
        rate_limiter.decrement()

        if not posts:
            logger.warning(f"⚠️  @{account_clean}: 投稿が取得できませんでした")
            return FetchResult(posts=[], persona={}, status=FetchStatus.FAILED, source="unknown")

        # 取得方法を判定
        if posts[0]['id'].startswith('web_search_'):
            source = "web_search"
            logger.info(f"✅ @{account_clean}: {len(posts)}件取得 (🌐 Grok Web Search)")
        elif posts[0]['id'].startswith('sample_') or posts[0]['id'].startswith('generated_'):
            source = "generated"
            logger.info(f"📝 @{account_clean}: {len(posts)}件生成 (⚠️ フォールバック)")
        else:
            source = "twitter"
            logger.info(f"✅ @{account_clean}: {len(posts)}件取得 (🔑 X API v2)")

        # ペルソナ生成
        logger.info(f"🧠 @{account_clean}: ペルソナ生成中...")
        persona_profile = grok_api.generate_persona_profile(
            posts,
            account=account_clean,
            enable_web_enrichment=enable_web_enrichment
        )

        if persona_profile:
            enrichment_note = "(マルチプラットフォーム)" if enable_web_enrichment else ""
            logger.info(
                f"✅ @{account_clean}: ペルソナ生成完了{enrichment_note} - "
                f"{persona_profile.get('name', account_clean)}"
            )

        # キャッシュ保存
        data = {
            'posts': posts,
            'persona': persona_profile,
            'fetched_at': datetime.now().isoformat(),
            'source': source  # データソースを保存
        }
        cache_data(cache_key, data)
        logger.info(f"💾 @{account_clean}: キャッシュ保存完了")

        return FetchResult(
            posts=posts,
            persona=persona_profile,
            status=FetchStatus.SUCCESS,
            source=source
        )

    except Exception as e:
        logger.error(f"❌ @{account_clean}: エラー - {str(e)}", exc_info=True)
        return FetchResult(posts=[], persona={}, status=FetchStatus.FAILED, source="unknown")


def process_accounts_batch(
    accounts: List[str],
    grok_api: GrokAPI,
    x_api: Optional[XAPIClient],
    batch_size: int,
    enable_web_enrichment: bool,
    force_refresh: bool
) -> Dict[str, any]:
    """
    アカウントリストをバッチ処理

    Args:
        accounts: アカウント名リスト
        grok_api: Grok API インスタンス
        x_api: X API インスタンス
        batch_size: バッチサイズ
        enable_web_enrichment: Web検索を有効化
        force_refresh: 強制再取得

    Returns:
        処理結果の統計情報
    """
    total = len(accounts)
    success_count = 0
    failed_count = 0
    skipped_count = 0

    # データソース別カウント
    twitter_count = 0
    web_search_count = 0
    generated_count = 0

    rate_limiter = RateLimitManager()

    logger.info("=" * 80)
    logger.info(f"🚀 一括処理開始: {total}件のアカウント")
    logger.info(f"   バッチサイズ: {batch_size}")
    logger.info(f"   Web検索: {'有効' if enable_web_enrichment else '無効'}")
    logger.info(f"   強制再取得: {'有効' if force_refresh else '無効'}")
    logger.info("=" * 80)

    start_time = time.time()

    for i, account in enumerate(accounts, 1):
        logger.info(f"\n[{i}/{total}] 処理中: @{account}")

        result = fetch_account_data(
            grok_api=grok_api,
            x_api=x_api,
            account=account,
            enable_web_enrichment=enable_web_enrichment,
            rate_limiter=rate_limiter,
            force_refresh=force_refresh
        )

        if result.status == FetchStatus.SUCCESS:
            success_count += 1
        elif result.status == FetchStatus.CACHED:
            skipped_count += 1
        elif result.status == FetchStatus.FAILED:
            failed_count += 1

        # データソース別カウント
        if result.source == "twitter":
            twitter_count += 1
        elif result.source == "web_search":
            web_search_count += 1
        elif result.source == "generated":
            generated_count += 1

        # 進捗表示
        progress_pct = (i / total) * 100
        logger.info(
            f"📊 進捗: {i}/{total} ({progress_pct:.1f}%) | "
            f"成功: {success_count} | スキップ: {skipped_count} | 失敗: {failed_count}"
        )

        # バッチ間の待機 (X API負荷軽減)
        if i % batch_size == 0 and i < total:
            wait_time = 2
            logger.info(f"⏸️  バッチ{i // batch_size}完了。{wait_time}秒待機...")
            time.sleep(wait_time)

    elapsed_time = time.time() - start_time

    # 結果サマリー
    logger.info("\n" + "=" * 80)
    logger.info("🎉 一括処理完了")
    logger.info("=" * 80)
    logger.info(f"総アカウント数: {total}")
    logger.info(f"  ✅ 成功: {success_count}")
    logger.info(f"  📦 スキップ (キャッシュ使用): {skipped_count}")
    logger.info(f"  ❌ 失敗: {failed_count}")
    logger.info("")
    logger.info("📊 データソース内訳:")
    logger.info(f"  🔑 X API (Twitter): {twitter_count}")
    logger.info(f"  🌐 Grok Web Search: {web_search_count}")
    logger.info(f"  📝 フォールバック生成: {generated_count}")

    # 実データ比率を計算
    real_data_count = twitter_count + web_search_count
    if total > 0:
        real_data_ratio = (real_data_count / total) * 100
        logger.info(f"  💡 実データ比率: {real_data_ratio:.1f}% ({real_data_count}/{total})")

    logger.info("")
    logger.info(f"処理時間: {elapsed_time:.1f}秒 ({elapsed_time / 60:.1f}分)")
    logger.info("=" * 80)

    return {
        'total': total,
        'success': success_count,
        'skipped': skipped_count,
        'failed': failed_count,
        'twitter': twitter_count,
        'web_search': web_search_count,
        'generated': generated_count,
        'real_data_ratio': (real_data_count / total * 100) if total > 0 else 0,
        'elapsed_time': elapsed_time
    }


def main():
    """メインエントリーポイント"""
    parser = argparse.ArgumentParser(
        description='アカウント一括インポートとキャッシュ前処理 CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  # CSVファイルから一括取得 (デフォルト設定)
  python ingest_accounts.py accounts.csv

  # バッチサイズを指定
  python ingest_accounts.py accounts.csv --batch-size 10

  # 既存キャッシュを強制再取得
  python ingest_accounts.py accounts.csv --force-refresh

  # Web検索を無効化して高速化
  python ingest_accounts.py accounts.csv --no-web-enrichment

ファイル形式:
  CSV: account, username, name, handle のいずれかの列を含む
  TXT: 1行1アカウント (# で始まる行はコメント)
        """
    )

    parser.add_argument(
        'accounts_file',
        type=str,
        help='アカウントリストファイル (CSV または TXT)'
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=5,
        help='バッチサイズ (デフォルト: 5、X API レート制限対策)'
    )

    parser.add_argument(
        '--force-refresh',
        action='store_true',
        help='既存キャッシュを無視して強制再取得'
    )

    parser.add_argument(
        '--no-web-enrichment',
        action='store_true',
        help='Web検索による情報強化を無効化 (高速化)'
    )

    parser.add_argument(
        '--secrets',
        type=str,
        default='.streamlit/secrets.toml',
        help='secrets.toml のパス (デフォルト: .streamlit/secrets.toml)'
    )

    parser.add_argument(
        '--log-level',
        type=str,
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='ログレベル (デフォルト: INFO)'
    )

    args = parser.parse_args()

    # ログレベル設定
    logging.getLogger().setLevel(getattr(logging, args.log_level))

    # secrets.toml から環境変数を読み込み
    logger.info(f"📖 設定ファイル読み込み: {args.secrets}")
    secrets = load_secrets_from_toml(args.secrets)
    if not secrets:
        logger.error("❌ secrets.toml が読み込めませんでした。環境変数を確認してください。")
        sys.exit(1)

    # API 初期化
    logger.info("🔧 API初期化中...")
    grok_api = load_grok_api_from_env()
    if not grok_api:
        logger.error("❌ Grok API の初期化に失敗しました。GROK_API_KEY を確認してください。")
        sys.exit(1)

    x_api = load_x_api_from_env()
    if x_api:
        logger.info("✅ X API v2 が利用可能です")
    else:
        logger.info("ℹ️  X API v2 が設定されていません (Grok Web Search を使用)")

    # アカウントリスト読み込み
    logger.info(f"📋 アカウントリスト読み込み: {args.accounts_file}")
    accounts = read_accounts_from_file(args.accounts_file)

    if not accounts:
        logger.error("❌ アカウントが読み込めませんでした。ファイルを確認してください。")
        sys.exit(1)

    logger.info(f"✅ {len(accounts)} 件のアカウントを読み込みました")

    # バッチ処理実行
    results = process_accounts_batch(
        accounts=accounts,
        grok_api=grok_api,
        x_api=x_api,
        batch_size=args.batch_size,
        enable_web_enrichment=not args.no_web_enrichment,
        force_refresh=args.force_refresh
    )

    # 終了コード
    if results['failed'] > 0:
        logger.warning(f"⚠️  {results['failed']} 件のアカウントで処理が失敗しました")
        sys.exit(1)
    else:
        logger.info("✅ すべてのアカウントの処理が完了しました")
        sys.exit(0)


if __name__ == "__main__":
    main()
