"""
Grok API連携モジュール
X投稿の取得とLLM生成を担当
"""

import requests
import os
import logging
import json
from typing import List, Dict, Optional
from datetime import datetime
from .error_handler import (
    ErrorHandler, 
    PerformanceLogger,
    APIConnectionError,
    log_function_call
)

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
    構造化ログを出力（grok_api.py用）
    
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

# 定数定義
MAX_CITATION_POSTS = 3  # 引用する投稿の最大数
# 生成フォールバックのデフォルト許可可否（運用では False を強制）
ALLOW_GENERATED_DEFAULT = False

# プリセットキーワード（頻出分野）
PRESET_KEYWORDS = {
    "ai_engineer": "AI engineer",
    "data_scientist": "data scientist",
    "ml_engineer": "machine learning engineer",
    "startup_founder": "startup founder",
    "tech_executive": "tech executive",
    "venture_capital": "venture capitalist",
    "cybersecurity": "cybersecurity expert",
    "cloud_architect": "cloud architect",
    "devops_engineer": "DevOps engineer",
    "blockchain_developer": "blockchain developer",
    "product_manager": "product manager",
    "ux_designer": "UX designer",
    "software_engineer": "software engineer",
    "open_source": "open source contributor",
    "tech_writer": "tech writer",
    "data_engineer": "data engineer"
}

# 品質基準（アカウント発見時のフィルタリングに使用）
# 実世界指標（X APIメトリクス）ベースで評価
QUALITY_THRESHOLDS = {
    'min_followers': 100,          # 最小フォロワー数
    'min_tweet_count': 50,         # 最小ツイート数（投稿数）
    'max_days_inactive': 180,      # 最大非アクティブ日数（最終ツイートから）
    'min_quality_score': 0.6      # 最小品質スコア（0.0-1.0）
}


