"""
Grok API連携モジュール
X投稿の取得とLLM生成を担当
"""

import requests
import logging
from typing import List, Dict, Optional
from datetime import datetime
from .error_handler import (
    ErrorHandler, 
    PerformanceLogger,
    APIConnectionError,
    log_function_call
)

logger = logging.getLogger(__name__)

# 定数定義
MAX_CITATION_POSTS = 3  # 引用する投稿の最大数


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
        x_api_client=None
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
                posts = x_api_client.fetch_user_tweets(account, max_results=limit)
                if posts:
                    logger.info(f"✅ X API (fetch_user_tweets) 成功: {len(posts)}件")
                    return posts
            except Exception as e:
                logger.warning(f"[方法1] 失敗: {str(e)}")
            
            # 方法2: 検索APIを使用（from:username クエリ）
            try:
                logger.info(f"[方法2] X API検索を試行中: from:{account}")
                search_query = f"from:{account} -is:retweet -is:reply"
                posts = x_api_client.search_recent_tweets(search_query, max_results=limit)
                if posts:
                    logger.info(f"✅ X API (search_recent_tweets) 成功: {len(posts)}件")
                    return posts
            except Exception as e:
                logger.warning(f"[方法2] 失敗: {str(e)}")
            
            logger.info("X API両方失敗、次の方法へフォールバック")
        
        # 方法3: Grok Realtime Web Searchで実投稿を取得
        logger.info(f"[方法3] Grok Web Searchで実投稿を検索中: @{account}")
        web_posts = self._fetch_posts_via_web_search(account, limit)
        if web_posts:
            logger.info(f"✅ Grok Web Search 成功: {len(web_posts)}件")
            return web_posts
        
        # 方法4: フォールバック - LLMでサンプル投稿生成
        logger.info(f"[方法4] フォールバック: サンプル投稿を生成中: @{account} (limit={limit})")
        
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
        enable_live_search: bool = False
    ) -> Optional[str]:
        """
        Grok LLMでテキスト生成（会話履歴・Web検索対応）
        
        Args:
            prompt: 生成プロンプト
            temperature: 生成の多様性（0.0-1.0）
            max_tokens: 最大トークン数
            use_history: 会話履歴を使用するか
            enable_live_search: ライブWeb検索を有効化するか
            
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
            logger.warning("投稿がないためデフォルトペルソナを使用")
            return self._default_persona()
        
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
                logger.warning("JSON パース失敗、テキストから抽出")
                # フォールバック: テキストから手動抽出
                return {
                    "name": "分析対象ユーザー",
                    "background": result[:200],
                    "tendencies": [],
                    "tone": "口調分析中",
                    "personality": "性格分析中"
                }
        
        return self._default_persona()
    
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
    
    def _fetch_posts_via_web_search(self, account: str, limit: int) -> List[Dict]:
        """
        Grok Realtime Web Searchで実際の投稿を検索・取得
        
        Args:
            account: アカウント名
            limit: 取得する投稿数
            
        Returns:
            実投稿リスト（見つかった場合）、空リスト（失敗時）
        """
        logger.info(f"Grok Web Searchで@{account}の実投稿を検索中...")
        
        prompt = f"""X (Twitter) で「@{account}」というアカウントの最近の投稿を{limit}件検索してください。

【重要な指示】
- 実際に存在する投稿のみを返してください（架空の投稿は不可）
- 投稿の本文テキストと投稿日時を正確に取得してください
- リツイートや返信は除外してください

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

