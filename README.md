# Persona Debate Simulator (AI Agent Edition)

Xアカウントの投稿を分析し、ペルソナを動的に生成して仮想議論をシミュレートする**AIエージェント**アプリケーションです。

## 🤖 AIエージェント機能

✨ **このシステムは本格的なAIエージェントです！**

- **🌐 マルチプラットフォーム分析**: Instagram、LinkedIn、GitHub等も検索してペルソナ精度を大幅向上
- **🔍 ライブWeb検索**: Grok Live Searchで最新情報をリアルタイム取得
- **💬 会話履歴保持**: 複数ターンの継続的な対話が可能
- **🔧 複数ツール統合**: X API、Grok LLM、類似検索を連携
- **🧠 推論チェーン**: 観察→分析→決定→行動の自律的フロー
- **📊 状態管理**: セッション間でコンテキストを維持

## 特徴

- **実投稿取得**: X API v2で実際のX投稿を取得（オプション）
- **サンプル生成**: X API未設定時はGrok LLMでサンプル投稿を生成
- **ペルソナ生成**: 投稿から口調・性格を徹底的に模倣（Grok LLM）
- **議論シミュレーション**: 指定トピックに対する意見を生成（過去投稿を引用）
- **10アカウント対応**: 最大10アカウントまで同時分析可能
- **データ駆動**: sentence-transformersで類似投稿を自動抽出

## セットアップ

### 1. 依存関係のインストール

```bash
pip install -r requirements.txt
```

### 2. APIキーの設定

プロジェクトルートに `.streamlit` フォルダを作成し、`secrets.toml` ファイルを追加：

```bash
mkdir .streamlit
```

`.streamlit/secrets.toml` の内容：

```toml
# Grok API (必須 - LLM用)
GROK_API_KEY = "your_grok_api_key_here"

# X API v2 (オプション - 実投稿取得用)
X_BEARER_TOKEN = "your_x_bearer_token_here"
```

**Grok APIキー（必須）**:
- [https://x.ai/api](https://x.ai/api) から取得
- ペルソナ生成・議論生成に使用

**X API Bearer Token（オプション）**:
- [https://developer.x.com/](https://developer.x.com/) から取得
- 実際のX投稿を取得する場合に設定
- 未設定の場合、Grok LLMがサンプル投稿を生成
- 詳細は `X_API_SETUP.md` を参照

**注意**: このファイルは `.gitignore` に含まれており、Gitにコミットされません。

### 3. アプリケーションの起動

```bash
streamlit run app.py
```

## 使い方

### 基本モード

1. Xアカウント名を入力（例: @cor_terisuke）
2. 議論トピックを入力（例: "AIの倫理的課題"）
3. 「議論を生成」ボタンをクリック
4. ペルソナの意見と引用された過去投稿を確認

### AIエージェントモード 🤖

1. サイドバーで**「マルチプラットフォーム分析」**をON（デフォルト） → Instagram、LinkedIn、GitHub等も検索
2. サイドバーで**「会話履歴を保持」**をON → 継続的な対話
3. サイドバーで**「Web検索を有効化」**をON → 最新情報を取得
4. トピックを入力して議論生成
5. 追加質問で前回の議論を参照した対話が可能

## デプロイ (Streamlit Cloud)

1. GitHubリポジトリにプッシュ
2. [Streamlit Cloud](https://streamlit.io/cloud) にアクセス
3. リポジトリを接続
4. Secrets設定で `GROK_API_KEY` を追加

## 技術スタック

- **フロントエンド**: Streamlit
- **API**: 
  - Grok API (LLM - ペルソナ生成・議論生成)
  - X API v2 (投稿取得 - オプション)
- **機械学習**: sentence-transformers (類似検索)
- **分析**: TextBlob (センチメント分析)

## プロジェクト構造

```
persona-simulator/
├── app.py                 # メインStreamlitアプリ
├── utils/
│   ├── grok_api.py       # Grok API連携（LLM）
│   ├── x_api.py          # X API v2連携（投稿取得）
│   ├── persona.py        # ペルソナ生成
│   ├── similarity.py     # 類似検索
│   └── error_handler.py  # エラーハンドリング
├── requirements.txt       # 依存関係
├── .streamlit/
│   ├── secrets.toml      # APIキー（Git非管理）
│   └── config.toml       # Streamlit設定
├── README.md             # このファイル
├── X_API_SETUP.md        # X API設定ガイド
└── test_setup.py         # セットアップテスト
```

## 📚 詳細ドキュメント

- `MULTI_PLATFORM_PERSONA.md` - **マルチプラットフォーム・ペルソナ生成（NEW!）**
- `AI_AGENT_FEATURES.md` - AIエージェント機能の詳細説明
- `GROK_MODEL_UPDATE.md` - Grokモデル更新ガイド
- `X_API_SETUP.md` - X API設定ガイド
- `QUICKSTART.md` - クイックスタート

## ライセンス

[MIT License](./LICENCE)

