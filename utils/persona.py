"""
ペルソナ生成・管理モジュール
投稿データからペルソナプロファイルを生成し、口調・性格を模倣
"""

import logging
from typing import List, Dict, Optional
from textblob import TextBlob

logger = logging.getLogger(__name__)


class PersonaManager:
    """ペルソナの生成と管理を行うクラス"""
    
    def __init__(self):
        """初期化"""
        self.personas = {}  # account_name -> persona_profile
    
    def create_persona(
        self, 
        account: str, 
        posts: List[Dict], 
        profile: Optional[Dict] = None
    ) -> Dict:
        """
        ペルソナを作成
        
        Args:
            account: アカウント名
            posts: 投稿リスト
            profile: Grok APIで生成されたプロファイル（オプション）
            
        Returns:
            ペルソナ辞書
        """
        logger.info(f"ペルソナ作成中: {account}")
        
        # 基本プロファイル
        if profile:
            persona = profile.copy()
        else:
            persona = {
                "name": account,
                "background": "",
                "tendencies": [],
                "tone": "",
                "personality": ""
            }
        
        # 投稿統計を追加
        persona.update({
            "account": account,
            "post_count": len(posts),
            "posts": posts,
            "statistics": self._calculate_statistics(posts)
        })
        
        # キャッシュ
        self.personas[account] = persona
        
        logger.info(f"ペルソナ作成完了: {persona['name']}")
        return persona
    
    def get_persona(self, account: str) -> Optional[Dict]:
        """
        キャッシュからペルソナを取得
        
        Args:
            account: アカウント名
            
        Returns:
            ペルソナ辞書（存在しない場合None）
        """
        return self.personas.get(account)
    
    def _calculate_statistics(self, posts: List[Dict]) -> Dict:
        """
        投稿統計を計算
        
        Args:
            posts: 投稿リスト
            
        Returns:
            統計辞書
        """
        if not posts:
            return {
                "avg_length": 0,
                "sentiment": {"positive": 0, "neutral": 0, "negative": 0},
                "tone_markers": {}
            }
        
        # 文字数統計
        lengths = [len(post["text"]) for post in posts]
        avg_length = sum(lengths) / len(lengths)
        
        # センチメント分析
        sentiments = {"positive": 0, "neutral": 0, "negative": 0}
        for post in posts:
            try:
                blob = TextBlob(post["text"])
                polarity = blob.sentiment.polarity
                if polarity > 0.1:
                    sentiments["positive"] += 1
                elif polarity < -0.1:
                    sentiments["negative"] += 1
                else:
                    sentiments["neutral"] += 1
            except:
                sentiments["neutral"] += 1
        
        # 口調マーカーの出現頻度
        tone_markers = {
            "exclamation": sum(post["text"].count("!") + post["text"].count("！") for post in posts),
            "w_lol": sum(post["text"].count("w") for post in posts),
            "emoji_count": sum(self._count_emojis(post["text"]) for post in posts),
            "casual_ending": sum(
                any(ending in post["text"] for ending in ["だなぁ", "んだよね", "よね", "だね"])
                for post in posts
            )
        }
        
        return {
            "avg_length": avg_length,
            "sentiment": sentiments,
            "tone_markers": tone_markers
        }
    
    def _count_emojis(self, text: str) -> int:
        """
        絵文字の数をカウント（簡易版）
        
        Args:
            text: テキスト
            
        Returns:
            絵文字数
        """
        emoji_count = 0
        for char in text:
            # Unicode絵文字範囲（簡易チェック）
            if ord(char) > 0x1F300:
                emoji_count += 1
        return emoji_count
    
    def format_persona_summary(self, persona: Dict) -> str:
        """
        ペルソナの要約を整形
        
        Args:
            persona: ペルソナ辞書
            
        Returns:
            整形された要約文字列
        """
        summary = f"""
## 📊 {persona['name']}のペルソナプロファイル

**アカウント**: @{persona['account']}  
**分析投稿数**: {persona['post_count']}件

### 📝 背景
{persona.get('background', '（情報なし）')}

### 💭 意見傾向
{', '.join(persona.get('tendencies', [])) if persona.get('tendencies') else '（分析中）'}

### 🗣️ 口調の特徴
{persona.get('tone', '（分析中）')}

### 🎭 性格
{persona.get('personality', '（分析中）')}

### 📈 統計情報
- 平均投稿長: {persona['statistics']['avg_length']:.1f}文字
- 感嘆符使用: {persona['statistics']['tone_markers']['exclamation']}回
- 「w」使用: {persona['statistics']['tone_markers']['w_lol']}回
- 絵文字使用: {persona['statistics']['tone_markers']['emoji_count']}回
- カジュアル語尾: {persona['statistics']['tone_markers']['casual_ending']}回

### 😊 センチメント分布
- ポジティブ: {persona['statistics']['sentiment']['positive']}件
- ニュートラル: {persona['statistics']['sentiment']['neutral']}件
- ネガティブ: {persona['statistics']['sentiment']['negative']}件
"""
        return summary
    
    def validate_tone_mimicry(self, generated_text: str, persona: Dict) -> Dict:
        """
        生成テキストの口調模倣を検証（NFR-08対応）
        
        Args:
            generated_text: 生成されたテキスト
            persona: ペルソナ辞書
            
        Returns:
            検証結果辞書
        """
        validation = {
            "has_exclamation": "!" in generated_text or "！" in generated_text,
            "has_w": "w" in generated_text,
            "has_emoji": self._count_emojis(generated_text) > 0,
            "has_casual_ending": any(
                ending in generated_text 
                for ending in ["だなぁ", "んだよね", "よね", "だね", "だわ"]
            ),
            "length_appropriate": 50 <= len(generated_text) <= 500
        }
        
        # スコア計算（各項目20%）
        score = sum([
            validation["has_exclamation"],
            validation["has_w"],
            validation["has_emoji"],
            validation["has_casual_ending"],
            validation["length_appropriate"]
        ]) / 5 * 100
        
        validation["score"] = score
        validation["passed"] = score >= 80.0
        
        logger.info(f"口調模倣検証: スコア={score:.1f}%, 合格={validation['passed']}")
        
        return validation

