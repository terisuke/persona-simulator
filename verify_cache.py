#!/usr/bin/env python3
"""
キャッシュファイルの内容を検証するスクリプト

使用例:
    # 特定のアカウントを検証
    python verify_cache.py cor_terisuke

    # すべてのキャッシュを検証
    python verify_cache.py --all
"""

import argparse
import pickle
import os
import sys
from pathlib import Path
from datetime import datetime


def verify_cache_file(account: str) -> dict:
    """
    キャッシュファイルの内容を検証

    Args:
        account: アカウント名

    Returns:
        検証結果の辞書
    """
    cache_path = f".cache/posts_{account}.pkl"

    result = {
        'account': account,
        'exists': False,
        'valid_structure': False,
        'has_posts': False,
        'has_persona': False,
        'has_fetched_at': False,
        'posts_count': 0,
        'fetched_at': None,
        'errors': []
    }

    # ファイル存在チェック
    if not os.path.exists(cache_path):
        result['errors'].append(f"キャッシュファイルが見つかりません: {cache_path}")
        return result

    result['exists'] = True

    try:
        # キャッシュ読み込み
        with open(cache_path, 'rb') as f:
            data = pickle.load(f)

        # 構造チェック
        if not isinstance(data, dict):
            result['errors'].append("データが辞書形式ではありません")
            return result

        result['valid_structure'] = True

        # posts チェック
        if 'posts' in data:
            result['has_posts'] = True
            if isinstance(data['posts'], list):
                result['posts_count'] = len(data['posts'])
            else:
                result['errors'].append("posts がリスト形式ではありません")
        else:
            result['errors'].append("posts キーが見つかりません")

        # persona チェック
        if 'persona' in data:
            result['has_persona'] = True
            if not isinstance(data['persona'], dict):
                result['errors'].append("persona が辞書形式ではありません")
        else:
            result['errors'].append("persona キーが見つかりません")

        # fetched_at チェック
        if 'fetched_at' in data:
            result['has_fetched_at'] = True
            result['fetched_at'] = data['fetched_at']

            # ISO形式の検証
            try:
                datetime.fromisoformat(data['fetched_at'])
            except (ValueError, TypeError):
                result['errors'].append(f"fetched_at が不正な形式です: {data['fetched_at']}")
        else:
            result['errors'].append("fetched_at キーが見つかりません")

    except Exception as e:
        result['errors'].append(f"読み込みエラー: {str(e)}")

    return result


def print_verification_result(result: dict):
    """検証結果を表示"""
    print(f"\n{'='*80}")
    print(f"アカウント: @{result['account']}")
    print(f"{'='*80}")

    # 基本情報
    status_icon = "✅" if result['exists'] and not result['errors'] else "❌"
    print(f"{status_icon} キャッシュファイル: {'存在' if result['exists'] else '不在'}")

    if not result['exists']:
        return

    # 構造チェック
    print(f"{'✅' if result['valid_structure'] else '❌'} 辞書構造: {'正常' if result['valid_structure'] else '異常'}")

    # 各キーの存在チェック
    print(f"{'✅' if result['has_posts'] else '❌'} posts キー: {'あり' if result['has_posts'] else 'なし'}")
    if result['has_posts']:
        print(f"   投稿数: {result['posts_count']} 件")

    print(f"{'✅' if result['has_persona'] else '❌'} persona キー: {'あり' if result['has_persona'] else 'なし'}")

    print(f"{'✅' if result['has_fetched_at'] else '❌'} fetched_at キー: {'あり' if result['has_fetched_at'] else 'なし'}")
    if result['has_fetched_at']:
        print(f"   取得日時: {result['fetched_at']}")

    # エラー表示
    if result['errors']:
        print(f"\n⚠️  問題点:")
        for error in result['errors']:
            print(f"   - {error}")
    else:
        print(f"\n✅ すべてのチェックに合格しました！")


def list_all_cache_files() -> list:
    """すべてのキャッシュファイルをリスト"""
    cache_dir = Path(".cache")
    if not cache_dir.exists():
        return []

    cache_files = list(cache_dir.glob("posts_*.pkl"))
    accounts = [f.stem.replace("posts_", "") for f in cache_files]
    return sorted(accounts)


def main():
    parser = argparse.ArgumentParser(
        description='キャッシュファイルの内容を検証',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        'account',
        nargs='?',
        help='検証するアカウント名（省略時は --all を使用）'
    )

    parser.add_argument(
        '--all',
        action='store_true',
        help='すべてのキャッシュファイルを検証'
    )

    args = parser.parse_args()

    if not args.account and not args.all:
        parser.print_help()
        sys.exit(1)

    # すべてのキャッシュを検証
    if args.all:
        accounts = list_all_cache_files()

        if not accounts:
            print("❌ キャッシュファイルが見つかりません")
            sys.exit(1)

        print(f"🔍 {len(accounts)} 件のキャッシュファイルを検証中...")

        results = []
        for account in accounts:
            result = verify_cache_file(account)
            results.append(result)

        # 個別結果を表示
        for result in results:
            print_verification_result(result)

        # サマリー表示
        print(f"\n{'='*80}")
        print("📊 検証サマリー")
        print(f"{'='*80}")

        total = len(results)
        valid = sum(1 for r in results if r['has_posts'] and r['has_persona'] and r['has_fetched_at'])
        invalid = total - valid

        print(f"総数: {total}")
        print(f"✅ 正常: {valid}")
        print(f"❌ 問題あり: {invalid}")

        if invalid == 0:
            print(f"\n🎉 すべてのキャッシュが正常です！")
            sys.exit(0)
        else:
            print(f"\n⚠️  {invalid} 件のキャッシュに問題があります")
            sys.exit(1)

    # 単一アカウントを検証
    else:
        account = args.account.lstrip('@')
        result = verify_cache_file(account)
        print_verification_result(result)

        # 終了コード
        if result['has_posts'] and result['has_persona'] and result['has_fetched_at']:
            sys.exit(0)
        else:
            sys.exit(1)


if __name__ == "__main__":
    main()
