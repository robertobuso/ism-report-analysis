"""
Test script for Quality Validation Engine
========================================
"""

import asyncio
import json
from quality_validation import quality_engine, validate_analysis_quality, is_quality_validation_available

def test_setup():
    """Test if quality validation is properly set up."""
    print("🧪 Testing Quality Validation Setup...")
    
    if is_quality_validation_available():
        print("✅ Quality validation is available")
        print(f"   • Anthropic client: {'✅ Connected' if quality_engine.anthropic_client else '❌ Not connected'}")
        print(f"   • Quality thresholds: {quality_engine.quality_thresholds}")
        return True
    else:
        print("❌ Quality validation is NOT available")
        print("   • Check ANTHROPIC_API_KEY environment variable")
        print("   • Ensure anthropic library is installed: pip install anthropic")
        return False

async def test_quality_validation():
    """Test quality validation with sample analysis."""
    
    if not is_quality_validation_available():
        print("❌ Cannot test - quality validation not available")
        return
    
    print("\n🧪 Testing Quality Validation Logic...")
    
    # Sample poor quality analysis (like the Palantir example)
    poor_analysis = {
        "executive": [
            "Company is doing great with 800% growth over 3 years",
            "Stock will probably go up 70% probability",
            "Management said Holy Christ this is unbelievable"
        ],
        "investor": [
            "Trading at record highs but looks cheap",
            "Analysts love it, buy rating from everyone",
            "No risk factors identified"
        ],
        "catalysts": [
            "Everything is bullish, no downside",
            "Will definitely beat earnings by 50%",
            "Target price $200 with 90% confidence"
        ]
    }
    
    # Sample articles
    sample_articles = [
        {
            "title": "Test Company Reports Strong Quarter",
            "snippet": "Company reported solid results with revenue growth",
            "source": "reuters.com",
            "source_type": "rss_feed"
        }
    ]
    
    try:
        result = await validate_analysis_quality("TEST", poor_analysis, sample_articles)
        
        print("✅ Quality validation completed")
        print(f"   • Overall score: {result['quality_validation']['score']:.1f}/10")
        print(f"   • Verdict: {result['quality_validation']['verdict']}")
        print(f"   • Issues found: {len(result['quality_validation'].get('critical_issues', []))}")
        
        if result['quality_validation'].get('critical_issues'):
            print("   • Sample issues:")
            for issue in result['quality_validation']['critical_issues'][:3]:
                print(f"     - {issue.get('severity', 'N/A').upper()}: {issue.get('issue', 'No description')}")
        
        return True
        
    except Exception as e:
        print(f"❌ Quality validation test failed: {e}")
        return False

async def main():
    """Run all tests."""
    print("🚀 Quality Validation Engine Test Suite")
    print("=" * 50)
    
    setup_ok = test_setup()
    
    if setup_ok:
        validation_ok = await test_quality_validation()
        
        if validation_ok:
            print("\n🎉 All tests passed! Quality validation is ready.")
            print("\n📋 Next steps:")
            print("   1. Update your Flask app to use the new quality-enhanced functions")
            print("   2. Monitor quality scores in the analysis results")
            print("   3. Adjust quality thresholds in environment variables if needed")
        else:
            print("\n❌ Quality validation test failed")
    else:
        print("\n❌ Setup test failed - fix configuration before proceeding")

if __name__ == "__main__":
    asyncio.run(main())