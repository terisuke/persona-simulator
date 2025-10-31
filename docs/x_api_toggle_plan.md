# X API オプトアウト機能 追加設計書

## 背景
- 現在の UI／CLI は `X_BEARER_TOKEN` が設定されている場合に自動で X API を使用する。
- レートリミット（15 req/15min）に達した際、CLI は 15 分待機、UI は即時フォールバックするため、連続運用が阻害される。
- Grok Web Search のみで大量候補を洗い出したい利用シナリオ（大量ペルソナ発見フェーズ）では、X API を一時的に無効化できた方が「100人の村」構築の目的に合致する。

## 目的
1. **UI（Streamlit）から X API 利用の ON/OFF を選択可能にする。**
2. **CLI も同じ制御ができるようフラグを追加し、UI と挙動を統一する。**
3. **X API を無効化した場合でも、品質評価や KPI 表示が破綻しないよう暫定ロジックを整備する。**

## 仕様概要

### 1. UI 側のトグル
- サイドバー「⚡ バッチ処理」の上部（収集セクションと同じ列）に `st.toggle("X API を使用する", value=True)` を追加。
- `MODE` が `prod/staging` の場合でも、ユーザー操作で OFF にできる。ただし OFF 時は quality_score が暫定値になることを警告。
- `fetch_and_analyze_posts()` 呼び出し時に `use_x_api` フラグを渡し、`load_x_api()` の代わりにトグル判定で None を返す。

### 2. CLI フラグ
- `ingest_accounts.py` に `--use-x-api / --no-x-api` の相互排他オプションを追加。
  - 未指定の場合は従来どおり secrets/env の `X_BEARER_TOKEN` 判定で自動決定。
  - `--no-x-api` 指定時は `load_x_api_from_env()` をスキップし、全処理で `x_api=None` を渡す。
- CLI ログに `X API 使用: True/False` を明記する。

### 3. 共通関数の調整
- `load_x_api()` / `load_x_api_from_env()` を `use_x_api` フラグ付きで呼び出せるようシグネチャを統一。
- `grok_api.fetch_posts()` / `check_account_quality()` では `x_api_client` が `None` の場合にメトリクス未取得の警告を出しつつ、信頼度ベースの暫定評価（既存ロジック）を実行。
- `quality_score` が暫定値の場合は `quality_reasons` に `"X API metrics unavailable – fallback evaluation"` を追加。

### 4. KPI と UI 表示
- サイドバー KPI カードで「X API 無効時は quality_score は暫定値」という注記を表示。
- CLI サマリにも `X API 使用: False` と `quality_score (fallback)` の件数を追加。

### 5. ドキュメント更新
- README: 「スマート投稿取得」「運用モード設定」「品質KPI」セクションにトグルの使い方を追記。
- AGENTS.md: ペルソナ状態／データソース説明に X API オプトアウト時のワークフローを追加。
- TEST_PROCEDURE.md: UI で X API を OFF にした際の収集／バッチ実行テスト、CLI の `--no-x-api` テストを追加。

## 実装ステップ
1. `app.py`
   - サイドバーに `st.checkbox/toggle` を配置 (`st.session_state['use_x_api']` として保持)。
   - `load_x_api()` 呼び出しを `use_x_api` で条件分岐。
   - `fetch_and_analyze_posts()`、収集コマンド (`subprocess.run`) へ `--no-x-api` フラグを付与。

2. `ingest_accounts.py`
   - 引数パーサーに `--use-x-api / --no-x-api` を追加。
   - `load_x_api_from_env()` で `use_x_api` 判定を反映。
   - ログと結果サマリに `X API 使用: {True/False}` を出力。

3. `utils/grok_api.py` / `utils/x_api.py`
   - 既存シグネチャ変更部分を `Optional[XAPIClient]` 前提で動作するよう確認。
   - `check_account_quality()` のフォールバック理由に追記。

4. テスト
   - `./discover_test.sh --dry-run` で UI/CLI どちらも `--no-x-api` 状態でも候補が取得できることを確認。
   - `./run_test.sh --no-x-api` を追加し、構造化ログが Web Search のみで出力されることを検証。

## リスクとフォローアップ
- Grok Web Search は投稿数が少ない場合があるため、X API を OFF にすると実データが乏しくなる可能性がある。KPI で real_data_ratio が下がった場合の警告を維持する。
- 今後 Stage3 の多SNS連携を導入する際は、本トグルと同じパターン（APIごとの ON/OFF）で実装できるよう、共通インターフェースを意識しておく。

以上を実装すれば、レート制限を気にせずに大量の候補を Grok Web Search で収集し、100人規模のペルソナ分析に必要なデータを素早く集められるようになります。
