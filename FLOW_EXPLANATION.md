# Self-Improvement Flow (100 words)

## Complete Flow:
1. **Task Analyzer** picks file based on maturity + user focus
2. **Step Planner** breaks task into method-specific steps
3. **Code Generator** generates code for each step (LLM returns ZERO-indented methods)
4. **Code Integrator** tries AST integration first (auto-indentation), falls back to normalize-then-indent (strips all indent, applies fresh)
5. **Proposal Generator** validates syntax + security (excludes analyzer tools from path validation)
6. **Patch Generator** creates unified diff
7. **Sandbox Tester** runs baseline tests, applies patch, runs tests again
8. **Update Gate** checks risk score, requires approval if high
9. **Atomic Applier** applies changes with backup

## Key Points:
- **AST integration** eliminates indentation errors by parsing/unparsing Python AST
- **Normalize-indent fallback** strips LLM indentation, applies original method indent
- **Security validation** excludes analyzer/validator tools from file operation checks
- **Zero-indent prompts** tell LLM to return methods with no leading spaces
