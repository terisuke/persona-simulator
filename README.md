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

- **チャット風UI + ターン制議論** 💬（NEW!）
  - 🎨 吹き出し形式で視覚的に分かりやすい
  - 🔄 ターン制で本物の議論を再現
  - 👥 最大10アカウントで議論可能
  - 💬 選択的反論 or 全員反論
  - 📊 ラウンド別表示で議論の流れを把握
- **3層キャッシュシステム**: all_data + セッション状態 + ファイルキャッシュでレート制限を完全回避
  - 💾 **ボタンクリック時も再取得なし**（議論開始ボタン等）
  - 💾 設定変更時も**再取得不要**（自動再実行でもAPI呼び出しなし）
  - 🔄 手動再取得ボタンで最新データを取得可能
  - 🆕 新規アカウント追加時のみ自動取得
- **スマート投稿取得**: 4段階のフォールバック戦略で確実に投稿を取得
  1. 🔑 X API v2 (ユーザーIDベース)
  2. 🔍 X API v2 (検索API: `from:username`)
  3. 🌐 **Grok Realtime Web Search**（実投稿を検索）
  4. ⚠️ フォールバック: サンプル投稿生成
- **他アカウント対応**: 認証なしで任意のアカウントを分析可能（Web Search活用）
- **ペルソナ生成**: 投稿から口調・性格を徹底的に模倣（Grok LLM）
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
- 実際のX投稿を高速に取得する場合に設定（推奨）
- 未設定の場合、Grok Realtime Web Searchで実投稿を検索
- 詳細は `X_API_SETUP.md` を参照

**注意**: このファイルは `.gitignore` に含まれており、Gitにコミットされません。

### 3. アプリケーションの起動

```bash
streamlit run app.py
```

## 使い方

### チャット風議論モード 💬（NEW!）

1. サイドバーでXアカウントを入力（例: cor_terisuke, elonmusk）
2. 議論トピックを入力（例: "AIの倫理的課題について"）
3. 「🚀 議論を開始」ボタンをクリック
4. **チャット風タイムライン**で全員の初回意見を確認

**ターン制議論**:

- 「💬 選択した反論を生成」→ 特定の人が特定の人に反論
- 「🔄 全員の反論を生成」→ 全員が順番に反論
- ラウンドを重ねて議論を深める

### AIエージェントモード 🤖

1. サイドバーで**「マルチプラットフォーム分析」**をON（デフォルト） → Instagram、LinkedIn、GitHub等も検索
2. サイドバーで**「会話履歴を保持」**をON → 継続的な対話
3. サイドバーで**「Web検索を有効化」**をON → 最新情報を取得
4. 議論を生成すると、文脈を考慮した自然な反論が可能

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

```text
persona-simulator/
├── app.py                 # メインStreamlitアプリ
├── utils/
│   ├── grok_api.py       # Grok API連携（LLM + 反論生成）
│   ├── x_api.py          # X API v2連携（投稿取得）
│   ├── persona.py        # ペルソナ生成
│   ├── similarity.py     # 類似検索
│   ├── debate_ui.py      # チャット風UI + ターン制議論（NEW!）
│   └── error_handler.py  # エラーハンドリング
├── requirements.txt       # 依存関係
├── .streamlit/
│   ├── secrets.toml      # APIキー（Git非管理）
│   └── config.toml       # Streamlit設定
├── README.md             # このファイル
├── X_API_SETUP.md        # X API設定ガイド
└── test_setup.py         # セットアップテスト
```

## 📚 ドキュメント

- 📖 **`FEATURES.md`** - 全機能の詳細説明（チャット風UI、キャッシュ、アカウント管理等）
- 🚀 **`QUICKSTART.md`** - クイックスタートガイド
- 🔑 **`X_API_SETUP.md`** - X API設定ガイド
- 📝 **`RELEASE_NOTES_v2.md`** - v2.0リリースノート

## ライセンス

[MIT License](./LICENCE)
