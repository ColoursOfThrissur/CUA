import ast

# What we want in the final generated code:
target = r'safe_id = item_id.strip().replace("/", "_").replace("\\", "_")'
print("TARGET OUTPUT:")
print(target)
print()

# Test different backslash counts in f-string
for n in [2, 4, 6, 8]:
    backslashes = '\\' * n
    result = f'safe_id = item_id.strip().replace("/", "_").replace("{backslashes}", "_")'
    print(f"{n} backslashes in f-string:")
    print(f"  Result: {result}")
    try:
        ast.parse(result)
        print("  OK VALID SYNTAX")
    except SyntaxError as e:
        print(f"  ERROR INVALID: {e.msg}")
    print()
