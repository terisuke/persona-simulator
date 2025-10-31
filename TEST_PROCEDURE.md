# 実運用準備確認手順

## 概要

Stage1 CLI と Stage2 Streamlit UI が実運用に耐えられるかを確認するための手順書です。

## 前提条件

- `.streamlit/secrets.toml` に `GROK_API_KEY` と `X_BEARER_TOKEN` が設定済み
- 依存関係インストール済み: `pip install -r requirements.txt`

---

## テスト0: 運用モードと生成フォールバック抑制の検証

### 目的

- 運用モード（`MODE=prod`/`staging`）で生成フォールバックが正しく抑制されること
- CLI の `--allow-generated`/`--disallow-generated` フラグが正常に機能すること
- 生成データ率が5%超過時に終了コード1で終了すること

### 手順

#### 0.1 運用モードの設定

`.streamlit/secrets.toml` を編集:

```toml
MODE = "prod"  # 運用モードを設定
```

#### 0.2 テスト用アカウントリストを作成

```bash
cat > test_mode_check.txt << 'EOF'
# 実在しないアカウント（生成フォールバックが発生する可能性）
nonexistent_account_12345
another_fake_account_67890
EOF
```

#### 0.3 CLI実行（生成フォールバック禁止）

```bash
python ingest_accounts.py test_mode_check.txt --disallow-generated
```

**期待される動作**:
- 実データ取得に失敗した場合、生成フォールバックは実行されない
- 生成データ率は0%になる
- 未確定ペルソナが増える可能性がある

#### 0.4 生成データ率の検証

ログに以下の出力があることを確認:

```text
⚠️  生成データ比率: 0.0% (0/2)
```

#### 0.5 開発モードでの動作確認

`.streamlit/secrets.toml` を編集:

```toml
MODE = "dev"  # 開発モード
```

```bash
python ingest_accounts.py test_mode_check.txt --allow-generated
```

**期待される動作**:
- 開発モードまたは `--allow-generated` 指定時は生成フォールバックが許可される
- ただし、運用では使用しないこと

#### 0.6 生成データ率閾値チェックの検証

テスト用に生成データを意図的に混入させ、閾値チェックを確認:

```bash
# 生成データ率が高い状況を作る（実際の運用では避ける）
# このテストは開発環境でのみ実行
```

**期待される動作**:
- 生成データ率が5%を超過した場合、CLI は exit code 1 で終了
- エラーメッセージが表示される

---

## テスト1: CLI で小規模リストを処理

### 目的

- レートリミット待機が `.cache/ingest.log` に記録されること
- `fetched_at` メタデータが書き込まれること

### 手順

#### 1.1 テスト用アカウントリストを作成

```bash
cat > test_accounts.txt << 'EOF'
# Test accounts for rate limit verification
cor_terisuke
elonmusk
sama
ylecun
karpathy
goodfellow_ian
EOF
```

6アカウントで、バッチサイズを小さくしてレートリミット動作を確認します。

#### 1.2 キャッシュをクリア

```bash
rm -rf .cache
```

#### 1.3 CLI を実行（バッチサイズを小さく設定）

```bash
python ingest_accounts.py test_accounts.txt --batch-size 2 --log-level INFO
```

**期待される動作**:
- 各アカウントの処理状況がコンソールに表示される
- バッチごとに2秒の待機が発生
- X API のレートリミットヘッダーが記録される

#### 1.4 ログファイルを確認

```bash
# レートリミット情報の確認
grep -i "rate" .cache/ingest.log

# 待機ログの確認
grep -i "待機\|wait" .cache/ingest.log

# エラーの確認
grep -i "error\|エラー" .cache/ingest.log

# 構造化ログの確認（[STRUCTURED] プレフィックス）
grep "\[STRUCTURED\]" .cache/ingest.log | head -5
```

**確認項目**:
- ✅ レートリミット残数が記録されているか
- ✅ レートリミット接近時の待機ログがあるか（条件次第）
- ✅ エラーがないか
- ✅ 構造化ログ（`[STRUCTURED]`）が出力されているか
  - `source`, `rate_limit_remaining`, `reset_at`, `generated_flag` が含まれているか

#### 1.5 キャッシュファイルの確認

