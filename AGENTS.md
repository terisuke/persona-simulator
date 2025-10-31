# Repository Guidelines

## Project Structure & Module Organization
`app.py` is the Streamlit entry point that coordinates persona fetching, caching, and the debate UI. Core logic lives under `utils/` (`grok_api.py`, `x_api.py`, `persona.py`, `similarity.py`, `debate_ui.py`, `error_handler.py`, `bootstrap.py`); extend functionality by adding focused modules there. Docs such as `README.md`, `FEATURES.md`, and `X_API_SETUP.md` outline user flows, while `requirements.txt` and `test_setup.py` support environment validation. Temporary runtime data lands in `.cache/`; keep it out of version control.

## Build, Test, and Development Commands
- `pip install -r requirements.txt` installs the Streamlit, Grok, and NLP dependencies.
- `streamlit run app.py` launches the debate simulator locally with hot-reload.
- `python test_setup.py` verifies third-party libraries, local modules, secrets, and cache directories before releasing changes.
- `python ingest_accounts.py <accounts_file>` pre-populates cache for large-scale batch processing (see CLI section below).

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indentation, explicit imports, and descriptive snake_case names (see `utils/persona.py`). Type hints are expected for public functions, and module-level constants use ALL_CAPS (e.g., `MAX_ACCOUNTS`). Prefer structured logging via the shared `logging` configuration, and keep docstrings bilingual when touching existing Japanese documentation.

## Testing Guidelines
Run `python test_setup.py` after dependency upgrades, secret changes, or module additions; it catches missing keys, import regressions, and cache issues. When altering UI or agent flows, pair the script with a manual pass of `streamlit run app.py` to validate multi-account debates and cache refresh logic. Add lightweight assertions to new helper modules so they can be imported inside `test_setup.py`.

## Commit & Pull Request Guidelines
Commit history follows Conventional Commits (`feat:`, `fix:`) with concise Japanese summaries (e.g., `feat: v2.0 - チャット風UI`). Keep the scope focused to a single feature or bugfix. Pull requests should include: 1) a narrative of user-visible changes, 2) test evidence or manual validation steps, and 3) linked issues or screenshots for UI updates.

## Secrets & Configuration
Store API credentials in `.streamlit/secrets.toml` using the keys referenced in `README.md`; never commit real tokens. If you add new providers, document them in `X_API_SETUP.md` and gate access via `st.secrets`. Maintain the `.cache/` directory structure so cached persona data and embeddings remain reusable across sessions.

## Stage 1: CLI for Batch Account Ingestion

- 目的は大規模アカウントの事前キャッシュ化とレートリミット対策です。
- コマンド例やレート制御の詳細は `README.md` の「クイックスタート」と「CLI を使った事前キャッシュ生成」を参照してください。
- テストや運用チェックは `run_test.sh` と `TEST_PROCEDURE.md` を使って自動化できます（レート待機・`fetched_at` の検証を含む）。
- 429 応答が続く場合は CLI 内の RateLimitManager を優先的に改善し、UI 側に不要なフォールバックを発生させないようにします。

## Stage 2: Streamlit UI 一括管理と進捗可視化

- 目標はキャッシュ済み＋未取得アカウントの混在でもリアルタイムで状況を把握できる管理 UI を提供することです。
- サイドバーの一括アップロード、バッチ処理トリガー、エラー一覧などのUI仕様は `README.md` の「一括管理モード」と `TEST_PROCEDURE.md` に記載しています。
- バッチ処理後は `st.session_state['account_status']` を必ず更新し、進捗メトリクスとエラー一覧（サイドバー下部）が一致するようにしてください。
- CLI のキャッシュを尊重するため、初回ロード時は `.cache/posts_{account}.pkl` を必ず参照し、不要な API コールを避ける実装を維持します。
- UI 上での X API リトライは最大待機時間を 0 秒に設定し（`UI_MAX_RATE_WAIT_SECONDS`）、レート制限に達した際は速やかに警告表示へ切り替えます。実データ取得は Stage1 のバッチに委ねる運用を徹底してください。

両ステージとも、機能追加時は `AGENTS.md` → `README.md` → `TEST_PROCEDURE.md` の順にドキュメントを更新し、`run_test.sh` で統合確認する運用を徹底してください。

### ペルソナ状態遷移とデータソース管理

**ペルソナ状態**:
- `unverified`（未確定）: データ不足または解析失敗によりペルソナ生成に失敗
  - 議論参加不可
  - UI で「データ不足」表示、CLI実行を促すCTA表示
  - CLI での再取得により `verified` へ移行可能
- `verified`（確定済み）: 正常にペルソナ生成が完了
  - 議論参加可能
  - `quality_score` が付与されている場合、品質評価も完了

**データソース**:
- `twitter`: X API v2 経由で取得（実データ）
- `web_search`: Grok Web Search 経由で取得（実データ）
- `generated`: フォールバック生成（運用モードでは禁止）
- `unknown`: 不明（キャッシュからの読み込み時など）

**X API オプトアウト時のワークフロー**:
- UI側で「X APIを使用する」トグルをOFF、またはCLIで`--no-x-api`指定時
  - X APIクライアントは`None`として扱われ、X API経由の取得はスキップされる
  - Grok Web Searchのみで投稿を取得（実データ）
  - `quality_score`は信頼度ベースの暫定評価となり、`quality_reasons`に「X API metrics unavailable – fallback evaluation」が追加される
  - UIのKPIカードで「X APIが無効化されているため、quality_scoreは暫定値です」という警告が表示される
  - CLIログには「X API使用: False」が記録され、サマリにも反映される
  - レート制限を気にせずに大量候補を収集したい場合に有効（「100人の村」構築フェーズ）

**品質スコア（quality_score）**:
- 実世界指標ベース（0.0-1.0）
- 計算式: `0.5 * followers_norm + 0.3 * recency_norm + 0.2 * postcount_norm`
- 0.6未満は品質基準未満として除外推奨
- X API メトリクスが取得できない場合は信頼度ベースの暫定評価
- X API無効時（トグルOFFまたは`--no-x-api`）は常に暫定評価となり、`quality_reasons`に明確な理由が記録される

### Open TODO（将来対応）

- UI サイドバーに TextBlob センチメントによるフィルタを追加
