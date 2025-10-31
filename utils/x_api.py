"""
X API v2連携モジュール
実際のX投稿を取得
"""

import requests
import logging
import json
from typing import List, Dict, Optional
from datetime import datetime, timezone
from .error_handler import ErrorHandler, PerformanceLogger, APIConnectionError

logger = logging.getLogger(__name__)


def log_structured_api_call(
    source: str,
    account: str = None,
    rate_limit_remaining: Optional[int] = None,
    reset_at: Optional[str] = None,
    generated_flag: bool = False,
    **kwargs
):
    """
    構造化ログを出力
    
    Args:
        source: データソース（twitter/web_search/generated）
        account: アカウント名
        rate_limit_remaining: レートリミット残り回数
        reset_at: リセット時刻（ISO形式文字列）
        generated_flag: 生成データフラグ
        **kwargs: その他のメタデータ
    """
    log_data = {
        "source": source,
        "generated_flag": generated_flag,
    }
    
    if account:
        log_data["account"] = account
    
    if rate_limit_remaining is not None:
        log_data["rate_limit_remaining"] = rate_limit_remaining
    
    if reset_at:
        log_data["reset_at"] = reset_at
    
    if kwargs:
        log_data.update(kwargs)
    
    logger.info(f"[STRUCTURED] {json.dumps(log_data, ensure_ascii=False)}")


