#!/bin/bash
# Fix SECRET_KEY mismatch between Flask and PI Backend

set -e

echo "🔧 Fixing SECRET_KEY Configuration"
echo "="*60

# Generate a secure secret key
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")

echo ""
echo "✅ Generated SECRET_KEY:"
echo "   $SECRET_KEY"
echo ""
echo "⚠️  IMPORTANT: This key will be set in BOTH services:"
echo "   1. ism-report-analysis (Flask)"
echo "   2. Portfolio Intelligence API (PI Backend)"
echo ""
echo "Press Enter to continue or Ctrl+C to cancel..."
read

echo ""
echo "📝 Setting SECRET_KEY in Flask service..."
railway link --service "ism-report-analysis" --environment production || {
    echo "❌ Failed to link to Flask service"
    echo "Please set manually via Railway Dashboard:"
    echo "   Service: ism-report-analysis"
    echo "   Variable: SECRET_KEY"
    echo "   Value: $SECRET_KEY"
    exit 1
}

railway variables --set "SECRET_KEY=$SECRET_KEY" || {
    echo "⚠️  Failed to set via CLI. Set manually via Railway Dashboard."
}

echo ""
echo "📝 Setting SECRET_KEY in PI Backend service..."
railway link --service "Portfolio Intelligence API" --environment production || {
    echo "❌ Failed to link to PI Backend service"
    echo "Please set manually via Railway Dashboard:"
    echo "   Service: Portfolio Intelligence API"
    echo "   Variable: SECRET_KEY"
    echo "   Value: $SECRET_KEY"
    exit 1
}

railway variables --set "SECRET_KEY=$SECRET_KEY" || {
    echo "⚠️  Failed to set via CLI. Set manually via Railway Dashboard."
}

echo ""
echo "="*60
echo "✅ SECRET_KEY Configuration Complete!"
echo "="*60
echo ""
echo "Next steps:"
echo "1. Verify both services redeployed automatically"
echo "2. Test login flow:"
echo "   - Visit: https://envoyllc-ism.up.railway.app"
echo "   - Log in with Google"
echo "   - Click Portfolio Intelligence"
echo "   - Should NOT redirect to landing"
echo ""
echo "If Railway CLI failed, set manually:"
echo "   1. Go to: https://railway.app/project/ism-report-analysis"
echo "   2. Set SECRET_KEY=$SECRET_KEY in BOTH services:"
echo "      - ism-report-analysis"
echo "      - Portfolio Intelligence API"
echo ""
