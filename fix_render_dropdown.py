#!/usr/bin/env python3
"""
Script to fix the broken renderDropdown function in the HTML file
"""
def fix_render_dropdown_function():
    # Read the file
    with open('frontend/templates/index.html', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find the broken part and fix it
    # Look for the pattern that's broken
    broken_part = "}\n\n      artistResultsDropdown.innerHTML = '';"
    fixed_part = "}\n\n    function renderDropdown(artists) {\n      artistResultsDropdown.innerHTML = '';"
    
    if broken_part in content:
        content_fixed = content.replace(broken_part, fixed_part, 1)
        
        # Write the file back
        with open('frontend/templates/index.html', 'w', encoding='utf-8') as f:
            f.write(content_fixed)
        
        print("Successfully fixed the renderDropdown function")
        return True
    else:
        print("Broken pattern not found")
        return False

if __name__ == "__main__":
    fix_render_dropdown_function()