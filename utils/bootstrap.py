"""
共通の初期化とキャッシュ管理ユーティリティ

Streamlit アプリと CLI の両方で使用可能な共通ロジック
"""

import os
import pickle
import logging
from typing import Optional, Dict, List, Any
from pathlib import Path

logger = logging.getLogger(__name__)

# デフォルト設定
CACHE_DIR = ".cache"
DEFAULT_POST_LIMIT = 20


def ensure_cache_dir():
    """キャッシュディレクトリの存在を確認・作成"""
    if not os.path.exists(CACHE_DIR):
        os.makedirs(CACHE_DIR)
        logger.info(f"キャッシュディレクトリ作成: {CACHE_DIR}")


def cache_data(key: str, data: Any):
    """データをキャッシュに保存"""
    ensure_cache_dir()
    cache_path = os.path.join(CACHE_DIR, f"{key}.pkl")
    try:
        with open(cache_path, 'wb') as f:
            pickle.dump(data, f)
        logger.info(f"キャッシュ保存: {key}")
    except Exception as e:
        logger.warning(f"キャッシュ保存失敗: {str(e)}")


def load_cache(key: str) -> Optional[Any]:
    """キャッシュからデータをロード"""
    cache_path = os.path.join(CACHE_DIR, f"{key}.pkl")
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'rb') as f:
                data = pickle.load(f)
            logger.info(f"キャッシュロード: {key}")
            return data
        except Exception as e:
            logger.warning(f"キャッシュロード失敗: {str(e)}")
    return None


def load_grok_api_from_env() -> Optional['GrokAPI']:
    """
    環境変数から Grok API インスタンスをロード

    環境変数:
        GROK_API_KEY: Grok API キー (必須)
        GROK_MODEL: Grok モデル名 (オプション)

    Returns:
        GrokAPI インスタンスまたは None
    """
    from utils.grok_api import GrokAPI

    try:
        api_key = os.environ.get("GROK_API_KEY")
        if not api_key:
            logger.error("GROK_API_KEY 環境変数が設定されていません")
            return None

        model = os.environ.get("GROK_MODEL", None)
        grok = GrokAPI(api_key, model=model)
        logger.info(f"Grok API初期化完了: モデル={grok.model}")
        return grok
    except Exception as e:
        logger.error(f"Grok API初期化失敗: {str(e)}")
        return None


def load_x_api_from_env() -> Optional['XAPIClient']:
    """
    環境変数から X API v2 インスタンスをロード (オプション)

    環境変数:
        X_BEARER_TOKEN: X API Bearer Token (オプション)

    Returns:
        XAPIClient インスタンスまたは None
    """
    from utils.x_api import XAPIClient

    try:
        bearer_token = os.environ.get("X_BEARER_TOKEN")
        if not bearer_token or bearer_token == "your_x_bearer_token_here":
            logger.info("X API Bearer Token が設定されていません(オプション)")
            return None
        return XAPIClient(bearer_token)
    except Exception as e:
        logger.warning(f"X API初期化エラー(続行可能): {str(e)}")
        return None


def load_secrets_from_toml(toml_path: str = ".streamlit/secrets.toml") -> Dict[str, str]:
    """
    secrets.toml ファイルから設定を読み込み、環境変数に設定

    Args:
        toml_path: secrets.toml のパス

    Returns:
        読み込んだ設定の辞書
    """
    if not os.path.exists(toml_path):
        logger.warning(f"{toml_path} が見つかりません")
        return {}

    try:
        import tomli
    except ImportError:
        try:
            import tomllib as tomli
        except ImportError:
            logger.warning("TOML パーサーが見つかりません。pip install tomli を実行してください")
            return {}

    try:
        with open(toml_path, 'rb') as f:
            secrets = tomli.load(f)

        # 環境変数に設定
        for key, value in secrets.items():
            if isinstance(value, str):
                os.environ[key] = value
                logger.debug(f"環境変数設定: {key}")

        return secrets
    except Exception as e:
        logger.error(f"secrets.toml 読み込み失敗: {str(e)}")
        return {}


def read_accounts_from_file(file_path: str) -> List[str]:
    """
    ファイルからアカウントリストを読み込み

    サポート形式:
        - CSV: account列を持つCSVファイル
        - TXT: 1行1アカウントのテキストファイル

    Args:
        file_path: アカウントリストファイルのパス

    Returns:
        アカウント名のリスト
    """
    accounts = []
    file_path_obj = Path(file_path)

    if not file_path_obj.exists():
        logger.error(f"ファイルが見つかりません: {file_path}")
        return accounts

    try:
        if file_path.endswith('.csv'):
            # CSV形式
            import pandas as pd
            df = pd.read_csv(file_path)

            # account または username 列を探す
            account_col = None
            for col in ['account', 'username', 'name', 'handle']:
                if col in df.columns:
                    account_col = col
                    break

            if account_col is None:
                logger.error(f"CSV に account/username/name/handle 列が見つかりません")
                return accounts

            accounts = df[account_col].dropna().astype(str).tolist()
        else:
            # テキスト形式 (1行1アカウント)
            with open(file_path, 'r', encoding='utf-8') as f:
                accounts = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        # @記号を除去してクリーンアップ
        accounts = [acc.lstrip('@') for acc in accounts]
        logger.info(f"{len(accounts)} 件のアカウントを読み込みました: {file_path}")

    except Exception as e:
        logger.error(f"アカウントリスト読み込み失敗: {str(e)}")

    return accounts
