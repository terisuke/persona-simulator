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
import os
import logging
import sys
import time
from collections import Counter
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
from utils.grok_api import GrokAPI, PRESET_KEYWORDS
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

# 生成フォールバックの許可フラグ（後方互換性のため残置）。
# 現在は常に False（実データのみ運用）。
ALLOW_GENERATED_FLAG: bool = False


def delete_cache_file(cache_key: str):
    """対象キャッシュファイルを削除"""
    cache_path = os.path.join('.cache', f"{cache_key}.pkl")
    if os.path.exists(cache_path):
        try:
            os.remove(cache_path)
            logger.info(f"キャッシュ削除: {cache_key}")
        except Exception as error:
            logger.warning(f"キャッシュ削除失敗({cache_key}): {error}")


class FetchStatus(Enum):
    """取得ステータス"""
    SUCCESS = "success"  # 新規取得成功
    CACHED = "cached"    # キャッシュ使用
    FAILED = "failed"    # 失敗


@dataclass
class FetchResult:
    """取得結果

    Stage3 多 SNS 連携に向けた拡張ポイント:
    - source フィールドは以下の値をサポート予定:
      - "twitter": X API v2 経由で取得
      - "web_search": Grok Web Search 経由で取得
      - "facebook": Facebook Graph API 経由（Stage3）
      - "instagram": Instagram Graph API 経由（Stage3）
      - "linkedin": LinkedIn Marketing API 経由（Stage3）
      - "tiktok": TikTok Research API 経由（Stage3）
    - 将来的には複数ソースの統合（例: "twitter,linkedin"）も検討
    """
    posts: List[Dict]
    persona: Dict
    status: FetchStatus
    source: str  # "twitter" | "web_search" | "facebook" | "instagram" | "linkedin" | "tiktok"


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
            cached_posts = cached.get('posts', [])
            if cached_posts and (cached_posts[0].get('id', '').startswith('sample_') or cached_posts[0].get('id', '').startswith('generated_')):
                logger.warning(
                    f"⚠️ @{account_clean}: キャッシュに生成データが含まれているため削除し再取得します。"
                )
                delete_cache_file(cache_key)
            else:
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
            x_api_client=x_api,
            allow_generated=ALLOW_GENERATED_FLAG
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
            
            # quality_scoreを評価してペルソナに付与
            account_info = {
                "handle": account_clean,
                "description": persona_profile.get('background', ''),
                "confidence": 0.8  # デフォルト値（発見時には既に評価済みの場合もある）
            }
            quality_result = grok_api.check_account_quality(
                account_clean,
                account_info,
                x_api_client=x_api
            )
            if quality_result:
                persona_profile['quality_score'] = quality_result['score']
                persona_profile['quality_reasons'] = quality_result.get('reasons', [])
                logger.info(f"📊 @{account_clean}: quality_score={quality_result['score']:.2f}を付与")

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


