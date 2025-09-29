#!/usr/bin/env python3
"""
Script to add keyboard navigation clearing to the renderDropdown function
"""
def add_keyboard_nav_clearing():
    with open('frontend/templates/index.html', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Find the function and add the keyboard navigation clearing
    for i, line in enumerate(lines):
        if 'function renderDropdown(artists)' in line:
            # Find the line after the opening brace
            for j in range(i+1, min(i+10, len(lines))):
                if lines[j].strip() == 'artistResultsDropdown.innerHTML = \'\';':
                    # Insert the keyboard nav clearing code right before this line
                    new_lines = lines[:j] + [
                        f'      // Clear any previous keyboard selection when re-rendering\n',
                        f'      const previousSelection = artistResultsDropdown.querySelector(\'.bg-near-white\');\n',
                        f'      if (previousSelection) {{\n',
                        f'        previousSelection.classList.remove(\'bg-near-white\');\n',
                        f'      }}\n',
                        f'\n'
                    ] + lines[j:]
                    
                    # Write the file back
                    with open('frontend/templates/index.html', 'w', encoding='utf-8') as f:
                        f.writelines(new_lines)
                    
                    print(f"Added keyboard navigation clearing after line {j+1}")
                    return True
    
    print("Could not find the right location in renderDropdown function")
    return False

if __name__ == "__main__":
    add_keyboard_nav_clearing()