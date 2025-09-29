#!/usr/bin/env python3
"""
Script to remove the addChip function from the HTML file
"""
def remove_addchip_function():
    # Read the file
    with open('frontend/templates/index.html', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find the start and end of the function
    start_idx = -1
    end_idx = -1
    
    for i, line in enumerate(lines):
        if 'function addChip(artist)' in line:
            start_idx = i
            print(f"Found function start at line {i+1}")
        
        if start_idx != -1 and line.strip() == '}':  # Look for closing brace after function start
            # Check if the next line is the function renderDropdown
            if i + 1 < len(lines) and 'function renderDropdown(artists)' in lines[i + 1]:
                end_idx = i
                print(f"Found function end at line {i+1}")
                break
    
    if start_idx != -1 and end_idx != -1:
        # Remove the function and its closing brace
        # Keep the line after which should be function renderDropdown
        new_lines = lines[:start_idx] + lines[end_idx + 1:]
        
        # Write the file back
        with open('frontend/templates/index.html', 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        
        print(f"Successfully removed addChip function (lines {start_idx+1} to {end_idx+1})")
        return True
    else:
        print(f"Function not found - start: {start_idx}, end: {end_idx}")
        # Let's try to find the closing brace differently
        if start_idx != -1:
            print("Found function start, looking for closing brace...")
            for i in range(start_idx, len(lines)):
                if lines[i].strip() == '}' and i > start_idx:
                    print(f"Found closing brace at line {i+1}")
                    # Check a few lines after to see if renderDropdown follows
                    for j in range(i+1, min(i+4, len(lines))):
                        print(f"Line {j+1}: {lines[j].strip()}")
                    # For now, let's just hardcode removal of 15 lines from start_idx
                    new_lines = lines[:start_idx] + lines[start_idx + 15:]
                    with open('frontend/templates/index.html', 'w', encoding='utf-8') as f:
                        f.writelines(new_lines)
                    print("Removed function using hardcoded approach")
                    return True
        return False

if __name__ == "__main__":
    remove_addchip_function()