class GrokAPI:
    """Grok APIとの連携を管理するクラス"""
    
    BASE_URL = "https://api.x.ai/v1"
    
    # 利用可能なGrokモデル（2025年10月時点）
    # - grok-4-fast-reasoning: 最新・高速推論モデル（推奨）
    # - grok-3: 標準モデル
    # - grok-beta: 廃止済み（2025年9月15日）
    DEFAULT_MODEL = "grok-4-fast-reasoning"
    
    def __init__(self, api_key: str, model: str = None):
        """
        Args:
            api_key: Grok APIキー
            model: 使用するモデル名（デフォルト: grok-4-fast-reasoning）
        """
        self.api_key = api_key
        self.model = model or self.DEFAULT_MODEL
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        self.conversation_history = []  # 会話履歴
        self.last_response_id = None    # 最後のレスポンスID
    
    @log_function_call
    def fetch_posts(
        self, 
        account: str, 
        limit: int = 20, 
        since_date: str = "2024-01-01",
        x_api_client=None,
        max_rate_wait_seconds: int = 900,
        allow_generated: Optional[bool] = None
    ) -> List[Dict]:
        """
        指定されたXアカウントの投稿を取得
        
        取得優先順位:
        1. X API v2 (fetch_user_tweets)
        2. X API v2 (search_recent_tweets with from:username)
        3. Grok Realtime Web Search
        4. フォールバック: サンプル投稿生成
        
        Args:
            account: Xアカウント名（@付きでも可）
            limit: 取得する投稿数
            since_date: この日付以降の投稿を取得（X API使用時）
            x_api_client: X APIクライアント（オプション）
            max_rate_wait_seconds: X API利用時に待機する最大秒数（UIでは0など短めに設定）
            
        Returns:
            投稿リスト [{"id": str, "text": str, "link": str, "date": str}]
        """
        # @を削除
        account = account.lstrip("@")
        
        # X API v2が利用可能な場合は実投稿を取得
        if x_api_client:
            # 方法1: ユーザーIDベースの取得を試行
            try:
                logger.info(f"[方法1] X APIでユーザーツイートを取得中: @{account}")
                posts = x_api_client.fetch_user_tweets(
                    account,
                    max_results=limit,
                    max_wait_seconds=max_rate_wait_seconds
                )
                if posts:
                    logger.info(f"✅ X API (fetch_user_tweets) 成功: {len(posts)}件")
                    # 構造化ログは x_api_client 内で出力済み
                    return posts
            except Exception as e:
                logger.warning(f"[方法1] 失敗: {str(e)}")
            
            # 方法2: 検索APIを使用（from:username クエリ）
            try:
                logger.info(f"[方法2] X API検索を試行中: from:{account}")
                search_query = f"from:{account} -is:retweet -is:reply"
                posts = x_api_client.search_recent_tweets(
                    search_query,
                    max_results=limit,
                    max_wait_seconds=max_rate_wait_seconds
                )
                if posts:
                    logger.info(f"✅ X API (search_recent_tweets) 成功: {len(posts)}件")
                    # 構造化ログは x_api_client 内で出力済み
                    return posts
            except Exception as e:
                logger.warning(f"[方法2] 失敗: {str(e)}")
            
            logger.info("X API両方失敗、次の方法へフォールバック")
        
        # 方法3: Grok Realtime Web Searchで実投稿を取得
        logger.info(f"[方法3] Grok Web Searchで実投稿を検索中: @{account}")
        # 環境に応じた検索パラメータ（例: 言語・地域）を付与
        search_params = {
            "lang": os.environ.get("GROK_SEARCH_LANG"),
            "region": os.environ.get("GROK_SEARCH_REGION")
        }
        web_posts = self._fetch_posts_via_web_search(account, limit, search_parameters=search_params)
        if web_posts:
            logger.info(f"✅ Grok Web Search 成功: {len(web_posts)}件")
            log_structured_api_call(
                source="web_search",
                account=account,
                generated_flag=False,
                post_count=len(web_posts)
            )
            return web_posts
        
        # 方法4: フォールバック - LLMでサンプル投稿生成
        logger.info(f"[方法4] フォールバック: サンプル投稿を生成中: @{account} (limit={limit})")
        # 運用ポリシー: 明示的に許可されない限り、生成データを返さない
        allow = ALLOW_GENERATED_DEFAULT if allow_generated is None else bool(allow_generated)
        if not allow:
            logger.warning("生成フォールバックは無効化されています（allow_generated=False）。空リストを返します。")
            log_structured_api_call(
                source="generated",
                account=account,
                generated_flag=True,
                allowed=False,
                post_count=0
            )
            return []
        
        try:
            with PerformanceLogger(f"投稿生成: @{account}"):
                # Grok LLMを使用してリアルな投稿例を生成
                prompt = f"""@{account}というXアカウントの投稿を{limit}件生成してください。
このアカウントは以下の特徴を持つと仮定します：
- テック系起業家またはデータサイエンティスト
- AI、機械学習、Web開発に興味がある
- カジュアルな口調（「だなぁ」「んだよね」「w」を使う）
- ポジティブで経験重視
- 絵文字や感嘆符を使う

以下のJSON配列形式で出力してください：
[
  {{"text": "投稿内容1", "date": "2024-10-15"}},
  {{"text": "投稿内容2", "date": "2024-10-14"}},
  ...
]

投稿は具体的で、テクノロジー、起業、学習、日常などのトピックを含めてください。
JSON配列のみを出力し、他の説明は不要です。"""

                result = self.generate_completion(prompt, temperature=0.8, max_tokens=2000)
                
                if result:
                    import json
                    # JSONパース
                    result_clean = result.strip()
                    if result_clean.startswith("```"):
                        result_clean = result_clean.split("```")[1]
                        if result_clean.startswith("json"):
                            result_clean = result_clean[4:]
                        result_clean = result_clean.strip()
                    
                    try:
                        generated_posts = json.loads(result_clean)
                        
                        # 投稿リストに変換
                        posts = []
                        for i, post_data in enumerate(generated_posts[:limit]):
                            posts.append({
                                "id": f"generated_{account}_{i}",
                                "text": post_data.get("text", ""),
                                "link": f"https://x.com/{account}/status/generated_{i}",
                                "date": post_data.get("date", "2024-10-15")
                            })
                        
                        logger.info(f"LLM生成完了: {len(posts)}件の投稿")
                        log_structured_api_call(
                            source="generated",
                            account=account,
                            generated_flag=True,
                            allowed=True,
                            post_count=len(posts)
                        )
                        return posts
                    
                    except json.JSONDecodeError as e:
                        logger.warning(f"JSON パース失敗: {e}")
                        # フォールバック: デフォルトサンプル投稿
                        return self._get_sample_posts(account, limit)
                else:
                    logger.warning("LLM生成失敗、サンプル投稿を使用")
                    return self._get_sample_posts(account, limit)
                
        except Exception as e:
            ErrorHandler.log_error(e, f"投稿生成: @{account}")
            logger.warning("エラー発生、サンプル投稿を使用")
            return self._get_sample_posts(account, limit)
    
    def generate_completion(
        self, 
        prompt: str, 
        temperature: float = 0.7,
        max_tokens: int = 1000,
        use_history: bool = False,
        enable_live_search: bool = False,
        search_parameters: Optional[Dict] = None
    ) -> Optional[str]:
        """
        Grok LLMでテキスト生成（会話履歴・Web検索対応）
        
        Args:
            prompt: 生成プロンプト
            temperature: 生成の多様性（0.0-1.0）
            max_tokens: 最大トークン数
            use_history: 会話履歴を使用するか
            enable_live_search: ライブWeb検索を有効化するか
            search_parameters: 検索パラメータ（lang, region 等）
            
        Returns:
            生成されたテキスト
        """
        logger.info(f"LLM生成を開始 (履歴={use_history}, Web検索={enable_live_search})")
        
        try:
            endpoint = f"{self.BASE_URL}/chat/completions"
            
            # メッセージ履歴を構築
            messages = []
            if use_history and self.conversation_history:
                messages = self.conversation_history.copy()
            
            # 新しいユーザーメッセージを追加
            messages.append({"role": "user", "content": prompt})
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            # ライブWeb検索を有効化
            if enable_live_search:
                payload["live_search"] = True
                logger.info("ライブWeb検索を有効化")
            
            # 検索パラメータを追加（存在する場合のみ）
            if search_parameters:
                payload["search_parameters"] = search_parameters
                logger.info(f"検索パラメータ設定: {search_parameters}")
            
            logger.debug(f"使用モデル: {self.model}, メッセージ数: {len(messages)}")
            
            response = requests.post(
                endpoint,
                headers=self.headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                result = data["choices"][0]["message"]["content"]
                
                # レスポンスIDを保存
                if "id" in data:
                    self.last_response_id = data["id"]
                
                # 会話履歴に追加
                if use_history:
                    self.conversation_history.append({"role": "user", "content": prompt})
                    self.conversation_history.append({"role": "assistant", "content": result})
                    logger.info(f"会話履歴更新: 現在{len(self.conversation_history)}メッセージ")
                
                logger.info("LLM生成完了")
                return result
            else:
                logger.error(f"LLM生成エラー: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"LLM生成例外: {str(e)}")
            return None
    
    def retrieve_previous_response(self, response_id: str) -> Optional[Dict]:
        """
        以前のレスポンスを取得
        
        Args:
            response_id: レスポンスID
            
        Returns:
            レスポンスデータ
        """
        try:
            endpoint = f"{self.BASE_URL}/chat/completions/{response_id}"
            
            response = requests.get(
                endpoint,
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"過去のレスポンスを取得: {response_id}")
                return data
            else:
                logger.error(f"レスポンス取得失敗: {response.status_code}")
                return None
        
        except Exception as e:
            logger.error(f"レスポンス取得エラー: {str(e)}")
            return None
    
    def clear_conversation_history(self):
        """会話履歴をクリア"""
        self.conversation_history = []
        self.last_response_id = None
        logger.info("会話履歴をクリアしました")
    
    def get_conversation_summary(self) -> str:
        """会話履歴のサマリーを取得"""
        if not self.conversation_history:
            return "会話履歴なし"
        
        user_messages = len([m for m in self.conversation_history if m["role"] == "user"])
        assistant_messages = len([m for m in self.conversation_history if m["role"] == "assistant"])
        
        return f"ユーザー: {user_messages}件, アシスタント: {assistant_messages}件"
    
    def search_user_web_presence(self, account: str, posts: List[Dict]) -> Optional[str]:
        """
        ユーザーの他プラットフォームでの情報をWeb検索
        
        Args:
            account: アカウント名
            posts: X投稿リスト（コンテキスト用）
            
        Returns:
            検索結果のサマリー
        """
        logger.info(f"Web検索でマルチプラットフォーム調査: @{account}")
        
        # X投稿から手がかりを抽出
        sample_texts = " ".join([post['text'][:100] for post in posts[:5]])
        
        prompt = f"""「{account}」というユーザーについて、以下の観点でWeb検索してください：

【X投稿サンプル】
{sample_texts}

【調査項目】
1. Instagram, TikTok等のSNS投稿
2. LinkedIn等のプロフェッショナルプロフィール
3. 個人ブログ、Note、Qiita等の記事
4. GitHub、Portfolio等の制作物
5. インタビュー記事、メディア出演

【出力形式】
見つかった情報を簡潔に要約してください（200-400文字）。
見つからない場合は「追加情報なし」と記載。
"""
        
        result = self.generate_completion(
            prompt,
            temperature=0.3,
            max_tokens=600,
            enable_live_search=True  # Web検索を強制有効化
        )
        
        if result and "追加情報なし" not in result:
            logger.info(f"Web検索完了: {len(result)}文字の追加情報")
            return result
        else:
            logger.info("Web検索: 追加情報なし")
            return None

    def generate_persona_profile(
        self, 
        posts: List[Dict], 
        account: str = None,
        enable_web_enrichment: bool = True
    ) -> Optional[Dict]:
        """
        投稿からペルソナプロファイルを生成（マルチプラットフォーム対応）
        
        Args:
            posts: 投稿リスト
            account: アカウント名（Web検索用）
            enable_web_enrichment: Web検索で情報を強化
            
        Returns:
            ペルソナプロファイル辞書
        """
        if not posts:
            logger.warning("投稿がないためペルソナを未確定として扱います")
            return None
        
        # Web検索でマルチプラットフォーム情報を収集
        web_info = None
        if enable_web_enrichment and account:
            web_info = self.search_user_web_presence(account, posts)
        
        # 投稿テキストを結合
        posts_text = "\n---\n".join([
            f"投稿{i+1}: {post['text']}" 
            for i, post in enumerate(posts[:20])
        ])
        
        # Web情報を追加
        web_section = ""
        if web_info:
            web_section = f"""

【他プラットフォームでの情報】
{web_info}
"""
        
        prompt = f"""以下の情報からペルソナプロファイルを生成してください。

【X投稿】
{posts_text}{web_section}

以下の項目を抽出・要約してください：
1. **名前/ニックネーム**: このアカウントを表す簡潔な名前
2. **背景**: 職業、専門分野、興味関心（複数プラットフォームの情報を統合）
3. **意見傾向**: よく言及するトピックや価値観
4. **口調**: 文体の特徴（例: カジュアル、感嘆符/絵文字多用、ユーモア「w」「ぐぬぬぬ」など）
5. **性格**: 全体的な印象（例: 経験重視、ポジティブ、自己反省的、ユーモア交じり）

JSON形式で出力してください：
{{
  "name": "名前",
  "background": "背景説明",
  "tendencies": ["傾向1", "傾向2", ...],
  "tone": "口調の特徴",
  "personality": "性格の特徴"
}}
"""
        
        result = self.generate_completion(
            prompt, 
            temperature=0.5, 
            max_tokens=800,
            enable_live_search=False  # ここでは不要（既にWeb検索済み）
        )
        
        if result:
            try:
                # JSONパース試行
                import json
                # Markdownのコードブロックを削除
                result_clean = result.strip()
                if result_clean.startswith("```"):
                    result_clean = result_clean.split("```")[1]
                    if result_clean.startswith("json"):
                        result_clean = result_clean[4:]
                    result_clean = result_clean.strip()
                
                persona = json.loads(result_clean)
                logger.info(f"ペルソナ生成完了: {persona.get('name', 'Unknown')}")
                return persona
            except json.JSONDecodeError:
                logger.warning("JSON パース失敗のためペルソナ未確定")
                return None
        
        return None
    
    def generate_debate_opinion(
        self, 
        topic: str, 
        persona: Dict, 
        relevant_posts: List[Dict],
        use_history: bool = False,
        enable_live_search: bool = False
    ) -> Optional[str]:
        """
        トピックに対するペルソナの意見を生成（エージェント機能付き）
        
        Args:
            topic: 議論トピック
            persona: ペルソナプロファイル
            relevant_posts: 関連する過去投稿
            use_history: 会話履歴を使用（継続的対話）
            enable_live_search: Web検索で最新情報を取得
            
        Returns:
            生成された意見（引用付き）
        """
        # 関連投稿を引用形式で整形
        citations = "\n".join([
            f"[{i+1}] {post['text']} (リンク: {post['link']})"
            for i, post in enumerate(relevant_posts[:MAX_CITATION_POSTS])
        ])
        
        web_search_note = ""
        if enable_live_search:
            web_search_note = "\n\n【重要】最新のWeb情報を検索して、議論に反映してください。"
        
        prompt = f"""あなたは以下のペルソナとして振る舞ってください：

【ペルソナ情報】
- 名前: {persona.get('name', 'Unknown')}
- 背景: {persona.get('background', '')}
- 意見傾向: {', '.join(persona.get('tendencies', []))}
- 口調: {persona.get('tone', '')}
- 性格: {persona.get('personality', '')}

【過去の投稿（引用可能）】
{citations if citations else '（関連投稿なし）'}

【議論トピック】
{topic}{web_search_note}

このトピックについて、ペルソナの口調と性格を**徹底的に模倣**して意見を述べてください。
- 口調の特徴（カジュアル、感嘆符、絵文字、「w」「だなぁ」など）を必ず含める
- 性格（経験重視、ユーモア交じり、ポジティブなど）を反映
- 可能であれば過去の投稿を引用（[1]、[2]の形式で参照）
- Web検索を有効にした場合、最新情報も参照
- 150-300文字程度

意見:
"""
        
        result = self.generate_completion(
            prompt, 
            temperature=0.8, 
            max_tokens=500,
            use_history=use_history,
            enable_live_search=enable_live_search
        )
        
        if result:
            logger.info("意見生成完了")
            return result.strip()
        
        return None
    
    def generate_rebuttal(
        self,
        topic: str,
        persona: Dict,
        target_account: str,
        target_opinion: str,
        previous_context: str = "",
        use_history: bool = True,
        enable_live_search: bool = False
    ) -> Optional[str]:
        """
        他者の意見に対する反論を生成
        
        Args:
            topic: 議論トピック
            persona: 反論する側のペルソナ
            target_account: 反論対象のアカウント
            target_opinion: 反論対象の意見
            previous_context: これまでの議論の文脈
            use_history: 会話履歴を使用
            enable_live_search: Web検索を有効化
            
        Returns:
            生成された反論
        """
        context_section = ""
        if previous_context:
            context_section = f"""
【これまでの議論】
{previous_context}
"""
        
        web_search_note = ""
        if enable_live_search:
            web_search_note = "\n\n【重要】必要に応じて最新のWeb情報を検索して、反論の根拠にしてください。"
        
        prompt = f"""あなたは以下のペルソナとして振る舞ってください：

【あなたのペルソナ】
- 名前: {persona.get('name', 'Unknown')}
- 背景: {persona.get('background', '')}
- 意見傾向: {', '.join(persona.get('tendencies', []))}
- 口調: {persona.get('tone', '')}
- 性格: {persona.get('personality', '')}

【議論トピック】
{topic}
{context_section}
【@{target_account}の意見】
{target_opinion}

@{target_account}の意見に対して、あなたのペルソナの立場から反論・応答してください。

【反論のガイドライン】
- ペルソナの口調と性格を**徹底的に模倣**
- 建設的な反論（相手の意見を一部認めつつ、自分の視点を示す）
- 攻撃的にならず、議論を深める
- 具体例や経験があれば言及
- 100-200文字程度{web_search_note}

反論:
"""
        
        result = self.generate_completion(
            prompt,
            temperature=0.85,  # やや高めで多様性を
            max_tokens=400,
            use_history=use_history,
            enable_live_search=enable_live_search
        )
        
        if result:
            logger.info(f"反論生成完了: @{target_account}への反論")
            return result.strip()
        
        return None
    
    def _fetch_posts_via_web_search(self, account: str, limit: int, search_parameters: Optional[Dict] = None) -> List[Dict]:
        """
        Grok Realtime Web Searchで実際の投稿を検索・取得
        
        Args:
            account: アカウント名
            limit: 取得する投稿数
            
        Returns:
            実投稿リスト（見つかった場合）、空リスト（失敗時）
        """
        logger.info(f"Grok Web Searchで@{account}の実投稿を検索中...")
        lang_note = ""
        region_note = ""
        if search_parameters:
            if search_parameters.get("lang"):
                lang_note = f"\n- 検索言語: {search_parameters.get('lang')}"
            if search_parameters.get("region"):
                region_note = f"\n- 対象地域: {search_parameters.get('region')}"
        
        prompt = f"""X (Twitter) で「@{account}」というアカウントの最近の投稿を{limit}件検索してください。

【重要な指示】
- 実際に存在する投稿のみを返してください（架空の投稿は不可）
- 投稿の本文テキストと投稿日時を正確に取得してください
- リツイートや返信は除外してください
{lang_note}{region_note}

以下のJSON配列形式で出力してください：
[
  {{"text": "実際の投稿内容1", "date": "YYYY-MM-DD"}},
  {{"text": "実際の投稿内容2", "date": "YYYY-MM-DD"}},
  ...
]

投稿が見つからない場合は空配列 [] を返してください。
JSON配列のみを出力し、他の説明は不要です。"""

        try:
            result = self.generate_completion(
                prompt,
                temperature=0.3,  # 正確性重視
                max_tokens=2500,
                enable_live_search=True,  # Web検索を強制有効化
                search_parameters=search_parameters
            )
            
            if result:
                import json
                # JSONパース
                result_clean = result.strip()
                if result_clean.startswith("```"):
                    result_clean = result_clean.split("```")[1]
                    if result_clean.startswith("json"):
                        result_clean = result_clean[4:]
                    result_clean = result_clean.strip()
                
                try:
                    found_posts = json.loads(result_clean)
                    
                    if not found_posts or len(found_posts) == 0:
                        logger.info("Web検索: 投稿が見つかりませんでした")
                        return []
                    
                    # 投稿リストに変換
                    posts = []
                    for i, post_data in enumerate(found_posts[:limit]):
                        text = post_data.get("text", "")
                        if text:  # 空でない投稿のみ
                            posts.append({
                                "id": f"web_search_{account}_{i}",
                                "text": text,
                                "link": f"https://x.com/{account}/status/web_search_{i}",
                                "date": post_data.get("date", "2024-10-15")
                            })
                    
                    logger.info(f"Web検索完了: {len(posts)}件の実投稿を取得")
                    return posts
                
                except json.JSONDecodeError as e:
                    logger.warning(f"Web検索結果のJSON パース失敗: {e}")
                    return []
            else:
                logger.warning("Web検索: レスポンスなし")
                return []
        
        except Exception as e:
            logger.error(f"Web検索エラー: {str(e)}")
            return []
    
    def _get_sample_posts(self, account: str, limit: int) -> List[Dict]:
        """
        サンプル投稿を返す（全ての方法が失敗した時の最終フォールバック）
        
        Args:
            account: アカウント名
            limit: 投稿数
            
        Returns:
            サンプル投稿リスト
        """
        sample_posts = [
            {"text": "AIの倫理って難しいよなぁ。経験から言うと、後出しジャンケンみたいで可哀想だわw でも大事なことだから議論は続けるべきだね！", "date": "2024-10-15"},
            {"text": "今日もコード書いてる！！ 実装しながら学ぶのが一番だと思うんだよね。理論も大事だけど、手を動かさないと身につかない💪", "date": "2024-10-14"},
            {"text": "リモートワーク最高だなぁ。集中できる時間が増えたし、家族との時間も取れる。これからの働き方のスタンダードになりそう😊", "date": "2024-10-13"},
            {"text": "機械学習モデルのデプロイって奥が深い... 学術的な精度よりも実運用の安定性が大事なんだよね。今日もまた学びがあった✨", "date": "2024-10-12"},
            {"text": "音楽とテクノロジーの融合って最高だと思うんだ！AI作曲も面白いけど、人間の感性は残したいよね🎵", "date": "2024-10-11"},
            {"text": "起業して分かったこと: 完璧な準備なんてない。走りながら学ぶしかないんだよなぁw ぐぬぬぬ！", "date": "2024-10-10"},
            {"text": "データサイエンスの実務で大事なのは、綺麗なコードよりも「動くコード」だと思う。もちろん両方目指すけどね！", "date": "2024-10-09"},
            {"text": "今日のランチは美味しかった😋 仕事も大事だけど、食事も大事！健康第一だよね", "date": "2024-10-08"},
            {"text": "Web3の可能性について考えてた。技術は面白いけど、実用化までの道のりは長そうだなぁ...", "date": "2024-10-07"},
            {"text": "朝活で勉強してる！早起きは三文の徳って本当だね。集中力が全然違う✨", "date": "2024-10-06"},
            {"text": "チーム開発って難しい。コミュニケーションが全てだと実感してる。コードだけじゃないんだよね", "date": "2024-10-05"},
            {"text": "新しいフレームワーク試してみた！学習コスト高いけど、楽しいw こういう探求心を失いたくないな", "date": "2024-10-04"},
            {"text": "失敗から学ぶことの方が多いんだよなぁ。成功体験よりも失敗体験の方が記憶に残る💡", "date": "2024-10-03"},
            {"text": "今日はコーヒー3杯目w カフェイン摂取量やばいけど、集中したい時はしょうがない😅", "date": "2024-10-02"},
            {"text": "テクノロジーで社会問題を解決したい。理想論かもしれないけど、そういう夢を持ち続けたいんだ！", "date": "2024-10-01"},
            {"text": "読書タイム📚 技術書だけじゃなくて、哲学書も読むと視野が広がるよね", "date": "2024-09-30"},
            {"text": "デバッグ中... バグとの戦いは終わらないなぁw でもこれがプログラミングの醍醐味！", "date": "2024-09-29"},
            {"text": "メンターに相談したら目から鱗だった。経験者のアドバイスって本当に価値があるよね🙏", "date": "2024-09-28"},
            {"text": "今日も一歩前進！小さな積み重ねが大きな成果につながると信じてる💪", "date": "2024-09-27"},
            {"text": "感謝の気持ちを忘れずに。周りの人のサポートがあってこそだよなぁ✨ ありがとう！！", "date": "2024-09-26"}
        ]
        
        posts = []
        for i, post_data in enumerate(sample_posts[:limit]):
            posts.append({
                "id": f"sample_{account}_{i}",
                "text": post_data["text"],
                "link": f"https://x.com/{account}/status/sample_{i}",
                "date": post_data["date"]
            })
        
        return posts
    
    def _default_persona(self) -> Dict:
        """デフォルトのペルソナプロファイル"""
        return {
            "name": "Terisuke (Default)",
            "background": "未経験起業家、AI実務家、音楽家",
            "tendencies": ["経験重視", "テクノロジー", "音楽"],
            "tone": "カジュアル、感嘆符多用、ユーモア（w、ぐぬぬぬ）",
            "personality": "ポジティブ、経験ベース、自己反省的、ユーモア交じり"
        }

    # =============================================================================
    # Stage 2.5: アカウント発見機能（Grok Realtime Web Search）
    # =============================================================================

    def discover_accounts_by_keyword(
        self,
        keyword: str,
        max_results: int = 50,
        dry_run: bool = False,
        x_api_client=None
    ) -> List[Dict]:
        """
        キーワードベースでXアカウント候補を発見

        Grok Realtime Web Search を使用して、指定されたキーワードに関連する
        影響力のあるアカウントを検索します。

        Args:
            keyword: 検索キーワード（例: "AI engineer", "data scientist", "startup founder"）
            max_results: 取得する最大アカウント数（デフォルト: 50, 上限: 100）
            dry_run: True の場合、モックデータを返す（Grok API を呼ばない）

        Returns:
            アカウント候補リスト [
                {
                    "handle": str,           # @なしのアカウント名
                    "display_name": str,     # 表示名
                    "confidence": float,     # 信頼度スコア (0.0-1.0)
                    "profile_url": str,      # プロフィールURL
                    "source": "grok_keyword" # データソース
                }
            ]
        """
        # プリセットキーワードかチェック
        if keyword in PRESET_KEYWORDS:
            actual_keyword = PRESET_KEYWORDS[keyword]
            logger.info(f"📝 プリセットキーワード '{keyword}' -> '{actual_keyword}'")
        else:
            actual_keyword = keyword

        if dry_run:
            logger.info(f"🎭 DRY RUN: キーワード '{actual_keyword}' のモックデータを生成中...")
            return self._generate_mock_accounts(actual_keyword, max_results, "grok_keyword")

        logger.info(f"🔍 Grok Web Search でキーワード '{actual_keyword}' のアカウントを検索中...")

        prompt = f"""X (Twitter) で「{actual_keyword}」に関連する影響力のあるアカウントを最大{max_results}件検索してください。

【重要な指示】
- 実際に存在するアクティブなアカウントのみを返してください
- フォロワー数が多い、またはその分野で認知されているアカウントを優先
- ボットやスパムアカウントは除外
- アカウント名（@handle）、表示名、簡単な説明を含める

【品質基準】
- フォロワー数: 可能であれば1,000以上を優先
- アクティビティ: 最近30日以内に投稿があるアカウント
- 信頼度スコア: 以下の基準で設定してください
  * 0.95-1.0: その分野で第一人者、大規模フォロワー（10万以上）、メディア露出あり
  * 0.85-0.94: 影響力のあるアカウント、ある程度のフォロワー（1万以上）、継続的な投稿
  * 0.70-0.84: アクティブな専門家、中小規模フォロワー、質の高い投稿
  * 0.60-0.69: 関連はあるが影響力は限定的
  * 0.60未満: 除外推奨

以下のJSON配列形式で出力してください：
[
  {{
    "handle": "account_name",
    "display_name": "Display Name",
    "description": "Brief description",
    "confidence": 0.95
  }},
  ...
]

アカウントが見つからない場合は空配列 [] を返してください。
JSON配列のみを出力し、他の説明は不要です。"""

        try:
            result = self.generate_completion(
                prompt,
                temperature=0.3,  # 正確性重視
                max_tokens=3000,
                enable_live_search=True  # Web検索を強制有効化
            )

            if result:
                import json
                # JSONパース
                result_clean = result.strip()
                if result_clean.startswith("```"):
                    result_clean = result_clean.split("```")[1]
                    if result_clean.startswith("json"):
                        result_clean = result_clean[4:]
                    result_clean = result_clean.strip()

                try:
                    found_accounts = json.loads(result_clean)

                    if not found_accounts or len(found_accounts) == 0:
                        logger.info("アカウントが見つかりませんでした")
                        return []

                    # アカウントリストに変換
                    accounts = []
                    for account_data in found_accounts[:max_results]:
                        handle = account_data.get("handle", "").lstrip("@")
                        display_name = account_data.get("display_name", account_data.get("name", handle))
                        confidence = account_data.get("confidence", 0.8)

                        if handle:  # 空でないハンドルのみ
                            accounts.append({
                                "handle": handle,
                                "display_name": display_name,
                                "confidence": float(confidence),
                                "profile_url": f"https://x.com/{handle}",
                                "description": account_data.get("description", ""),
                                "source": "grok_keyword"
                            })

                    # 品質フィルタリングを適用（信頼度ベース）
                    filtered_accounts = self._filter_accounts_by_quality(accounts)
                    
                    # 詳細品質評価を実行
                    quality_evaluated = []
                    quality_passed = 0
                    quality_failed = 0
                    
                    for account in filtered_accounts:
                        quality_result = self.check_account_quality(
                            account['handle'],
                            account,
                            x_api_client=x_api_client
                        )
                        if quality_result['passed']:
                            account['quality_score'] = quality_result['score']
                            account['quality_reasons'] = quality_result['reasons']
                            quality_evaluated.append(account)
                            quality_passed += 1
                        else:
                            logger.debug(f"❌ @{account['handle']}: 品質基準未満 - {quality_result['recommendation']}")
                            quality_failed += 1
                    
                    logger.info(
                        f"✅ {len(quality_evaluated)}件のアカウント候補を発見 "
                        f"（信頼度フィルタ後: {len(accounts)} -> {len(filtered_accounts)}件、"
                        f"品質評価後: {len(filtered_accounts)} -> {len(quality_evaluated)}件、"
                        f"合格: {quality_passed}件、不合格: {quality_failed}件）"
                    )
                    return quality_evaluated

                except json.JSONDecodeError as e:
                    logger.warning(f"JSON パース失敗: {e}")
                    return []
            else:
                logger.warning("レスポンスなし")
                return []

        except Exception as e:
            logger.error(f"アカウント検索エラー: {str(e)}")
            return []

    def discover_accounts_random(
        self,
        max_results: int = 50,
        dry_run: bool = False,
        category: Optional[str] = None,
        x_api_client=None
    ) -> List[Dict]:
        """
        ランダムに影響力のあるXアカウント候補を発見

        複数のプリセットクエリ（random influencer, random engineer など）を
        ランダムに実行し、重複を除いたアカウントリストを返します。

        Args:
            max_results: 取得する最大アカウント数（デフォルト: 50, 上限: 100）
            dry_run: True の場合、モックデータを返す（Grok API を呼ばない）
            category: カテゴリ指定（'tech', 'business', 'creative', 'science', 'developer', 'product', 'community'）

        Returns:
            アカウント候補リスト（discover_accounts_by_keyword と同じ形式）
        """
        if dry_run:
            logger.info(f"🎭 DRY RUN: ランダムアカウントのモックデータを生成中...")
            return self._generate_mock_accounts("random", max_results, "grok_random")

        logger.info(f"🎲 Grok Web Search でランダムにアカウントを検索中...")

        # プリセットクエリをカテゴリ別に分類（多様性を確保）
        preset_queries_by_category = {
            'tech': [
                "influential tech Twitter accounts",
                "popular AI researcher on Twitter",
                "famous machine learning engineer on X",
                "influential cybersecurity expert on Twitter",
                "well-known blockchain developer on X",
                "popular cloud architect on Twitter",
                "influential DevOps engineer on X",
                "famous data engineer on Twitter"
            ],
            'business': [
                "famous startup founder on X",
                "influential entrepreneur on X",
                "popular venture capitalist on Twitter",
                "well-known angel investor on X",
                "influential business executive on Twitter",
                "famous CEO on X platform",
                "popular business strategist on Twitter"
            ],
            'creative': [
                "influential designer on X",
                "popular UX designer on Twitter",
                "famous graphic designer on X",
                "well-known creative director on Twitter",
                "influential illustrator on X",
                "popular digital artist on Twitter",
                "famous photographer on X"
            ],
            'science': [
                "well-known data scientist Twitter",
                "influential researcher on X",
                "popular scientist on Twitter",
                "famous physicist on X",
                "influential biologist on Twitter",
                "well-known chemist on X"
            ],
            'developer': [
                "influential developer on Twitter",
                "famous open source contributor on X",
                "popular software engineer on Twitter",
                "influential backend engineer on X",
                "famous frontend developer on Twitter",
                "well-known full stack developer on X"
            ],
            'product': [
                "famous product manager Twitter",
                "influential product strategist on X",
                "popular product designer on Twitter",
                "well-known product marketing on X"
            ],
            'community': [
                "influential tech writer on Twitter",
                "famous tech blogger on X",
                "popular tech podcaster on Twitter",
                "influential tech community leader on X",
                "well-known tech educator on Twitter"
            ]
        }

        # カテゴリ指定がある場合は該当カテゴリのみ使用
        if category and category in preset_queries_by_category:
            preset_queries = preset_queries_by_category[category].copy()
            logger.info(f"📂 カテゴリ '{category}' を指定: {len(preset_queries)}件のクエリ")
        else:
            # 全プリセットクエリを結合
            preset_queries = []
            for cat, queries in preset_queries_by_category.items():
                preset_queries.extend(queries)
            if category:
                logger.warning(f"⚠️  不明なカテゴリ '{category}'、全カテゴリを使用します")

        all_accounts = []
        seen_handles = set()

        # 各クエリで検索（重複除外しながら max_results に達するまで）
        import random
        random.shuffle(preset_queries)

        for query in preset_queries:
            if len(all_accounts) >= max_results:
                break

            logger.info(f"  📡 クエリ実行中: '{query}'")
            accounts = self.discover_accounts_by_keyword(
                query,
                max_results=min(20, max_results - len(all_accounts)),  # 一度に最大20件
                dry_run=False,  # 内部でモックは使わない
                x_api_client=x_api_client
            )

            # 重複除外しながら追加
            for account in accounts:
                handle = account["handle"]
                if handle not in seen_handles:
                    seen_handles.add(handle)
                    account["source"] = "grok_random"  # ソースを上書き
                    all_accounts.append(account)

                    if len(all_accounts) >= max_results:
                        break

        logger.info(f"✅ ランダム検索完了: {len(all_accounts)}件のアカウント候補を発見")
        return all_accounts

    def _generate_mock_accounts(
        self,
        keyword: str,
        count: int,
        source: str
    ) -> List[Dict]:
        """
        モックアカウントデータを生成（テスト・dry-run 用）

        Args:
            keyword: キーワード（表示名に反映）
            count: 生成するアカウント数
            source: データソース（"grok_keyword" または "grok_random"）

        Returns:
            モックアカウントリスト
        """
        mock_accounts = []

        for i in range(min(count, 20)):  # 最大20件
            mock_accounts.append({
                "handle": f"mock_{keyword.replace(' ', '_')}_{i}",
                "display_name": f"Mock {keyword.title()} {i}",
                "confidence": 0.8 + (i % 3) * 0.05,  # 0.80-0.90
                "profile_url": f"https://x.com/mock_{keyword.replace(' ', '_')}_{i}",
                "description": f"Mock account for testing '{keyword}' discovery",
                "source": source
            })

        logger.info(f"🎭 {len(mock_accounts)}件のモックアカウントを生成")
        return mock_accounts

    def _filter_accounts_by_quality(
        self,
        accounts: List[Dict],
        min_confidence: float = 0.7
    ) -> List[Dict]:
        """
        信頼度スコアでアカウントをフィルタリング

        Args:
            accounts: アカウント候補リスト
            min_confidence: 最小信頼度スコア（デフォルト: 0.7）

        Returns:
            フィルタリングされたアカウントリスト（信頼度の降順）
        """
        filtered = [a for a in accounts if a.get('confidence', 0.0) >= min_confidence]
        sorted_accounts = sorted(filtered, key=lambda x: x.get('confidence', 0.0), reverse=True)
        
        if len(accounts) > len(sorted_accounts):
            logger.info(f"🔍 品質フィルタ: {len(accounts)} -> {len(sorted_accounts)}件 (信頼度 {min_confidence} 以上)")
        
        return sorted_accounts

    def check_account_quality(
        self,
        account: str,
        account_info: Dict,
        thresholds: Dict = None,
        x_api_client=None
    ) -> Dict:
        """
        アカウントの品質を評価（実世界指標ベース）
        
        X APIメトリクス（followers_count, tweet_count, last_tweet_at）を使用して
        品質スコアを計算します。
        
        Args:
            account: アカウント名
            account_info: アカウント情報辞書（handle, confidence, descriptionなど）
            thresholds: 品質基準の辞書（デフォルト: QUALITY_THRESHOLDS）
            x_api_client: X APIクライアント（メトリクス取得用、オプション）
            
        Returns:
            {
                'passed': bool,           # 品質基準を満たしているか
                'score': float,           # 品質スコア (0.0-1.0)
                'reasons': List[str],     # 評価理由
                'recommendation': str     # 推奨アクション
            }
        """
        if thresholds is None:
            thresholds = QUALITY_THRESHOLDS.copy()
        
        logger.info(f"📊 アカウント品質評価: @{account}")
        
        passed = True
        reasons = []
        metrics_available = False
        
        # X APIメトリクスが利用可能な場合
        followers_count = None
        tweet_count = None
        last_tweet_at = None
        
        if x_api_client:
            try:
                metrics = x_api_client.fetch_user_metrics(account)
                if metrics:
                    followers_count = metrics.get('followers_count', 0)
                    tweet_count = metrics.get('tweet_count', 0)
                    last_tweet_at = metrics.get('last_tweet_at')
                    metrics_available = True
                    logger.info(
                        f"  X APIメトリクス: フォロワー={followers_count}, "
                        f"ツイート={tweet_count}, 最終投稿={last_tweet_at or '不明'}"
                    )
            except Exception as e:
                logger.warning(f"X APIメトリクス取得エラー（続行）: {str(e)}")
        
        # アカウント情報からも取得を試行（Grok発見時のメトリクス）
        if not metrics_available:
            public_metrics = account_info.get('public_metrics', {})
            if public_metrics:
                followers_count = public_metrics.get('followers_count', 0)
                tweet_count = public_metrics.get('tweet_count', 0)
                metrics_available = True
                logger.info(f"  Grok発見時のメトリクス: フォロワー={followers_count}, ツイート={tweet_count}")
        
        # 実世界指標ベースの品質スコア計算
        if metrics_available and (followers_count is not None or tweet_count is not None):
            # 正規化されたスコア（0.0-1.0）を計算
            # 1. フォロワー数スコア（0.5の重み）
            followers_norm = 0.0
            if followers_count is not None:
                # 1000フォロワーで0.5、10000フォロワーで1.0になる対数スケール
                if followers_count >= 10000:
                    followers_norm = 1.0
                elif followers_count >= 1000:
                    followers_norm = 0.5 + 0.5 * ((followers_count - 1000) / 9000)
                elif followers_count >= thresholds['min_followers']:
                    followers_norm = 0.3 * (followers_count / thresholds['min_followers'])
                else:
                    followers_norm = 0.1 * (followers_count / thresholds['min_followers'])
                reasons.append(f"フォロワー数: {followers_count} (正規化スコア: {followers_norm:.2f})")
            else:
                reasons.append("フォロワー数: 不明（スコア0.0）")
            
            # 2. 最終ツイートの新しさスコア（0.3の重み）
            recency_norm = 0.0
            if last_tweet_at:
                try:
                    from datetime import datetime, timezone
                    tweet_date = datetime.fromisoformat(last_tweet_at.replace('Z', '+00:00'))
                    days_inactive = (datetime.now(timezone.utc) - tweet_date).days
                    
                    if days_inactive <= 30:
                        recency_norm = 1.0
                    elif days_inactive <= 90:
                        recency_norm = 0.7
                    elif days_inactive <= thresholds['max_days_inactive']:
                        recency_norm = 0.3
                    else:
                        recency_norm = 0.0
                    
                    reasons.append(f"最終投稿: {days_inactive}日前 (正規化スコア: {recency_norm:.2f})")
                except Exception as e:
                    logger.warning(f"日付パースエラー: {e}")
                    reasons.append("最終投稿: 日付不明（スコア0.0）")
            else:
                reasons.append("最終投稿: 不明（スコア0.0）")
            
            # 3. ツイート数スコア（0.2の重み）
            postcount_norm = 0.0
            if tweet_count is not None:
                if tweet_count >= 1000:
                    postcount_norm = 1.0
                elif tweet_count >= thresholds['min_tweet_count']:
                    postcount_norm = 0.5 + 0.5 * ((tweet_count - thresholds['min_tweet_count']) / 950)
                else:
                    postcount_norm = 0.3 * (tweet_count / thresholds['min_tweet_count'])
                reasons.append(f"ツイート数: {tweet_count} (正規化スコア: {postcount_norm:.2f})")
            else:
                reasons.append("ツイート数: 不明（スコア0.0）")
            
            # 加重合計で品質スコアを計算
            score = 0.5 * followers_norm + 0.3 * recency_norm + 0.2 * postcount_norm
            score = max(0.0, min(1.0, score))  # 0.0-1.0に制限
            
            # 最低基準チェック
            if followers_count is not None and followers_count < thresholds['min_followers']:
                passed = False
                reasons.append(f"フォロワー数が最小基準未満 ({followers_count} < {thresholds['min_followers']})")
            
            if tweet_count is not None and tweet_count < thresholds['min_tweet_count']:
                passed = False
                reasons.append(f"ツイート数が最小基準未満 ({tweet_count} < {thresholds['min_tweet_count']})")
            
            if last_tweet_at:
                try:
                    from datetime import datetime, timezone
                    tweet_date = datetime.fromisoformat(last_tweet_at.replace('Z', '+00:00'))
                    days_inactive = (datetime.now(timezone.utc) - tweet_date).days
                    if days_inactive > thresholds['max_days_inactive']:
                        passed = False
                        reasons.append(f"非アクティブ期間が長すぎる ({days_inactive}日 > {thresholds['max_days_inactive']}日)")
                except:
                    pass
            
            if score < thresholds['min_quality_score']:
                passed = False
                reasons.append(f"品質スコアが最小基準未満 ({score:.2f} < {thresholds['min_quality_score']})")
        else:
            # メトリクスが取得できない場合、フォールバック評価
            confidence = account_info.get('confidence', 0.0)
            description = account_info.get('description', '')
            
            if confidence < 0.7:
                passed = False
                score = confidence * 0.8  # 信頼度ベースの暫定スコア
            else:
                score = 0.5 + (confidence - 0.5) * 0.5
            
            if not description or len(description.strip()) < 20:
                score *= 0.9
                reasons.append("説明文が不十分")
            
            reasons.append(f"メトリクス未取得（信頼度ベース評価: {confidence:.2f}）")
            if x_api_client is None:
                reasons.append("X API metrics unavailable – fallback evaluation")
            logger.warning("X APIメトリクスが利用できないため、信頼度ベースの暫定評価を実施")
        
        # ハンドルの妥当性をチェック
        handle = account_info.get('handle', '')
        if len(handle) < 3 or len(handle) > 15:
            passed = False
            reasons.append(f"ハンドルが不自然 (@{handle})")
        
        # 推奨アクション
        if passed and score >= 0.7:
            recommendation = "高品質アカウント - 推奨"
        elif passed:
            recommendation = "品質基準を満たす - 使用可能"
        else:
            recommendation = "品質基準未満 - 除外推奨"
        
        result = {
            'passed': passed,
            'score': score,
            'reasons': reasons,
            'recommendation': recommendation
        }
        
        logger.info(f"  結果: {'✅' if passed else '❌'} {score:.2f} - {recommendation}")
        
        return result