def discover_and_save_accounts(
    grok_api: GrokAPI,
    keyword: Optional[str],
    random: bool,
    max_results: int,
    dry_run: bool,
    category: Optional[str] = None,
    preset: Optional[str] = None,
    x_api: Optional[XAPIClient] = None,
    diversity_sampling: bool = False,
    sampling_method: str = "stratified",
    prefer_x_api: bool = True,
    fallback_to_grok: bool = True,
    quotas: Optional[Dict] = None
) -> Optional[str]:
    """
    Grok Web Search でアカウント候補を発見し、CSV/TXT に保存

    Args:
        grok_api: Grok API インスタンス
        keyword: 検索キーワード (keyword モード時)
        random: ランダムモード
        max_results: 最大取得件数
        dry_run: モックデータを使用
        category: カテゴリ指定（ランダムモード時）
        preset: プリセットキーワード指定

    Returns:
        保存したファイルパス（失敗時は None）
    """
    from datetime import datetime
    import os
    import csv

    # .cache/discover_results ディレクトリを作成（UI と共通）
    discover_dir = os.path.join(".cache", "discover_results")
    if not os.path.exists(discover_dir):
        os.makedirs(discover_dir)
        logger.info(f"📁 ディレクトリ作成: {discover_dir}")

    diversity_metrics: Dict[str, float] = {}
    diversity_report_path: Optional[str] = None

    # アカウント発見
    if diversity_sampling:
        logger.info(
            "🎲 多様性サンプリングモード (ハイブリッド) を開始 "
            f"(sampling_method={sampling_method}, prefer_x_api={prefer_x_api}, "
            f"fallback_to_grok={fallback_to_grok})"
        )
        accounts = grok_api.discover_accounts_with_diversity_hybrid(
            max_results=max_results,
            sampling_method=sampling_method,
            x_api_client=x_api,
            quotas=quotas,
            prefer_x_api=prefer_x_api,
            fallback_to_grok=fallback_to_grok
        )
        mode = "diversity_hybrid"
        filename_base = f"diversity_{sampling_method}_hybrid_accounts"
    elif preset:
        # プリセットキーワードを使用
        actual_keyword = PRESET_KEYWORDS[preset]
        logger.info(f"🔍 プリセット '{preset}' ({actual_keyword}) でアカウント発見中...")
        accounts = grok_api.discover_accounts_by_keyword(
            preset,  # プリセット名を渡す
            max_results=max_results,
            dry_run=dry_run,
            x_api_client=x_api
        )
        mode = "preset"
        filename_base = f"preset_{preset}"
    elif keyword:
        logger.info(f"🔍 キーワード '{keyword}' でアカウント発見中...")
        accounts = grok_api.discover_accounts_by_keyword(
            keyword,
            max_results=max_results,
            dry_run=dry_run,
            x_api_client=x_api
        )
        mode = "keyword"
        filename_base = f"keyword_{keyword.replace(' ', '_')}"
    else:  # random
        logger.info(f"🎲 ランダムにアカウント発見中...")
        accounts = grok_api.discover_accounts_random(
            max_results=max_results,
            dry_run=dry_run,
            category=category,
            x_api_client=x_api
        )
        mode = "random"
        filename_base = "random_accounts"
        if category:
            filename_base = f"random_{category}_accounts"

    if not accounts:
        logger.error("❌ アカウントが見つかりませんでした")
        return None

    # タイムスタンプ付きファイル名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(discover_dir, f"{filename_base}_{timestamp}.csv")
    txt_path = os.path.join(discover_dir, f"{filename_base}_{timestamp}.txt")

    # CSV 保存（quality_score も含める）
    fieldnames = [
        'handle',
        'display_name',
        'confidence',
        'profile_url',
        'description',
        'source',
        'quality_score',
        'diversity_score',
        'followers_count',
        'tweet_count',
        'region',
        'language',
        'dominant_sentiment',
        'last_tweet_at',
        'account_created_at'
    ]
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for account in accounts:
            writer.writerow(account)

    logger.info(f"💾 CSV 保存: {csv_path} ({len(accounts)}件)")

    # TXT 保存（handle のみ、1行1アカウント）
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"# Discovered accounts via Grok {mode} search\n")
        f.write(f"# Generated: {datetime.now().isoformat()}\n")
        f.write(f"# Total: {len(accounts)} accounts\n")
        f.write("#\n")
        for account in accounts:
            f.write(f"{account['handle']}\n")

    logger.info(f"💾 TXT 保存: {txt_path} ({len(accounts)}件)")

    # 多様性レポート作成
    if diversity_sampling:
        from utils.diversity_sampling import DiversitySampler

        sampler = DiversitySampler(x_api_client=x_api, grok_api=grok_api)
        diversity_metrics = sampler.calculate_diversity_metrics(
            accounts,
            attributes=['followers', 'region', 'language', 'sentiment']
        )
        diversity_report_path = csv_path.replace('.csv', '_diversity_report.txt')

        with open(diversity_report_path, 'w', encoding='utf-8') as f:
            f.write("=== ハイブリッド多様性サンプリングレポート ===\n\n")
            f.write(f"サンプリング手法: {sampling_method}\n")
            f.write(f"X API優先: {prefer_x_api}\n")
            f.write(f"Grokフォールバック: {fallback_to_grok}\n")
            f.write(f"総アカウント数: {len(accounts)}\n\n")
            f.write("多様性指標:\n")
            for key, value in diversity_metrics.items():
                f.write(f"  {key}: {value:.3f}\n")
            f.write("\nデータソース分布:\n")
            source_counts = Counter(acc.get('source', 'unknown') for acc in accounts)
            for source, count in source_counts.items():
                f.write(f"  {source}: {count}件\n")

        logger.info(f"📊 多様性レポート保存: {diversity_report_path}")

    # 統計表示
    logger.info("")
    logger.info("=" * 80)
    logger.info("📊 発見結果サマリー")
    logger.info("=" * 80)
    logger.info(f"モード: {mode}")
    logger.info(f"発見件数: {len(accounts)}")
    if any(a.get('confidence') is not None for a in accounts):
        avg_conf = sum(a.get('confidence', 0.0) for a in accounts) / len(accounts)
        logger.info(f"平均信頼度: {avg_conf:.2f}")
    if diversity_metrics:
        logger.info("多様性指標:")
        for key, value in diversity_metrics.items():
            logger.info(f"  {key}: {value:.3f}")
    source_distribution = Counter(acc.get('source', 'unknown') for acc in accounts)
    if source_distribution:
        logger.info("データソース内訳:")
        for source, count in source_distribution.items():
            logger.info(f"  {source}: {count}件")
    logger.info(f"CSV: {csv_path}")
    logger.info(f"TXT: {txt_path}")
    if diversity_report_path:
        logger.info(f"Diversity Report: {diversity_report_path}")
    logger.info("=" * 80)
    logger.info("")
    logger.info("💡 次のステップ:")
    logger.info(f"  python ingest_accounts.py {txt_path}")
    logger.info("=" * 80)

    return csv_path


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
    
    # 未確定数とquality_scoreの集計
    unverified_count = 0
    quality_scores = []

    rate_limiter = RateLimitManager()

    logger.info("=" * 80)
    logger.info(f"🚀 一括処理開始: {total}件のアカウント")
    logger.info(f"   バッチサイズ: {batch_size}")
    logger.info(f"   Web検索: {'有効' if enable_web_enrichment else '無効'}")
    logger.info(f"   強制再取得: {'有効' if force_refresh else '無効'}")
    logger.info(f"   X API使用: {x_api is not None}")
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
        
        # 未確定数（ペルソナがNoneまたは空）
        if not result.persona or len(result.persona) == 0:
            unverified_count += 1
        
        # quality_scoreがあれば集計（キャッシュから読み込んだ場合も含む）
        if result.persona and 'quality_score' in result.persona:
            quality_scores.append(result.persona['quality_score'])

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
    logger.info(f"X API使用: {x_api is not None}")
    logger.info("")
    logger.info("📊 データソース内訳:")
    logger.info(f"  🔑 X API (Twitter): {twitter_count}")
    logger.info(f"  🌐 Grok Web Search: {web_search_count}")
    logger.info(f"  📝 フォールバック生成: {generated_count}")

    # 実データ比率と生成データ比率を計算
    real_data_count = twitter_count + web_search_count
    if total > 0:
        real_data_ratio = (real_data_count / total) * 100
        generated_data_ratio = (generated_count / total) * 100
        logger.info(f"  💡 実データ比率: {real_data_ratio:.1f}% ({real_data_count}/{total})")
        logger.info(f"  ⚠️  生成データ比率: {generated_data_ratio:.1f}% ({generated_count}/{total})")
    
    # 未確定数
    logger.info("")
    logger.info(f"📊 品質指標:")
    logger.info(f"  ⚠️  未確定ペルソナ: {unverified_count}件")
    
    # 平均quality_score
    if quality_scores:
        avg_quality = sum(quality_scores) / len(quality_scores)
        median_quality = sorted(quality_scores)[len(quality_scores) // 2] if quality_scores else 0.0
        logger.info(f"  📈 平均quality_score: {avg_quality:.2f}")
        logger.info(f"  📊 中央値quality_score: {median_quality:.2f} (対象: {len(quality_scores)}件)")

    logger.info("")
    logger.info(f"処理時間: {elapsed_time:.1f}秒 ({elapsed_time / 60:.1f}分)")
    logger.info("=" * 80)

    generated_data_ratio = (generated_count / total * 100) if total > 0 else 0
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else None
    median_quality = sorted(quality_scores)[len(quality_scores) // 2] if quality_scores else None
    
    return {
        'total': total,
        'success': success_count,
        'skipped': skipped_count,
        'failed': failed_count,
        'twitter': twitter_count,
        'web_search': web_search_count,
        'generated': generated_count,
        'real_data_ratio': (real_data_count / total * 100) if total > 0 else 0,
        'generated_data_ratio': generated_data_ratio,
        'unverified_count': unverified_count,
        'avg_quality_score': avg_quality,
        'median_quality_score': median_quality,
        'quality_score_count': len(quality_scores),
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
        nargs='?',  # optional（discover モード時は不要）
        help='アカウントリストファイル (CSV または TXT)'
    )

    # Stage 2.5: アカウント発見機能
    discover_group = parser.add_argument_group('アカウント発見（Stage 2.5）')
    discover_group.add_argument(
        '--discover-keyword',
        type=str,
        metavar='KEYWORD',
        help='キーワードでアカウント候補を発見（例: "AI engineer"）'
    )
    discover_group.add_argument(
        '--discover-random',
        action='store_true',
        help='ランダムにアカウント候補を発見（複数プリセットクエリを実行）'
    )
    discover_group.add_argument(
        '--max-results',
        type=int,
        default=50,
        help='発見する最大アカウント数（デフォルト: 50, 上限: 100）'
    )
    discover_group.add_argument(
        '--dry-run',
        action='store_true',
        help='モックデータを使用（Grok API を呼ばない、テスト用）'
    )
    discover_group.add_argument(
        '--category',
        type=str,
        choices=['tech', 'business', 'creative', 'science', 'developer', 'product', 'community'],
        help='カテゴリ指定（ランダム検索時）- tech, business, creative, science, developer, product, community'
    )
    discover_group.add_argument(
        '--preset',
        type=str,
        choices=list(PRESET_KEYWORDS.keys()),
        help=f'プリセットキーワード指定 - {", ".join(sorted(PRESET_KEYWORDS.keys()))}'
    )
    discover_group.add_argument(
        '--diversity-sampling',
        action='store_true',
        help='多様性を担保したハイブリッドサンプリングでアカウント候補を発見'
    )
    discover_group.add_argument(
        '--sampling-method',
        type=str,
        choices=['stratified', 'quota', 'random'],
        default='stratified',
        help='多様性サンプリング時の手法（デフォルト: stratified）'
    )
    discover_group.add_argument(
        '--prefer-x-api',
        dest='prefer_x_api',
        action='store_true',
        help='X APIを優先して使用（デフォルト: 有効）'
    )
    discover_group.add_argument(
        '--no-prefer-x-api',
        dest='prefer_x_api',
        action='store_false',
        help='X API優先を無効化'
    )
    discover_group.add_argument(
        '--no-fallback-grok',
        action='store_true',
        help='Grok Web Searchへのフォールバックを無効化'
    )

    parser.set_defaults(prefer_x_api=True)

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

    # 生成フォールバック許可/不許可の切替（相互排他）
    gen_group = parser.add_mutually_exclusive_group()
    gen_group.add_argument(
        '--allow-generated',
        action='store_true',
        help='【非推奨】生成フォールバックを許可（現在は無効化済み）'
    )
    gen_group.add_argument(
        '--disallow-generated',
        action='store_true',
        help='生成フォールバックを明示的に禁止（デフォルト）'
    )

    # X API使用可否の切替（相互排他）
    x_api_group = parser.add_mutually_exclusive_group()
    x_api_group.add_argument(
        '--use-x-api',
        action='store_true',
        help='X APIを使用する（明示的に有効化）'
    )
    x_api_group.add_argument(
        '--no-x-api',
        action='store_true',
        help='X APIを使用しない（無効化）'
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

    # MODE に関わらず生成フォールバックは常に無効化
    mode_val = (secrets.get('MODE') or os.environ.get('MODE') or 'dev').lower()
    global ALLOW_GENERATED_FLAG
    ALLOW_GENERATED_FLAG = False
    if args.allow_generated:
        logger.warning("⚠️ --allow-generated は無効です。実データのみを使用します。")
    elif args.disallow_generated:
        logger.info("--disallow-generated 指定: 生成フォールバックは無効 (既定値)")
    else:
        logger.info("生成フォールバック許可: False（固定運用）")

    # X API使用可否を決定
    if args.use_x_api:
        use_x_api = True
        logger.info("X API使用: True (--use-x-api指定)")
    elif args.no_x_api:
        use_x_api = False
        logger.info("X API使用: False (--no-x-api指定)")
    else:
        # 未指定の場合は従来どおりX_BEARER_TOKENの存在で判定
        bearer_token = os.environ.get("X_BEARER_TOKEN")
        use_x_api = bool(bearer_token and bearer_token != "your_x_bearer_token_here")
        logger.info(f"X API使用: {use_x_api} (X_BEARER_TOKEN{'設定済み' if use_x_api else '未設定'})")

    # API 初期化
    logger.info("🔧 API初期化中...")
    grok_api = load_grok_api_from_env()
    if not grok_api:
        logger.error("❌ Grok API の初期化に失敗しました。GROK_API_KEY を確認してください。")
        sys.exit(1)

    # =============================================================================
    # Stage 2.5: Discover モード（アカウント発見）
    # =============================================================================
    if args.discover_keyword or args.discover_random or args.preset or args.diversity_sampling:
        logger.info("=" * 80)
        logger.info("🔍 Stage 2.5: アカウント発見モード")
        logger.info("=" * 80)

        # 引数の検証（同時に複数の発見モードを指定しない）
        mode_count = sum([
            bool(args.discover_keyword),
            bool(args.discover_random),
            bool(args.preset),
            bool(args.diversity_sampling)
        ])
        if mode_count > 1:
            logger.error("❌ --discover-keyword, --discover-random, --preset, --diversity-sampling は同時に1つだけ指定してください")
            sys.exit(1)

        # アカウント発見実行
        if use_x_api:
            x_api = load_x_api_from_env(use_x_api=True)
        else:
            x_api = None
            logger.info("X APIを無効化しています（--no-x-api指定またはX_BEARER_TOKEN未設定）")
        
        saved_path = discover_and_save_accounts(
            grok_api=grok_api,
            keyword=args.discover_keyword,
            random=args.discover_random,
            max_results=min(args.max_results, 100),  # 上限100
            dry_run=args.dry_run,
            category=args.category,
            preset=args.preset,
            x_api=x_api,
            diversity_sampling=args.diversity_sampling,
            sampling_method=args.sampling_method,
            prefer_x_api=args.prefer_x_api,
            fallback_to_grok=not args.no_fallback_grok
        )

        if saved_path:
            logger.info("✅ アカウント発見が完了しました")
            sys.exit(0)
        else:
            logger.error("❌ アカウント発見に失敗しました")
            sys.exit(1)

    # =============================================================================
    # 通常モード（アカウント一括処理）
    # =============================================================================
    if not args.accounts_file:
        logger.error("❌ accounts_file が指定されていません。--discover-keyword または --discover-random を使用するか、ファイルを指定してください。")
        parser.print_help()
        sys.exit(1)

    if use_x_api:
        x_api = load_x_api_from_env(use_x_api=True)
        if x_api:
            logger.info("✅ X API v2 が利用可能です")
        else:
            logger.info("ℹ️  X API v2 が設定されていません (Grok Web Search を使用)")
    else:
        x_api = None
        logger.info("X APIを無効化しています（--no-x-api指定またはX_BEARER_TOKEN未設定）")

    # アカウントリスト読み込み（Stage 2.5: discovery source の統計を取得）
    logger.info(f"📋 アカウントリスト読み込み: {args.accounts_file}")

    # まず metadata 付きで読み込んで discovery source を確認
    accounts_with_meta = read_accounts_from_file(args.accounts_file, with_metadata=True)
    accounts = [acc['handle'] if isinstance(acc, dict) else acc for acc in accounts_with_meta]

    if not accounts:
        logger.error("❌ アカウントが読み込めませんでした。ファイルを確認してください。")
        sys.exit(1)

    logger.info(f"✅ {len(accounts)} 件のアカウントを読み込みました")

    # Discovery source の統計を表示（Stage 2.5）
    if isinstance(accounts_with_meta[0], dict):
        from collections import Counter
        source_counts = Counter([acc['source'] for acc in accounts_with_meta])
        if any(s in source_counts for s in ['grok_keyword', 'grok_random']):
            logger.info("📊 発見元内訳:")
            for source, count in sorted(source_counts.items()):
                if source in ['grok_keyword', 'grok_random']:
                    logger.info(f"  🔍 {source}: {count}")
                elif source == 'unknown':
                    logger.info(f"  ❓ {source}: {count}")

    # バッチ処理実行
    results = process_accounts_batch(
        accounts=accounts,
        grok_api=grok_api,
        x_api=x_api,
        batch_size=args.batch_size,
        enable_web_enrichment=not args.no_web_enrichment,
        force_refresh=args.force_refresh
    )

    # 生成データ率の閾値チェック（デフォルト: 5%）
    GENERATED_RATIO_THRESHOLD = 5.0  # 5%超過でエラー
    generated_ratio = results.get('generated_data_ratio', 0.0)
    
    if generated_ratio > GENERATED_RATIO_THRESHOLD:
        logger.error("")
        logger.error("=" * 80)
        logger.error(f"❌ 生成データ率が閾値を超過: {generated_ratio:.1f}% > {GENERATED_RATIO_THRESHOLD}%")
        logger.error("=" * 80)
        logger.error("運用モードでは生成データは許可されていません。")
        logger.error("実データ取得を再試行するか、--disallow-generated フラグを確認してください。")
        logger.error("=" * 80)
        sys.exit(1)
    
    # 終了コード
    if results['failed'] > 0:
        logger.warning(f"⚠️  {results['failed']} 件のアカウントで処理が失敗しました")
        sys.exit(1)
    else:
        logger.info("✅ すべてのアカウントの処理が完了しました")
        sys.exit(0)


if __name__ == "__main__":
    main()
