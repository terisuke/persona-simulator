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
- **スマート投稿取得**: 実データ優先の4段階取得戦略
  1. 🔑 X API v2 (ユーザーIDベース)
  2. 🔍 X API v2 (検索API: `from:username`)
  3. 🌐 **Grok Realtime Web Search**（実投稿を検索）
  4. ⚠️ フォールバック: サンプル投稿生成（**運用モードでは禁止**）
  
  > **運用ポリシー**: 運用モード（`MODE=prod`/`staging`）では生成フォールバックは実行されません。実データ取得に失敗した場合は未確定ペルソナとして扱い、CLIでの再取得を促します。
  
  > **X API オプトアウト機能**: UIサイドバーの「🔑 X API設定」セクションで「X APIを使用する」トグルをOFFにすると、X APIを無効化してGrok Web Searchのみで投稿を取得できます。レート制限を気にせずに大量候補を収集したい場合に便利です。CLIでは`--no-x-api`フラグで同様の動作になります。X API無効時は`quality_score`が暫定値になるため、KPI表示で警告が表示されます。
- **他アカウント対応**: 認証なしで任意のアカウントを分析可能（Web Search活用）
- **ペルソナ生成**: 投稿から口調・性格を徹底的に模倣（Grok LLM）
- **データ駆動**: sentence-transformersで類似投稿を自動抽出

## 📚 ドキュメント

### 主要ドキュメント

- **[「100人の村」アプローチ - 多様性とマーケティング活用の仕組み](./docs/100_VILLAGE_APPROACH.md)**: 「100人の村」のように多様な意見を集約し、マーケティングに活用する仕組みを初めて見る方にもわかりやすく説明
- **[実装アプローチ完全ドキュメント](./docs/IMPLEMENTATION_APPROACH.md)**: 技術的な実装詳細
  - キーワード検索、多様性サンプリング、ランダム収集の詳細ロジック
  - quality_scoreの算出方法
  - データ取得パイプライン、ペルソナ生成、議論システムの完全解説

### その他のドキュメント

- **[機能詳細](./FEATURES.md)**: 全機能の詳細説明
- **[使い方ガイド](./USAGE_GUIDE.md)**: ステップバイステップの使い方
- **[X APIセットアップ](./X_API_SETUP.md)**: X API v2の設定方法
- **[テスト手順](./TEST_PROCEDURE.md)**: テストと検証の手順
- **[リリースノート v2.0](./RELEASE_NOTES_v2.md)**: v2.0の変更内容

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

# ========================================
# 運用モード設定（オプション）
# ========================================
# prod, staging, dev のいずれかを設定
# prod/staging: 生成フォールバックを禁止（実データのみ）
# dev: 開発・テスト用（生成フォールバックを許可）
MODE = "dev"  # デフォルト: dev

# ========================================
# Stage3: 多 SNS 連携（すべてオプション）
# ========================================

# Facebook Graph API
FACEBOOK_APP_ID = "your_facebook_app_id"
FACEBOOK_APP_SECRET = "your_facebook_app_secret"
FACEBOOK_ACCESS_TOKEN = "your_facebook_access_token"  # オプション

# Instagram Graph API
INSTAGRAM_APP_ID = "your_instagram_app_id"  # Facebook App ID と同じ
INSTAGRAM_APP_SECRET = "your_instagram_app_secret"  # Facebook App Secret と同じ
INSTAGRAM_ACCESS_TOKEN = "your_instagram_access_token"  # オプション
INSTAGRAM_BUSINESS_ACCOUNT_ID = "your_instagram_business_account_id"

# LinkedIn Marketing API
LINKEDIN_CLIENT_ID = "your_linkedin_client_id"
LINKEDIN_CLIENT_SECRET = "your_linkedin_client_secret"
LINKEDIN_ACCESS_TOKEN = "your_linkedin_access_token"  # オプション

