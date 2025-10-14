#!/usr/bin/env python3
"""
Test script to verify This Is playlist generation fixes
Phase 1: Test "This Is" playlist type
"""

import json
import asyncio
import sys
import os

# Import from backend directory
sys.path.insert(0, os.path.join(os.getcwd(), 'backend'))

from backend.ai_client import AIClient

async def test_this_is_playlist():
    """Test This Is playlist generation with sample data"""
    
    print("🧪 TESTING THIS IS PLAYLIST GENERATION")
    print("=" * 50)
    
    # Sample track data that mimics real Navidrome data structure
    sample_tracks = [
        {
            "id": "track_001",
            "title": "Song One",
            "artist": "Test Artist",
            "album": "Album A",
            "year": 2020,
            "play_count": 25,
            "genre": "Rock"
        },
        {
            "id": "track_002", 
            "title": "Song Two",
            "artist": "Test Artist",
            "album": "Album B",
            "year": 2018,
            "play_count": 15,
            "genre": "Rock"
        },
        {
            "id": "track_003",
            "title": "Song Three", 
            "artist": "Test Artist",
            "album": "Album A",
            "year": 2020,
            "play_count": 30,
            "genre": "Pop"
        },
        {
            "id": "track_004",
            "title": "Song Four",
            "artist": "Test Artist", 
            "album": "Album C",
            "year": 2015,
            "play_count": 8,
            "genre": "Rock"
        },
        {
            "id": "track_005",
            "title": "Song Five",
            "artist": "Test Artist",
            "album": "Album B", 
            "year": 2018,
            "play_count": 12,
            "genre": "Alternative"
        }
    ]
    
    print(f"📊 Sample data: {len(sample_tracks)} tracks for 'Test Artist'")
    
    # Initialize AI client
    ai_client = AIClient()
    
    try:
        print("\n🎵 Testing This Is playlist generation...")
        
        # Test the curate_this_is method
        result = await ai_client.curate_this_is(
            artist_name="Test Artist",
            tracks_json=sample_tracks,
            num_tracks=3,
            include_reasoning=True,
            variety_context="Testing Phase 1 fixes"
        )
        
        if isinstance(result, tuple):
            track_ids, reasoning = result
            print(f"\n✅ SUCCESS - Generated playlist:")
            print(f"🎵 Track IDs: {track_ids}")
            print(f"💭 Reasoning: {reasoning}")
        else:
            print(f"\n✅ SUCCESS - Generated playlist:")
            print(f"🎵 Track IDs: {result}")
            
        print(f"\n🎯 Test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ ERROR in This Is playlist generation:")
        print(f"💥 {e}")
        import traceback
        print(f"📋 Traceback: {traceback.format_exc()}")
        
    finally:
        await ai_client.close()

def check_environment():
    """Check if environment is properly set up"""
    print("🔧 ENVIRONMENT CHECK")
    print("-" * 30)
    
    api_key = os.getenv("AI_API_KEY")
    ai_model = os.getenv("AI_MODEL", "openai/gpt-3.5-turbo")
    
    print(f"🔑 AI_API_KEY present: {bool(api_key)}")
    print(f"🤖 AI_MODEL: {ai_model}")
    
    if not api_key:
        print("⚠️ WARNING: No AI_API_KEY found. Will test fallback behavior.")
    
    # Check if recipes directory exists
    if os.path.exists("recipes"):
        print("📁 Recipes directory: ✅ Found")
        if os.path.exists("recipes/registry.json"):
            print("📋 Recipe registry: ✅ Found")
        else:
            print("📋 Recipe registry: ❌ Missing")
    else:
        print("📁 Recipes directory: ❌ Missing")
        
    print()

if __name__ == "__main__":
    check_environment()
    asyncio.run(test_this_is_playlist())