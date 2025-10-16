# Grokモデル更新ガイド

## 🔄 更新内容（2025年10月16日）

### 問題
- 古いモデル `grok-beta` が廃止（2025年9月15日）
- エラー: "The model grok-beta was deprecated"

### 解決策
最新モデル **`grok-4-fast-reasoning`** に更新

## ✅ 変更詳細

### 1. デフォルトモデルの更新

**utils/grok_api.py**:
```python
# 変更前
"model": "grok-beta"  # 廃止済み

# 変更後
"model": "grok-4-fast-reasoning"  # 最新・推奨
```

### 2. 柔軟なモデル設定

**GrokAPIクラス**:
```python
class GrokAPI:
    # 利用可能なGrokモデル（2025年10月時点）
    # - grok-4-fast-reasoning: 最新・高速推論モデル（推奨）
    # - grok-3: 標準モデル
    # - grok-beta: 廃止済み（2025年9月15日）
    DEFAULT_MODEL = "grok-4-fast-reasoning"
    
    def __init__(self, api_key: str, model: str = None):
        self.model = model or self.DEFAULT_MODEL
```

### 3. secrets.tomlでのカスタマイズ（オプション）

**`.streamlit/secrets.toml`** に追加可能:
```toml
# Grok Model (オプション)
# GROK_MODEL = "grok-4-fast-reasoning"
```

## 📊 利用可能なモデル

| モデル名                     | ステータス      | 特徴          | コンテキスト        |
|---------------------------|------------|-------------|---------------|
| **grok-4-fast-reasoning** | ✅ 推奨     | 最新・高速推論 | 2,000,000トークン |
| grok-3                    | ✅ 利用可能 | 標準モデル       | -             |
| grok-beta                 | ❌ 廃止     | 2025/9/15廃止 | -             |

## 🚀 再起動手順

1. **Streamlitを停止** (Ctrl+C)

2. **キャッシュをクリア**:
```bash
rm -rf .cache/
```

3. **再起動**:
```bash
streamlit run app.py
```

4. **確認**:
   - サイドバーに "✅ Grok API接続OK" 表示
   - ログに "使用モデル: grok-4-fast-reasoning"

## 🎯 期待される動作

### ✅ 正常動作

```
2025-10-16 09:45:00 - INFO - Grok API初期化完了: モデル=grok-4-fast-reasoning
2025-10-16 09:45:05 - INFO - LLM生成を開始
2025-10-16 09:45:08 - INFO - LLM生成完了
```

### ❌ エラー（古いモデル）

```
LLM生成エラー: 404 - {"error":"The model grok-beta was deprecated..."}
```

## 💡 モデル選択のガイド

### grok-4-fast-reasoning（推奨）
- ✅ **最新・最速**
- ✅ 高度な推論機能
- ✅ 関数呼び出しサポート
- ✅ 構造化出力
- ✅ 2,000,000トークンコンテキスト

**用途**: 
- ペルソナ生成
- 議論シミュレーション
- 複雑な分析

### grok-3（標準）
- ✅ 安定性重視
- ⚠️ grok-4より低速

**用途**:
- 標準的なテキスト生成

## 🔧 カスタマイズ例

### secrets.tomlで変更

```toml
# grok-3を使用
GROK_MODEL = "grok-3"
```

### コードで変更

```python
# 特定モデルを明示的に指定
grok = GrokAPI(api_key, model="grok-3")
```

## 📚 参考リンク

- [Grok Models Documentation](https://docs.x.ai/docs/models/grok-4-fast-reasoning)
- [Grok API Overview](https://docs.x.ai/docs/overview)
- [xAI Platform](https://x.ai/api)

## ✅ チェックリスト

- [x] モデル名を `grok-4-fast-reasoning` に更新
- [x] GrokAPIクラスに柔軟性追加
- [x] secrets.tomlテンプレート更新
- [x] ログ出力追加
- [x] リントエラー解消
- [x] ドキュメント更新

## 🎉 完了

最新のGrokモデルに更新完了！アプリを再起動して、高速で正確な議論シミュレーションをお楽しみください！

---

**更新日**: 2025年10月16日  
**適用バージョン**: MVP 1.1  
**ステータス**: ✅ 完了

