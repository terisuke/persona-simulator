"""
X API v2連携モジュール
実際のX投稿を取得
"""

import requests
import logging
from typing import List, Dict, Optional
from datetime import datetime, timezone
from .error_handler import ErrorHandler, PerformanceLogger, APIConnectionError

logger = logging.getLogger(__name__)


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

    def _wait_for_rate_limit_reset(self, response_headers: Dict[str, str]) -> bool:
        """
        レートリミットリセットまで待機
        
        Args:
            response_headers: 429レスポンスのヘッダー
            
        Returns:
            待機を実行した場合True、ヘッダーが無効な場合False
        """
        if 'x-rate-limit-reset' not in response_headers:
            logger.warning("x-rate-limit-reset ヘッダーが見つかりません")
            return False
        
        try:
            import time
            from datetime import datetime
            
            reset_timestamp = int(response_headers['x-rate-limit-reset'])
            reset_time = datetime.fromtimestamp(reset_timestamp)
            now = datetime.now()
            wait_seconds = (reset_time - now).total_seconds()
            
            if wait_seconds <= 0:
                logger.info("レートリミットは既にリセット済みです")
                return True
            
            # 最大15分（900秒）まで待機
            if wait_seconds > 900:
                logger.warning(f"待機時間が長すぎます（{int(wait_seconds)}秒）。15分に制限します")
                wait_seconds = 900
            
            logger.warning(
                f"⏳ X APIレートリミット到達。リセットまで {int(wait_seconds)}秒（約{int(wait_seconds/60)}分）待機します..."
            )
            logger.info(f"リセット時刻: {reset_time.strftime('%Y-%m-%d %H:%M:%S')}")
            
            time.sleep(wait_seconds + 5)  # 余裕を持って5秒追加
            logger.info("✅ レートリミット待機完了。リトライします")
            return True
            
        except (ValueError, KeyError) as e:
            logger.error(f"レートリミットヘッダーの解析に失敗: {e}")
            return False
    
    def fetch_user_tweets(
        self, 
        username: str, 
        max_results: int = 20
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
                    "tweet.fields": "created_at,text,id",
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
                    
                    if response.status_code == 200:
                        data = response.json()
                        tweets = []
                        
                        if "data" in data:
                            for tweet in data["data"]:
                                tweets.append({
                                    "id": tweet.get("id", ""),
                                    "text": tweet.get("text", ""),
                                    "link": f"https://x.com/{username}/status/{tweet.get('id', '')}",
                                    "date": tweet.get("created_at", "")
                                })
                        
                        logger.info(f"取得完了: {len(tweets)}件のツイート")
                        return tweets
                    
                    elif response.status_code == 429:
                        if attempt == 0:
                            # 初回の429エラー: リセットまで待機してリトライ
                            logger.warning("X APIレートリミットに達しました")
                            if self._wait_for_rate_limit_reset(response.headers):
                                logger.info("リトライします（2回目の試行）")
                                continue  # リトライ
                            else:
                                # ヘッダーが無効な場合は例外を投げる
                                logger.error("レートリミット情報が取得できませんでした")
                                raise APIConnectionError("⚠️ X APIレートリミットに達しました。時間をおいて再試行してください。")
                        else:
                            # 2回目も429: 諦めて例外を投げる
                            logger.error("リトライ後もレートリミットエラーが継続しています")
                            raise APIConnectionError("⚠️ X APIレートリミットに達しました。時間をおいて再試行してください。")
                    
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
        max_results: int = 20
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
                    
                    logger.info(f"検索完了: {len(tweets)}件")
                    return tweets
                
                elif response.status_code == 429:
                    if attempt == 0:
                        # 初回の429エラー: リセットまで待機してリトライ
                        logger.warning("X API検索でレートリミットに達しました")
                        if self._wait_for_rate_limit_reset(response.headers):
                            logger.info("検索をリトライします（2回目の試行）")
                            continue  # リトライ
                        else:
                            # ヘッダーが無効な場合は空リストを返す
                            logger.error("レートリミット情報が取得できませんでした")
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

