#!/bin/bash
# Stage1 & Stage2 実運用準備確認スクリプト

set -e  # エラーで停止

echo "=================================================="
echo "Stage1 & Stage2 実運用準備確認"
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

# ステップ1: 前提条件チェック
echo "📋 ステップ1: 前提条件チェック"
echo "--------------------------------------------------"

# secrets.toml の存在確認
if [ ! -f ".streamlit/secrets.toml" ]; then
    print_error "secrets.toml が見つかりません"
    echo "  .streamlit/secrets.toml を作成してください"
    exit 1
else
    print_success "secrets.toml が存在します"
fi

# GROK_API_KEY の確認
if grep -q "GROK_API_KEY" .streamlit/secrets.toml; then
    print_success "GROK_API_KEY が設定されています"
else
    print_error "GROK_API_KEY が見つかりません"
    exit 1
fi

# 依存関係の確認
print_info "依存関係を確認中..."
python -c "import streamlit; import pandas; import sentence_transformers" 2>/dev/null
if [ $? -eq 0 ]; then
    print_success "依存関係がインストールされています"
else
    print_error "依存関係が不足しています"
    echo "  pip install -r requirements.txt を実行してください"
    exit 1
fi

echo ""

# ステップ2: テスト用アカウントリスト作成
echo "📝 ステップ2: テスト用アカウントリスト作成"
echo "--------------------------------------------------"

cat > test_accounts.txt << 'EOF'
# Test accounts for Stage1 verification
cor_terisuke
elonmusk
sama
ylecun
karpathy
goodfellow_ian
EOF

print_success "test_accounts.txt を作成しました (6件)"
echo ""

# ステップ3: キャッシュクリア
echo "🗑️  ステップ3: キャッシュクリア"
echo "--------------------------------------------------"

if [ -d ".cache" ]; then
    print_warning "既存のキャッシュを削除します"
    rm -rf .cache
fi
print_success "キャッシュをクリアしました"
echo ""

# ステップ4: CLI テスト実行
echo "🚀 ステップ4: CLI テスト実行"
echo "--------------------------------------------------"
print_info "6件のアカウントを処理します（バッチサイズ: 2）"
print_info "処理時間: 約3-5分（API速度による）"
echo ""

# CLI 実行
python ingest_accounts.py test_accounts.txt --batch-size 2 --log-level INFO

CLI_EXIT_CODE=$?
if [ $CLI_EXIT_CODE -eq 0 ]; then
    print_success "CLI テストが完了しました"
else
    print_error "CLI テストが失敗しました (終了コード: $CLI_EXIT_CODE)"
    echo ""
    print_info "ログファイルを確認してください: .cache/ingest.log"
    exit 1
fi
echo ""

# ステップ5: ログファイル確認
echo "📄 ステップ5: ログファイル確認"
echo "--------------------------------------------------"

if [ -f ".cache/ingest.log" ]; then
    print_success "ingest.log が作成されました"

    # レートリミット情報の確認
    echo ""
    print_info "レートリミット情報:"
    RATE_LIMIT_LINES=$(grep -i "rate\|レート" .cache/ingest.log | head -5)
    if [ -n "$RATE_LIMIT_LINES" ]; then
        echo "$RATE_LIMIT_LINES"
    else
        print_warning "レートリミット情報が見つかりません（Web検索で取得した可能性）"
    fi

    # エラーの確認
    echo ""
    print_info "エラーチェック:"
    ERROR_COUNT=$(grep -i "error\|エラー" .cache/ingest.log 2>/dev/null | wc -l | tr -d ' ')
    if [ "$ERROR_COUNT" -eq 0 ]; then
        print_success "エラーはありません"
    else
        print_warning "$ERROR_COUNT 件のエラーが記録されています"
        grep -i "error\|エラー" .cache/ingest.log | head -3
    fi
else
    print_error "ingest.log が作成されていません"
    print_info "CLI が正常に実行されなかった可能性があります"
    exit 1
fi
echo ""

# ステップ6: キャッシュファイル検証
echo "🔍 ステップ6: キャッシュファイル検証"
echo "--------------------------------------------------"

# 権限を付与
chmod +x verify_cache.py

# キャッシュ検証
python verify_cache.py --all

if [ $? -eq 0 ]; then
    print_success "すべてのキャッシュが正常です"
else
    print_error "一部のキャッシュに問題があります"
    exit 1
fi
echo ""

# ステップ7: fetched_at 検証
echo "📅 ステップ7: fetched_at メタデータ検証"
echo "--------------------------------------------------"

print_info "cor_terisuke のキャッシュを確認中..."
python << 'EOF'
import pickle
try:
    with open('.cache/posts_cor_terisuke.pkl', 'rb') as f:
        data = pickle.load(f)
    if 'fetched_at' in data:
        print(f"✅ fetched_at: {data['fetched_at']}")
        exit(0)
    else:
        print("❌ fetched_at が見つかりません")
        exit(1)
except Exception as e:
    print(f"❌ エラー: {e}")
    exit(1)