```bash
# キャッシュファイルの一覧
ls -lh .cache/*.pkl

# 特定アカウントのキャッシュを確認
python << 'EOF'
import pickle

# cor_terisuke のキャッシュを読み込み
with open('.cache/posts_cor_terisuke.pkl', 'rb') as f:
    data = pickle.load(f)

print("=== キャッシュ構造 ===")
print(f"Keys: {data.keys()}")
print(f"\n=== Posts ===")
print(f"投稿数: {len(data['posts'])}")
print(f"最初の投稿ID: {data['posts'][0]['id']}")
print(f"\n=== Persona ===")
print(f"名前: {data['persona'].get('name', 'N/A')}")
print(f"背景: {data['persona'].get('background', 'N/A')[:100]}...")
print(f"\n=== Metadata ===")
print(f"取得日時: {data.get('fetched_at', 'なし')}")
EOF
```

**確認項目**:
- ✅ `posts` キーが存在し、投稿リストが格納されている
- ✅ `persona` キーが存在し、ペルソナ情報が格納されている
- ✅ `fetched_at` キーが存在し、ISO形式のタイムスタンプが記録されている

#### 1.6 データソース統計の確認

ログファイルからデータソース統計を確認します:

```bash
# データソース統計の確認
grep -A 5 "📊 データソース内訳" .cache/ingest.log
```

**期待される出力**:

```
📊 データソース内訳:
  🔑 X API (Twitter): X件
  🌐 Grok Web Search: Y件
  📝 フォールバック生成: Z件
  💡 実データ比率: XX.X% (N/6)
```

**確認項目**:
- ✅ データソース内訳が記録されているか
- ✅ 実データ比率が表示されているか
- ✅ 実データ比率が妥当か（X API 設定時: 80%以上推奨）
- ✅ 生成データ比率が表示されているか
- ✅ 未確定ペルソナ数が表示されているか
- ✅ 平均/中央値quality_scoreが表示されているか

**品質KPIの評価**:
- **実データ比率**: 80%以上を推奨（運用モードでは100%が理想）
- **生成データ比率**: 運用モードでは5%超過でエラー（exit code 1）
- **未確定ペルソナ**: 0件が理想、発生時はCLIで再取得を実行
- **quality_score**: 0.6以上を推奨、0.6未満は除外推奨

**実データ比率の評価**:
- **80%以上**: ✅ 質の高いペルソナ生成が期待できます
- **50-80%**: ⚠️ 中程度。必要に応じて X API 設定を確認
- **50%未満**: ⚠️ X_BEARER_TOKEN の設定を確認してください

#### 1.7 結果の記録

以下の情報を記録してください:

```
□ 処理したアカウント数: ___ / 6
□ 成功: ___ 件
□ 失敗: ___ 件
□ 処理時間: ___ 秒
□ レートリミット待機: あり / なし
□ fetched_at 記録: あり / なし
□ データソース統計: あり / なし
□ 実データ比率: ___ %
□ 生成データ比率: ___ %（5%超過でエラー）
□ 未確定ペルソナ数: ___ 件
□ 平均quality_score: ___.__（0.6以上推奨）
□ エラー: あり / なし
```

---

## テスト2: Streamlit でキャッシュ混在状態をテスト

### 目的

- キャッシュ済み＋未取得アカウントが混在した状態で「不足分を取得」が正常動作すること
- 各ステータス（成功・失敗・キャッシュ）が正しく表示されること

### 手順

#### 2.1 部分的なキャッシュ状態を作成

```bash
# 前のテストのキャッシュを一部削除
rm .cache/posts_sama.pkl
rm .cache/posts_ylecun.pkl

# 新しいアカウントを追加したリストを作成
cat > test_accounts_mixed.txt << 'EOF'
cor_terisuke
elonmusk
sama
ylecun
karpathy
goodfellow_ian
# 新規追加（キャッシュなし）
AndrewYNg
lexfridman
EOF
```

**状態**:
- キャッシュ済み: cor_terisuke, elonmusk, karpathy, goodfellow_ian (4件)
- キャッシュなし: sama, ylecun, AndrewYNg, lexfridman (4件)

#### 2.2 Streamlit アプリを起動

```bash
streamlit run app.py
```

#### 2.3 一括アップロード機能をテスト

1. サイドバーの **「📁 一括アップロード」** セクションを開く
2. `test_accounts_mixed.txt` をアップロード
3. 「📥 アカウントを一括追加」ボタンをクリック

**確認項目**:
- ✅ 8件のアカウントが読み込まれる
- ✅ サイドバーに全アカウントが表示される

