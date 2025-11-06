"""
Persona Debate Simulator (Terisuke Edition)
Streamlitメインアプリケーション
"""

import streamlit as st
import logging
import json
import pickle
import os
import pandas as pd
import io
import subprocess
import glob
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

# 定数定義
MAX_ACCOUNTS = 100  # 一括管理に対応して上限を拡張
DEFAULT_POST_LIMIT = 20
TOP_K_RELEVANT_POSTS = 3
RECENT_CONTEXT_MESSAGES = 3
BATCH_SIZE = 10  # バッチ処理のサイズ
UI_MAX_RATE_WAIT_SECONDS = 0  # UIではレート制限待ちを実施しない

# 自作モジュール
from utils.grok_api import GrokAPI
from utils.x_api import XAPIClient
from utils.persona import PersonaManager, PersonaProfile
from utils.similarity import SimilaritySearcher
from utils.debate_ui import DebateUI
from utils.error_handler import APIConnectionError

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ページ設定
st.set_page_config(
    page_title="Persona Debate Simulator",
    page_icon="💬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# キャッシュディレクトリ
CACHE_DIR = ".cache"
os.makedirs(CACHE_DIR, exist_ok=True)


def load_grok_api() -> Optional[GrokAPI]:
    """Grok APIインスタンスをロード"""
    try:
        api_key = st.secrets.get("GROK_API_KEY")
        if not api_key:
            st.error("❌ Grok APIキーが設定されていません。`.streamlit/secrets.toml`を確認してください。")
            return None
        
        # オプション: カスタムモデル名
        model = st.secrets.get("GROK_MODEL", None)
        
        grok = GrokAPI(api_key, model=model)
        logger.info(f"Grok API初期化完了: モデル={grok.model}")
        return grok
    except Exception as e:
        st.error(f"❌ Grok API初期化エラー: {str(e)}")
        logger.error(f"Grok API初期化失敗: {str(e)}")
        return None


def load_x_api(use_x_api: bool = True) -> Optional[XAPIClient]:
    """
    X API v2インスタンスをロード（オプション）
    
    Args:
        use_x_api: X APIを使用するかどうか（Falseの場合は常にNoneを返す）
    
    Returns:
        XAPIClient インスタンスまたは None
    """
    if not use_x_api:
        logger.info("X APIを使用しない設定のためスキップ")
        return None
    
    try:
        bearer_token = st.secrets.get("X_BEARER_TOKEN")
        if not bearer_token or bearer_token == "your_x_bearer_token_here":
            logger.info("X API Bearer Tokenが設定されていません（オプション）")
            return None
        return XAPIClient(bearer_token)
    except Exception as e:
        logger.warning(f"X API初期化エラー（続行可能）: {str(e)}")
        return None


def cache_data(key: str, data: any):
    """データをキャッシュに保存"""
    cache_path = os.path.join(CACHE_DIR, f"{key}.pkl")
    try:
        with open(cache_path, 'wb') as f:
            pickle.dump(data, f)
        logger.info(f"キャッシュ保存: {key}")
    except Exception as e:
        logger.warning(f"キャッシュ保存失敗: {str(e)}")


def load_cache(key: str) -> Optional[any]:
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


def delete_cache(key: str):
    """キャッシュファイルを削除"""
    cache_path = os.path.join(CACHE_DIR, f"{key}.pkl")
    if os.path.exists(cache_path):
        try:
            os.remove(cache_path)
            logger.info(f"キャッシュ削除: {key}")
        except Exception as e:
            logger.warning(f"キャッシュ削除失敗: {str(e)}")


def parse_uploaded_file(uploaded_file) -> List[str]:
    """
    アップロードされたファイルをパースしてアカウントリストを取得
    
    Args:
        uploaded_file: Streamlitのアップロードファイルオブジェクト
        
    Returns:
        アカウント名のリスト
    """
    try:
        # ファイル内容を読み込み
        content = uploaded_file.read()
        
        if uploaded_file.name.endswith('.csv'):
            # CSVファイルの場合
            df = pd.read_csv(io.StringIO(content.decode('utf-8')))
            
            # username列を探す（大文字小文字を区別しない）
            username_col = None
            for col in df.columns:
                if col.lower() in ['username', 'account', 'user', 'name']:
                    username_col = col
                    break
            
            if username_col is None:
                # 最初の列を使用
                username_col = df.columns[0]
                st.warning(f"username列が見つからないため、最初の列 '{username_col}' を使用します")
            
            accounts = df[username_col].astype(str).tolist()
            
        elif uploaded_file.name.endswith('.txt'):
            # テキストファイルの場合（改行区切り）
            content_str = content.decode('utf-8')
            accounts = [line.strip() for line in content_str.split('\n') if line.strip()]
            
        else:
            st.error("サポートされていないファイル形式です。CSVまたはTXTファイルをアップロードしてください。")
            return []
        
        # アカウント名をクリーンアップ（@を除去、空白を削除）
        cleaned_accounts = []
        for account in accounts:
            if account and account != 'nan':  # pandasのNaNを除外
                clean_account = str(account).strip().lstrip('@')
                if clean_account:
                    cleaned_accounts.append(clean_account)
        
        # 重複を除去
        unique_accounts = list(dict.fromkeys(cleaned_accounts))
        
        logger.info(f"ファイル解析完了: {len(unique_accounts)}アカウント")
        return unique_accounts
        
    except Exception as e:
        st.error(f"ファイル解析エラー: {str(e)}")
        logger.error(f"ファイル解析失敗: {str(e)}")
        return []


def check_cache_status(accounts: List[str]) -> Dict[str, str]:
    """
    アカウントのキャッシュ状況をチェック
    
    Args:
        accounts: アカウント名のリスト
        
    Returns:
        アカウント名 -> ステータスの辞書
    """
    status = {}
    
    for account in accounts:
        cache_key = f"posts_{account}"
        session_key = f"session_data_{account}"
        
        # 既存のエラーステータスは維持
        existing_status = st.session_state.get('account_status', {}).get(account)
        if existing_status == 'error':
            status[account] = 'error'
            continue
        
        # セッション状態をチェック（最優先）
        if session_key in st.session_state:
            status[account] = "cached_session"
        # ファイルキャッシュをチェック
        elif os.path.exists(os.path.join(CACHE_DIR, f"{cache_key}.pkl")):
            status[account] = "cached_file"
        else:
            status[account] = "pending"
    
    return status


def update_account_status(account: str, status: str):
    """
    アカウントステータスを原子的に更新
    
    Args:
        account: アカウント名（@付きでも可）
        status: ステータス（'cached_session', 'cached_file', 'pending', 'error', 'unverified'）
    """
    account_clean = account.lstrip('@')
    st.session_state.setdefault('account_status', {})[account_clean] = status


def initialize_session_state():
    """セッション状態を初期化"""
    if 'accounts_list' not in st.session_state:
        st.session_state['accounts_list'] = ['cor_terisuke']  # デフォルト
    
    if 'batch_processing' not in st.session_state:
        st.session_state['batch_processing'] = False
    
    if 'processing_progress' not in st.session_state:
        st.session_state['processing_progress'] = 0
    
    if 'account_status' not in st.session_state:
        st.session_state['account_status'] = {}
    
    if 'account_page' not in st.session_state:
        st.session_state['account_page'] = 0
    
    if 'batch_processed_count' not in st.session_state:
        st.session_state['batch_processed_count'] = 0

    if 'discovery_in_progress' not in st.session_state:
        st.session_state['discovery_in_progress'] = False

    if 'discovered_source' not in st.session_state:
        st.session_state['discovered_source'] = {}
    
    # X API使用可否の初期化（X_BEARER_TOKENが設定されていればTrue、なければFalse）
    if 'use_x_api' not in st.session_state:
        try:
            bearer_token = st.secrets.get("X_BEARER_TOKEN")
            st.session_state['use_x_api'] = bool(bearer_token and bearer_token != "your_x_bearer_token_here")
        except:
            st.session_state['use_x_api'] = False


def restore_session_from_cache():
    """キャッシュからセッション状態を復元"""
    try:
        # .cacheディレクトリから利用可能なアカウントを検出
        if os.path.exists(CACHE_DIR):
            cached_accounts = []
            for filename in os.listdir(CACHE_DIR):
                if filename.startswith('posts_') and filename.endswith('.pkl'):
                    account = filename.replace('posts_', '').replace('.pkl', '')
                    cached_accounts.append(account)
            
            # 既存のアカウントリストとマージ
            existing_accounts = set(st.session_state.get('accounts_list', []))
            new_accounts = [acc for acc in cached_accounts if acc not in existing_accounts]
            
            if new_accounts:
                st.session_state['accounts_list'].extend(new_accounts)
                logger.info(f"キャッシュから{len(new_accounts)}アカウントを復元: {new_accounts}")
                
                # キャッシュ状況を更新
                st.session_state['account_status'] = check_cache_status(st.session_state['accounts_list'])
                
                return True
        
        return False
        
    except Exception as e:
        logger.error(f"セッション復元エラー: {str(e)}")
        return False


def save_session_state():
    """セッション状態を保存（必要に応じて）"""
    try:
        # 重要な状態をログに記録
        accounts_count = len(st.session_state.get('accounts_list', []))
        cached_count = sum(1 for s in st.session_state.get('account_status', {}).values() 
                          if s in ['cached_session', 'cached_file'])
        
        logger.info(f"セッション状態保存: {accounts_count}アカウント, {cached_count}キャッシュ済み")
        
    except Exception as e:
        logger.error(f"セッション状態保存エラー: {str(e)}")


def ensure_quality_score(
    grok_api: GrokAPI,
    persona_profile: PersonaProfile,
    account_clean: str,
    x_api: Optional[XAPIClient] = None
) -> bool:
    """
    persona_profileがquality_scoreを持っていなければ評価して付与する。

    Returns:
        bool: quality_scoreを追加した場合はTrue
    """
    if not persona_profile or 'quality_score' in persona_profile:
        return False

    account_info = {
        "handle": account_clean,
        "description": persona_profile.get('background', ''),
        "confidence": persona_profile.get('confidence', 0.8)
    }

    try:
        quality_result = grok_api.check_account_quality(
            account_clean,
            account_info,
            x_api_client=x_api
        )
    except Exception as error:
        logger.warning(f"quality_score算出に失敗: @{account_clean} - {error}")
        return False

    if not quality_result:
        return False

    persona_profile['quality_score'] = quality_result['score']
    persona_profile['quality_reasons'] = quality_result.get('reasons', [])
    logger.info(f"📊 @{account_clean}: quality_score={quality_result['score']:.2f}を付与(UI)")
    return True


def has_generated_posts(posts: List[Dict]) -> bool:
    """生成データ（sample_/generated_）かどうかを判定"""
    if not posts:
        return False
    first_id = posts[0].get('id', '')
    return first_id.startswith('sample_') or first_id.startswith('generated_')


def fetch_and_analyze_posts(
    grok_api: GrokAPI, 
    account: str, 
    use_cache: bool = True,
    x_api: Optional[XAPIClient] = None,
    force_refresh: bool = False
) -> tuple[List[Dict], PersonaProfile]:
    """
    投稿を取得してペルソナを生成
    
    Args:
        grok_api: Grok APIインスタンス
        account: アカウント名
        use_cache: ファイルキャッシュを使用するか
        x_api: X APIクライアント
        force_refresh: 強制再取得フラグ
    
    Returns:
        (投稿リスト, ペルソナプロファイル)
    """
    account_clean = account.lstrip('@')
    cache_key = f"posts_{account_clean}"
    session_key = f"session_data_{account_clean}"
    
    # 強制再取得でない場合、セッション状態をチェック（優先度最高）
    if not force_refresh and session_key in st.session_state:
        st.info(f"💾 セッションから@{account}のデータをロード（再取得不要）")
        data = st.session_state[session_key]
        # ステータスを即時反映
        update_account_status(account_clean, 'cached_session')
        posts = data.get('posts', [])
        if has_generated_posts(posts):
            st.warning(
                f"⚠️ @{account} のセッションキャッシュに生成データを検出しました。実データのみ再取得します。"
            )
            del st.session_state[session_key]
            delete_cache(cache_key)
        else:
            persona = data.get('persona', {})
            if ensure_quality_score(grok_api, persona, account_clean, x_api):
                # セッション・キャッシュを更新（quality_scoreを追加）
                data['persona'] = persona
                st.session_state[session_key] = data
                cache_data(cache_key, data)
            return posts, persona
    
    # ファイルキャッシュチェック
    if use_cache and not force_refresh:
        cached = load_cache(cache_key)
        if cached:
            st.info(f"📦 キャッシュから@{account}のデータをロード")
            # セッション状態にも保存
            st.session_state[session_key] = cached
            # ステータスを即時反映
            update_account_status(account_clean, 'cached_file')
            posts = cached.get('posts', [])
            if has_generated_posts(posts):
                st.warning(
                    f"⚠️ @{account}: キャッシュに生成データが含まれているため削除し再取得します。"
                )
                delete_cache(cache_key)
                del st.session_state[session_key]
            else:
                persona = cached.get('persona', {})
                if ensure_quality_score(grok_api, persona, account_clean, x_api):
                    cached['persona'] = persona
                    st.session_state[session_key] = cached
                    cache_data(cache_key, cached)
                return posts, persona
    
    # 投稿取得
    with st.spinner(f"📡 @{account}の投稿を取得中..."):
        try:
            posts = grok_api.fetch_posts(
                account, 
                limit=DEFAULT_POST_LIMIT, 
                since_date="2024-01-01",
                x_api_client=x_api,
                max_rate_wait_seconds=UI_MAX_RATE_WAIT_SECONDS if x_api else 900,
                allow_generated=False
            )
        except APIConnectionError as err:
            st.warning(
                f"⚠️ @{account} の投稿取得がレート制限のため中断されました。\n"
                "👉 バッチ生成(ingest_accounts.py)を再実行し、15分後に再試行ください。\n"
                "詳しくは README の『一括管理モード』を参照してください。"
            )
            logger.warning(f"UIレート制限: @{account} - {err}")
            update_account_status(account_clean, 'error')
            return [], {}
    
    if not posts:
        st.warning(f"⚠️ @{account}の投稿が取得できませんでした")
        # エラーステータスを反映
        update_account_status(account_clean, 'error')
        return [], {}
    
    # 取得方法を判定して表示
    if has_generated_posts(posts):
        st.warning(
            "⚠️ 生成データを検出したため、このアカウントは議論から除外します。\n"
            "👉 ingest_accounts.py を使用して実データを再取得してください。"
        )
        update_account_status(account_clean, 'unverified')
        delete_cache(cache_key)
        return [], {}

    source = "unknown"
    if posts[0]['id'].startswith('web_search_'):
        st.success(f"✅ {len(posts)}件の実投稿を取得（🌐 Grok Web Search）")
        source = "web_search"
    else:
        st.success(f"✅ {len(posts)}件の実投稿を取得（🔑 X API v2）")
        source = "twitter"
    
    # ペルソナ生成（マルチプラットフォーム対応）
    with st.spinner(f"🧠 @{account}のペルソナを生成中..."):
        # Web検索で情報を強化するか確認
        enable_web = st.session_state.get('enable_web_enrichment', True)
        
        if enable_web:
            st.info("🌐 Web検索で他プラットフォームの情報を収集中...")
        
        persona_profile = grok_api.generate_persona_profile(
            posts, 
            account=account,
            enable_web_enrichment=enable_web
        )
    
    if persona_profile:
        enrichment_note = "（マルチプラットフォーム分析）" if enable_web else ""
        st.success(f"✅ ペルソナ生成完了{enrichment_note}: {persona_profile.get('name', account)}")
        ensure_quality_score(grok_api, persona_profile, account_clean, x_api)
    else:
        st.warning(
            "⚠️ ペルソナは未確定です（実データ不足または解析失敗）。\n"
            "👉 まずは CLI のバッチ取得で実投稿のキャッシュ生成を行ってください。"
        )
        update_account_status(account_clean, 'unverified')
    
    # データを保存
    data = {
        'posts': posts,
        'persona': persona_profile or {},
        'fetched_at': datetime.now().isoformat(),
        'source': source
    }
    
    # ファイルキャッシュ保存
    cache_data(cache_key, data)
    
    # セッション状態にも保存（自動再実行時に再取得を防ぐ）
    st.session_state[session_key] = data
    # ステータスを反映（未確定の場合は unverified）
    status = 'cached_session' if persona_profile else 'unverified'
    update_account_status(account_clean, status)
    
    return posts, persona_profile


def get_agent_settings():
    """エージェント機能の設定を取得"""
    use_history = st.session_state.get('enable_history', False)
    use_web_search = st.session_state.get('enable_web_search', False)
    enable_web_enrichment = st.session_state.get('enable_web_enrichment', True)
    return use_history, use_web_search, enable_web_enrichment


def build_previous_context(debate_ui) -> str:
    """直近のメッセージから文脈を構築"""
    return "\n".join([
        f"@{m.account}: {m.content}"
        for m in debate_ui.get_messages()[-RECENT_CONTEXT_MESSAGES:]
    ])


def main():
    """メインアプリケーション"""
    
    # セッション状態の初期化
    initialize_session_state()
    if 'grok_history_summary' not in st.session_state:
        st.session_state['grok_history_summary'] = "会話履歴なし"
    
    # キャッシュからセッション状態を復元（初回のみ）
    if 'session_restored' not in st.session_state:
        if restore_session_from_cache():
            st.info("💾 キャッシュからアカウント情報を復元しました")
        st.session_state['session_restored'] = True
    
    # タイトル
    st.title("💬 Persona Debate Simulator")
    st.markdown("**AI Agent Edition** - Xアカウントからペルソナを生成し、議論をシミュレートします")
    
    # エージェント機能説明
    st.markdown("""
    <div style="background-color: #f0f2f6; padding: 10px; border-radius: 5px; margin-bottom: 20px;">
    🤖 <b>AIエージェント</b> | 🌐 マルチプラットフォーム分析 | 💬 会話履歴保持
    </div>
    """, unsafe_allow_html=True)
    
    # 進捗サマリ表示（メインエリア）
    accounts = st.session_state.get('accounts_list', [])
    if accounts:
        status = st.session_state.get('account_status', {})
        cached_count = sum(1 for s in status.values() if s in ['cached_session', 'cached_file'])
        pending_count = sum(1 for s in status.values() if s == 'pending')
        error_count = sum(1 for s in status.values() if s == 'error')
        
        # 進捗サマリカード
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "総アカウント数", 
                len(accounts),
                help="登録されているアカウントの総数"
            )
        
        with col2:
            st.metric(
                "キャッシュ済み", 
                cached_count,
                delta=f"{cached_count/len(accounts)*100:.1f}%" if accounts else "0%",
                help="データが取得済みのアカウント数"
            )
        
        with col3:
            st.metric(
                "取得待ち", 
                pending_count,
                delta=f"{pending_count/len(accounts)*100:.1f}%" if accounts else "0%",
                help="まだデータを取得していないアカウント数"
            )
        
        with col4:
            st.metric(
                "エラー", 
                error_count,
                delta=f"{error_count/len(accounts)*100:.1f}%" if accounts else "0%",
                help="データ取得に失敗したアカウント数"
            )
        
        # 進捗バー
        if accounts:
            progress = cached_count / len(accounts)
            st.progress(progress, text=f"データ取得進捗: {cached_count}/{len(accounts)} ({progress*100:.1f}%)")
        
        st.markdown("---")
    
    # サイドバー
    with st.sidebar:
        st.header("⚙️ 設定")
        
        # APIキーチェック
        grok_api = load_grok_api()
        if not grok_api:
            st.stop()
        
        st.success("✅ Grok API接続OK")
        
        # X API v2チェック（オプション）
        # 注意: トグルは後で表示されるが、ここではセッション状態を参照
        use_x_api_flag = st.session_state.get('use_x_api', True)
        x_api = load_x_api(use_x_api=use_x_api_flag)
        if x_api:
            st.success("✅ X API v2接続OK（実投稿取得）")
        elif use_x_api_flag:
            st.info("ℹ️ X API未設定（Grok Web Searchを使用）")
        else:
            st.info("ℹ️ X APIは無効化されています（Grok Web Searchを使用）")
        
        # アカウント管理（一括アップロード対応）
        st.subheader("📝 Xアカウント管理")
        
        # 一括アップロードセクション
        st.markdown("**📁 一括アップロード**")
        uploaded_file = st.file_uploader(
            "CSVまたはTXTファイルをアップロード",
            type=['csv', 'txt'],
            help="CSV: username列を含むファイル\nTXT: 改行区切りでアカウント名を記載"
        )
        
        if uploaded_file is not None:
            if st.button("📥 ファイルからアカウントを読み込み", type="primary"):
                accounts_from_file = parse_uploaded_file(uploaded_file)
                if accounts_from_file:
                    # 既存のアカウントとマージ（重複除去）
                    existing_accounts = set(st.session_state['accounts_list'])
                    new_accounts = [acc for acc in accounts_from_file if acc not in existing_accounts]
                    
                    if new_accounts:
                        st.session_state['accounts_list'].extend(new_accounts)
                        st.success(f"✅ {len(new_accounts)}アカウントを追加しました")
                    else:
                        st.info("新しいアカウントはありませんでした")
                    
                    # キャッシュ状況を更新
                    st.session_state['account_status'] = check_cache_status(st.session_state['accounts_list'])
                    st.rerun()
        
        st.markdown("---")
        
        # 現在のアカウントリスト表示
        accounts = st.session_state['accounts_list']
        if accounts:
            # 進捗サマリ表示
            status = st.session_state.get('account_status', {})
            cached_count = sum(1 for s in status.values() if s in ['cached_session', 'cached_file'])
            pending_count = sum(1 for s in status.values() if s == 'pending')
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("総アカウント数", len(accounts))
            with col2:
                st.metric("キャッシュ済み", cached_count)
            with col3:
                st.metric("取得待ち", pending_count)
            
            st.markdown("**登録済みアカウント:**")
            
            # ページング対応（10件ずつ表示）
            page_size = 10
            total_pages = (len(accounts) + page_size - 1) // page_size
            current_page = st.session_state.get('account_page', 0)
            
            if total_pages > 1:
                col1, col2, col3 = st.columns([1, 2, 1])
                with col1:
                    if st.button("◀️", disabled=(current_page == 0)):
                        st.session_state['account_page'] = max(0, current_page - 1)
                        st.rerun()
                with col2:
                    st.caption(f"ページ {current_page + 1} / {total_pages}")
                with col3:
                    if st.button("▶️", disabled=(current_page >= total_pages - 1)):
                        st.session_state['account_page'] = min(total_pages - 1, current_page + 1)
                        st.rerun()
            
            # 現在のページのアカウントを表示
            start_idx = current_page * page_size
            end_idx = min(start_idx + page_size, len(accounts))
            page_accounts = accounts[start_idx:end_idx]
            
            for i, acc in enumerate(page_accounts):
                actual_idx = start_idx + i
                col1, col2, col3 = st.columns([3, 1, 1])
                
                with col1:
                    # ステータス表示
                    acc_status = status.get(acc, 'pending')
                    if acc_status == 'cached_session':
                        st.text(f"@{acc} ✅")
                    elif acc_status == 'cached_file':
                        st.text(f"@{acc} 📦")
                    else:
                        st.text(f"@{acc} ⏳")
                
                with col2:
                    if st.button("🔄", key=f"refresh_{actual_idx}", help=f"@{acc}の投稿を再取得"):
                        # 個別アカウントのキャッシュをクリア
                        session_key = f"session_data_{acc}"
                        if session_key in st.session_state:
                            del st.session_state[session_key]
                        # all_dataキャッシュもクリア（再構築が必要）
                        if 'all_data_cache' in st.session_state:
                            del st.session_state['all_data_cache']
                        if 'cached_accounts_key' in st.session_state:
                            del st.session_state['cached_accounts_key']
                        st.success(f"✅ @{acc}の投稿を再取得します")
                        st.rerun()
                
                with col3:
                    if st.button("🗑️", key=f"delete_{actual_idx}", help=f"@{acc}を削除"):
                        st.session_state['accounts_list'].pop(actual_idx)
                        # セッションキャッシュも削除
                        session_key = f"session_data_{acc}"
                        if session_key in st.session_state:
                            del st.session_state[session_key]
                        # all_dataキャッシュもクリア
                        if 'all_data_cache' in st.session_state:
                            del st.session_state['all_data_cache']
                        if 'cached_accounts_key' in st.session_state:
                            del st.session_state['cached_accounts_key']
                        # ページを調整
                        if current_page > 0 and len(st.session_state['accounts_list']) <= current_page * page_size:
                            st.session_state['account_page'] = max(0, current_page - 1)
                        st.rerun()
        
        st.markdown("---")
        
        # 新規アカウント追加（個別）
        if len(accounts) < MAX_ACCOUNTS:
            st.markdown("**➕ 個別アカウント追加:**")
            new_account = st.text_input(
                "アカウント名を入力",
                value="",
                key="new_account_input",
                placeholder="例: elonmusk（@なしで入力）",
                help="アカウント名を完全に入力してから追加ボタンをクリック",
                autocomplete="off"
            )
            
            col1, col2 = st.columns([3, 1])
            with col1:
                if st.button("➕ アカウント追加", type="primary", use_container_width=True):
                    if new_account.strip():
                        clean_account = new_account.strip().lstrip('@')
                        if clean_account not in accounts:
                            st.session_state['accounts_list'].append(clean_account)
                            st.success(f"✅ @{clean_account}を追加しました")
                            st.rerun()
                        else:
                            st.warning(f"⚠️ @{clean_account}は既に登録されています")
                    else:
                        st.error("アカウント名を入力してください")
            
            with col2:
                if st.button("🔄 リセット", use_container_width=True):
                    st.session_state['accounts_list'] = ['cor_terisuke']
                    st.session_state['account_page'] = 0
                    st.success("デフォルトにリセットしました")
                    st.rerun()
        else:
            st.warning(f"⚠️ 最大{MAX_ACCOUNTS}アカウントまで登録可能です")
        
        # accounts変数に代入（後続の処理で使用）
        accounts = st.session_state['accounts_list']
        
        # エージェント機能設定
        st.subheader("🤖 エージェント機能")
        
        enable_web_enrichment = st.checkbox(
            "マルチプラットフォーム分析", 
            value=True, 
            help="Instagram、LinkedIn、ブログ等も検索してペルソナ精度を向上"
        )
        st.session_state['enable_web_enrichment'] = enable_web_enrichment
        
        enable_history = st.checkbox(
            "会話履歴を保持", 
            value=False, 
            help="複数回の議論で文脈を継続（AIエージェント機能）"
        )
        
        enable_web_search = st.checkbox(
            "Web検索を有効化", 
            value=False, 
            help="最新情報をリアルタイム検索（AIエージェント機能）"
        )
        
        # 会話履歴管理
        if enable_history:
            if 'grok_history_summary' in st.session_state:
                st.info(f"📝 {st.session_state['grok_history_summary']}")
            
            if st.button("🗑️ 会話履歴をクリア"):
                if grok_api:
                    grok_api.clear_conversation_history()
                    st.session_state['grok_history_summary'] = "会話履歴なし"
                    st.success("会話履歴をクリアしました")
                    st.rerun()
        
        st.divider()
        
        # データソースフィルタ（Stage3準備）
        st.subheader("🌐 データソースフィルタ")
        source_filter = st.multiselect(
            "表示するデータソース",
            options=["全て", "Twitter", "Web", "Sample", "Keyword", "Random", "Diversity"],
            default=["全て"],
            help="データ取得元でフィルタ（Twitter=🔑 X API, Web=🌐 Grok 検索, Sample=📝 フォールバック, Diversity=多様性サンプリング）"
        )
        st.session_state["source_filter"] = source_filter
        
        # 収集（Stage2.5）
        st.subheader("🔍 キーワードで収集")
        discover_keyword = st.text_input(
            "キーワード",
            value="AI engineer",
            help="例: AI engineer, LLM researcher, startup founder など",
            autocomplete="off"
        )
        max_results = st.slider(
            "最大人数",
            min_value=1,
            max_value=100,
            value=50
        )
        col_dk1, col_dk2 = st.columns([2, 1])
        with col_dk1:
            if st.button("🚀 収集開始", use_container_width=True):
                st.session_state['discovery_in_progress'] = True
                st.session_state['discovery_mode'] = 'keyword'
                st.rerun()
        with col_dk2:
            dry_run = st.toggle("ドライラン", value=False, help="Grok未設定でも固定ダミーデータで動作確認")

        st.caption("🧮 多様性サンプリング（ハイブリッド）")
        use_diversity_sampling = st.checkbox(
            "多様性サンプリングを実行する",
            key="ui_use_diversity_sampling",
            help="X APIとGrok Web Searchを組み合わせて多様性を担保した候補リストを収集します"
        )
        if use_diversity_sampling:
            sampling_method = st.selectbox(
                "サンプリング手法",
                options=["stratified", "quota", "random"],
                format_func=lambda x: {
                    "stratified": "層化サンプリング",
                    "quota": "クォータサンプリング",
                    "random": "ランダムサンプリング"
                }[x],
                key="ui_diversity_sampling_method"
            )
            prefer_x_api_toggle = st.toggle(
                "X APIを優先する",
                value=st.session_state.get('use_x_api', True),
                key="ui_diversity_prefer_x_api"
            )
            fallback_toggle = st.toggle(
                "Grok Web Searchにフォールバックする",
                value=True,
                key="ui_diversity_fallback"
            )
            if st.button("🧮 多様性サンプリングを開始", use_container_width=True):
                st.session_state['discovery_in_progress'] = True
                st.session_state['discovery_mode'] = 'diversity'
                st.session_state['diversity_params'] = {
                    'sampling_method': sampling_method,
                    'prefer_x_api': prefer_x_api_toggle,
                    'fallback_to_grok': fallback_toggle,
                    'dry_run': dry_run
                }
                st.rerun()

        st.caption("🎲 ランダム収集（プリセットクエリ）")
        if st.button("🎲 ランダム収集を開始", use_container_width=True):
            st.session_state['discovery_in_progress'] = True
            st.session_state['discovery_mode'] = 'random'
            st.rerun()

        # 収集中の処理
        if st.session_state.get('discovery_in_progress', False):
            st.info("🔄 候補アカウントを収集中… 少しお待ちください")
            try:
                discover_dir = Path(".cache/discover_results")
                discover_dir.mkdir(parents=True, exist_ok=True)

                mode = st.session_state.get('discovery_mode', 'keyword')

                if mode == 'diversity':
                    params = st.session_state.get('diversity_params', {}) or {}
                    sampling_method = params.get('sampling_method', 'stratified')
                    prefer_x_api_flag = params.get('prefer_x_api', True)
                    fallback_flag = params.get('fallback_to_grok', True)
                    cmd = [
                        "python", "ingest_accounts.py", "--diversity-sampling",
                        "--max-results", str(max_results)
                    ]
                    if sampling_method:
                        cmd.extend(["--sampling-method", sampling_method])
                    if not prefer_x_api_flag:
                        cmd.append("--no-prefer-x-api")
                    if not fallback_flag:
                        cmd.append("--no-fallback-grok")
                    if params.get('dry_run'):
                        cmd.append("--dry-run")
                    if not st.session_state.get('use_x_api', True):
                        cmd.append("--no-x-api")
                    subprocess.run(cmd, check=True)
                    pattern_csv = str(discover_dir / f"diversity_{sampling_method}_hybrid_accounts_*.csv")
                    pattern_txt = str(discover_dir / f"diversity_{sampling_method}_hybrid_accounts_*.txt")
                    discovered_kind = "diversity_hybrid"
                elif mode == 'random':
                    cmd = [
                        "python", "ingest_accounts.py", "--discover-random",
                        "--max-results", str(max_results)
                    ]
                    if dry_run:
                        cmd.append("--dry-run")
                    if not st.session_state.get('use_x_api', True):
                        cmd.append("--no-x-api")
                    subprocess.run(cmd, check=True)
                    pattern_csv = str(discover_dir / "random_accounts_*.csv")
                    pattern_txt = str(discover_dir / "random_accounts_*.txt")
                    discovered_kind = "grok_random"
                else:
                    cmd = [
                        "python", "ingest_accounts.py", "--discover-keyword", discover_keyword,
                        "--max-results", str(max_results)
                    ]
                    if dry_run:
                        cmd.append("--dry-run")
                    if not st.session_state.get('use_x_api', True):
                        cmd.append("--no-x-api")
                    subprocess.run(cmd, check=True)
                    pattern_csv = str(discover_dir / "keyword_*.csv")
                    pattern_txt = str(discover_dir / "keyword_*.txt")
                    discovered_kind = "grok_keyword"

                # 最新の結果ファイルを取得
                candidates = []
                files = sorted(glob.glob(pattern_csv) + glob.glob(pattern_txt), key=lambda p: Path(p).stat().st_mtime, reverse=True)
                latest = files[0] if files else None
                if latest:
                    if latest.endswith('.csv'):
                        try:
                            df = pd.read_csv(latest)
                            # handle 列が基本、なければ username/account/name をフォールバック
                            handle_col = None
                            for col in df.columns:
                                if str(col).lower() in ["handle", "username", "account", "name"]:
                                    handle_col = col
                                    break
                            if handle_col is not None:
                                candidates = [str(h).strip().lstrip('@') for h in df[handle_col].tolist() if str(h).strip()]
                            # 発見元をセッションに記録（Stage1が未実行でもUI表示用）
                            for h in candidates:
                                st.session_state['discovered_source'][h] = discovered_kind
                        except Exception as e:
                            st.warning(f"結果CSVの読込に失敗: {e}")
                    else:
                        try:
                            with open(latest, 'r', encoding='utf-8') as f:
                                lines = [l.strip() for l in f if l.strip() and not l.strip().startswith('#')]
                                candidates = [l.lstrip('@') for l in lines]
                            for h in candidates:
                                st.session_state['discovered_source'][h] = discovered_kind
                        except Exception as e:
                            st.warning(f"結果TXTの読込に失敗: {e}")

                # 既存にマージ（上限チェック）
                if candidates:
                    existing_list = st.session_state.get('accounts_list', [])
                    existing = set(existing_list)
                    new_unique = [c for c in candidates if c not in existing]
                    if new_unique:
                        available = max(0, MAX_ACCOUNTS - len(existing_list))
                        if available <= 0:
                            st.warning(f"最大 {MAX_ACCOUNTS} 件に達しています。新規追加できませんでした。")
                            to_add = []
                        else:
                            to_add = new_unique[:available]
                            dropped = max(0, len(new_unique) - available)
                            if dropped > 0:
                                st.warning(f"{dropped} 件は上限超過のため追加されませんでした。")
                            st.session_state['accounts_list'].extend(to_add)
                            # ステータス更新
                            st.session_state['account_status'] = check_cache_status(st.session_state['accounts_list'])
                        if to_add:
                            st.success(f"✅ 新規 {len(to_add)} アカウントを追加しました")
                    else:
                        st.info("新規追加はありません（重複）")
                    # ダウンロードとStage1送付
                    st.download_button(
                        label="📥 収集リストをダウンロード",
                        data=open(latest, 'rb').read(),
                        file_name=Path(latest).name
                    )
                    if st.button("📦 Stage1(ingest_accounts.py) に送る", use_container_width=True):
                        try:
                            cmd = ["python", "ingest_accounts.py", latest]
                            if not st.session_state.get('use_x_api', True):
                                cmd.append("--no-x-api")
                            subprocess.run(cmd, check=True)
                            st.success("Stage1 バッチを開始しました。完了後にキャッシュが反映されます。")
                        except Exception as e:
                            st.error(f"Stage1 実行に失敗: {e}")
                else:
                    st.warning("候補が見つかりませんでした")

            except subprocess.CalledProcessError as e:
                st.error(f"収集コマンドが失敗しました: {e}")
            except Exception as e:
                st.error(f"収集中にエラーが発生: {e}")
            finally:
                st.session_state['discovery_in_progress'] = False
                st.session_state.pop('discovery_mode', None)
                st.session_state.pop('diversity_params', None)
                st.rerun()

        # X API使用トグル
        st.subheader("🔑 X API設定")
        use_x_api = st.toggle(
            "X APIを使用する",
            value=st.session_state.get('use_x_api', True),
            help="X APIを無効化すると、Grok Web Searchのみで投稿を取得します。quality_scoreは暫定値になります。"
        )
        st.session_state['use_x_api'] = use_x_api
        
        if not use_x_api:
            mode_val = st.secrets.get("MODE", "dev")
            is_operational_mode = str(mode_val).lower() in {"prod", "staging"}
            if is_operational_mode:
                st.warning("⚠️ 運用モードでX APIを無効化しています。quality_scoreは暫定値になります。")
            else:
                st.info("ℹ️ X APIが無効化されています。Grok Web Searchのみで取得します。")

        # バッチ処理セクション
        st.subheader("⚡ バッチ処理")
        
        # 不足分を取得ボタン
        if accounts:
            pending_accounts = [acc for acc, status in st.session_state.get('account_status', {}).items() 
                              if status == 'pending']
            
            if pending_accounts:
                st.info(f"⏳ {len(pending_accounts)}アカウントの取得待ちがあります")
                
                if st.button("🚀 不足分を取得", type="primary", use_container_width=True):
                    st.session_state['batch_processing'] = True
                    st.session_state['processing_progress'] = 0
                    st.rerun()
            else:
                st.success("✅ 全アカウントのデータが揃っています")
        
        # バッチ処理中の進捗表示
        if st.session_state.get('batch_processing', False):
            st.progress(st.session_state.get('processing_progress', 0))
            st.info("🔄 バッチ処理中...")
        
        st.divider()
        
        # キャッシュ制御
        st.subheader("💾 データ管理")
        
        # キャッシュされているアカウントを表示
        cached_accounts = [k.replace('session_data_', '') for k in st.session_state.keys() if k.startswith('session_data_')]
        if cached_accounts:
            st.caption(f"📌 キャッシュ済み: {', '.join(['@' + a for a in cached_accounts])}")
        else:
            st.caption("📌 キャッシュなし")
        
        use_cache = st.checkbox("キャッシュを使用", value=True, help="以前取得したデータを再利用")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 全て再取得", use_container_width=True, help="全アカウントの投稿を再取得"):
                # セッション状態のデータをクリア
                keys_to_clear = [k for k in st.session_state.keys() if k.startswith('session_data_')]
                for key in keys_to_clear:
                    del st.session_state[key]
                # all_dataキャッシュもクリア
                if 'all_data_cache' in st.session_state:
                    del st.session_state['all_data_cache']
                if 'cached_accounts_key' in st.session_state:
                    del st.session_state['cached_accounts_key']
                st.success("✅ 全アカウントの最新データを取得します")
                st.rerun()
        
        with col2:
            if st.button("🗑️ キャッシュクリア", use_container_width=True, help="ファイルキャッシュを削除"):
                import shutil
                if os.path.exists(CACHE_DIR):
                    shutil.rmtree(CACHE_DIR)
                    os.makedirs(CACHE_DIR)
                # セッション状態もクリア
                keys_to_clear = [k for k in st.session_state.keys() if k.startswith('session_data_')]
                for key in keys_to_clear:
                    del st.session_state[key]
                # all_dataキャッシュもクリア
                if 'all_data_cache' in st.session_state:
                    del st.session_state['all_data_cache']
                if 'cached_accounts_key' in st.session_state:
                    del st.session_state['cached_accounts_key']
                st.success("✅ キャッシュをクリアしました")
                st.rerun()

        # エラー一覧（429等の失敗を可視化）
        st.markdown("---")
        st.subheader("❌ エラー一覧")
        error_accounts = [acc for acc, s in st.session_state.get('account_status', {}).items() if s == 'error']
        if error_accounts:
            err_df = pd.DataFrame({"アカウント": [f"@{a}" for a in error_accounts]})
            st.dataframe(err_df, width='content', hide_index=True)
            if st.button("🔁 エラーを再試行", use_container_width=True):
                # エラー状態をpendingへ戻し、次のバッチで再取得
                for a in error_accounts:
                    update_account_status(a, 'pending')
                # サマリ・メトリクスを即時更新
                st.session_state['account_status'] = check_cache_status(st.session_state.get('accounts_list', []))
                st.session_state['batch_processing'] = True
                st.session_state['processing_progress'] = 0
                st.success("再試行を開始しました")
                st.rerun()
        else:
            st.caption("現在エラーはありません")
        
        # KPIカード（サイドバー下部）
        st.markdown("---")
        st.subheader("📊 品質KPI")
        
        # アカウントデータからKPIを計算
        accounts_list = st.session_state.get('accounts_list', [])
        if accounts_list:
            # データソース別カウント
            twitter_count = 0
            web_search_count = 0
            generated_count = 0
            unverified_count = 0
            quality_scores = []
            
            for account in accounts_list:
                account_clean = account.lstrip('@')
                session_key = f"session_data_{account_clean}"
                
                if session_key in st.session_state:
                    data = st.session_state[session_key]
                    source = data.get('source', 'unknown')
                    
                    if source == 'twitter':
                        twitter_count += 1
                    elif source == 'web_search':
                        web_search_count += 1
                    elif source == 'generated':
                        generated_count += 1
                    
                    # 未確定チェック
                    persona = data.get('persona', {})
                    if not persona or len(persona) == 0:
                        unverified_count += 1
                    
                    # quality_score集計
                    if 'quality_score' in persona:
                        quality_scores.append(persona['quality_score'])
                
                # ステータスから未確定をカウント
                status = st.session_state.get('account_status', {}).get(account_clean, 'pending')
                if status == 'unverified':
                    unverified_count += 1
            
            total = len(accounts_list)
            if total > 0:
                real_count = twitter_count + web_search_count
                real_ratio = (real_count / total) * 100
                generated_ratio = (generated_count / total) * 100
                
                # 実/生成比
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("実データ比率", f"{real_ratio:.1f}%", f"{real_count}/{total}")
                with col2:
                    if generated_ratio > 0:
                        st.metric("生成データ率", f"{generated_ratio:.1f}%", f"{generated_count}/{total}", delta_color="inverse")
                    else:
                        st.metric("生成データ率", "0%", "0/0")
                
                # 未確定数
                st.metric("未確定ペルソナ", unverified_count, f"全{total}件中")
                
                # 平均/中央値quality_score
                if quality_scores:
                    avg_quality = sum(quality_scores) / len(quality_scores)
                    median_quality = sorted(quality_scores)[len(quality_scores) // 2]
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("平均quality_score", f"{avg_quality:.2f}", f"{len(quality_scores)}件")
                    with col2:
                        st.metric("中央値quality_score", f"{median_quality:.2f}", "")
                    
                    # X API無効時の警告
                    if not st.session_state.get('use_x_api', True):
                        st.warning("⚠️ X APIが無効化されているため、quality_scoreは暫定値です。")
                else:
                    st.caption("quality_scoreデータなし")
                    # X API無効時の警告
                    if not st.session_state.get('use_x_api', True):
                        st.warning("⚠️ X APIが無効化されているため、quality_scoreは暫定値になります。")
                
                # 運用モード警告（生成データがある場合）
                mode_val = st.secrets.get("MODE", "dev")
                is_operational = str(mode_val).lower() in {"prod", "staging"}
                
                if is_operational and generated_ratio > 0:
                    st.error(f"⚠️ 運用モードで生成データが検出されました ({generated_ratio:.1f}%)")
                    st.caption("実データ取得を再実行してください")
            else:
                st.caption("データなし")
        else:
            st.caption("アカウントが登録されていません")
    
    # メインエリア
    if not accounts:
        st.info("👈 サイドバーからXアカウントを入力してください")
        return
    
    # バッチ処理の実行
    if st.session_state.get('batch_processing', False):
        pending_accounts = [acc for acc, status in st.session_state.get('account_status', {}).items() 
                          if status == 'pending']
        
        if pending_accounts and grok_api:
            # バッチサイズで分割して処理
            total_pending = len(pending_accounts)
            processed = st.session_state.get('batch_processed_count', 0)
            
            if processed < total_pending:
                # 次のバッチを処理
                start_idx = processed
                end_idx = min(start_idx + BATCH_SIZE, total_pending)
                current_batch = pending_accounts[start_idx:end_idx]
                
                st.info(f"🔄 バッチ処理中: {processed + 1}-{end_idx} / {total_pending}")
                
                # プログレスバーを更新
                progress = (processed + len(current_batch)) / total_pending
                st.session_state['processing_progress'] = progress
                
                # バッチ内のアカウントを処理
                for i, account in enumerate(current_batch):
                    with st.spinner(f"📡 @{account}のデータを取得中... ({i+1}/{len(current_batch)})"):
                        try:
                            posts, persona = fetch_and_analyze_posts(
                                grok_api, 
                                account, 
                                use_cache=True, 
                                x_api=x_api,
                                force_refresh=False
                            )
                            
                            if posts and persona:
                                # ステータスを更新
                                update_account_status(account, 'cached_session')
                                st.success(f"✅ @{account}のデータを取得完了")
                            else:
                                st.warning(f"⚠️ @{account}のデータ取得に失敗")
                                update_account_status(account, 'error')
                                
                        except Exception as e:
                            st.error(f"❌ @{account}の処理中にエラー: {str(e)}")
                            logger.error(f"バッチ処理エラー @{account}: {str(e)}")
                            update_account_status(account, 'error')
                
                # 処理済みカウントを更新
                st.session_state['batch_processed_count'] = end_idx
                
                # 全て完了したかチェック
                if end_idx >= total_pending:
                    st.session_state['batch_processing'] = False
                    st.session_state['batch_processed_count'] = 0
                    st.success("🎉 バッチ処理が完了しました！")
                    st.rerun()
                else:
                    # 次のバッチのために少し待機
                    import time
                    time.sleep(1)
                    st.rerun()
            else:
                # 処理完了
                st.session_state['batch_processing'] = False
                st.session_state['batch_processed_count'] = 0
                st.success("🎉 バッチ処理が完了しました！")
                st.rerun()
        else:
            # 処理対象なし
            st.session_state['batch_processing'] = False
            st.session_state['batch_processed_count'] = 0
            st.info("処理対象のアカウントがありません")
            st.rerun()
    
    # アカウントリストの変更を検知
    if 'previous_accounts' not in st.session_state:
        st.session_state['previous_accounts'] = []
    
    previous_accounts = set(st.session_state['previous_accounts'])
    current_accounts = set(accounts)
    
    # 新しく追加されたアカウントを検出
    new_accounts = current_accounts - previous_accounts
    
    # 削除されたアカウントを検出
    removed_accounts = previous_accounts - current_accounts
    
    # 削除されたアカウントのキャッシュをクリーンアップ
    for removed in removed_accounts:
        session_key = f"session_data_{removed}"
        if session_key in st.session_state:
            del st.session_state[session_key]
            logger.info(f"削除されたアカウント @{removed} のキャッシュをクリア")
    
    # アカウントリストを更新（同一参照を避けるためコピーを保存）
    st.session_state['previous_accounts'] = list(accounts)
    
    # キャッシュ状況を更新
    st.session_state['account_status'] = check_cache_status(accounts)
    
    # all_dataもセッション状態で管理（再取得を防ぐ）
    all_data_key = "all_data_cache"
    current_accounts_key = tuple(sorted(accounts))  # ハッシュ可能なキーに変換
    
    # 現在のアカウントリストでキャッシュがあるかチェック
    if all_data_key in st.session_state and st.session_state.get('cached_accounts_key') == current_accounts_key:
        # キャッシュがある場合は再利用
        all_data = st.session_state[all_data_key]
        logger.info(f"all_dataをセッションキャッシュから読み込み: {len(all_data)}アカウント")
    else:
        # キャッシュがない、またはアカウントリストが変更された場合のみ取得
        logger.info("all_dataを新規取得")
        all_data = {}
        failed_accounts: List[str] = []
        for account in accounts:
            # まずファイルキャッシュを明示的に確認（CLI→UI 連携を最優先）
            account_clean = account.lstrip('@')
            cache_key = f"posts_{account_clean}"
            session_key = f"session_data_{account_clean}"

            cached_data = load_cache(cache_key) if use_cache else None
            new_account = account in new_accounts

            posts: List[Dict] = []
            persona: Dict = {}
            use_cached = False

            if cached_data is not None:
                cached_posts = cached_data.get('posts', [])
                if has_generated_posts(cached_posts):
                    st.warning(
                        f"⚠️ @{account}: キャッシュに生成データが含まれているため削除し再取得します。"
                    )
                    delete_cache(cache_key)
                    if session_key in st.session_state:
                        del st.session_state[session_key]
                    cached_data = None
                else:
                    if new_account:
                        st.info(f"📦 新しいアカウント: @{account} - キャッシュから即時ロード")
                    st.session_state[session_key] = cached_data
                    update_account_status(account_clean, 'cached_file')
                    posts = cached_posts
                    persona = cached_data.get('persona', {})
                    if ensure_quality_score(grok_api, persona, account_clean, x_api):
                        cached_data['persona'] = persona
                        st.session_state[session_key] = cached_data
                        cache_data(cache_key, cached_data)
                    use_cached = True

            should_force_refresh = new_account and not use_cached

            if not use_cached:
                if new_account and should_force_refresh:
                    st.info(f"🆕 新しいアカウント: @{account} - 投稿を取得します")
                posts, persona = fetch_and_analyze_posts(
                    grok_api,
                    account,
                    use_cache,
                    x_api,
                    force_refresh=should_force_refresh
                )

            if posts and persona:
                all_data[account] = {
                    'posts': posts,
                    'persona': persona
                }
            else:
                failed_accounts.append(account)
                update_account_status(account_clean, 'unverified')
                # セッションキャッシュは失敗時に破棄して再試行しやすくする
                if session_key in st.session_state:
                    del st.session_state[session_key]

        if failed_accounts:
            st.info(f"🔄 {len(failed_accounts)}アカウントの再試行中...")
            for account in failed_accounts:
                account_clean = account.lstrip('@')
                session_key = f"session_data_{account_clean}"
                posts, persona = fetch_and_analyze_posts(
                    grok_api,
                    account,
                    use_cache=False,
                    x_api=x_api,
                    force_refresh=True
                )

                if posts and persona:
                    all_data[account] = {
                        'posts': posts,
                        'persona': persona
                    }
                    st.success(f"✅ @{account}: 再試行で取得成功")
                else:
                    st.warning(f"⚠️ @{account}: 再試行後も取得失敗 - 議論から除外")
                    update_account_status(account_clean, 'unverified')
                    if session_key in st.session_state:
                        del st.session_state[session_key]

        # all_dataをセッション状態に保存
        st.session_state[all_data_key] = all_data
        st.session_state['cached_accounts_key'] = tuple(sorted(all_data.keys()))
        logger.info(f"all_dataをセッションキャッシュに保存: {len(all_data)}アカウント")
    
    # タブ作成
    tabs = st.tabs(["🎯 議論シミュレーション", "👤 ペルソナ分析", "📊 投稿データ", "📋 アカウント管理"])
    
    # === タブ1: 議論シミュレーション（チャット風UI + ターン制） ===
    with tabs[0]:
        st.header("🎯 議論シミュレーション")
        
        if not all_data:
            st.warning("アカウントデータがありません")
            return
        
        # DebateUI初期化
        debate_ui = DebateUI()
        
        # 上部コントロール
        col1, col2, col3 = st.columns([3, 1, 1])
        
        with col1:
            # トピック入力
            topic = st.text_input(
                "💬 議論トピック",
                value=st.session_state.get('debate_topic', 'AIの倫理的課題について'),
                placeholder="議論したいトピックを入力してください",
                autocomplete="off"
            )
            st.session_state['debate_topic'] = topic
        
        with col2:
            # 新しい議論を開始
            if st.button("🆕 新しい議論", use_container_width=True):
                debate_ui.clear_debate()
                if grok_api:
                    grok_api.clear_conversation_history()
                # アバター割り当てもクリア（完全リセット）
                if 'account_avatars' in st.session_state:
                    st.session_state['account_avatars'] = {}
                st.success("議論をリセットしました")
                st.rerun()
        
        with col3:
            # 現在のラウンド表示
            current_round = debate_ui.get_current_round()
            st.metric("ラウンド", current_round)
        
        st.markdown("---")
        
        # 参加者リスト
        debate_ui.render_participant_list(list(all_data.keys()))
        
        st.markdown("---")
        
        # 議論タイムライン
        debate_ui.render_debate_timeline()
        
        st.markdown("---")
        
        # アクションボタン
        if current_round == 0:
            # 初回ラウンド: 全員の意見を生成
            if st.button("🚀 議論を開始", type="primary", use_container_width=True):
                if not topic.strip():
                    st.error("トピックを入力してください")
                else:
                    # 類似検索の初期化
                    with st.spinner("🔍 類似検索モデルをロード中..."):
                        searcher = SimilaritySearcher()
                    
                    # ペルソナマネージャー初期化
                    persona_manager = PersonaManager()
                    
                    # エージェント機能の状態を取得
                    use_history, use_web_search, _ = get_agent_settings()
                    
                    # 各アカウントの初回意見を生成
                    for account, data in all_data.items():
                        posts = data['posts']
                        persona = data['persona']
                        
                        if not posts or not persona:
                            st.warning(f"⚠️ @{account}: データ不足のためスキップ")
                            continue
                        
                        # 関連投稿検索
                        with st.spinner(f"🔍 @{account}の関連投稿を検索中..."):
                            relevant_posts = searcher.find_relevant_posts(topic, posts, top_k=TOP_K_RELEVANT_POSTS)
                        
                        # 意見生成
                        with st.spinner(f"✍️ @{account}の意見を生成中..."):
                            opinion = grok_api.generate_debate_opinion(
                                topic, 
                                persona, 
                                relevant_posts,
                                use_history=use_history,
                                enable_live_search=use_web_search
                            )
                        
                        if opinion:
                            # メッセージを追加
                            debate_ui.add_message(
                                account=account,
                                name=persona.get('name', account),
                                content=opinion,
                                message_type="initial"
                            )
                    
                    # 会話履歴サマリーを更新
                    if use_history:
                        st.session_state['grok_history_summary'] = grok_api.get_conversation_summary()
                    
                    # ラウンドを進める
                    debate_ui.increment_round()
                    st.success("✅ 初回意見を生成しました！")
                    st.rerun()
        
        else:
            # 反論ラウンド: 誰が誰に反論するか選択
            st.subheader("🔄 次のラウンドを生成")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # 反論する人を選択
                replier = st.selectbox(
                    "反論する人",
                    options=list(all_data.keys()),
                    format_func=lambda x: f"@{x} ({all_data[x]['persona'].get('name', x)})"
                )
            
            with col2:
                # 反論対象を選択
                other_accounts = [acc for acc in all_data.keys() if acc != replier]
                if other_accounts:
                    target = st.selectbox(
                        "反論対象",
                        options=other_accounts,
                        format_func=lambda x: f"@{x} ({all_data[x]['persona'].get('name', x)})"
                    )
                else:
                    target = None
                    st.warning("反論対象がいません")
            
            col_action1, col_action2 = st.columns(2)
            
            with col_action1:
                # 選択した反論を生成
                if target and st.button("💬 選択した反論を生成", type="primary", use_container_width=True):
                    # 対象の最新意見を取得
                    target_messages = [m for m in debate_ui.get_messages() if m.account == target]
                    if target_messages:
                        target_message = target_messages[-1]
                        
                        # エージェント機能の状態を取得
                        use_history, use_web_search, _ = get_agent_settings()
                        
                        # これまでの文脈を構築
                        previous_context = build_previous_context(debate_ui)
                        
                        # 反論生成
                        with st.spinner(f"✍️ @{replier}の反論を生成中..."):
                            rebuttal = grok_api.generate_rebuttal(
                                topic=topic,
                                persona=all_data[replier]['persona'],
                                target_account=target,
                                target_opinion=target_message.content,
                                previous_context=previous_context,
                                use_history=use_history,
                                enable_live_search=use_web_search
                            )
                        
                        if rebuttal:
                            # メッセージを追加
                            debate_ui.add_message(
                                account=replier,
                                name=all_data[replier]['persona'].get('name', replier),
                                content=rebuttal,
                                reply_to=target,
                                message_type="rebuttal"
                            )
                            
                            # 会話履歴サマリーを更新
                            if use_history:
                                st.session_state['grok_history_summary'] = grok_api.get_conversation_summary()
                            
                            st.success(f"✅ @{replier}の反論を生成しました！")
                            st.rerun()
                        else:
                            st.error("反論の生成に失敗しました")
                    else:
                        st.error(f"@{target}の意見が見つかりません")
            
            with col_action2:
                # 全員に反論させる
                if st.button("🔄 全員の反論を生成", use_container_width=True):
                    # エージェント機能の状態を取得
                    use_history, use_web_search, _ = get_agent_settings()
                    
                    # 各アカウントが他の誰かに反論
                    accounts_list = list(all_data.keys())
                    for i, account in enumerate(accounts_list):
                        # 反論対象を選択（次の人、または最初の人）
                        target_idx = (i + 1) % len(accounts_list)
                        target_account = accounts_list[target_idx]
                        
                        # 対象の最新意見を取得
                        target_messages = [m for m in debate_ui.get_messages() if m.account == target_account]
                        if not target_messages:
                            continue
                        
                        target_message = target_messages[-1]
                        
                        # これまでの文脈を構築
                        previous_context = build_previous_context(debate_ui)
                        
                        # 反論生成
                        with st.spinner(f"✍️ @{account}の反論を生成中..."):
                            rebuttal = grok_api.generate_rebuttal(
                                topic=topic,
                                persona=all_data[account]['persona'],
                                target_account=target_account,
                                target_opinion=target_message.content,
                                previous_context=previous_context,
                                use_history=use_history,
                                enable_live_search=use_web_search
                            )
                        
                        if rebuttal:
                            # メッセージを追加
                            debate_ui.add_message(
                                account=account,
                                name=all_data[account]['persona'].get('name', account),
                                content=rebuttal,
                                reply_to=target_account,
                                message_type="rebuttal"
                            )
                    
                    # ラウンドを進める
                    debate_ui.increment_round()
                    
                    # 会話履歴サマリーを更新
                    if use_history:
                        st.session_state['grok_history_summary'] = grok_api.get_conversation_summary()
                    
                    st.success("✅ 全員の反論を生成しました！")
                    st.rerun()
    
    # === タブ2: ペルソナ分析 ===
    with tabs[1]:
        st.header("👤 ペルソナ分析")
        
        for account, data in all_data.items():
            persona = data['persona']
            posts = data['posts']
            
            if not persona:
                continue
            
            persona_manager = PersonaManager()
            full_persona = persona_manager.create_persona(account, posts, persona)
            
            # ペルソナサマリー表示
            st.markdown(persona_manager.format_persona_summary(full_persona))
            st.markdown("---")
    
    # === タブ3: 投稿データ ===
    with tabs[2]:
        st.header("📊 投稿データ")
        
        for account, data in all_data.items():
            posts = data['posts']
            
            if not posts:
                continue
            
            st.subheader(f"@{account} の投稿 ({len(posts)}件)")
            
            # エクスポートボタン
            col1, col2 = st.columns([3, 1])
            with col2:
                json_data = json.dumps(posts, ensure_ascii=False, indent=2)
                st.download_button(
                    label="📥 JSONダウンロード",
                    data=json_data,
                    file_name=f"{account}_posts_{datetime.now().strftime('%Y%m%d')}.json",
                    mime="application/json"
                )
            
            # 投稿リスト表示
            for i, post in enumerate(posts[:10]):  # 最初の10件
                with st.expander(f"投稿 {i+1} - {post.get('date', 'N/A')[:10]}"):
                    st.markdown(post['text'])
                    st.markdown(f"[🔗 投稿を見る]({post['link']})")
            
            if len(posts) > 10:
                st.info(f"残り{len(posts) - 10}件の投稿は非表示")
            
            st.markdown("---")
    
    # === タブ4: アカウント管理 ===
    with tabs[3]:
        st.header("📋 アカウント管理")
        
        if not all_data:
            st.warning("アカウントデータがありません")
        else:
            # フィルタリングオプション
            col1, col2, col3 = st.columns(3)
            
            with col1:
                status_filter = st.selectbox(
                    "ステータスでフィルタ",
                    options=["全て", "キャッシュ済み", "取得待ち", "エラー"],
                    help="アカウントのステータスでフィルタリング"
                )
            
            with col2:
                search_term = st.text_input(
                    "アカウント名で検索",
                    placeholder="アカウント名の一部を入力",
                    help="アカウント名の一部で検索",
                    autocomplete="off"
                )
            
            with col3:
                sort_option = st.selectbox(
                    "並び順",
                    options=["アカウント名", "ステータス", "投稿数"],
                    help="表示順序を選択"
                )
            
            # フィルタリングとソート
            filtered_accounts = []
            for account, data in all_data.items():
                # ステータスフィルタ
                account_status = st.session_state.get('account_status', {}).get(account, 'pending')
                if status_filter == "全て":
                    pass
                elif status_filter == "キャッシュ済み" and account_status not in ['cached_session', 'cached_file']:
                    continue
                elif status_filter == "取得待ち" and account_status != 'pending':
                    continue
                elif status_filter == "エラー" and account_status != 'error':
                    continue
                
                # データソース取得（セッション優先 → ファイル）
                sess_key = f"session_data_{account}"
                source_val = None
                if sess_key in st.session_state:
                    source_val = st.session_state[sess_key].get('source')
                if not source_val:
                    cached_obj = load_cache(f"posts_{account}")
                    if cached_obj:
                        source_val = cached_obj.get('source')
                # カテゴリマッピング
                if source_val == 'twitter':
                    source_cat = 'Twitter'
                elif source_val == 'web_search':
                    source_cat = 'Web'
                elif source_val == 'generated':
                    source_cat = 'Sample'
                elif source_val == 'grok_keyword':
                    source_cat = 'Keyword'
                elif source_val == 'grok_random':
                    source_cat = 'Random'
                elif source_val == 'diversity_hybrid':
                    source_cat = 'Diversity'
                else:
                    source_cat = 'Unknown'
                
                # ソースフィルタ（サイドバー）
                sf = st.session_state.get('source_filter', ["全て"]) or ["全て"]
                if "全て" not in sf:
                    if source_cat not in sf:
                        continue
                
                # 検索フィルタ
                if search_term and search_term.lower() not in account.lower():
                    continue
                
                # 未取得のアカウントは discovery 情報を補助表示
                if source_cat == 'Unknown':
                    disc = st.session_state.get('discovered_source', {}).get(account)
                    if disc == 'grok_keyword':
                        source_cat = 'Keyword'
                    elif disc == 'grok_random':
                        source_cat = 'Random'
                    elif disc == 'diversity_hybrid':
                        source_cat = 'Diversity'
                
                filtered_accounts.append((account, data, account_status, source_cat))
            
            # ソート
            if sort_option == "アカウント名":
                filtered_accounts.sort(key=lambda x: x[0])
            elif sort_option == "ステータス":
                filtered_accounts.sort(key=lambda x: x[2])
            elif sort_option == "投稿数":
                filtered_accounts.sort(key=lambda x: len(x[1].get('posts', [])), reverse=True)
            
            # 結果表示
            st.markdown(f"**表示中: {len(filtered_accounts)} / {len(all_data)} アカウント**")
            
            if filtered_accounts:
                # データフレーム形式で表示
                display_data = []
                for account, data, status, source_cat in filtered_accounts:
                    posts = data.get('posts', [])
                    persona = data.get('persona', {})
                    
                    # ステータス表示
                    status_display = {
                        'cached_session': '✅ セッション',
                        'cached_file': '📦 ファイル',
                        'pending': '⏳ 待機中',
                        'error': '❌ エラー'
                    }.get(status, '❓ 不明')
                    
                    # ソースバッジ
                    if source_cat == 'Twitter':
                        source_display = '✅ Twitter'
                    elif source_cat == 'Web':
                        source_display = '🌐 Web'
                    elif source_cat == 'Sample':
                        source_display = '📝 Sample'
                    elif source_cat == 'Keyword':
                        source_display = '🔍 Keyword'
                    elif source_cat == 'Random':
                        source_display = '🎲 Random'
                    else:
                        source_display = '❓ Unknown'
                    
                    # キャッシュ日時を取得
                    cache_time = "不明"
                    if status in ['cached_session', 'cached_file']:
                        fetched_at = None
                        # セッションにあれば優先
                        session_key = f"session_data_{account}"
                        if session_key in st.session_state:
                            fetched_at = st.session_state[session_key].get('fetched_at')
                        if not fetched_at:
                            # ファイルキャッシュから取得
                            cached = load_cache(f"posts_{account}")
                            if cached:
                                fetched_at = cached.get('fetched_at')
                        if fetched_at:
                            try:
                                cache_time = datetime.fromisoformat(fetched_at).strftime("%Y-%m-%d %H:%M")
                            except Exception:
                                cache_time = fetched_at
                    
                    display_data.append({
                        "アカウント": f"@{account}",
                        "ステータス": status_display,
                        "データソース": source_display,
                        "投稿数": len(posts),
                        "ペルソナ名": persona.get('name', account),
                        "キャッシュ日時": cache_time
                    })
                
                # データフレーム表示
                df = pd.DataFrame(display_data)
                st.dataframe(
                    df,
                    width='stretch',
                    hide_index=True,
                    column_config={
                        "アカウント": st.column_config.TextColumn("アカウント", width="medium"),
                        "ステータス": st.column_config.TextColumn("ステータス", width="small"),
                        "データソース": st.column_config.TextColumn("データソース", width="small"),
                        "投稿数": st.column_config.NumberColumn("投稿数", width="small"),
                        "ペルソナ名": st.column_config.TextColumn("ペルソナ名", width="medium"),
                        "キャッシュ日時": st.column_config.TextColumn("キャッシュ日時", width="small")
                    }
                )
                
                # 一括操作ボタン
                st.markdown("---")
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button("🔄 選択したアカウントを再取得", use_container_width=True):
                        # フィルタされたアカウントを再取得
                        for account, _, _, _ in filtered_accounts:
                            session_key = f"session_data_{account}"
                            if session_key in st.session_state:
                                del st.session_state[session_key]
                        if 'all_data_cache' in st.session_state:
                            del st.session_state['all_data_cache']
                        if 'cached_accounts_key' in st.session_state:
                            del st.session_state['cached_accounts_key']
                        st.success("選択したアカウントの再取得を開始します")
                        st.rerun()
                
                with col2:
                    if st.button("📥 データをエクスポート", use_container_width=True):
                        # 全データをJSONでエクスポート
                        export_data = {}
                        for account, data, _, _ in filtered_accounts:
                            export_data[account] = {
                                'posts': data.get('posts', []),
                                'persona': data.get('persona', {})
                            }
                        
                        json_data = json.dumps(export_data, ensure_ascii=False, indent=2)
                        st.download_button(
                            label="📥 JSONダウンロード",
                            data=json_data,
                            file_name=f"persona_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                            mime="application/json"
                        )
                
                with col3:
                    if st.button("🗑️ 選択したアカウントを削除", use_container_width=True):
                        # フィルタされたアカウントを削除
                        for account, _, _, _ in filtered_accounts:
                            if account in st.session_state['accounts_list']:
                                st.session_state['accounts_list'].remove(account)
                            session_key = f"session_data_{account}"
                            if session_key in st.session_state:
                                del st.session_state[session_key]
                        if 'all_data_cache' in st.session_state:
                            del st.session_state['all_data_cache']
                        if 'cached_accounts_key' in st.session_state:
                            del st.session_state['cached_accounts_key']
                        st.success("選択したアカウントを削除しました")
                        st.rerun()
            else:
                st.info("フィルタ条件に一致するアカウントがありません")
    
    # フッター
    st.markdown("---")
    st.markdown("**Persona Debate Simulator** | Powered by Grok API & Streamlit")


if __name__ == "__main__":
    main()
