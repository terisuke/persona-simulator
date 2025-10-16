"""
Persona Debate Simulator (Terisuke Edition)
Streamlitメインアプリケーション
"""

import streamlit as st
import logging
import json
import pickle
import os
from datetime import datetime
from typing import List, Dict, Optional

# 定数定義
MAX_ACCOUNTS = 10
DEFAULT_POST_LIMIT = 20
TOP_K_RELEVANT_POSTS = 3
RECENT_CONTEXT_MESSAGES = 3

# 自作モジュール
from utils.grok_api import GrokAPI
from utils.x_api import XAPIClient
from utils.persona import PersonaManager
from utils.similarity import SimilaritySearcher
from utils.debate_ui import DebateUI

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


def load_x_api() -> Optional[XAPIClient]:
    """X API v2インスタンスをロード（オプション）"""
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


def fetch_and_analyze_posts(
    grok_api: GrokAPI, 
    account: str, 
    use_cache: bool = True,
    x_api: Optional[XAPIClient] = None,
    force_refresh: bool = False
) -> tuple[List[Dict], Dict]:
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
        return data['posts'], data['persona']
    
    # ファイルキャッシュチェック
    if use_cache and not force_refresh:
        cached = load_cache(cache_key)
        if cached:
            st.info(f"📦 キャッシュから@{account}のデータをロード")
            # セッション状態にも保存
            st.session_state[session_key] = cached
            return cached['posts'], cached['persona']
    
    # 投稿取得
    with st.spinner(f"📡 @{account}の投稿を取得中..."):
        posts = grok_api.fetch_posts(
            account, 
            limit=DEFAULT_POST_LIMIT, 
            since_date="2024-01-01",
            x_api_client=x_api
        )
    
    if not posts:
        st.warning(f"⚠️ @{account}の投稿が取得できませんでした")
        return [], {}
    
    # 取得方法を判定して表示
    if posts[0]['id'].startswith('web_search_'):
        st.success(f"✅ {len(posts)}件の実投稿を取得（🌐 Grok Web Search）")
    elif posts[0]['id'].startswith('sample_') or posts[0]['id'].startswith('generated_'):
        st.info(f"📝 {len(posts)}件のサンプル投稿を生成（⚠️ フォールバック）")
    else:
        st.success(f"✅ {len(posts)}件の実投稿を取得（🔑 X API v2）")
    
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
    
    # データを保存
    data = {'posts': posts, 'persona': persona_profile}
    
    # ファイルキャッシュ保存
    cache_data(cache_key, data)
    
    # セッション状態にも保存（自動再実行時に再取得を防ぐ）
    st.session_state[session_key] = data
    
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
    if 'grok_history_summary' not in st.session_state:
        st.session_state['grok_history_summary'] = "会話履歴なし"
    
    # タイトル
    st.title("💬 Persona Debate Simulator")
    st.markdown("**AI Agent Edition** - Xアカウントからペルソナを生成し、議論をシミュレートします")
    
    # エージェント機能説明
    st.markdown("""
    <div style="background-color: #f0f2f6; padding: 10px; border-radius: 5px; margin-bottom: 20px;">
    🤖 <b>AIエージェント</b> | 🌐 マルチプラットフォーム分析 | 💬 会話履歴保持
    </div>
    """, unsafe_allow_html=True)
    
    # サイドバー
    with st.sidebar:
        st.header("⚙️ 設定")
        
        # APIキーチェック
        grok_api = load_grok_api()
        if not grok_api:
            st.stop()
        
        st.success("✅ Grok API接続OK")
        
        # X API v2チェック（オプション）
        x_api = load_x_api()
        if x_api:
            st.success("✅ X API v2接続OK（実投稿取得）")
        else:
            st.info("ℹ️ X API未設定（サンプル投稿生成）")
        
        # アカウント管理（追加ボタン方式）
        st.subheader("📝 Xアカウント管理")
        
        # セッション状態でアカウントリストを管理
        if 'accounts_list' not in st.session_state:
            st.session_state['accounts_list'] = ['cor_terisuke']  # デフォルト
        
        # 現在のアカウントリストを表示
        if st.session_state['accounts_list']:
            st.markdown("**登録済みアカウント:**")
            for i, acc in enumerate(st.session_state['accounts_list']):
                col1, col2, col3 = st.columns([3, 1, 1])
                with col1:
                    st.text(f"@{acc}")
                with col2:
                    if st.button("🔄", key=f"refresh_{i}", help=f"@{acc}の投稿を再取得"):
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
                    if st.button("🗑️", key=f"delete_{i}", help=f"@{acc}を削除"):
                        st.session_state['accounts_list'].pop(i)
                        # セッションキャッシュも削除
                        session_key = f"session_data_{acc}"
                        if session_key in st.session_state:
                            del st.session_state[session_key]
                        # all_dataキャッシュもクリア
                        if 'all_data_cache' in st.session_state:
                            del st.session_state['all_data_cache']
                        if 'cached_accounts_key' in st.session_state:
                            del st.session_state['cached_accounts_key']
                        st.rerun()
        
        st.markdown("---")
        
        # 新規アカウント追加
        if len(st.session_state['accounts_list']) < MAX_ACCOUNTS:
            st.markdown("**アカウント追加:**")
            new_account = st.text_input(
                "アカウント名を入力",
                value="",
                key="new_account_input",
                placeholder="例: elonmusk（@なしで入力）",
                help="アカウント名を完全に入力してから追加ボタンをクリック"
            )
            
            col1, col2 = st.columns([3, 1])
            with col1:
                if st.button("➕ アカウント追加", type="primary", use_container_width=True):
                    if new_account.strip():
                        clean_account = new_account.strip().lstrip('@')
                        if clean_account not in st.session_state['accounts_list']:
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
    
    # メインエリア
    if not accounts:
        st.info("👈 サイドバーからXアカウントを入力してください")
        return
    
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
    
    # アカウントリストを更新
    st.session_state['previous_accounts'] = accounts
    
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
        for account in accounts:
            # 新しいアカウントの場合は強制再取得
            force_refresh = account in new_accounts
            if force_refresh:
                st.info(f"🆕 新しいアカウント: @{account} - 投稿を取得します")
            
            posts, persona = fetch_and_analyze_posts(
                grok_api, 
                account, 
                use_cache, 
                x_api,
                force_refresh=force_refresh
            )
            all_data[account] = {
                'posts': posts,
                'persona': persona
            }
        
        # all_dataをセッション状態に保存
        st.session_state[all_data_key] = all_data
        st.session_state['cached_accounts_key'] = current_accounts_key
        logger.info(f"all_dataをセッションキャッシュに保存: {len(all_data)}アカウント")
    
    # タブ作成
    tabs = st.tabs(["🎯 議論シミュレーション", "👤 ペルソナ分析", "📊 投稿データ"])
    
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
                placeholder="議論したいトピックを入力してください"
            )
            st.session_state['debate_topic'] = topic
        
        with col2:
            # 新しい議論を開始
            if st.button("🆕 新しい議論", use_container_width=True):
                debate_ui.clear_debate()
                if grok_api:
                    grok_api.clear_conversation_history()
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
    
    # フッター
    st.markdown("---")
    st.markdown("**Persona Debate Simulator** | Powered by Grok API & Streamlit")


if __name__ == "__main__":
    main()