#### 2.4 キャッシュステータスを確認

サイドバーで各アカウントの横に表示されるアイコンを確認:

```
✅ cor_terisuke    (キャッシュ済み)
✅ elonmusk        (キャッシュ済み)
⏳ sama            (未取得)
⏳ ylecun          (未取得)
✅ karpathy        (キャッシュ済み)
✅ goodfellow_ian  (キャッシュ済み)
⏳ AndrewYNg       (未取得)
⏳ lexfridman      (未取得)
```

**確認項目**:
- ✅ キャッシュ済みアカウントに ✅ マークが表示される
- ✅ 未取得アカウントに ⏳ マークまたは空白が表示される

#### 2.5 バッチ処理を実行

1. 「⚡ バッチ処理」セクションまでスクロール
2. 未取得アカウント数を確認（4件のはず）
3. 「🚀 不足分を取得」ボタンをクリック

**確認項目**:
- ✅ 進捗バーが表示される
- ✅ 処理中のアカウント名が表示される
- ✅ バッチごとの進捗が表示される（例: 「🔄 バッチ処理中: 1-2 / 4」）

#### 2.6 サイドバーのKPIカードを確認

サイドバー下部の **「📊 品質KPI」** セクションを確認:

**確認項目**:
- ✅ 実データ比率が表示されているか（例: "85.0%"）
- ✅ 生成データ率が表示されているか（0%の場合は "0/0"）
- ✅ 未確定ペルソナ数が表示されているか（例: "2件"）
- ✅ 平均/中央値quality_scoreが表示されているか（データがある場合）
- ✅ 運用モードで生成データがある場合、エラーメッセージが表示されるか

**KPIの意味**:
- **実データ比率**: 実投稿（Twitter + Web Search）の割合、100%が理想
- **生成データ率**: フォールバック生成の割合、運用モードでは0%が理想
- **未確定ペルソナ**: データ不足により未確定となったアカウント数
- **quality_score**: 実世界指標ベースの品質スコア、0.6以上推奨

#### 2.7 処理結果を確認

バッチ処理完了後、以下を確認:

**メインエリア**:
- ✅ 「🎉 バッチ処理が完了しました！」メッセージ
- ✅ 処理結果のサマリー:
  ```
  ✅ 成功: X件
  📦 キャッシュ使用: 4件
  ❌ 失敗: Y件
  ```

**サイドバー**:
- ✅ 全アカウントに ✅ マークが表示される（失敗がなければ）
- ✅ 各アカウントの横に投稿数が表示される

#### 2.7 キャッシュ済みアカウントの動作確認

1. サイドバーで `cor_terisuke` (キャッシュ済み) を選択
2. メッセージの表示を確認

**確認項目**:
- ✅ 「📦 キャッシュからデータをロード」メッセージが表示される
- ✅ API呼び出しなしで即座にロードされる
- ✅ ペルソナ情報が表示される

#### 2.8 新規取得アカウントの動作確認

1. サイドバーで `sama` (新規取得) を選択
2. メッセージの表示を確認

**確認項目**:
- ✅ 投稿数が表示される
- ✅ ペルソナ情報が表示される
- ✅ 取得方法が表示される（「🔑 X API v2」など）

#### 2.8.1 未確定ペルソナの確認（該当する場合）

実在しないアカウントや取得に失敗したアカウントで、未確定ペルソナの動作を確認:

**確認項目**:
- ✅ ペルソナ生成に失敗した場合、「⚠️ ペルソナは未確定です」という警告が表示される
- ✅ 「👉 まずは CLI のバッチ取得で実投稿のキャッシュ生成を行ってください。」というメッセージが表示される
- ✅ アカウントステータスが `unverified` として記録される
- ✅ 議論参加がブロックされる（該当UIで確認）

#### 2.9 アカウント管理タブをテスト

1. 画面上部の「📊 アカウント管理」タブをクリック
2. アカウント一覧を確認

**確認項目**:
- ✅ 全8アカウントが表示される
- ✅ ステータス列に「キャッシュ済み」「取得済み」などが表示される
- ✅ 投稿数が表示される
- ✅ フィルタ機能が動作する

#### 2.10 個別再取得をテスト

1. サイドバーで `cor_terisuke` の横の 🔄 ボタンをクリック
2. 再取得の動作を確認

