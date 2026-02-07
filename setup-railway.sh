#!/bin/bash
# Railway Setup Script for Portfolio Intelligence

set -e

echo "🚀 Setting up Portfolio Intelligence on Railway..."

# Navigate to project root
cd /Users/robertobuso-garcia/Projects/envoy-apps/ism-report-analysis

# Make sure we're linked to the project
railway link -p ism-report-analysis

echo "✅ Linked to project"

# Get the domain URLs (we'll need to set these after services are created)
FLASK_URL="https://envoyllc-ism.up.railway.app"

echo "📦 Current services:"
railway status --json | grep -o '"name":"[^"]*"' | cut -d'"' -f4

echo ""
echo "⚠️  Note: You need to create services via Railway dashboard:"
echo ""
echo "1. Go to: https://railway.app/project/ism-report-analysis"
echo "2. Click 'New Service' → 'Empty Service'"
echo "3. Name it: 'Portfolio Intelligence API'"
echo "4. Add another: 'Portfolio Intelligence Frontend'"
echo "5. Add databases: Redis and PostgreSQL"
echo ""
echo "Then run this script again to set environment variables!"
echo ""
echo "Press Enter when services are created..."
read

# TODO: Add environment variables once services exist
