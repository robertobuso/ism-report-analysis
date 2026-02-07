#!/bin/bash
# Get actual production logs from Railway

echo "📋 Getting PI Backend logs..."
echo ""
echo "Go to Railway Dashboard and get the logs:"
echo "1. https://railway.app/project/ism-report-analysis"
echo "2. Click 'Portfolio Intelligence API' service"
echo "3. Click 'Deployments' tab"
echo "4. Click the latest deployment"
echo "5. Click 'View Logs'"
echo ""
echo "Look for the MOST RECENT error when you access Portfolio Intelligence"
echo ""
echo "Copy the error logs and paste them here."
echo ""
echo "OR use Railway CLI (if it works):"
echo ""

# Try to get logs via CLI
railway link -e production 2>&1
railway logs -d 2>&1 | tail -200
