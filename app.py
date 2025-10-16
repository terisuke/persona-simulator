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

# 自作モジュール
from utils.grok_api import GrokAPI
from utils.x_api import XAPIClient
from utils.persona import PersonaManager
from utils.similarity import SimilaritySearcher

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
    x_api: Optional[XAPIClient] = None
) -> tuple[List[Dict], Dict]:
    """
    投稿を取得してペルソナを生成
    
    Returns:
        (投稿リスト, ペルソナプロファイル)
    """
    cache_key = f"posts_{account.lstrip('@')}"
    
    # キャッシュチェック
    if use_cache:
        cached = load_cache(cache_key)
        if cached:
            st.info(f"📦 キャッシュから@{account}のデータをロード")
            return cached['posts'], cached['persona']
    
    # 投稿取得
    with st.spinner(f"📡 @{account}の投稿を取得中..."):
        posts = grok_api.fetch_posts(
            account, 
            limit=20, 
            since_date="2024-01-01",
            x_api_client=x_api
        )
    
    if not posts:
        st.warning(f"⚠️ @{account}の投稿が取得できませんでした")
        return [], {}
    
    # X API使用の場合は表示を変える
    if x_api:
        st.success(f"✅ {len(posts)}件の実際の投稿を取得（X API v2）")
    else:
        st.info(f"📝 {len(posts)}件のサンプル投稿を生成（Grok LLM）")
    
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
    
    # キャッシュ保存
    cache_data(cache_key, {'posts': posts, 'persona': persona_profile})
    
    return posts, persona_profile


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
        
        # アカウント入力（10個まで）
        st.subheader("📝 Xアカウント入力")
        st.markdown("最大10アカウントまで入力可能（@付きでも可）")
        
        num_accounts = st.number_input(
            "分析するアカウント数",
            min_value=1,
            max_value=10,
            value=1,
            step=1
        )
        
        accounts = []
        for i in range(num_accounts):
            account = st.text_input(
                f"アカウント {i+1}",
                value="cor_terisuke" if i == 0 else "",
                key=f"account_{i}",
                placeholder="例: cor_terisuke"
            )
            if account.strip():
                accounts.append(account.strip())
        
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
        use_cache = st.checkbox("キャッシュを使用", value=True, help="以前取得したデータを再利用")
        
        if st.button("🔄 キャッシュをクリア"):
            import shutil
            if os.path.exists(CACHE_DIR):
                shutil.rmtree(CACHE_DIR)
                os.makedirs(CACHE_DIR)
            st.success("キャッシュをクリアしました")
            st.rerun()
    
    # メインエリア
    if not accounts:
        st.info("👈 サイドバーからXアカウントを入力してください")
        return
    
    # タブ作成
    tabs = st.tabs(["🎯 議論シミュレーション", "👤 ペルソナ分析", "📊 投稿データ"])
    
    # 投稿とペルソナを取得
    all_data = {}
    for account in accounts:
        posts, persona = fetch_and_analyze_posts(grok_api, account, use_cache, x_api)
        all_data[account] = {
            'posts': posts,
            'persona': persona
        }
    
    # === タブ1: 議論シミュレーション ===
    with tabs[0]:
        st.header("🎯 議論シミュレーション")
        
        if not all_data:
            st.warning("アカウントデータがありません")
            return
        
        # トピック入力
        topic = st.text_area(
            "議論トピックを入力",
            value="AIの倫理的課題について",
            height=100,
            help="このトピックについて各ペルソナの意見を生成します"
        )
        
        # 生成ボタン
        if st.button("🚀 議論を生成", type="primary", use_container_width=True):
            if not topic.strip():
                st.error("トピックを入力してください")
                return
            
            # 類似検索の初期化
            with st.spinner("🔍 類似検索モデルをロード中..."):
                searcher = SimilaritySearcher()
            
            # ペルソナマネージャー初期化
            persona_manager = PersonaManager()
            
            st.markdown("---")
            
            # 各アカウントの意見を生成
            for account, data in all_data.items():
                posts = data['posts']
                persona = data['persona']
                
                if not posts or not persona:
                    st.warning(f"⚠️ @{account}: データ不足のためスキップ")
                    continue
                
                st.subheader(f"💭 @{account} ({persona.get('name', account)})")
                
                # ペルソナ作成
                full_persona = persona_manager.create_persona(account, posts, persona)
                
                # 関連投稿検索
                with st.spinner(f"🔍 @{account}の関連投稿を検索中..."):
                    relevant_posts = searcher.find_relevant_posts(topic, posts, top_k=3)
                
                # エージェント機能の状態を取得
                use_history = st.session_state.get('enable_history', False) if 'enable_history' in st.session_state else enable_history
                use_web_search = st.session_state.get('enable_web_search', False) if 'enable_web_search' in st.session_state else enable_web_search
                
                # 意見生成（エージェント機能付き）
                with st.spinner(f"✍️ @{account}の意見を生成中..."):
                    opinion = grok_api.generate_debate_opinion(
                        topic, 
                        persona, 
                        relevant_posts,
                        use_history=use_history,
                        enable_live_search=use_web_search
                    )
                
                # 会話履歴サマリーを更新
                if use_history:
                    st.session_state['grok_history_summary'] = grok_api.get_conversation_summary()
                
                if opinion:
                    # エージェント機能表示
                    agent_badges = []
                    if use_web_search:
                        agent_badges.append("🌐 Web検索")
                    if use_history:
                        agent_badges.append("💬 会話履歴")
                    
                    if agent_badges:
                        st.markdown(f"**エージェント機能**: {' | '.join(agent_badges)}")
                    
                    # 意見表示
                    st.markdown("**意見:**")
                    st.info(opinion)
                    
                    # 口調模倣検証
                    validation = persona_manager.validate_tone_mimicry(opinion, full_persona)
                    
                    # 検証結果
                    col1, col2, col3 = st.columns([2, 1, 1])
                    with col1:
                        st.metric("口調模倣スコア", f"{validation['score']:.1f}%")
                    with col2:
                        st.metric("検証", "✅ 合格" if validation['passed'] else "❌ 不合格")
                    with col3:
                        if st.button(f"詳細", key=f"detail_{account}"):
                            st.json(validation)
                    
                    # 引用投稿
                    if relevant_posts:
                        with st.expander("📎 引用された投稿"):
                            for i, post in enumerate(relevant_posts):
                                st.markdown(f"**[{i+1}]** (類似度: {post.get('similarity_score', 0):.3f})")
                                st.markdown(f"> {post['text']}")
                                st.markdown(f"[🔗 投稿を見る]({post['link']})")
                                st.markdown("---")
                else:
                    st.error(f"❌ @{account}の意見生成に失敗しました")
                
                st.markdown("---")
    
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

