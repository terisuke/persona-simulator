# 実運用準備確認手順

## 概要

Stage1 CLI と Stage2 Streamlit UI が実運用に耐えられるかを確認するための手順書です。

## 前提条件

- `.streamlit/secrets.toml` に `GROK_API_KEY` と `X_BEARER_TOKEN` が設定済み
- 依存関係インストール済み: `pip install -r requirements.txt`

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
```

**確認項目**:
- ✅ レートリミット残数が記録されているか
- ✅ レートリミット接近時の待機ログがあるか（条件次第）
- ✅ エラーがないか

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

#### 1.6 結果の記録

以下の情報を記録してください:

```
□ 処理したアカウント数: ___ / 6
□ 成功: ___ 件
□ 失敗: ___ 件
□ 処理時間: ___ 秒
□ レートリミット待機: あり / なし
□ fetched_at 記録: あり / なし
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

#### 2.6 処理結果を確認

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
4. ✅ Streamlit でキャッシュ混在状態を正しく認識する
5. ✅ バッチ処理で未取得分のみを取得する
6. ✅ ステータス表示が正確（成功・失敗・キャッシュ）
7. ✅ エラーハンドリングが適切
8. ✅ API 呼び出しが最適化されている（キャッシュ使用時は0回）

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

## 次のステップ

すべてのテストが成功したら:

1. 実際の本番用アカウントリスト（50-100件）を準備
2. CLI で事前キャッシュ生成
3. Streamlit で分析開始
4. 議論生成機能のテスト

**おめでとうございます！実運用準備が整いました！🎉**