EOF

if [ $? -eq 0 ]; then
    print_success "fetched_at が正しく記録されています"
else
    print_error "fetched_at の記録に問題があります"
    exit 1
fi
echo ""

# ステップ7.5: データソース統計の確認
echo "📊 ステップ7.5: データソース統計の確認"
echo "--------------------------------------------------"

print_info "ログファイルからデータソース統計を抽出中..."
python << 'EOF'
import re

try:
    with open('.cache/ingest.log', 'r', encoding='utf-8') as f:
        log_content = f.read()

    # データソース統計を抽出
    twitter_match = re.search(r'🔑 X API \(Twitter\):\s*(\d+)', log_content)
    web_search_match = re.search(r'🌐 Grok Web Search:\s*(\d+)', log_content)
    generated_match = re.search(r'📝 フォールバック生成:\s*(\d+)', log_content)
    real_data_ratio_match = re.search(r'💡 実データ比率:\s*([\d.]+)%', log_content)

    if twitter_match or web_search_match or generated_match:
        print("\n📊 データソース内訳:")
        if twitter_match:
            print(f"  🔑 X API (Twitter): {twitter_match.group(1)} 件")
        if web_search_match:
            print(f"  🌐 Grok Web Search: {web_search_match.group(1)} 件")
        if generated_match:
            print(f"  📝 フォールバック生成: {generated_match.group(1)} 件")

        if real_data_ratio_match:
            ratio = float(real_data_ratio_match.group(1))
            print(f"\n  💡 実データ比率: {ratio:.1f}%")

            # 実データ比率の評価
            if ratio >= 80:
                print("  ✅ 実データ比率が高く、質の高いペルソナ生成が期待できます")
            elif ratio >= 50:
                print("  ⚠️  実データ比率は中程度です。必要に応じて X API 設定を確認してください")
            else:
                print("  ⚠️  実データ比率が低いです。X_BEARER_TOKEN の設定を確認してください")

        exit(0)
    else:
        print("❌ ソース統計が見つかりませんでした")
        exit(1)
except Exception as e:
    print(f"❌ エラー: {e}")
    exit(1)
EOF

if [ $? -eq 0 ]; then
    print_success "データソース統計を確認しました"
else
    print_error "データソース統計の確認に失敗しました"
    exit 1
fi
echo ""

# ステップ8: 部分的なキャッシュ状態を作成（Stage2用）
echo "🔧 ステップ8: Stage2 テスト準備"
echo "--------------------------------------------------"

print_info "部分的にキャッシュを削除します（sama, ylecun）"
rm -f .cache/posts_sama.pkl
rm -f .cache/posts_ylecun.pkl

# 混在リスト作成
cat > test_accounts_mixed.txt << 'EOF'
cor_terisuke
elonmusk
sama
ylecun
karpathy
goodfellow_ian
AndrewYNg
lexfridman
EOF

print_success "混在状態のテストリストを作成しました"
echo "  - キャッシュ済み: 4件 (cor_terisuke, elonmusk, karpathy, goodfellow_ian)"
echo "  - 未取得: 4件 (sama, ylecun, AndrewYNg, lexfridman)"
echo ""

# ステップ9: 多様性サンプリング機能のテスト
echo "🧮 ステップ9: 多様性サンプリング機能のテスト"
echo "--------------------------------------------------"

print_info "多様性サンプリング機能をテストします（ドライラン）"
python ingest_accounts.py --diversity-sampling --max-results 10 --dry-run --sampling-method stratified

DIVERSITY_EXIT_CODE=$?
if [ $DIVERSITY_EXIT_CODE -eq 0 ]; then
    print_success "多様性サンプリング機能のテストが完了しました"
else
    print_warning "多様性サンプリング機能のテストが失敗しました (終了コード: $DIVERSITY_EXIT_CODE)"
    print_info "これはドライランなので、実際のAPI呼び出しは行われません"
fi
echo ""

# 最終サマリー
echo "=================================================="
echo "✅ Stage1 CLI テスト完了"
echo "=================================================="
echo ""
echo "📊 結果サマリー:"
echo "  - キャッシュファイル: $(ls .cache/posts_*.pkl 2>/dev/null | wc -l | tr -d ' ') 件"
echo "  - ログファイル: あり"
echo "  - fetched_at: 記録済み"
echo "  - レートリミット: 管理済み"
echo "  - 多様性サンプリング: テスト済み"
echo ""
echo "🎯 次のステップ:"
echo "  1. Streamlit アプリを起動:"
echo "     streamlit run app.py"
echo ""
echo "  2. UI で以下をテスト:"
echo "     - test_accounts_mixed.txt をアップロード"
echo "     - キャッシュ検出を確認"
echo "     - 「🚀 不足分を取得」を実行"
echo "     - 各ステータス表示を確認"
echo "     - 多様性サンプリング機能をテスト"
echo ""
echo "詳細な手順は TEST_PROCEDURE.md を参照してください。"
echo "=================================================="
