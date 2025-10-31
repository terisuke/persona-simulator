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


def load_x_api_from_env(use_x_api: bool = True) -> Optional['XAPIClient']:
    """
    環境変数から X API v2 インスタンスをロード (オプション)

    環境変数:
        X_BEARER_TOKEN: X API Bearer Token (オプション)

    Args:
        use_x_api: X APIを使用するかどうか（Falseの場合は常にNoneを返す）

    Returns:
        XAPIClient インスタンスまたは None
    """
    if not use_x_api:
        logger.info("X APIを使用しない設定のためスキップ")
        return None

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


def read_accounts_from_file(
    file_path: str,
    with_metadata: bool = False
) -> List[str] | List[Dict[str, str]]:
    """
    ファイルからアカウントリストを読み込み（Stage 2.5: source 列対応）

    サポート形式:
        - CSV: account/username/name/handle 列を持つCSVファイル
          - オプション: source 列（grok_keyword, grok_random 等）
        - TXT: 1行1アカウントのテキストファイル

    Args:
        file_path: アカウントリストファイルのパス
        with_metadata: True の場合、メタデータ（source 等）を含む Dict のリストを返す

    Returns:
        with_metadata=False: アカウント名のリスト (List[str])
        with_metadata=True: メタデータを含む Dict のリスト (List[Dict[str, str]])
            [{"handle": str, "source": str}, ...]
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

            # source 列の有無を確認（Stage 2.5）
            has_source = 'source' in df.columns

            if with_metadata:
                # メタデータを含む Dict のリストを返す
                for _, row in df.iterrows():
                    handle = str(row[account_col]).strip().lstrip('@')
                    source = str(row['source']) if has_source and not pd.isna(row.get('source')) else 'unknown'
                    if handle:  # 空でない行のみ
                        accounts.append({
                            'handle': handle,
                            'source': source
                        })
            else:
                # 既存の互換性: アカウント名のみのリストを返す
                accounts = df[account_col].dropna().astype(str).tolist()
                # @記号を除去
                accounts = [acc.strip().lstrip('@') for acc in accounts]
        else:
            # テキスト形式 (1行1アカウント)
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]

            if with_metadata:
                # メタデータを含む Dict のリストを返す
                for line in lines:
                    handle = line.lstrip('@')
                    accounts.append({
                        'handle': handle,
                        'source': 'unknown'  # TXT ファイルには source 情報なし
                    })
            else:
                # 既存の互換性: アカウント名のみのリストを返す
                accounts = [line.lstrip('@') for line in lines]

        if with_metadata:
            logger.info(f"{len(accounts)} 件のアカウント（メタデータ付き）を読み込みました: {file_path}")
        else:
            logger.info(f"{len(accounts)} 件のアカウントを読み込みました: {file_path}")

    except Exception as e:
        logger.error(f"アカウントリスト読み込み失敗: {str(e)}")

    return accounts


# =============================================================================
# Stage3 多 SNS 連携: API 初期化 Skeleton
# =============================================================================
#
# 以下は Stage3 で実装予定の他 SNS プラットフォーム向け API クライアント初期化関数です。
# 各関数は環境変数から認証情報を読み込み、対応する API クライアントインスタンスを返します。
#
# 推奨 SDK:
#   - Facebook/Instagram: facebook-sdk または公式 Graph API
#     (https://developers.facebook.com/docs/graph-api/)
#   - LinkedIn: linkedin-api または公式 Marketing Developer Platform
#     (https://learn.microsoft.com/linkedin/marketing/)
#   - TikTok: TikTok for Developers / Research API
#     (https://developers.tiktok.com/)
#
# 実装時の注意:
#   - 各 API のレートリミット管理は個別に実装
#   - 取得したデータは FetchResult.source に適切なソース名を設定
#   - エラーハンドリングを統一（Optional 返却、ログ出力）
# =============================================================================


def load_facebook_api_from_env() -> Optional[Any]:
    """
    環境変数から Facebook Graph API インスタンスをロード（Stage3 実装予定）

    環境変数:
        FACEBOOK_APP_ID: Facebook アプリケーション ID
        FACEBOOK_APP_SECRET: Facebook アプリケーション Secret
        FACEBOOK_ACCESS_TOKEN: Facebook Graph API アクセストークン（オプション）

    Returns:
        Facebook API クライアントインスタンスまたは None

    Raises:
        NotImplementedError: Stage3 で実装予定

    参考:
        https://developers.facebook.com/docs/graph-api/
    """
    logger.warning("Facebook API は Stage3 で実装予定です")
    # Stage3 実装例:
    # try:
    #     app_id = os.environ.get("FACEBOOK_APP_ID")
    #     app_secret = os.environ.get("FACEBOOK_APP_SECRET")
    #     access_token = os.environ.get("FACEBOOK_ACCESS_TOKEN")  # オプション: サーバー間認証で生成も可
    #
    #     if not app_id or not app_secret:
    #         logger.info("FACEBOOK_APP_ID または FACEBOOK_APP_SECRET が設定されていません（オプション）")
    #         return None
    #
    #     from utils.facebook_api import FacebookAPIClient
    #     return FacebookAPIClient(app_id=app_id, app_secret=app_secret, access_token=access_token)
    # except Exception as e:
    #     logger.warning(f"Facebook API初期化エラー(続行可能): {str(e)}")
    #     return None
    return None


def load_instagram_api_from_env() -> Optional[Any]:
    """
    環境変数から Instagram Graph API インスタンスをロード（Stage3 実装予定）

    環境変数:
        INSTAGRAM_APP_ID: Instagram アプリケーション ID（Facebook App ID と同じ）
        INSTAGRAM_APP_SECRET: Instagram アプリケーション Secret（Facebook App Secret と同じ）
        INSTAGRAM_ACCESS_TOKEN: Instagram Graph API アクセストークン（オプション）
        INSTAGRAM_BUSINESS_ACCOUNT_ID: Instagram ビジネスアカウント ID

    Returns:
        Instagram API クライアントインスタンスまたは None

    Raises:
        NotImplementedError: Stage3 で実装予定

    参考:
        https://developers.facebook.com/docs/instagram-api/
    """
    logger.warning("Instagram API は Stage3 で実装予定です")
    # Stage3 実装例:
    # try:
    #     app_id = os.environ.get("INSTAGRAM_APP_ID")
    #     app_secret = os.environ.get("INSTAGRAM_APP_SECRET")
    #     access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")  # オプション: サーバー間認証で生成も可
    #     business_account_id = os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    #
    #     if not app_id or not app_secret or not business_account_id:
    #         logger.info("INSTAGRAM_APP_ID, APP_SECRET, BUSINESS_ACCOUNT_ID のいずれかが設定されていません（オプション）")
    #         return None
    #
    #     from utils.instagram_api import InstagramAPIClient
    #     return InstagramAPIClient(
    #         app_id=app_id,
    #         app_secret=app_secret,
    #         access_token=access_token,
    #         business_account_id=business_account_id
    #     )
    # except Exception as e:
    #     logger.warning(f"Instagram API初期化エラー(続行可能): {str(e)}")
    #     return None
    return None


def load_linkedin_api_from_env() -> Optional[Any]:
    """
    環境変数から LinkedIn Marketing API インスタンスをロード（Stage3 実装予定）

    環境変数:
        LINKEDIN_CLIENT_ID: LinkedIn アプリケーション Client ID
        LINKEDIN_CLIENT_SECRET: LinkedIn アプリケーション Client Secret
        LINKEDIN_ACCESS_TOKEN: LinkedIn OAuth 2.0 アクセストークン（オプション）

    Returns:
        LinkedIn API クライアントインスタンスまたは None

    Raises:
        NotImplementedError: Stage3 で実装予定

    参考:
        https://learn.microsoft.com/linkedin/marketing/
    """
    logger.warning("LinkedIn API は Stage3 で実装予定です")
    # Stage3 実装例:
    # try:
    #     client_id = os.environ.get("LINKEDIN_CLIENT_ID")
    #     client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET")
    #     access_token = os.environ.get("LINKEDIN_ACCESS_TOKEN")  # オプション: OAuth フローで生成も可
    #
    #     if not client_id or not client_secret:
    #         logger.info("LINKEDIN_CLIENT_ID または LINKEDIN_CLIENT_SECRET が設定されていません（オプション）")
    #         return None
    #
    #     from utils.linkedin_api import LinkedInAPIClient
    #     return LinkedInAPIClient(client_id=client_id, client_secret=client_secret, access_token=access_token)
    # except Exception as e:
    #     logger.warning(f"LinkedIn API初期化エラー(続行可能): {str(e)}")
    #     return None
    return None


def load_tiktok_api_from_env() -> Optional[Any]:
    """
    環境変数から TikTok Research API インスタンスをロード（Stage3 実装予定）

    環境変数:
        TIKTOK_APP_ID: TikTok アプリケーション ID（Client Key）
        TIKTOK_APP_SECRET: TikTok アプリケーション Secret（Client Secret）
        TIKTOK_ACCESS_TOKEN: TikTok アクセストークン（オプション）

    Returns:
        TikTok API クライアントインスタンスまたは None

    Raises:
        NotImplementedError: Stage3 で実装予定

    参考:
        https://developers.tiktok.com/
    """
    logger.warning("TikTok API は Stage3 で実装予定です")
    # Stage3 実装例:
    # try:
    #     app_id = os.environ.get("TIKTOK_APP_ID")
    #     app_secret = os.environ.get("TIKTOK_APP_SECRET")
    #     access_token = os.environ.get("TIKTOK_ACCESS_TOKEN")  # オプション: OAuth フローで生成も可
    #
    #     if not app_id or not app_secret:
    #         logger.info("TIKTOK_APP_ID または TIKTOK_APP_SECRET が設定されていません（オプション）")
    #         return None
    #
    #     from utils.tiktok_api import TikTokAPIClient
    #     return TikTokAPIClient(app_id=app_id, app_secret=app_secret, access_token=access_token)
    # except Exception as e:
    #     logger.warning(f"TikTok API初期化エラー(続行可能): {str(e)}")
    #     return None
    return None