# TikTok Research API
TIKTOK_APP_ID = "your_tiktok_app_id"
TIKTOK_APP_SECRET = "your_tiktok_app_secret"
TIKTOK_ACCESS_TOKEN = "your_tiktok_access_token"  # オプション
```

**Grok APIキー（必須）**:

- [https://x.ai/api](https://x.ai/api) から取得
- ペルソナ生成・議論生成に使用

**X API Bearer Token（オプション）**:

- [https://developer.x.com/](https://developer.x.com/) から取得
- 実際のX投稿を高速に取得する場合に設定（推奨）
- 未設定の場合、Grok Realtime Web Searchで実投稿を検索
- 詳細は `X_API_SETUP.md` を参照

**Stage3 多 SNS 連携（すべてオプション）**:

- **Facebook**: [Facebook for Developers](https://developers.facebook.com/) でアプリを作成
- **Instagram**: [Instagram Graph API](https://developers.facebook.com/docs/instagram-api/) でビジネスアカウントを連携
- **LinkedIn**: [LinkedIn Developers](https://www.linkedin.com/developers/) でアプリを作成
- **TikTok**: [TikTok for Developers](https://developers.tiktok.com/) で Research API にアクセス

**運用モード設定**:

- `MODE = "prod"` または `MODE = "staging"`: 運用モード
  - 生成フォールバックを**禁止**（実データのみで議論/分析）
  - 生成データが混入すると警告・エラー表示
- `MODE = "dev"` または未設定: 開発モード
  - 生成フォールバックを許可（テスト・デモ用）

**X API オプトアウト設定**:

- UI側: サイドバーの「🔑 X API設定」セクションで「X APIを使用する」トグルをON/OFF
  - OFFにするとGrok Web Searchのみで投稿を取得（レート制限回避）
  - OFF時は`quality_score`が暫定値になるため警告が表示される
  - 運用モードでもOFF可能（警告付き）
- CLI側: `--use-x-api` / `--no-x-api` フラグで制御
  - 未指定時は`X_BEARER_TOKEN`の有無で自動判定
  - `--no-x-api`指定時はログに「X API使用: False」が記録される

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

> ⚠️ レート制限に達した場合は、`ingest_accounts.py` でバッチ生成を再実行し、約15分後にUIで再試行してください。UI側は待機せず警告表示のみ行い、実データ取得はCLIバッチに委ねる運用を徹底します（詳細は本セクションの手順に準拠）。

### CLI を使った事前キャッシュ生成 🖥️（推奨: 50人以上）

UI からのバッチ処理に加えて、**CLI で事前にキャッシュを生成**することで、より効率的な大規模分析が可能です:

```bash
# アカウントリスト (CSV または TXT) から一括取得
python ingest_accounts.py accounts.csv

# バッチサイズを調整してレート制限を管理
python ingest_accounts.py accounts.csv --batch-size 10

# Web検索を無効化して高速化
python ingest_accounts.py accounts.csv --no-web-enrichment

# X APIの使用可否を制御（相互排他）
python ingest_accounts.py accounts.csv --use-x-api   # 明示的に有効化
python ingest_accounts.py accounts.csv --no-x-api    # 無効化（Grok Web Searchのみ）

# 生成フォールバックの許可/禁止（デフォルトはMODE設定に従う）
python ingest_accounts.py accounts.csv --allow-generated   # 明示的に許可（開発用）
python ingest_accounts.py accounts.csv --disallow-generated  # 明示的に禁止（運用用）
```

**CLI のメリット**:
- ✅ レート制限を自動監視・管理 (15分/15リクエスト)
- ✅ バックグラウンドで長時間実行可能
- ✅ 詳細ログファイル (`.cache/ingest.log`)
- ✅ 中断・再開が可能 (キャッシュ済みはスキップ)
- ✅ 100人分のデータを30-60分で取得
- ✅ **データソース統計**を自動記録（実データ比率の推移を追跡）

**品質KPIとデータソース統計**:

CLI 実行後、ログには以下の統計が記録されます:

```text
📊 データソース内訳:
  🔑 X API (Twitter): 15
  🌐 Grok Web Search: 3
  📝 フォールバック生成: 2
  💡 実データ比率: 90.0% (18/20)
  ⚠️  生成データ比率: 10.0% (2/20)

📊 品質指標:
  ⚠️  未確定ペルソナ: 1件
  📈 平均quality_score: 0.75
  📊 中央値quality_score: 0.78 (対象: 18件)
