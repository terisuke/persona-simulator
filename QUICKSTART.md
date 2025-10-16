# Persona Debate Simulator - クイックスタートガイド

このガイドでは、Persona Debate Simulatorを最短で起動する手順を説明します。

## 📋 前提条件

- Python 3.10以上
- Grok APIキー（[https://x.ai/api](https://x.ai/api) から取得）

## 🚀 セットアップ手順（5分）

### 1. 依存関係のインストール

```bash
# プロジェクトディレクトリに移動
cd /Users/teradakousuke/Developer/persona-simulator

# 必要なライブラリをインストール
pip install -r requirements.txt
```

### 2. APIキーの設定

```bash
# .streamlitディレクトリが存在しない場合は作成
mkdir -p .streamlit

# secrets.tomlファイルを作成
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

次に、`.streamlit/secrets.toml`をテキストエディタで開き、Grok APIキーを設定します：

```toml
# .streamlit/secrets.toml
GROK_API_KEY = "xai-YOUR_ACTUAL_API_KEY_HERE"
```

**重要**: `your_grok_api_key_here`を実際のAPIキーに置き換えてください。

### 3. セットアップの確認

```bash
python test_setup.py
```

すべてのテストが✅になればOKです！

### 4. アプリケーションの起動

```bash
streamlit run app.py
```

ブラウザが自動的に開き、`http://localhost:8501`でアプリが表示されます。

## 💡 使い方

### 基本的な使い方

1. **サイドバー**でXアカウントを入力（例: `cor_terisuke`）
2. **議論トピック**を入力（例: "AIの倫理的課題について"）
3. **「議論を生成」**ボタンをクリック
4. ペルソナの意見と引用された投稿を確認

### 複数アカウントの分析

1. サイドバーの「分析するアカウント数」を変更（最大10）
2. 各アカウント名を入力
3. トピックを入力して生成

## 📊 主な機能

### タブ1: 議論シミュレーション
- トピックに対する各ペルソナの意見を生成
- 口調模倣スコアを表示
- 関連する過去投稿を引用

### タブ2: ペルソナ分析
- 各アカウントのペルソナプロファイルを表示
- 統計情報（投稿長、センチメント、口調マーカー）

### タブ3: 投稿データ
- 取得した投稿の一覧表示
- JSONデータのダウンロード

## 🔧 トラブルシューティング

### エラー: "Grok APIキーが設定されていません"

→ `.streamlit/secrets.toml`ファイルが正しく作成されているか確認してください。

### エラー: "投稿が取得できませんでした"

原因：
- APIキーが無効
- アカウント名が間違っている
- ネットワーク接続の問題

対処法：
1. APIキーを再確認
2. アカウント名を`@`なしで入力（例: `cor_terisuke`）
3. キャッシュをクリアして再試行

### モデルのダウンロードに時間がかかる

初回起動時は、sentence-transformersモデル（約400MB）がダウンロードされます。
これは一度だけで、次回からは高速です。

## 🎯 おすすめトピック例

- "AIの倫理的課題について"
- "リモートワークの未来"
- "起業家に必要なスキル"
- "音楽とテクノロジーの融合"
- "データサイエンスの実務で重要なこと"

## 📚 詳細情報

- README.md - プロジェクト全体の説明
- 要件定義 - 機能仕様の詳細

## 🐛 バグ報告

問題が発生した場合は、以下の情報を含めて報告してください：

- エラーメッセージ
- 実行コマンド
- Python バージョン（`python --version`）
- OS情報

## 🎉 完了

セットアップが完了しました！素晴らしい議論シミュレーションをお楽しみください！