**確認項目**:
- ✅ 「🔄 再取得中...」メッセージが表示される
- ✅ 再取得が完了する
- ✅ 「✅ 再取得完了」メッセージが表示される
- ✅ キャッシュが更新される

#### 2.11 結果の記録

以下の情報を記録してください:

```
□ 一括アップロード: 成功 / 失敗
□ キャッシュ検出: 正常 / 異常
□ バッチ処理: 成功 / 失敗
  - 処理したアカウント数: ___ / 4
  - 成功: ___ 件
  - 失敗: ___ 件
□ ステータス表示: 正確 / 不正確
□ キャッシュ使用: 正常 / 異常
□ 個別再取得: 成功 / 失敗
□ UIの応答性: 良好 / 問題あり
```

---

## テスト3: エラーハンドリングの確認

### 3.1 無効なアカウント名のテスト

```bash
cat > test_invalid.txt << 'EOF'
cor_terisuke
invalid_account_xyz123456789
elonmusk
EOF

python ingest_accounts.py test_invalid.txt
```

**確認項目**:
- ✅ 無効なアカウントでエラーが発生する
- ✅ 他のアカウントは正常に処理される
- ✅ エラーメッセージが分かりやすい

### 3.2 API キーエラーのテスト

```bash
# 一時的に環境変数をクリア
unset GROK_API_KEY
python ingest_accounts.py test_accounts.txt
```

**確認項目**:
- ✅ 分かりやすいエラーメッセージが表示される
- ✅ secrets.toml の設定を促すメッセージが表示される

---

## テスト4: パフォーマンス確認

### 4.1 大規模リスト（20-30件）のテスト

```bash
# 20件のアカウントリストを作成
cat > test_large.txt << 'EOF'
cor_terisuke
elonmusk
sama
ylecun
karpathy
goodfellow_ian
AndrewYNg
lexfridman
# ... 合計20-30件
EOF

# 処理時間を計測
time python ingest_accounts.py test_large.txt --batch-size 5
```

**確認項目**:
- ✅ レートリミットが正しく管理される
- ✅ 処理時間が妥当（20件で5-10分程度）
- ✅ メモリ使用量が安定している

---

## 総合評価チェックリスト

### Stage1 CLI

```
□ ディレクトリなしで起動してもエラーにならない
□ レートリミットが自動検出・待機される
□ fetched_at が正しく記録される
□ データソース統計（source 別カウント）が記録される
□ 実データ比率がログに出力される
□ ログファイルが正常に作成される
□ キャッシュファイルが正しい形式で保存される
□ エラー時も適切にハンドリングされる
□ 進捗表示が分かりやすい
□ 中断・再開が可能（キャッシュスキップ）
```

### Stage2 Streamlit UI

```
□ 一括アップロードが動作する
□ キャッシュ検出が正常に動作する
□ バッチ処理が正常に動作する
□ 進捗表示が分かりやすい
□ ステータス表示が正確
□ キャッシュ使用時に API 呼び出しがない
□ 個別再取得が動作する
□ エラーメッセージが分かりやすい
□ UI の応答性が良好
□ アカウント管理タブが動作する
```

### 統合動作

```
□ CLI で生成したキャッシュを UI が認識する
□ UI で生成したキャッシュを CLI が認識する
□ 混在状態でも正常動作する
□ レートリミットエラーが発生しない
□ データ整合性が保たれる
```

---

## 実運用 Ready の判定基準

以下の条件を**すべて**満たした場合、実運用準備完了と判断します:

1. ✅ CLI で 6件以上を正常に処理できる
2. ✅ `.cache/ingest.log` にレートリミット情報が記録される
3. ✅ `fetched_at` が全キャッシュに記録される
4. ✅ **データソース統計（source 別カウントと実データ比率）がログに記録される**
5. ✅ Streamlit でキャッシュ混在状態を正しく認識する
6. ✅ バッチ処理で未取得分のみを取得する
7. ✅ ステータス表示が正確（成功・失敗・キャッシュ）
8. ✅ エラーハンドリングが適切
9. ✅ API 呼び出しが最適化されている（キャッシュ使用時は0回）

---

## トラブルシューティング

### 問題: レートリミットに達した

**対処法**:
```bash
# 15分待機してから再実行
sleep 900
python ingest_accounts.py test_accounts.txt
```

### 問題: キャッシュが認識されない

