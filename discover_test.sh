#!/bin/bash
# Stage 2.5: アカウント発見機能のスモークテスト

set -e  # エラーで停止

echo "=================================================="
echo "Stage 2.5: アカウント発見機能 スモークテスト"
echo "=================================================="
echo ""

# 色の定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 関数定義
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# ステップ1: Dry-run キーワード検索テスト
echo "🎭 テスト1: Dry-run キーワード検索（モックデータ）"
echo "--------------------------------------------------"

print_info "キーワード 'AI engineer' で 5 件のモックアカウントを生成..."
python ingest_accounts.py \
    --discover-keyword "AI engineer" \
    --max-results 5 \
    --dry-run \
    --log-level INFO

KEYWORD_EXIT_CODE=$?
if [ $KEYWORD_EXIT_CODE -eq 0 ]; then
    print_success "キーワード検索（dry-run）が成功しました"
else
    print_error "キーワード検索（dry-run）が失敗しました (終了コード: $KEYWORD_EXIT_CODE)"
    exit 1
fi

# 生成されたファイルを確認
KEYWORD_FILES=$(ls -t .cache/discover_results/keyword_AI_engineer_*.csv 2>/dev/null | head -1)
if [ -n "$KEYWORD_FILES" ]; then
    print_success "CSV ファイルが生成されました: $KEYWORD_FILES"
    print_info "内容を確認中..."
    head -6 "$KEYWORD_FILES"
else
    print_error "CSV ファイルが見つかりません"
    exit 1
fi

echo ""

# ステップ2: Dry-run ランダム検索テスト
echo "🎲 テスト2: Dry-run ランダム検索（モックデータ）"
echo "--------------------------------------------------"

print_info "ランダムに 5 件のモックアカウントを生成..."
python ingest_accounts.py \
    --discover-random \
    --max-results 5 \
    --dry-run \
    --log-level INFO

RANDOM_EXIT_CODE=$?
if [ $RANDOM_EXIT_CODE -eq 0 ]; then
    print_success "ランダム検索（dry-run）が成功しました"
else
    print_error "ランダム検索（dry-run）が失敗しました (終了コード: $RANDOM_EXIT_CODE)"
    exit 1
fi

# 生成されたファイルを確認
RANDOM_FILES=$(ls -t .cache/discover_results/random_accounts_*.csv 2>/dev/null | head -1)
if [ -n "$RANDOM_FILES" ]; then
    print_success "CSV ファイルが生成されました: $RANDOM_FILES"
    print_info "内容を確認中..."
    head -6 "$RANDOM_FILES"
else
    print_error "CSV ファイルが見つかりません"
    exit 1
fi

echo ""

# ステップ3: 生成されたCSVからアカウントリストを読み込みテスト
echo "📋 テスト3: 生成された CSV からアカウントリストを読み込み"
echo "--------------------------------------------------"

print_info "discovery source の統計を確認中..."
python << EOF
import sys
sys.path.insert(0, '.')
from utils.bootstrap import read_accounts_from_file

# 最新のキーワード検索結果を読み込み
accounts = read_accounts_from_file("$KEYWORD_FILES", with_metadata=True)

print(f"読み込みアカウント数: {len(accounts)}")
print(f"サンプル: {accounts[0]}")

# source フィールドの確認
if all('source' in acc for acc in accounts):
    sources = set(acc['source'] for acc in accounts)
    print(f"検出された source: {sources}")

    if 'grok_keyword' in sources:
        print("✅ grok_keyword source が正しく設定されています")
        exit(0)
    else:
        print("❌ grok_keyword source が見つかりません")
        exit(1)
else:
    print("❌ source フィールドが見つかりません")
    exit(1)
EOF

SOURCE_EXIT_CODE=$?
if [ $SOURCE_EXIT_CODE -eq 0 ]; then
    print_success "source フィールドが正しく読み込まれました"
else
    print_error "source フィールドの読み込みに失敗しました"
    exit 1
fi

echo ""

# 最終サマリー
echo "=================================================="
echo "✅ Stage 2.5: アカウント発見機能 スモークテスト完了"
echo "=================================================="
echo ""
echo "📊 結果サマリー:"
echo "  - キーワード検索（dry-run）: ✅"
echo "  - ランダム検索（dry-run）: ✅"
echo "  - CSV source フィールド: ✅"
echo ""
echo "生成されたファイル:"
echo "  - キーワード: $KEYWORD_FILES"
echo "  - ランダム: $RANDOM_FILES"
echo ""
echo "💡 実際の Grok API を使用する場合:"
echo "  python ingest_accounts.py --discover-keyword \"AI engineer\" --max-results 10"
echo "  python ingest_accounts.py --discover-random --max-results 10"
echo "=================================================="
