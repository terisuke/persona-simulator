# X API v2セットアップガイド

## 🎯 概要

Persona Debate Simulatorで**実際のX投稿**を取得するには、X API v2のBearer Tokenが必要です。

**注意**: X API v2は**オプション**です。設定しない場合、Grok LLMがサンプル投稿を生成します。

## 📋 X API v2の取得手順

### 1. X Developerアカウントの作成

1. [https://developer.x.com/](https://developer.x.com/) にアクセス
2. Xアカウントでログイン
3. 「Sign up for Free Account」をクリック

### 2. 用途の登録

開発者ポータルで以下を入力：
- **アプリ名**: Persona Debate Simulator
- **用途**: データ分析・研究目的
- **詳細**: Xアカウントの投稿を分析し、ペルソナを生成するツール

### 3. プロジェクトとアプリの作成

1. ダッシュボードで「Create Project」
2. プロジェクト名を入力（例: persona-simulator）
3. 用途を選択（Making a bot / Doing something else）
4. アプリを作成

### 4. Bearer Tokenの取得

1. アプリのダッシュボードで「Keys and tokens」タブをクリック
2. 「Bearer Token」セクションで「Generate」をクリック
3. 表示されたBearer Tokenを**安全に保存**（再表示不可）
   - 形式: `AAAAAAAAAAAAAAAAAxxxxxxxxx...`（長いトークン）

### 5. アクセスレベルの確認

X APIのアクセスレベル：

| プラン       | 月間取得数    | 料金      |
|-----------|---------------|----------|
| **Free**  | 1,500ツイート     | 無料      |
| **Basic** | 10,000ツイート    | $100/月   |
| **Pro**   | 1,000,000ツイート | $5,000/月 |

MVPテストには**Freeプラン**で十分です。

## 🔧 アプリへの設定

### secrets.tomlに追加

`.streamlit/secrets.toml`ファイルを開き、Bearer Tokenを設定：

```toml
# X (Twitter) API v2 (投稿取得用)
X_BEARER_TOKEN = "YOUR_ACTUAL_BEARER_TOKEN_HERE"
```

例：
```toml
X_BEARER_TOKEN = "AAAAAAAAAAAAAAAAAAAAABcdefghijklmnopqrstuvwxyz123456789"
```

### 設定の確認

アプリを起動すると、サイドバーに表示されます：

- ✅ **X API v2接続OK（実投稿取得）** → 設定成功
- ℹ️ **X API未設定（サンプル投稿生成）** → 未設定（Grok LLMで生成）

## 📊 X API使用時の動作

### 実際の投稿を取得

```python
# サイドバーで「cor_terisuke」を入力
# → X APIで実際の@cor_terisukeの投稿を取得
```

表示：
- ✅ **20件の実際の投稿を取得（X API v2）**

### フォールバック動作

X API取得に失敗した場合、自動的にGrok LLMでサンプル投稿を生成：

```
⚠️ X API取得失敗: Rate limit exceeded
📝 サンプル投稿を生成中...
```

## 🔒 セキュリティ

- **Bearer Tokenは秘密情報**です
- `.gitignore`で`secrets.toml`は除外済み
- GitHubにコミット**しないでください**
- 漏洩した場合は即座にRevoke（無効化）

## 🐛 トラブルシューティング

### エラー: "401 Unauthorized"

**原因**: Bearer Tokenが無効

**解決策**:
1. X Developerダッシュボードで新しいTokenを生成
2. `secrets.toml`を更新

### エラー: "429 Too Many Requests"

**原因**: レート制限（Freeプランは月1,500件）

**解決策**:
1. 時間をおいて再試行
2. キャッシュを活用（「キャッシュを使用」チェックをON）
3. 必要に応じてプランをアップグレード

### エラー: "User not found"

**原因**: アカウント名が間違っている

**解決策**:
- `@`なしで入力（例: `cor_terisuke`）
- アカウントが存在するか確認

## 💡 推奨設定

### MVP/テスト段階

- X API v2: **未設定**（Grok LLMで十分）
- コスト: Grok APIのみ
- 制限: なし

### 本格運用

- X API v2: **設定**（実投稿取得）
- コスト: Grok API + X API（Freeプランなら無料）
- メリット: 実際のデータで精度向上

## 📚 参考リンク

- [X API Documentation](https://developer.x.com/en/docs/twitter-api)
- [Authentication Guide](https://developer.x.com/en/docs/authentication/oauth-2-0/bearer-tokens)
- [Rate Limits](https://developer.x.com/en/docs/twitter-api/rate-limits)

## 🎉 完了

X API v2の設定が完了したら、アプリを再起動して動作確認してください！

```bash
streamlit run app.py
```