**対処法**:
```bash
# キャッシュファイルの権限を確認
ls -l .cache/*.pkl

# キャッシュの内容を確認
python -c "import pickle; print(pickle.load(open('.cache/posts_cor_terisuke.pkl', 'rb')).keys())"
```

### 問題: Streamlit でエラーが出る

**対処法**:
```bash
# Streamlit をクリーンスタート
streamlit cache clear
streamlit run app.py
```

---

## テスト3.5: X API オプトアウト機能の検証（NEW!）

### 目的

- UI側で「X APIを使用する」トグルをOFFにした際の動作確認
- CLI側で`--no-x-api`フラグを使用した際の動作確認
- X API無効時の品質評価（暫定評価）が正常に動作すること
- KPI表示で警告が適切に表示されること

### 手順

#### 3.5.1 UI側でX APIをOFFにする

1. Streamlitアプリを起動: `streamlit run app.py`
2. サイドバーの「🔑 X API設定」セクションまでスクロール
3. 「X APIを使用する」トグルをOFFに設定

**確認項目**:
- ✅ トグルがOFFになる
- ✅ 運用モードの場合は警告「⚠️ 運用モードでX APIを無効化しています。quality_scoreは暫定値になります。」が表示される
- ✅ 開発モードの場合は情報「ℹ️ X APIが無効化されています。Grok Web Searchのみで取得します。」が表示される

#### 3.5.2 UI側で収集機能を実行（X API OFF）

1. サイドバーの「🔍 キーワードで収集」セクションでキーワードを入力（例: "AI engineer"）
2. 最大人数を設定（例: 10）
3. 「🚀 収集開始」ボタンをクリック

**確認項目**:
- ✅ Grok Web Searchのみで候補アカウントが取得される
- ✅ 収集コマンドに`--no-x-api`フラグが自動的に付与される
- ✅ 結果CSV/TXTが正常に生成される

#### 3.5.3 UI側でバッチ処理を実行（X API OFF）

1. 複数のアカウントを追加（一括アップロードまたは個別追加）
2. 「🚀 不足分を取得」ボタンをクリック

**確認項目**:
- ✅ Grok Web Searchのみで投稿が取得される（X APIは使用されない）
- ✅ 投稿のsourceが`web_search`として記録される
- ✅ バッチ処理が正常に完了する

#### 3.5.4 UI側のKPI表示を確認（X API OFF）

サイドバー下部の「📊 品質KPI」セクションを確認:

**確認項目**:
- ✅ quality_scoreが表示されている場合、「⚠️ X APIが無効化されているため、quality_scoreは暫定値です。」という警告が表示される
- ✅ quality_scoreデータがない場合、「⚠️ X APIが無効化されているため、quality_scoreは暫定値になります。」という警告が表示される
- ✅ 実データ比率が表示される（Grok Web Search分がカウントされる）

#### 3.5.5 CLI側で`--no-x-api`フラグをテスト

```bash
# テスト用アカウントリストを作成
cat > test_no_x_api.txt << 'EOF'
cor_terisuke
elonmusk
sama
EOF

# X APIを無効化して実行
python ingest_accounts.py test_no_x_api.txt --no-x-api
```

**確認項目**:
- ✅ ログに「X API使用: False (--no-x-api指定)」が表示される
- ✅ 一括処理開始ログに「X API使用: False」が記録される
- ✅ 結果サマリに「X API使用: False」が記録される
- ✅ すべてのアカウントがGrok Web Searchのみで取得される（sourceが`web_search`）
- ✅ quality_scoreが暫定評価となり、`quality_reasons`に「X API metrics unavailable – fallback evaluation」が含まれる

#### 3.5.6 CLI側で`--use-x-api`フラグをテスト

```bash
# X APIを明示的に有効化して実行
python ingest_accounts.py test_no_x_api.txt --use-x-api
```

**確認項目**:
- ✅ ログに「X API使用: True (--use-x-api指定)」が表示される
- ✅ X_BEARER_TOKENが設定されている場合はX API経由で取得される
- ✅ X_BEARER_TOKENが未設定の場合は警告が表示され、Grok Web Searchへフォールバック

#### 3.5.7 X API無効時の品質評価を確認

CLI実行後、キャッシュファイルを確認:

