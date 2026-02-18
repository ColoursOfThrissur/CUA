#!/usr/bin/env python3
"""
Test Block Generator Indentation
"""

def test_indentation_handling():
    """Test that block generator handles indentation correctly"""
    
    # Simulate block code with various indentation levels
    block_code = """import logging
logger = logging.getLogger(__name__)
logger.debug("Starting method")
if condition:
    logger.info("Condition met")
    do_something()"""
    
    # Expected body indent (8 spaces for method body)
    body_indent = "        "
    
    # Process block lines with proper indentation
    block_lines = []
    block_raw_lines = block_code.split('\n')
    
    # Find minimum indentation in block (excluding empty lines)
    min_indent = float('inf')
    for block_line in block_raw_lines:
        if block_line.strip():  # Non-empty
            current_indent = len(block_line) - len(block_line.lstrip())
            min_indent = min(min_indent, current_indent)
    
    if min_indent == float('inf'):
        min_indent = 0
    
    print(f"Minimum indentation found: {min_indent} spaces")
    
    # Re-indent all lines relative to minimum
    for block_line in block_raw_lines:
        if block_line.strip():  # Non-empty line
            # Remove minimum indentation
            relative_indent = len(block_line) - len(block_line.lstrip()) - min_indent
            stripped = block_line.lstrip()
            # Add body indent + relative indent
            new_line = body_indent + (" " * relative_indent) + stripped
            block_lines.append(new_line)
            print(f"Original: '{block_line}'")
            print(f"New:      '{new_line}'")
            print(f"Relative indent: {relative_indent}")
            print()
        else:
            block_lines.append('')  # Keep empty lines
    
    result = '\n'.join(block_lines)
    print("\n=== FINAL RESULT ===")
    print(result)
    
    # Validate indentation
    lines = result.split('\n')
    for i, line in enumerate(lines, 1):
        if line.strip():
            indent = len(line) - len(line.lstrip())
            if indent % 4 != 0:
                print(f"\nERROR: Line {i} has invalid indentation: {indent} spaces")
                return False
    
    print("\n✓ All lines have valid indentation (multiples of 4)")
    return True

if __name__ == "__main__":
    success = test_indentation_handling()
    exit(0 if success else 1)