class XAPIClient:
    """X API v2との連携を管理するクラス"""
    
    BASE_URL = "https://api.twitter.com/2"
    
    def __init__(self, bearer_token: str):
        """
        Args:
            bearer_token: X API Bearer Token
        """
        self.bearer_token = bearer_token
        self.headers = {
            "Authorization": f"Bearer {bearer_token}",
            "Content-Type": "application/json"
        }

    def _wait_for_rate_limit_reset(
        self,
        response_headers: Dict[str, str],
        max_wait_seconds: int,
        attempt: int = 0
    ) -> bool:
        """
        レートリミットリセットまで待機（指数バックオフ+フルジッター）
        
        Args:
            response_headers: 429レスポンスのヘッダー
            max_wait_seconds: 最大待機秒数
            attempt: リトライ試行回数（指数バックオフ用）
            
        Returns:
            待機を実行した場合True、ヘッダーが無効な場合False
        """
        if 'x-rate-limit-reset' not in response_headers:
            logger.warning("x-rate-limit-reset ヘッダーが見つかりません")
            return False
        
        try:
            import time
            import random
            from datetime import datetime
            
            reset_timestamp = int(response_headers['x-rate-limit-reset'])
            reset_time = datetime.fromtimestamp(reset_timestamp)
            now = datetime.now()
            base_wait_seconds = (reset_time - now).total_seconds()
            
            if base_wait_seconds <= 0:
                logger.info("レートリミットは既にリセット済みです")
                return True
            
            if max_wait_seconds <= 0:
                logger.warning("max_wait_seconds=0のため待機せず終了します")
                return False
            
            # 指数バックオフ+フルジッター（AWS推奨パターン）
            # ベースは retry-after を優先、試行回数に応じて指数増加
            exponential_backoff = min(2 ** attempt, 60)  # 最大60秒
            jitter = random.uniform(0, 0.3) * exponential_backoff  # 最大30%のジッター
            wait_seconds = base_wait_seconds + exponential_backoff + jitter
            
            if wait_seconds > max_wait_seconds:
                logger.warning(
                    f"待機時間が長すぎます（{int(wait_seconds)}秒）。"
                    f"{max_wait_seconds}秒を超えるため待機せず終了します"
                )
                return False
            
            # 構造化ログ出力
            log_structured_api_call(
                source="twitter",
                rate_limit_remaining=0,
                reset_at=reset_time.isoformat(),
                wait_seconds=int(wait_seconds),
                attempt=attempt,
                exponential_backoff=exponential_backoff,
                jitter=jitter
            )
            
            logger.warning(
                f"⏳ X APIレートリミット到達。リセットまで {int(wait_seconds)}秒（約{int(wait_seconds/60)}分）待機します..."
                f" [試行{attempt+1}回目, 指数バックオフ: {exponential_backoff:.1f}秒]"
            )
            logger.info(f"リセット時刻: {reset_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            time.sleep(wait_seconds)
            logger.info("✅ レートリミット待機完了。リトライします")
            return True
            
        except (ValueError, KeyError) as e:
            logger.error(f"レートリミットヘッダーの解析に失敗: {e}")
            return False
    
    def fetch_user_tweets(
        self, 
        username: str, 
        max_results: int = 20,
        max_wait_seconds: int = 900
    ) -> List[Dict]:
        """
        指定されたユーザーの最近のツイートを取得
        
        Args:
            username: Xユーザー名（@なし）
            max_results: 取得する投稿数（5-100）
            
        Returns:
            ツイートリスト [{"id": str, "text": str, "created_at": str}]
        """
        username = username.lstrip("@")
        logger.info(f"X APIで投稿を取得中: @{username} (max={max_results})")
        
        try:
            with PerformanceLogger(f"X API投稿取得: @{username}"):
                # ステップ1: ユーザーIDを取得
                user_id = self._get_user_id(username)
                if not user_id:
                    logger.error(f"ユーザーIDが見つかりません: @{username}")
                    return []
                
                # ステップ2: ユーザーのツイートを取得（429時は1回リトライ）
                endpoint = f"{self.BASE_URL}/users/{user_id}/tweets"
                
                params = {
                    "max_results": min(max_results, 100),  # API制限: 5-100
                    "tweet.fields": "created_at,text,id,public_metrics",
                    "exclude": "retweets,replies"  # RTと返信を除外
                }
                
                # 最大2回試行（初回 + 429リトライ1回）
                for attempt in range(2):
                    response = requests.get(
                        endpoint,
                        headers=self.headers,
                        params=params,
                        timeout=15
                    )
                    
                    # レートリミット情報を取得
                    rate_limit_remaining = response.headers.get('x-rate-limit-remaining')
                    rate_limit_reset = response.headers.get('x-rate-limit-reset')
                    reset_at = None
                    if rate_limit_reset:
                        try:
                            reset_timestamp = int(rate_limit_reset)
                            reset_at = datetime.fromtimestamp(reset_timestamp).isoformat()
                        except:
                            pass
                    
                    if response.status_code == 200:
                        data = response.json()
                        tweets = []
                        
                        if "data" in data:
                            for tweet in data["data"]:
                                tweet_dict = {
                                    "id": tweet.get("id", ""),
                                    "text": tweet.get("text", ""),
                                    "link": f"https://x.com/{username}/status/{tweet.get('id', '')}",
                                    "date": tweet.get("created_at", "")
                                }
                                # public_metricsが含まれている場合は追加
                                if "public_metrics" in tweet:
                                    tweet_dict["public_metrics"] = tweet.get("public_metrics", {})
                                tweets.append(tweet_dict)
                        
                        # 構造化ログ出力
                        log_structured_api_call(
                            source="twitter",
                            account=username,
                            rate_limit_remaining=int(rate_limit_remaining) if rate_limit_remaining else None,
                            reset_at=reset_at,
                            generated_flag=False,
                            tweet_count=len(tweets),
                            attempt=attempt
                        )
                        
                        logger.info(f"取得完了: {len(tweets)}件のツイート")
                        return tweets
                    
                    elif response.status_code == 429:
                        # 429エラーの場合、例外に429属性を付与
                        error = APIConnectionError("⚠️ X APIレートリミットに達しました。時間をおいて再試行してください。")
                        error.status_code = 429
                        error.response_headers = response.headers
                        
                        # 構造化ログ出力（429エラー）
                        log_structured_api_call(
                            source="twitter",
                            account=username,
                            rate_limit_remaining=0,
                            reset_at=reset_at,
                            generated_flag=False,
                            status_code=429,
                            attempt=attempt
                        )
                        
                        if attempt == 0:
                            # 初回の429エラー: リセットまで待機してリトライ（CLIのみ、UIでは即座に例外）
                            logger.warning("X APIレートリミットに達しました")
                            if max_wait_seconds > 0 and self._wait_for_rate_limit_reset(response.headers, max_wait_seconds, attempt=attempt):
                                logger.info("リトライします（2回目の試行）")
                                continue  # リトライ
                            else:
                                # ヘッダーが無効な場合、またはUI（max_wait_seconds=0）の場合は例外を投げる
                                logger.error("レートリミット情報が取得できませんでした、または待機が許可されていません")
                                raise error
                        else:
                            # 2回目も429: 諦めて例外を投げる
                            logger.error("リトライ後もレートリミットエラーが継続しています")
                            raise error
                    
                    elif response.status_code == 401:
                        logger.error("X API認証エラー")
                        raise APIConnectionError("🔑 X API認証エラー。Bearer Tokenを確認してください。")
                    
                    else:
                        error_msg = ErrorHandler.handle_api_error(
                            Exception(f"Status {response.status_code}: {response.text}"),
                            "X API"
                        )
                        logger.error(error_msg)
                        raise APIConnectionError(error_msg)
                
                # ループを抜けた場合（通常はここに到達しない）
                raise APIConnectionError("予期しないエラー: リトライループが完了しました")
        
        except APIConnectionError:
            raise
        except Exception as e:
            ErrorHandler.log_error(e, f"X API投稿取得: @{username}")
            raise APIConnectionError(f"X API取得エラー: {str(e)}")
    
    def fetch_user_by_handle(
        self,
        handles: List[str],
        fields: List[str] = None
    ) -> List[Dict]:
        """
        複数のユーザーハンドルからユーザー情報を取得
        
        Args:
            handles: ユーザーハンドルリスト（@なし）
            fields: 取得するフィールド（デフォルト: ["public_metrics", "created_at", "verified"]）
            
        Returns:
            ユーザー情報リスト [{"id": str, "username": str, "public_metrics": {...}, ...}]
        """
        if fields is None:
            fields = ["public_metrics", "created_at", "verified"]
        
        # @を削除
        handles_clean = [h.lstrip("@") for h in handles]
        
        # X API v2 の users/by エンドポイントは最大100ユーザーまで
        if len(handles_clean) > 100:
            logger.warning(f"ハンドル数が100を超えています。最初の100件のみ取得します")
            handles_clean = handles_clean[:100]
        
        endpoint = f"{self.BASE_URL}/users/by"
        
        params = {
            "usernames": ",".join(handles_clean),
            "user.fields": ",".join(fields)
        }
        
        try:
            response = requests.get(
                endpoint,
                headers=self.headers,
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                users = []
                
                if "data" in data:
                    for user in data["data"]:
                        users.append({
                            "id": user.get("id"),
                            "username": user.get("username"),
                            "name": user.get("name"),
                            "verified": user.get("verified", False),
                            "created_at": user.get("created_at"),
                            "public_metrics": user.get("public_metrics", {}),
                            "description": user.get("description", "")
                        })
                    
                    logger.info(f"ユーザー情報取得完了: {len(users)}件")
                    return users
                else:
                    logger.warning("ユーザー情報が取得できませんでした")
                    return []
            
            elif response.status_code == 429:
                # 429エラーの場合、例外に429属性を付与
                error = APIConnectionError("⚠️ X APIレートリミットに達しました。")
                error.status_code = 429
                error.response_headers = response.headers
                raise error
            
            else:
                logger.error(f"ユーザー情報取得失敗: {response.status_code} - {response.text}")
                return []
        
        except APIConnectionError:
            raise
        except Exception as e:
            logger.error(f"ユーザー情報取得エラー: {str(e)}")
            return []
    
    def fetch_user_metrics(
        self,
        handle: str
    ) -> Optional[Dict]:
        """
        ユーザーのメトリクスを取得（followers_count, tweet_count, last_tweet_at）
        
        Args:
            handle: ユーザーハンドル（@なし）
            
        Returns:
            メトリクス辞書 {
                "followers_count": int,
                "tweet_count": int,
                "last_tweet_at": Optional[str]  # ISO形式の日時文字列
            } または None（取得失敗時）
        """
        handle_clean = handle.lstrip("@")
        
        try:
            # ユーザー情報を取得
            users = self.fetch_user_by_handle([handle_clean], fields=["public_metrics", "created_at"])
            
            if not users or len(users) == 0:
                logger.warning(f"ユーザー情報が取得できませんでした: @{handle_clean}")
                return None
            
            user = users[0]
            metrics = user.get("public_metrics", {})
            
            # 最新のツイートを1件取得してlast_tweet_atを取得
            last_tweet_at = None
            tweets = self.fetch_user_tweets(handle_clean, max_results=1, max_wait_seconds=0)
            if tweets and len(tweets) > 0:
                last_tweet_at = tweets[0].get("date")
            
            result = {
                "followers_count": metrics.get("followers_count", 0),
                "tweet_count": metrics.get("tweet_count", 0),
                "following_count": metrics.get("following_count", 0),
                "listed_count": metrics.get("listed_count", 0),
                "last_tweet_at": last_tweet_at,
                "account_created_at": user.get("created_at")
            }
            
            logger.info(
                f"メトリクス取得完了: @{handle_clean} - "
                f"フォロワー: {result['followers_count']}, "
                f"ツイート: {result['tweet_count']}"
            )
            
            return result
        
        except Exception as e:
            logger.error(f"メトリクス取得エラー: @{handle_clean} - {str(e)}")
            return None
    
    def _get_user_id(self, username: str) -> Optional[str]:
        """
        ユーザー名からユーザーIDを取得
        
        Args:
            username: Xユーザー名（@なし）
            
        Returns:
            ユーザーID
        """
        endpoint = f"{self.BASE_URL}/users/by/username/{username}"
        
        try:
            response = requests.get(
                endpoint,
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if "data" in data:
                    user_id = data["data"].get("id")
                    logger.info(f"ユーザーID取得: @{username} -> {user_id}")
                    return user_id
            else:
                logger.error(f"ユーザーID取得失敗: {response.status_code}")
                return None
        
        except Exception as e:
            logger.error(f"ユーザーID取得エラー: {str(e)}")
            return None
    
    def search_recent_tweets(
        self,
        query: str,
        max_results: int = 20,
        max_wait_seconds: int = 900
    ) -> List[Dict]:
        """
        検索クエリで最近のツイートを検索
        
        Args:
            query: 検索クエリ（例: "from:username AI"）
            max_results: 取得数（10-100）
            
        Returns:
            ツイートリスト
        """
        logger.info(f"X APIでツイート検索: {query}")
        
        try:
            endpoint = f"{self.BASE_URL}/tweets/search/recent"
            
            params = {
                "query": query,
                "max_results": min(max_results, 100),
                "tweet.fields": "created_at,text,id"
            }
            
            # 最大2回試行（初回 + 429リトライ1回）
            for attempt in range(2):
                response = requests.get(
                    endpoint,
                    headers=self.headers,
                    params=params,
                    timeout=15
                )
                
                # レートリミット情報を取得
                rate_limit_remaining = response.headers.get('x-rate-limit-remaining')
                rate_limit_reset = response.headers.get('x-rate-limit-reset')
                reset_at = None
                if rate_limit_reset:
                    try:
                        reset_timestamp = int(rate_limit_reset)
                        reset_at = datetime.fromtimestamp(reset_timestamp).isoformat()
                    except:
                        pass
                
                if response.status_code == 200:
                    data = response.json()
                    tweets = []
                    
                    if "data" in data:
                        for tweet in data["data"]:
                            tweets.append({
                                "id": tweet.get("id", ""),
                                "text": tweet.get("text", ""),
                                "link": f"https://x.com/i/status/{tweet.get('id', '')}",
                                "date": tweet.get("created_at", "")
                            })
                    
                    # 構造化ログ出力
                    log_structured_api_call(
                        source="twitter",
                        account=None,
                        rate_limit_remaining=int(rate_limit_remaining) if rate_limit_remaining else None,
                        reset_at=reset_at,
                        generated_flag=False,
                        query=query,
                        tweet_count=len(tweets),
                        attempt=attempt
                    )
                    
                    logger.info(f"検索完了: {len(tweets)}件")
                    return tweets
                
                elif response.status_code == 429:
                    # 構造化ログ出力（429エラー）
                    log_structured_api_call(
                        source="twitter",
                        account=None,
                        rate_limit_remaining=0,
                        reset_at=reset_at,
                        generated_flag=False,
                        query=query,
                        status_code=429,
                        attempt=attempt
                    )
                    
                    if attempt == 0:
                        # 初回の429エラー: リセットまで待機してリトライ（CLIのみ、UIでは即座に例外）
                        logger.warning("X API検索でレートリミットに達しました")
                        if max_wait_seconds > 0 and self._wait_for_rate_limit_reset(response.headers, max_wait_seconds, attempt=attempt):
                            logger.info("検索をリトライします（2回目の試行）")
                            continue  # リトライ
                        else:
                            # ヘッダーが無効な場合、またはUI（max_wait_seconds=0）の場合は空リストを返す
                            logger.error("レートリミット情報が取得できませんでした、または待機が許可されていません")
                            return []
                    else:
                        # 2回目も429: 空リストを返す
                        logger.error("検索リトライ後もレートリミットエラーが継続しています")
                        return []
                
                else:
                    logger.error(f"検索失敗: {response.status_code}")
                    return []
            
            # ループを抜けた場合
            return []
        
        except Exception as e:
            logger.error(f"検索エラー: {str(e)}")
            return []
