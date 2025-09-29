#!/usr/bin/env python3
"""
Quick verification script for the chips removal changes
"""
import re
from pathlib import Path

def main():
    print("Verifying chips removal changes...")
    
    frontend_file = Path("frontend/templates/index.html")
    
    if not frontend_file.exists():
        print("❌ Frontend file not found")
        return 1
    
    content = frontend_file.read_text()
    
    # Check that chips-related elements are removed
    chips_references = []
    
    if 'chips-container' in content:
        chips_references.append('chips-container HTML element still present')
    
    if 'addChip(' in content or 'addChip(' in content:
        chips_references.append('addChip function still present')
    
    if 'remove-chip' in content:
        chips_references.append('remove-chip class still present')
        
    if 'const chipsContainer' in content:
        chips_references.append('chipsContainer variable still present')
        
    # Check that single selection behavior is implemented
    single_selection_indicators = []
    
    if 'artistSearchInput.value = artist.name' in content:
        single_selection_indicators.append('Setting artist name in input field')
    
    if 'artistSearchInput.blur()' in content:
        single_selection_indicators.append('Input field blur behavior')
        
    if 'selectedArtists.length > 1' in content:
        single_selection_indicators.append('Multiple artist validation')
    
    print(f"🔍 Found {len(chips_references)} remaining chips references:")
    for ref in chips_references:
        print(f"   ❌ {ref}")
    
    print(f"🔍 Found {len(single_selection_indicators)} single selection indicators:")
    for indicator in single_selection_indicators:
        print(f"   ✅ {indicator}")
    
    if not chips_references:
        print("\n🎉 No chips-related code found - removal was successful!")
    else:
        print(f"\n⚠️  Still have {len(chips_references)} chips references to clean up")
        return 1
    
    if single_selection_indicators:
        print("✅ Single selection behavior is properly implemented")
    else:
        print("⚠️  Single selection behavior not fully implemented")
        return 1
        
    print("\n✅ All changes verified successfully!")
    return 0

if __name__ == "__main__":
    exit(main())