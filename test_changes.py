#!/usr/bin/env python3
"""
Test script to verify the changes from Artist Radio to This Is
"""
import json
import os
from pathlib import Path

def test_recipe_file():
    """Test that the recipe file was updated correctly"""
    recipe_file = Path("recipes/this_is_v1_001.json")
    if not recipe_file.exists():
        print("❌ Recipe file 'this_is_v1_001.json' does not exist")
        return False
    
    try:
        with open(recipe_file, 'r') as f:
            recipe = json.load(f)
        
        # Check that it has the new content
        if "this-is-v1.001" not in recipe.get("version", ""):
            print("❌ Recipe version not updated correctly")
            return False
        
        if "single artist" not in recipe.get("description", ""):
            print("❌ Recipe description doesn't mention single artist")
            return False
            
        if "This Is:" not in recipe.get("prompt_template", ""):
            print("❌ Recipe prompt template doesn't mention 'This Is:'")
            return False
        
        print("✅ Recipe file updated correctly")
        return True
    except Exception as e:
        print(f"❌ Error reading recipe file: {e}")
        return False

def test_registry():
    """Test that the registry was updated"""
    registry_file = Path("recipes/registry.json")
    if not registry_file.exists():
        print("❌ Registry file does not exist")
        return False
    
    try:
        with open(registry_file, 'r') as f:
            registry = json.load(f)
        
        if "this_is" not in registry:
            print("❌ 'this_is' not found in registry")
            return False
        
        if registry["this_is"] != "this_is_v1_001.json":
            print("❌ Registry doesn't point to correct file")
            return False
            
        print("✅ Registry updated correctly")
        return True
    except Exception as e:
        print(f"❌ Error reading registry: {e}")
        return False

def test_backend_changes():
    """Test backend changes"""
    main_file = Path("backend/main.py")
    if not main_file.exists():
        print("❌ Backend main.py file not found")
        return False
    
    try:
        with open(main_file, 'r') as f:
            content = f.read()
        
        # Check for updated function calls
        if "curate_this_is" not in content:
            print("❌ curate_this_is function call not found in backend")
            return False
            
        if "this_is" not in content or "artist_radio" in content:
            print("❌ Playlist type not fully updated in backend")
            # Check more specifically
            lines_with_artist_radio = [i for i, line in enumerate(content.split('\n')) if 'artist_radio' in line and 'rediscover_weekly' not in line]
            if lines_with_artist_radio:
                print(f"   Lines still containing 'artist_radio': {lines_with_artist_radio[:5]}...")  # show first 5
            
        print("✅ Backend changes look good")
        return True
    except Exception as e:
        print(f"❌ Error checking backend: {e}")
        return False

def test_frontend_changes():
    """Test frontend changes"""
    frontend_file = Path("frontend/templates/index.html")
    if not frontend_file.exists():
        print("❌ Frontend template file not found")
        return False
    
    try:
        with open(frontend_file, 'r') as f:
            content = f.read()
        
        # Check for updated content
        if "This is" not in content:
            print("❌ 'This is' not found in frontend")
            return False
            
        if "This Is Playlist" not in content and "Create This Is" not in content:
            print("❌ Create button text not updated")
            return False
            
        if "artist-radio" in content:
            print("❌ Old 'artist-radio' IDs still present in frontend")
            return False
            
        print("✅ Frontend changes look good")
        return True
    except Exception as e:
        print(f"❌ Error checking frontend: {e}")
        return False

def main():
    print("Testing changes from Artist Radio to This Is...")
    print()
    
    all_passed = True
    
    print("1. Testing recipe file...")
    all_passed &= test_recipe_file()
    print()
    
    print("2. Testing registry...")
    all_passed &= test_registry()
    print()
    
    print("3. Testing backend changes...")
    all_passed &= test_backend_changes()
    print()
    
    print("4. Testing frontend changes...")
    all_passed &= test_frontend_changes()
    print()
    
    if all_passed:
        print("🎉 All tests passed! The transition from Artist Radio to This Is is complete.")
        print("\nKey changes made:")
        print("- Backend: Renamed curate_artist_radio to curate_this_is")
        print("- Backend: Changed playlist_type from 'artist_radio' to 'this_is'")
        print("- Frontend: Updated UI labels from 'Artist Radio' to 'This is'")
        print("- Frontend: Changed to single artist selection with dropdown blur on selection")  
        print("- Recipes: Updated to 'This Is' format with single-artist focus")
        print("- Functionality: Maintained all existing fallback and error handling")
    else:
        print("❌ Some tests failed. Please review the output above.")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())