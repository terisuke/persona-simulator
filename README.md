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

- **一括管理機能** 📁（NEW!）
  - 📥 CSV/テキストファイルから100アカウントまで一括アップロード
  - 🔄 バッチ処理で段階的にデータ取得（10件ずつ）
  - 📊 進捗サマリとリアルタイム状況表示
  - 🔍 フィルタリング・検索・ソート機能
  - 📋 アカウント管理タブで一括操作
  - 💾 キャッシュ自動検出と復元
- **チャット風UI + ターン制議論** 💬
  - 🎨 吹き出し形式で視覚的に分かりやすい
  - 🔄 ターン制で本物の議論を再現
  - 👥 最大100アカウントで議論可能（一括管理対応）
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

## クイックスタート（5分）

1. **依存関係をインストール**
   ```bash
   pip install -r requirements.txt
   ```
2. **APIキーを設定**  
   `.streamlit/secrets.toml` を作成し、最低でも `GROK_API_KEY` を登録します。（任意で `X_BEARER_TOKEN` を加えるとX API経由の高速取得が可能）
3. **環境チェック**
   ```bash
   python test_setup.py
   ```
4. **アプリを起動**
   ```bash
   streamlit run app.py
   ```

大規模（50-100件）のアカウントを扱う場合は、UI を開く前に CLI (`python ingest_accounts.py accounts.csv`) でキャッシュを作成しておくと即座に分析を始められます。

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

### 一括管理モード 📁（NEW!）

**大規模アカウント管理**:

1. **CSV/テキストファイルで一括アップロード**
   - CSV: `username`列を含むファイル
   - TXT: 改行区切りでアカウント名を記載
   - 最大100アカウントまで対応

2. **バッチ処理で段階的取得**
   - 「🚀 不足分を取得」ボタンで10件ずつ処理
   - 進捗バーでリアルタイム状況確認
   - レート制限を考慮した安全な処理

3. **アカウント管理タブで一括操作**
   - フィルタリング・検索・ソート機能
   - 一括再取得・エクスポート・削除
   - ステータス別表示（キャッシュ済み/取得待ち/エラー）

### CLI を使った事前キャッシュ生成 🖥️（推奨: 50人以上）

UI からのバッチ処理に加えて、**CLI で事前にキャッシュを生成**することで、より効率的な大規模分析が可能です:

```bash
# アカウントリスト (CSV または TXT) から一括取得
python ingest_accounts.py accounts.csv

# バッチサイズを調整してレート制限を管理
python ingest_accounts.py accounts.csv --batch-size 10

# Web検索を無効化して高速化
python ingest_accounts.py accounts.csv --no-web-enrichment
```

**CLI のメリット**:
- ✅ レート制限を自動監視・管理 (15分/15リクエスト)
- ✅ バックグラウンドで長時間実行可能
- ✅ 詳細ログファイル (`.cache/ingest.log`)
- ✅ 中断・再開が可能 (キャッシュ済みはスキップ)
- ✅ 100人分のデータを30-60分で取得

**ファイル形式**:
- **CSV**: `account`, `username`, `name`, `handle` 列のいずれかを含む
- **TXT**: 1行1アカウント（`#` で始まる行はコメント）

**詳細な使い方**は `AGENTS.md` の「CLI for Batch Account Ingestion」セクションを参照してください。

### チャット風議論モード 💬

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
├── ingest_accounts.py     # CLI一括取得ツール（NEW!）
├── utils/
│   ├── grok_api.py       # Grok API連携（LLM + 反論生成）
│   ├── x_api.py          # X API v2連携（投稿取得）
│   ├── persona.py        # ペルソナ生成
│   ├── similarity.py     # 類似検索
│   ├── debate_ui.py      # チャット風UI + ターン制議論
│   ├── error_handler.py  # エラーハンドリング
│   └── bootstrap.py      # 共通初期化ユーティリティ（NEW!）
├── requirements.txt       # 依存関係
├── .streamlit/
│   ├── secrets.toml      # APIキー（Git非管理）
│   └── config.toml       # Streamlit設定
├── README.md             # このファイル
├── X_API_SETUP.md        # X API設定ガイド
├── test_setup.py         # セットアップテスト
├── verify_cache.py       # キャッシュ検証ツール（NEW!）
└── run_test.sh           # 自動テストスクリプト（NEW!）
```

## 📚 ドキュメント

- 🛠️ **`AGENTS.md`** - コントリビューターガイド（開発フロー、命名規則、Stage1/Stage2の運用方針）
- 📖 **`FEATURES.md`** - 機能の詳細解説（チャット風UI、キャッシュ、アカウント管理など）
- 🔑 **`X_API_SETUP.md`** - X API のセットアップ手順とトラブルシューティング
- 📝 **`RELEASE_NOTES_v2.md`** - リリースノート
- 🧪 **`TEST_PROCEDURE.md`** - Stage1/Stage2 の統合動作確認手順とチェックリスト

## ライセンス

[MIT License](./LICENCE)