```

**統計の意味**:

- **X API (Twitter)**: X API v2 経由で取得した実投稿
- **Grok Web Search**: Grok のリアルタイム検索で取得した投稿
- **フォールバック生成**: API エラー時の代替生成（運用モードでは禁止）
- **実データ比率**: 実投稿（Twitter + Web Search）の割合
- **生成データ比率**: フォールバック生成の割合（運用では5%超過でエラー）
- **未確定ペルソナ**: データ不足や解析失敗により未確定となったアカウント数
- **quality_score**: 実世界指標（フォロワー数・最終投稿・ツイート数）ベースの品質スコア（0.0-1.0）
  - X API無効時は暫定評価（信頼度ベース）となり、`quality_reasons`に「X API metrics unavailable – fallback evaluation」が記録される
  - UIのKPIカードでX API無効時は警告が表示される

**運用モードでの品質管理**:

- **生成データ比率が5%を超過**: CLI は終了コード1で終了し、エラーメッセージを表示
- **未確定ペルソナ**: 議論参加不可、CLI実行を促す表示
- **quality_score**: 0.6未満のアカウントは品質基準未満として除外推奨

**実データ比率が高いほど、ペルソナの精度が向上します。** 定期バッチで実データ比率の推移を追跡し、API 設定や取得戦略を最適化できます。

**ファイル形式**:

- **CSV**: `account`, `username`, `name`, `handle` 列のいずれかを含む
- **TXT**: 1行1アカウント（`#` で始まる行はコメント）

**詳細な使い方**は `AGENTS.md` の「CLI for Batch Account Ingestion」セクションを参照してください。

### アカウント候補の発見 🔍（Stage 2.5 強化版）

**Grok Realtime Web Search でアカウント候補を自動発見**:

CLI を使って、キーワードやランダム検索で影響力のあるアカウント候補を自動的に発見できます。

#### 基本的な使用方法

```bash
# キーワードでアカウント発見（最大 50 件）
python ingest_accounts.py --discover-keyword "AI engineer" --max-results 50

# ランダムにアカウント発見（複数プリセットクエリを実行）
python ingest_accounts.py --discover-random --max-results 50

# カテゴリ指定でランダム検索
python ingest_accounts.py --discover-random --category tech --max-results 50

# プリセットキーワードを使用（16種類のプリセット）
python ingest_accounts.py --preset ai_engineer --max-results 50

# モックデータでテスト（Grok API を呼ばない）
python ingest_accounts.py --discover-keyword "data scientist" --dry-run
```

#### プリセットキーワード一覧

| プリセット名                | 対応する検索語              |
|------------------------|---------------------------|
| `ai_engineer`          | AI engineer               |
| `data_scientist`       | data scientist            |
| `ml_engineer`          | machine learning engineer |
| `startup_founder`      | startup founder           |
| `tech_executive`       | tech executive            |
| `venture_capital`      | venture capitalist        |
| `cybersecurity`        | cybersecurity expert      |
| `cloud_architect`      | cloud architect           |
| `devops_engineer`      | DevOps engineer           |
| `blockchain_developer` | blockchain developer      |
| `product_manager`      | product manager           |
| `ux_designer`          | UX designer               |
| `software_engineer`    | software engineer         |
| `open_source`          | open source contributor   |
| `tech_writer`          | tech writer               |
| `data_engineer`        | data engineer             |

#### カテゴリ指定（ランダム検索時）

ランダム検索をカテゴリ別に絞り込めます：

- `tech`: 技術系アカウント
- `business`: ビジネス・起業家
- `creative`: デザイナー・アーティスト
- `science`: 研究者・科学者
- `developer`: ソフトウェア開発者
- `product`: プロダクトマネージャー
- `community`: テックライター・教育者

#### 発見したアカウントの活用

```bash
# 発見されたアカウントリストを自動生成
# .cache/discover_results/keyword_AI_engineer_20250130_123456.csv
# .cache/discover_results/keyword_AI_engineer_20250130_123456.txt
# .cache/discover_results/preset_ai_engineer_20250130_123456.csv
# .cache/discover_results/random_tech_accounts_20250130_123456.csv

# 生成された TXT ファイルをそのままバッチ処理に流し込む
python ingest_accounts.py .cache/discover_results/keyword_AI_engineer_20250130_123456.txt
```

#### 発見機能の特徴

**精度向上**:
- ✅ 品質基準ベースのフィルタリング: 信頼度スコア 0.7 以上を自動抽出
- ✅ 詳細な品質評価: フォロワー数、アクティビティ、影響力で評価
- ✅ カテゴリ別検索: 特定分野に特化したアカウント発見

**多様性確保**:
- ✅ 48のプリセットクエリ: 7カテゴリ × 最大8パターン
- ✅ 重複除外: 同一アカウントの複数検出を防止

