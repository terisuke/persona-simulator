"""
エラーハンドリングとロギング機能
"""

import logging
import functools
import traceback
from typing import Callable, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ErrorHandler:
    """エラーハンドリングユーティリティ"""
    
    @staticmethod
    def log_error(error: Exception, context: str = ""):
        """
        エラーをログに記録
        
        Args:
            error: 例外オブジェクト
            context: エラーコンテキスト
        """
        error_msg = f"[{context}] {type(error).__name__}: {str(error)}"
        logger.error(error_msg)
        logger.debug(traceback.format_exc())
    
    @staticmethod
    def handle_api_error(error: Exception, service: str = "API") -> str:
        """
        API エラーをユーザーフレンドリーなメッセージに変換
        
        Args:
            error: 例外オブジェクト
            service: サービス名
            
        Returns:
            ユーザー向けエラーメッセージ
        """
        error_name = type(error).__name__
        
        if "timeout" in str(error).lower():
            return f"⏱️ {service}のタイムアウトが発生しました。もう一度お試しください。"
        elif "401" in str(error) or "403" in str(error):
            return f"🔑 {service}の認証エラーです。APIキーを確認してください。"
        elif "429" in str(error):
            return f"⚠️ {service}のレート制限に達しました。しばらくお待ちください。"
        elif "500" in str(error) or "502" in str(error) or "503" in str(error):
            return f"🔧 {service}サーバーエラーです。時間をおいて再試行してください。"
        else:
            return f"❌ {service}エラー: {error_name} - {str(error)[:100]}"
    
    @staticmethod
    def retry_on_failure(
        max_retries: int = 3, 
        delay: float = 1.0,
        exceptions: tuple = (Exception,)
    ):
        """
        失敗時にリトライするデコレータ
        
        Args:
            max_retries: 最大リトライ回数
            delay: リトライ間の待機時間（秒）
            exceptions: リトライ対象の例外タプル
            
        Returns:
            デコレータ関数
        """
        def decorator(func: Callable) -> Callable:
            @functools.wraps(func)
            def wrapper(*args, **kwargs) -> Any:
                import time
                
                last_exception = None
                for attempt in range(max_retries):
                    try:
                        return func(*args, **kwargs)
                    except exceptions as e:
                        last_exception = e
                        logger.warning(
                            f"{func.__name__} 失敗 (試行 {attempt + 1}/{max_retries}): {str(e)}"
                        )
                        if attempt < max_retries - 1:
                            time.sleep(delay * (attempt + 1))  # 指数バックオフ
                
                # 最終的に失敗
                logger.error(f"{func.__name__} が {max_retries} 回失敗しました")
                raise last_exception
            
            return wrapper
        return decorator


class PerformanceLogger:
    """パフォーマンス計測ロガー"""
    
    def __init__(self, operation_name: str):
        """
        Args:
            operation_name: 計測する操作名
        """
        self.operation_name = operation_name
        self.start_time = None
    
    def __enter__(self):
        """コンテキストマネージャー開始"""
        self.start_time = datetime.now()
        logger.info(f"⏱️ [{self.operation_name}] 開始")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """コンテキストマネージャー終了"""
        if self.start_time:
            elapsed = (datetime.now() - self.start_time).total_seconds()
            
            if exc_type:
                logger.error(f"❌ [{self.operation_name}] 失敗 ({elapsed:.2f}秒)")
            else:
                logger.info(f"✅ [{self.operation_name}] 完了 ({elapsed:.2f}秒)")
        
        return False  # 例外を再発生させる


def log_function_call(func: Callable) -> Callable:
    """
    関数呼び出しをログに記録するデコレータ
    
    Args:
        func: デコレート対象の関数
        
    Returns:
        ラップされた関数
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        func_name = func.__name__
        logger.debug(f"🔧 関数呼び出し: {func_name}")
        
        try:
            result = func(*args, **kwargs)
            logger.debug(f"✅ 関数完了: {func_name}")
            return result
        except Exception as e:
            logger.error(f"❌ 関数エラー: {func_name} - {str(e)}")
            raise
    
    return wrapper


# カスタム例外クラス
class PersonaSimulatorError(Exception):
    """ベースカスタム例外"""
    pass


class APIConnectionError(PersonaSimulatorError):
    """API接続エラー"""
    pass


class RateLimitError(APIConnectionError):
    """レート制限エラー"""
    pass


class DataProcessingError(PersonaSimulatorError):
    """データ処理エラー"""
    pass


class PersonaGenerationError(PersonaSimulatorError):
    """ペルソナ生成エラー"""
    pass


class ValidationError(PersonaSimulatorError):
    """検証エラー"""
    pass

