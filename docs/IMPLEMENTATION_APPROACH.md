# Persona Debate Simulator - 実装アプローチ完全ドキュメント

## 📋 目次

1. [プロジェクトの目的とビジョン](#1-プロジェクトの目的とビジョン)
2. [全体アーキテクチャ](#2-全体アーキテクチャ)
3. [ステップ1: 実データ優先の取得パイプライン](#3-ステップ1-実データ優先の取得パイプライン)
4. [ステップ2: 多様性を担保したアカウント発見](#4-ステップ2-多様性を担保したアカウント発見)
5. [ステップ3: ペルソナ生成と日本語出力の強制](#5-ステップ3-ペルソナ生成と日本語出力の強制)
6. [ステップ4: 品質管理とキャッシュハイジーン](#6-ステップ4-品質管理とキャッシュハイジーン)
7. [ステップ5: ターン制議論システム](#7-ステップ5-ターン制議論システム)
8. [ステップ6: マーケティング活用のための多様性指標](#8-ステップ6-マーケティング活用のための多様性指標)

---

## 1. プロジェクトの目的とビジョン

### 1.1 目的

「100人の村」のように多様な意見を集約し、マーケティングに活用する。実在アカウントの投稿からペルソナを生成し、最大100人での議論をシミュレートする。

### 1.2 設計原則

1. **実データのみ使用**: 生成フォールバックは無効化（`allow_generated`パラメータは後方互換性のために残存するが無視される）、実データ取得失敗時はアカウントを除外
2. **多様性の担保**: 層化/クォータ/ランダムサンプリングで多様な意見を確保
3. **日本語出力の統一**: 議論を日本語で統一
4. **品質管理**: フォロワー数・最新投稿日・投稿総数から品質スコアを算出
5. **スケーラビリティ**: 最大100アカウントまで対応

---

## 2. 全体アーキテクチャ

### 2.1 システム構成

```text
┌─────────────────────────────────────────────────────────┐
│  Persona Debate Simulator                               │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ データ取得層  │  │ 多様性サンプリング│  │ ペルソナ生成層 │  │
│  │              │  │              │  │              │  │
│  │ X API v2     │  │ DiversitySampler│  │ Grok LLM    │  │
│  │ Grok Web     │  │ (ハイブリッド)  │  │ (日本語強制)  │  │
│  │ Search       │  │              │  │              │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│         │                  │                  │          │
│         └──────────────────┼──────────────────┘          │
│                            │                             │
│  ┌──────────────────────────────────────────────────┐   │
│  │  3層キャッシュシステム                             │   │
│  │  - all_data (最上位)                               │   │
│  │  - セッション状態 (アカウント単位)                  │   │
│  │  - ファイルキャッシュ (.cache/)                     │   │
│  └──────────────────────────────────────────────────┘   │
│                            │                             │
│  ┌──────────────────────────────────────────────────┐   │
│  │  議論生成層                                        │   │
│  │  - ターン制議論                                     │   │
│  │  - チャット風UI                                     │   │
│  │  - 会話履歴保持                                     │   │
│  └──────────────────────────────────────────────────┘   │
│                            │                             │
│  ┌──────────────────────────────────────────────────┐   │
│  │  マーケティング分析層                              │   │
│  │  - 多様性指標（エントロピー）                      │   │
│  │  - 地域・言語・センチメント分布                     │   │
│  │  - 品質スコア集計                                  │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 3. ステップ1: 実データ優先の取得パイプライン

### 3.1 設計思想

マーケティングで使うため、実データのみを使用。生成データは混入させない。

### 3.2 4段階取得戦略（リトライ対応）

```python
# utils/grok_api.py:122-287
def fetch_posts(...) -> List[Dict]:
    """
    取得優先順位（各手段で最大1回リトライ）:
    1. X API v2 (fetch_user_tweets) - リトライ1回
    2. X API v2 (search_recent_tweets) - リトライ1回
    3. Grok Realtime Web Search - リトライ1回
    4. すべて失敗した場合は空リストを返す（アカウント除外）
    """
```

#### 実装の詳細

1. **方法1: X API (fetch_user_tweets)**
   - ユーザーIDベースで取得
   - 失敗時はリトライ1回（一時的エラーのみ）
   - 成功時は即座に返却

2. **方法2: X API (search_recent_tweets)**
   - `from:username`クエリで検索
   - 方法1が失敗した場合のみ実行
   - リトライ1回

3. **方法3: Grok Realtime Web Search**
   - 実投稿をWeb検索
   - X APIが利用不可または失敗時
   - リトライ1回

4. **すべて失敗した場合**
   - 空リストを返す
   - 構造化ログに`reason="all_real_data_sources_failed"`を記録
   - アカウントは`unverified`となり議論から除外

### 3.3 リトライロジック

```python
def _should_retry_error(error: Exception) -> bool:
    """一時的なエラーのみリトライ"""
    status_code = getattr(error, "status_code", None)
    if status_code in {401, 403, 404, 429}:  # 永続的エラー
        return False
    
    # 一時的エラー（timeout, connection, 503, 500等）のみリトライ
    retriable_keywords = ["timeout", "connection", "503", "500", ...]
    return any(keyword in str(error).lower() for keyword in retriable_keywords)
```

### 3.4 生成フォールバックの無効化

- **以前**: 運用モードでのみ生成フォールバックを禁止
- **現在**: モードに関係なく生成フォールバックを無効化
- **実装**: `allow_generated`パラメータは後方互換性のために残存するが、常に無視され、実データのみを使用
- **警告**: `allow_generated=True`が指定されても警告を表示し、実データのみを使用

---

## 4. ステップ2: 多様性を担保したアカウント発見

### 4.1 設計思想

「100人の村」の多様性を確保するため、ハイブリッドサンプリングで偏りを抑制。

### 4.2 ハイブリッドサンプリングアーキテクチャ

```python
# utils/diversity_sampling.py:19-162
class DiversitySampler:
    """
    X API + Grok Web Search のハイブリッドでアカウントを発見し、
    多様性を担保する
    """
```

#### データソースのハイブリッド（2段階アプローチ）

このシステムは「ハイブリッド」という用語を**データソースの組み合わせ**として使用しています：

1. **第1段階: データソースのハイブリッド**
   - **X API経由の検索**: ツイート検索でメンション抽出、ユーザー情報取得（フォロワー数、ツイート数等）、レート制限を考慮
   - **Grok Web Search経由の検索**: X APIが利用不可または結果不足時、重複除去して統合
   - 両方のソースから候補を収集し、統合

2. **第2段階: サンプリング手法の適用**
   - 統合された候補に対して、ユーザーが選択したサンプリング手法を適用
   - 確率サンプリング（層化サンプリング、ランダムサンプリング）または非確率サンプリング（クォータサンプリング）のいずれかを選択
   - **注意**: 複数のサンプリング手法を同時に組み合わせることはない（if-elif-else構造）

#### 重要: サンプリング手法の適用条件

**多様性サンプリングモード（`--diversity-sampling`）の場合**:

- ✅ **X API経由の候補も、Grok API経由の候補も**、統合後にサンプリング手法が適用される
- ✅ `discover_accounts_hybrid()` 内で、両方のソースから収集した候補を統合し、その後サンプリング手法を適用

**キーワード/プリセット/ランダムモードの場合**:

- ❌ **Grok API経由で収集した候補にはサンプリング手法が適用されない**
- ❌ `discover_accounts_by_keyword()` や `discover_accounts_random()` は直接呼ばれ、品質フィルタリングのみ行う
- ❌ 単なるWeb検索結果をそのまま返す（サンプリングなし）

**結論**: 確率/非確率サンプリングを適用するには、**必ず多様性サンプリングモード（`--diversity-sampling`）を使用する必要があります**。

#### サンプリング処理の実装方法

**重要**: サンプリング処理は**アルゴリズム（Python標準ライブラリ）で実装**されており、**Grok APIは使用していません**。

- ✅ **層化サンプリング**: `random.sample()` （Python標準ライブラリ）を使用
- ✅ **クォータサンプリング**: `random.shuffle()` とリスト処理（Python標準ライブラリ）を使用
- ✅ **ランダムサンプリング**: `random.sample()` （Python標準ライブラリ）を使用

Grok APIは**候補収集**にのみ使用され、サンプリング処理自体には関与しません。

#### サンプリング処理の具体的な実装箇所

サンプリング処理は以下の流れで実行されます：

1. **エントリーポイント**: `ingest_accounts.py:349`

   ```python
   accounts = grok_api.discover_accounts_with_diversity_hybrid(...)
   ```

2. **Grok APIラッパー**: `utils/grok_api.py:1177-1183`

   ```python
   accounts = sampler.discover_accounts_hybrid(
       queries=queries[:20],
       max_results=max_results,
       sampling_method=sampling_method
   )
   ```

3. **サンプリング処理の実行**: `utils/diversity_sampling.py:155-172`

   ```python
   # 候補収集・統合（139行目）
   all_candidates.extend(account_batch)  # X API + Grok Web Search
   
   # 属性付与（150-153行目）
   enriched_candidates = self.enrich_account_attributes(...)
   
   # サンプリング手法の適用（155-172行目）
   if sampling_method == "stratified":
       sampled = self.stratified_sampling(...)  # 155-160行目
   elif sampling_method == "quota":
       sampled = self.quota_sampling(...)  # 161-167行目
   else:
       sampled = random.sample(...)  # 168-172行目
   ```

4. **層化サンプリングの実装**: `utils/diversity_sampling.py:300-349`
   - 層化処理: 325-336行目（属性の組み合わせで層を作成）
   - サンプリング: 341-344行目（各層から `random.sample()` で選択）

5. **クォータサンプリングの実装**: `utils/diversity_sampling.py:351-414`
   - シャッフル: 373-374行目（`random.shuffle()`）
   - クォータチェック: 375-405行目（クォータを満たすものを順次選択）

### 4.3 多様性指標の計算

#### 属性の付与

```python
def enrich_account_attributes(accounts, x_api_client):
    """
    アカウントに以下を付与:
    - followers_count: フォロワー数（階層化）
    - region: 地域（JP, US, GB, KR等）
    - language: 言語（ja, en, ko, zh等）
    - dominant_sentiment: センチメント（positive, neutral, negative）
    """
```

#### エントロピー指標

```python
def calculate_diversity_metrics(accounts, attributes):
    """
    正規化エントロピーを計算:
    - followers_entropy: フォロワー階層の多様性
    - region_entropy: 地域の多様性
    - language_entropy: 言語の多様性
    - sentiment_entropy: センチメントの多様性
    - overall_diversity: 全体の多様性スコア（0.0-1.0）
    """
```

### 4.4 サンプリング手法

このシステムは、**確率サンプリング**と**非確率サンプリング**の両方をサポートしています。ただし、ユーザーが選択した1つの手法のみを適用します（複数の手法を同時に組み合わせることはありません）。

#### 確率サンプリング（Probability Sampling）

選択確率が明確に定義されている手法：

##### 1. 層化サンプリング（Stratified Sampling）

```python
# utils/diversity_sampling.py:275-311
def stratified_sampling(accounts, num_samples, strata_attributes):
    """
    複数属性（followers, region, language, sentiment）で層化し、
    各層から比例的にランダムサンプリング（random.sample使用）
    """
```

- **分類**: 確率サンプリング
- **実装**: `random.sample()`を使用して各層からランダムに選択
- **特徴**: 各層の比率を維持し、属性の組み合わせで層化
- **選択確率**: 各層内では均一な確率で選択

##### 3. ランダムサンプリング（Random Sampling）

```python
# utils/diversity_sampling.py:144-147
sampled = random.sample(enriched_candidates, min(max_results, len(enriched_candidates)))
```

- **分類**: 確率サンプリング
- **実装**: `random.sample()`を使用
- **特徴**: 単純ランダムサンプリング
- **選択確率**: 全候補から均一な確率で選択

#### 非確率サンプリング（Non-Probability Sampling）

選択確率が定義されていない手法：

##### 2. クォータサンプリング（Quota Sampling）

```python
# utils/diversity_sampling.py:313-361
def quota_sampling(accounts, quotas, max_total):
    """
    指定されたクォータに従ってサンプリング（便利サンプリングに近い）
    - followers: micro, small, medium, large, macro, mega
    - region: JP, US, GB, KR等
    - sentiment: positive, neutral, negative
    """
```

- **分類**: 非確率サンプリング（便利サンプリングに近い）
- **実装**: シャッフル済みリストを順次処理し、クォータを満たすものを選択
- **特徴**: マーケティング要件に合わせたクォータ設定が可能
- **選択確率**: クォータを満たすかどうかで判断（確率は定義されない）

### 4.5 CLI統合

#### 多様性サンプリングモード（推奨）

```bash
# ingest_accounts.py:865-901
python ingest_accounts.py \
    --diversity-sampling \
    --max-results 50 \
    --sampling-method stratified \
    --prefer-x-api \
    --fallback-to-grok
```

- ✅ **X API経由の候補も、Grok API経由の候補も**、統合後にサンプリング手法が適用される
- ✅ 多様性レポート生成（CSV/テキスト）
- ✅ 多様性スコア、地域・言語・センチメント分布を記録

#### キーワード/プリセット/ランダムモード（非推奨: サンプリングなし）

```bash
# キーワードモード
python ingest_accounts.py --discover-keyword "AI engineer" --max-results 50

# プリセットモード
python ingest_accounts.py --preset tech_ai --max-results 50

# ランダムモード
python ingest_accounts.py --discover-random --max-results 50
```

- ❌ **Grok API経由で収集した候補にはサンプリング手法が適用されない**
- ❌ 単なるWeb検索結果をそのまま返す（多様性を担保しない）
- ⚠️ 品質フィルタリングは行われるが、多様性を担保するサンプリングは行われない

---

## 5. ステップ3: ペルソナ生成と日本語出力の強制

### 5.1 設計思想

議論を日本語で統一し、マーケティング分析を容易にする。

### 5.2 ペルソナ生成プロンプト

```python
# utils/grok_api.py:510-534
prompt = f"""以下の情報からペルソナプロファイルを生成してください。

【X投稿】
{posts_text}

必ず守るルール：
- 出力はすべて自然な日本語で記述する（原文が英語でも日本語に翻訳する）
- JSON内の値も日本語で表現する
"""
```

- 背景・傾向・口調・性格を日本語で抽出
- マルチプラットフォーム情報を統合

### 5.3 意見生成プロンプト

```python
# utils/grok_api.py:595-619
prompt = f"""あなたは以下のペルソナとして振る舞ってください：

【ペルソナ情報】
- 名前: {persona.get('name')}
- 口調: {persona.get('tone')}
- 性格: {persona.get('personality')}

【議論トピック】
{topic}

このトピックについて、ペルソナの口調と性格を**徹底的に模倣**して意見を述べてください。

- すべて自然な日本語で回答し、英語表現が含まれる場合は日本語に言い換える
- 口調の特徴（カジュアル、感嘆符、絵文字、「w」「だなぁ」など）を必ず含める
"""
```

- 口調・性格を反映
- 日本語出力を強制

### 5.4 反論生成プロンプト

同様に日本語出力を強制し、ペルソナの口調を維持。

---

## 6. ステップ4: 品質管理とキャッシュハイジーン

### 6.1 キャッシュサニタイザー

生成データが混入しないよう、キャッシュ読み込み時に検出・削除。

```python
# app.py:351-356
def has_generated_posts(posts: List[Dict]) -> bool:
    """生成データ（sample_/generated_）かどうかを判定"""
    if not posts:
        return False
    first_id = posts[0].get('id', '')
    return first_id.startswith('sample_') or first_id.startswith('generated_')
```

#### 適用箇所

1. セッションキャッシュ読み込み時（390-395行目）
2. ファイルキャッシュ読み込み時（415-420行目）
3. 新規取得完了時（457-464行目）
4. バッチ集約時（1312-1319行目）

### 6.2 品質スコアリング

```python
# utils/grok_api.py:1203-1348
def check_account_quality(account, account_info, thresholds, x_api_client):
    """
    品質スコア計算:
    quality_score = 0.5 * followers_norm + 0.3 * recency_norm + 0.2 * postcount_norm
    """
```

- 0.6未満は品質基準未満として除外推奨
- X API無効時は暫定評価

---

## 7. ステップ5: ターン制議論システム

### 7.1 チャット風UI

```python
# utils/debate_ui.py:36-148
class DebateUI:
    AVATARS = ["🧑", "👨", "👩", ...]  # 10種類
    MESSAGE_COLORS = {
        "initial": "#e3f2fd",    # 水色
        "reply": "#f3e5f5",      # 紫
        "rebuttal": "#fff3e0"    # オレンジ
    }
```

- 吹き出し形式で表示
- ラウンド別表示

### 7.2 ターン制議論フロー

1. **ラウンド0**: 全員が初回意見
2. **ラウンド1以降**: 反論・応答
   - 選択的反論: 特定の人が特定の人に反論
   - 全員反論: 全員が順番に反論

### 7.3 会話履歴保持

- 前のラウンドを参照して反論を生成
- 文脈を維持

---

## 8. ステップ6: マーケティング活用のための多様性指標

### 8.1 多様性レポート

```bash
# ingest_accounts.py:440-465
=== ハイブリッド多様性サンプリングレポート ===

多様性指標:
- followers_entropy: 0.85
- region_entropy: 0.72
- language_entropy: 0.68
- sentiment_entropy: 0.79
- overall_diversity: 0.76

地域分布:
- JP: 25件
- US: 15件
- GB: 5件
- KR: 5件

言語分布:
- ja: 30件
- en: 15件
- ko: 5件
```

### 8.2 CSV出力

- `diversity_score`: 多様性スコア
- `region`: 地域
- `language`: 言語
- `dominant_sentiment`: センチメント
- `followers_count`: フォロワー数
- `quality_score`: 品質スコア

### 8.3 マーケティング活用例（現在のMVP機能）

1. **セグメント分析**: 地域・言語・センチメントでセグメント化
2. **インフルエンサーマーケティング**: フォロワー階層別の意見分布
3. **トレンド分析**: 多様性指標の推移
4. **A/Bテスト**: クォータサンプリングでテストグループ作成

### 8.4 将来の拡張機能（検討中）

- 自動レポート生成
- セグメント別のクラスタリング
- 長期トレンド分析
- 予測モデルの構築

---

## まとめ: 「100人の村」を支える実装アプローチ

### 実装の特徴

1. **実データのみ**: 生成フォールバックを無効化、実データ取得失敗時は除外
2. **多様性の担保**: ハイブリッドサンプリングで多様な意見を確保
3. **日本語統一**: 議論を日本語で統一
4. **品質管理**: 品質スコアとキャッシュサニタイザーで品質を担保
5. **スケーラビリティ**: 最大100アカウントまで対応
6. **マーケティング活用**: 多様性指標とレポートで分析可能（MVP段階）

### 技術スタック

- **フロントエンド**: Streamlit
- **LLM**: Grok API (grok-4-fast-reasoning)
- **データ取得**: X API v2 + Grok Realtime Web Search
- **多様性サンプリング**: 層化/クォータ/ランダムサンプリング
- **品質管理**: quality_score (0.0-1.0)
- **キャッシュ**: 3層キャッシュシステム（all_data + セッション + ファイル）

この実装により、「100人の村」のような多様な意見を集約し、マーケティングに活用できるシステムを実現しています。