**使いやすさ**:
- ✅ 16のプリセットキーワード: 頻出分野をワンタップ検索
- ✅ CSV/TXT 同時出力: すぐにバッチ処理に使える
- ✅ Dry-run モード: テストやデバッグに便利

**スモークテスト**:

```bash
# アカウント発見機能のテスト（モックデータ使用）
./discover_test.sh
```

#### 今後の拡張（TODO）

- Grok Live Search の `search_parameters` 連携（`x_handles`/`mode`）
- UI 側のセンチメントフィルタ（TextBlob 指標での絞り込み）
- 品質スコア（`quality_score`）のCSV出力列としての追加、または別レポート出力

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

- 📘 **`USAGE_GUIDE.md`** - **使い方ガイド**（ペルソナ作成から議論開始までの手順を詳しく解説）
- 🛠️ **`AGENTS.md`** - コントリビューターガイド（開発フロー、命名規則、Stage1/Stage2の運用方針）
- 📖 **`FEATURES.md`** - 機能の詳細解説（チャット風UI、キャッシュ、アカウント管理など）
- 🔑 **`X_API_SETUP.md`** - X API のセットアップ手順とトラブルシューティング
- 📝 **`RELEASE_NOTES_v2.md`** - リリースノート
- 🧪 **`TEST_PROCEDURE.md`** - Stage1/Stage2 の統合動作確認手順とチェックリスト

## システム概要と今後のロードマップ

### 100人の村を支える実装アプローチ
- **実データ優先の取得パイプライン**: CLI/Streamlit から `ingest_accounts.py` → `utils/grok_api.py` → `utils/x_api.py` の順に接続し、X API → Grok Web Search → フォールバックの優先順位で投稿を収集。運用モードでは生成フォールバックを完全に禁止し、実在データのみでペルソナを構成。
- **品質ゲートとスコアリング**: `check_account_quality()` がフォロワー数・最新投稿日・投稿総数を正規化し、`quality_score` と評価理由をペルソナへ付与。閾値を満たさないアカウントは未確定 (`unverified`) として議論参加をブロック。
- **観測性とKPI**: すべての API 呼び出しで構造化ログを出力し、CLI/Streamlit の両方で実データ比率・生成データ率・未確定数・quality_score をリアルタイムに可視化。生成データ率が閾値を超えた場合は自動的に失敗扱いにして運用品質を担保。
- **キャッシュと再利用**: `.cache/` に投稿・ペルソナ・品質スコアを保存し、セッション/ファイルキャッシュ/ディスクキャッシュの三層でレート制限を抑制。CLI と UI で同じキャッシュを共有して 100 人規模の「村」を即時復元。

### 現在のコア機能
1. **大規模アカウント発見**: Grok Live Search と X API を併用した 48 パターンのプリセット検索、16 種類のキーワード検索、カテゴリ指定や dry-run による高速検証。
2. **多様なペルソナ生成**: Grok LLM で投稿＋Web情報から背景・傾向・口調・性格を抽出。TextBlob の投稿統計や口調マーカーで「キャラクター感」を補強。
3. **議論エージェント**: 類似投稿検索とターン制 UI により、最大 100 人が同時に議論へ参加。マルチプラットフォーム分析・会話履歴保持・Web 検索の ON/OFF を柔軟に制御。
4. **品質モニタリング**: サイドバー KPI／CLI サマリ／構造化ログを通じて、誰が実データか・誰が未確定か・品質スコアは妥当かを即座に判断可能。

### 今後の展望
- **Stage3 多SNS連携**: `utils/bootstrap.py` の Skeleton を基に Facebook / Instagram / LinkedIn / TikTok の API 連携を段階的に実装し、100 人の村をクロスプラットフォーム化。
- **センチメント＆UI拡張**: TextBlob 指標を用いた UI フィルタリング、quality_score の分布可視化、対話エージェントの評価メトリクスを追加予定。
- **マーケ分析自動化**: KPI を基にした自動レポート生成、セグメント別のクラスタリング、長期トレンド分析など、マーケティング向けの派生機能を検討中。

これらの方針に沿って、実在人物の多様なペルソナを維持しつつ、データ分析・マーケティングに活用できる拡張性の高い基盤を継続的に育てていきます。

## ライセンス

[MIT License](./LICENCE)
