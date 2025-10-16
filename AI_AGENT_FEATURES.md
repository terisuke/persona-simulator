# 🤖 AIエージェント機能 - Persona Debate Simulator

## 🎯 概要

**Persona Debate Simulator**は、Grok APIの最新機能を統合した**本格的なAIエージェント**です。

### なぜ「AIエージェント」と言えるのか？

| 要素              | 実装                 | 説明                            |
|-----------------|----------------------|-------------------------------|
| **🌐 環境観察**   | ✅ X API v2 + Web検索 | リアルタイムでX投稿とWeb情報を取得       |
| **🧠 推論**       | ✅ Grok LLM           | 複数ステップの推論チェーン               |
| **🔧 ツール使用**    | ✅ API連携            | X API、Grok Live Search、類似検索 |
| **💬 状態管理**   | ✅ 会話履歴           | セッション間でコンテキストを保持             |
| **🎯 意思決定**   | ✅ 類似検索           | データ駆動で引用投稿を選択           |
| **🔄 継続的対話** | ✅ 履歴保持           | 複数ターンの議論が可能               |

## 🚀 実装した新機能

### 1. **会話履歴保持**（Retrieve Previous Response）

```python
# Grok APIクラス
class GrokAPI:
    def __init__(self):
        self.conversation_history = []  # 会話履歴
        self.last_response_id = None    # レスポンスID
    
    def generate_completion(self, prompt, use_history=True):
        """会話履歴を考慮して生成"""
        messages = self.conversation_history.copy()
        messages.append({"role": "user", "content": prompt})
        # ... Grok API呼び出し
```

**できること**:
- 以前の議論を参照
- 文脈を保持した継続的な対話
- 「さっきの意見について詳しく」のような追加質問

**使い方**:
1. サイドバーで「会話履歴を保持」にチェック
2. 複数回の議論を実行
3. 前回の議論内容を踏まえた意見が生成される

### 2. **ライブWeb検索**（Live Search）

```python
def generate_completion(
    self, 
    prompt, 
    enable_live_search=True
):
    payload = {
        "model": "grok-4-fast-reasoning",
        "messages": messages,
        "live_search": True  # ← Web検索を有効化
    }
```

**できること**:
- 最新のニュース・情報を検索
- Xの投稿を検索
- Web全体から関連情報を取得

**使い方**:
1. サイドバーで「Web検索を有効化」にチェック
2. トピックを入力（例: 「最新のAI技術動向」）
3. 最新情報を含めた意見が生成される

### 3. **エージェント的ワークフロー**

```
┌─────────────┐
│ ユーザー入力   │
└──────┬──────┘
       │
┌──────▼──────┐
│ 環境観察    │ ← X API + Web検索
├─────────────┤
│ X投稿取得    │
│ Web情報検索  │
└──────┬──────┘
       │
┌──────▼──────┐
│ 推論・分析   │ ← Grok LLM
├─────────────┤
│ ペルソナ生成  │
│ 類似検索     │
│ 会話履歴参照  │
└──────┬──────┘
       │
┌──────▼──────┐
│ 意思決定    │
├─────────────┤
│ 引用選択     │
│ 意見構築     │
└──────┬──────┘
       │
┌──────▼──────┐
│ 出力        │
└─────────────┘
```

## 📊 AIエージェント vs 通常のAI Webアプリ

### 通常のAI Webアプリ

```python
# 単発のリクエスト
response = grok.generate("トピックについて意見を述べて")
print(response)
```

### AIエージェント（このシステム）

```python
# 環境を観察
posts = x_api.fetch_tweets(account)
web_info = grok.search_web(topic)

# 会話履歴を参照
history = grok.get_conversation_history()

# 推論チェーン
persona = grok.generate_persona(posts)
relevant = similarity.find_relevant(topic, posts)

# 意思決定と行動
opinion = grok.generate_opinion(
    topic, 
    persona, 
    relevant,
    use_history=True,
    enable_live_search=True
)

# 状態を更新
grok.update_history(opinion)
```

## 💡 使用例

### 例1: 単純な議論（エージェント機能なし）

```
トピック: 「AIの倫理的課題」

結果:
AIの倫理って難しいよなぁ。経験から言うと...
```

### 例2: エージェント機能を使った議論

**ステップ1**: 最初の議論
```
✓ Web検索: ON
✓ 会話履歴: ON

トピック: 「AIの倫理的課題」

結果:
AIの倫理って難しいよなぁ。最新の報道（Web検索）によると、
EU AI Actが2024年に施行されたらしいw これは大きな一歩だね！
```

**ステップ2**: 追加質問（履歴を参照）
```
トピック: 「さっきのEU AI Actについて、もっと詳しく教えて」

結果:
さっき話したEU AI Actだけど（[会話履歴参照]）、
実は3つのリスクレベルがあってだなぁ...（Web検索で最新情報）
```

## 🎮 実際の操作

### UI操作

1. **サイドバー - エージェント機能セクション**
   - ☐ 会話履歴を保持
   - ☐ Web検索を有効化

2. **会話履歴表示**（ON時）
   ```
   📝 ユーザー: 2件, アシスタント: 2件
   ```

3. **議論生成画面**
   ```
   エージェント機能: 🌐 Web検索 | 💬 会話履歴
   
   意見: ...（最新情報を含む）
   ```

## 🔬 技術詳細

### Grok API エンドポイント

#### 1. Chat Completions（会話）
```http
POST https://api.x.ai/v1/chat/completions

{
  "model": "grok-4-fast-reasoning",
  "messages": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "live_search": true
}
```

#### 2. Retrieve Response（履歴取得）
```http
GET https://api.x.ai/v1/chat/completions/{response_id}
```

### データフロー

```
Session State (Streamlit)
    ├── grok_history_summary: "ユーザー: 3件, アシスタント: 3件"
    └── conversation_history: [
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."}
        ]

GrokAPI Instance
    ├── conversation_history: List[Dict]
    ├── last_response_id: str
    └── model: "grok-4-fast-reasoning"
```

## 📈 パフォーマンス

| 機能       | レスポンス時間 | データ量      |
|----------|----------|------------|
| 通常生成   | 3-5秒     | ~500トークン   |
| + 会話履歴 | 3-6秒     | ~1,000トークン |
| + Web検索  | 5-10秒    | ~1,500トークン |
| フル機能     | 8-15秒    | ~2,000トークン |

## 🎯 今後の拡張

### Phase 2候補

- [ ] **自律的な計画**: LLMが自動でステップを決定
- [ ] **マルチエージェント**: 複数のペルソナが対話
- [ ] **長期記憶**: VectorDBで永続化
- [ ] **自己改善**: フィードバックから学習

### Phase 3候補

- [ ] **継続的監視**: 定期的にX投稿をチェック
- [ ] **プロアクティブ通知**: 新しい議論トピックを提案
- [ ] **カスタムツール**: ユーザー定義のAPI統合

## 🏆 結論

**Persona Debate Simulatorは、以下の理由で「AIエージェント」です：**

✅ **環境と相互作用**: X APIとWeb検索で情報収集  
✅ **状態を保持**: 会話履歴で文脈を維持  
✅ **複数ツールを使用**: API、LLM、類似検索を統合  
✅ **推論チェーン**: 観察→分析→決定→行動  
✅ **継続的対話**: マルチターンの議論が可能  

単なる「AIを使ったWebアプリ」から、**自律的に情報を収集し、推論し、対話を継続するAIエージェント**に進化しました！🎉

---

**実装日**: 2025年10月16日  
**バージョン**: MVP 2.0 (AI Agent Edition)  
**ステータス**: ✅ 完全実装