```bash
python << 'EOF'
import pickle
import json

# キャッシュを読み込み
with open('.cache/posts_cor_terisuke.pkl', 'rb') as f:
    data = pickle.load(f)

persona = data.get('persona', {})
quality_reasons = persona.get('quality_reasons', [])

print("=== Quality Score ===")
print(f"quality_score: {persona.get('quality_score', 'N/A')}")
print(f"\n=== Quality Reasons ===")
for reason in quality_reasons:
    print(f"- {reason}")

# X API無効時の理由が含まれているか確認
if any("X API metrics unavailable" in str(r) for r in quality_reasons):
    print("\n✅ X API無効時の理由が正しく記録されています")
else:
    print("\n⚠️ X API無効時の理由が記録されていません")
EOF
```

**確認項目**:
- ✅ `quality_reasons`に「X API metrics unavailable – fallback evaluation」が含まれている
- ✅ quality_scoreが暫定値として計算されている

#### 3.5.8 結果の記録

以下の情報を記録してください:

```
□ UIトグル動作: 正常 / 異常
  - トグルOFF時の警告表示: あり / なし
□ UI収集機能（X API OFF）: 成功 / 失敗
  - --no-x-apiフラグの付与: あり / なし
□ UIバッチ処理（X API OFF）: 成功 / 失敗
  - 取得方法: Grok Web Search / その他
□ KPI警告表示: あり / なし
□ CLI --no-x-apiフラグ: 正常 / 異常
  - ログ記録: あり / なし
  - サマリ記録: あり / なし
□ CLI --use-x-apiフラグ: 正常 / 異常
□ 品質評価（暫定評価）: 正常 / 異常
  - quality_reasonsの記録: あり / なし
```

---

## テスト4: Stage 2.5 アカウント発見機能（NEW!）

### 4.1 Dry-run スモークテスト

```bash
# 自動テストスクリプトを実行
./discover_test.sh
```

**確認項目**:
- ✅ キーワード検索（dry-run）が成功する
- ✅ ランダム検索（dry-run）が成功する
- ✅ CSV ファイルが `.cache/discover_results/` に生成される
- ✅ CSV に `source` 列が含まれる（grok_keyword または grok_random）
- ✅ TXT ファイルも同時に生成される

### 4.2 キーワード検索テスト（実API）

**⚠️ 注意**: Grok API を実際に呼び出します。API クレジットを消費します。

```bash
# キーワード "AI engineer" で 10 件発見
python ingest_accounts.py --discover-keyword "AI engineer" --max-results 10
```

**確認項目**:
- ✅ Grok API が呼び出される
- ✅ 10 件前後のアカウント候補が発見される
- ✅ CSV と TXT が生成される
- ✅ 各アカウントに `confidence` スコアが付与される
- ✅ 発見結果サマリーが表示される

### 4.3 ランダム検索テスト（実API）

```bash
# ランダムに 10 件発見
python ingest_accounts.py --discover-random --max-results 10
```

**確認項目**:
- ✅ 複数のプリセットクエリが実行される
- ✅ 重複なしで 10 件前後のアカウント候補が発見される
- ✅ 多様なカテゴリ（tech, AI, startup 等）のアカウントが含まれる

### 4.4 発見したアカウントをバッチ処理に流し込み

```bash
# 最新の発見結果を取得
LATEST_CSV=$(ls -t .cache/discover_results/*.csv | head -1)

# バッチ処理で取得（少数でテスト）
python ingest_accounts.py "$LATEST_CSV" --batch-size 3
```

**確認項目**:
- ✅ discover で生成された CSV を読み込める
- ✅ `source` 列が正しく認識される
- ✅ ログに「📊 発見元内訳」が表示される
- ✅ grok_keyword または grok_random がカウントされる

### 4.5 結果の記録

以下の情報を記録してください:

```
□ Dry-run スモークテスト: 成功 / 失敗
□ キーワード検索（実API）: 成功 / 失敗
  - 発見件数: ___ 件
  - 平均信頼度: ___
□ ランダム検索（実API）: 成功 / 失敗
  - 発見件数: ___ 件
□ バッチ処理統合: 成功 / 失敗
  - 発見元内訳の表示: あり / なし
```

---

## 次のステップ

すべてのテストが成功したら:

1. 実際の本番用アカウントリスト（50-100件）を準備
2. CLI で事前キャッシュ生成
3. Streamlit で分析開始
4. 議論生成機能のテスト
5. **Stage 2.5**: アカウント発見機能で新規候補を継続的に追加

**おめでとうございます！実運用準備が整いました！🎉**
