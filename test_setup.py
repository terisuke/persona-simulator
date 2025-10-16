"""
セットアップテストスクリプト
依存関係とAPI接続を確認
"""

import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_imports():
    """必要なライブラリのインポートをテスト"""
    logger.info("📦 ライブラリのインポートをテスト中...")
    
    try:
        import streamlit
        logger.info(f"✅ Streamlit {streamlit.__version__}")
    except ImportError as e:
        logger.error(f"❌ Streamlit のインポート失敗: {e}")
        return False
    
    try:
        import requests
        logger.info(f"✅ Requests インストール済み")
    except ImportError as e:
        logger.error(f"❌ Requests のインポート失敗: {e}")
        return False
    
    try:
        import pandas
        logger.info(f"✅ Pandas {pandas.__version__}")
    except ImportError as e:
        logger.error(f"❌ Pandas のインポート失敗: {e}")
        return False
    
    try:
        from sentence_transformers import SentenceTransformer
        logger.info(f"✅ Sentence Transformers インストール済み")
    except ImportError as e:
        logger.error(f"❌ Sentence Transformers のインポート失敗: {e}")
        return False
    
    try:
        from textblob import TextBlob
        logger.info(f"✅ TextBlob インストール済み")
    except ImportError as e:
        logger.error(f"❌ TextBlob のインポート失敗: {e}")
        return False
    
    return True


def test_modules():
    """自作モジュールのインポートをテスト"""
    logger.info("\n🔧 自作モジュールのインポートをテスト中...")
    
    try:
        from utils.grok_api import GrokAPI
        logger.info("✅ utils.grok_api")
    except ImportError as e:
        logger.error(f"❌ utils.grok_api のインポート失敗: {e}")
        return False
    
    try:
        from utils.persona import PersonaManager
        logger.info("✅ utils.persona")
    except ImportError as e:
        logger.error(f"❌ utils.persona のインポート失敗: {e}")
        return False
    
    try:
        from utils.similarity import SimilaritySearcher
        logger.info("✅ utils.similarity")
    except ImportError as e:
        logger.error(f"❌ utils.similarity のインポート失敗: {e}")
        return False
    
    try:
        from utils.error_handler import ErrorHandler
        logger.info("✅ utils.error_handler")
    except ImportError as e:
        logger.error(f"❌ utils.error_handler のインポート失敗: {e}")
        return False
    
    return True


def test_api_key():
    """APIキーの設定をテスト"""
    logger.info("\n🔑 APIキー設定をテスト中...")
    
    import os
    
    # Streamlit secretsファイルの存在確認
    secrets_path = ".streamlit/secrets.toml"
    if os.path.exists(secrets_path):
        logger.info(f"✅ {secrets_path} が存在します")
        
        # 内容確認
        with open(secrets_path, 'r') as f:
            content = f.read()
            if "GROK_API_KEY" in content:
                logger.info("✅ GROK_API_KEY が設定されています")
                
                # プレースホルダーチェック
                if "your_" in content or "here" in content:
                    logger.warning("⚠️ APIキーがプレースホルダーのままの可能性があります")
                    logger.warning("   実際のAPIキーに置き換えてください")
            else:
                logger.error("❌ GROK_API_KEY が見つかりません")
                return False
    else:
        logger.error(f"❌ {secrets_path} が見つかりません")
        logger.info(f"   .streamlit/secrets.toml.example をコピーして作成してください")
        return False
    
    return True


def test_cache_directory():
    """キャッシュディレクトリの確認"""
    logger.info("\n📁 キャッシュディレクトリをテスト中...")
    
    import os
    
    cache_dir = ".cache"
    if not os.path.exists(cache_dir):
        try:
            os.makedirs(cache_dir)
            logger.info(f"✅ {cache_dir} を作成しました")
        except Exception as e:
            logger.error(f"❌ {cache_dir} の作成に失敗: {e}")
            return False
    else:
        logger.info(f"✅ {cache_dir} が存在します")
    
    return True


def main():
    """メインテスト"""
    logger.info("=" * 60)
    logger.info("🧪 Persona Debate Simulator - セットアップテスト")
    logger.info("=" * 60)
    
    results = []
    
    # テスト実行
    results.append(("ライブラリインポート", test_imports()))
    results.append(("自作モジュール", test_modules()))
    results.append(("APIキー設定", test_api_key()))
    results.append(("キャッシュディレクトリ", test_cache_directory()))
    
    # 結果サマリー
    logger.info("\n" + "=" * 60)
    logger.info("📊 テスト結果サマリー")
    logger.info("=" * 60)
    
    passed = 0
    failed = 0
    
    for test_name, result in results:
        status = "✅ 成功" if result else "❌ 失敗"
        logger.info(f"{test_name}: {status}")
        if result:
            passed += 1
        else:
            failed += 1
    
    logger.info("-" * 60)
    logger.info(f"合計: {passed} 成功, {failed} 失敗")
    
    if failed == 0:
        logger.info("\n🎉 すべてのテストに合格しました！")
        logger.info("次のコマンドでアプリを起動できます:")
        logger.info("  streamlit run app.py")
        return 0
    else:
        logger.error("\n❌ いくつかのテストが失敗しました")
        logger.error("上記のエラーを修正してから再実行してください")
        return 1


if __name__ == "__main__":
    sys.exit(main())

