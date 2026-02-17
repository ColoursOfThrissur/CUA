"""
LLM Log Analyzer - Analyze patterns in LLM interactions
"""
import json
from pathlib import Path
from collections import Counter

def analyze_session(session_file: str):
    """Analyze a session log file"""
    with open(session_file, 'r', encoding='utf-8') as f:
        interactions = [json.loads(line) for line in f]
    
    print(f"\n=== Session Analysis: {Path(session_file).name} ===")
    print(f"Total interactions: {len(interactions)}")
    
    # Phase breakdown
    phases = Counter(i.get('metadata', {}).get('phase', 'unknown') for i in interactions if 'metadata' in i)
    print(f"\nPhases:")
    for phase, count in phases.items():
        print(f"  {phase}: {count}")
    
    # Validation failures
    validation_errors = [i for i in interactions if 'error' in i and 'validation' in i.get('context', {}).get('phase', '')]
    if validation_errors:
        print(f"\nValidation Failures: {len(validation_errors)}")
        error_types = Counter(i['context'].get('validation_error', 'unknown')[:50] for i in validation_errors)
        for error, count in error_types.most_common(5):
            print(f"  {error}: {count}")
    
    # Temperature usage
    temps = [i.get('metadata', {}).get('temperature') for i in interactions if 'metadata' in i and 'temperature' in i.get('metadata', {})]
    if temps:
        print(f"\nTemperature: avg={sum(temps)/len(temps):.2f}, min={min(temps)}, max={max(temps)}")
    
    # File targets
    targets = [i.get('metadata', {}).get('target_file') for i in interactions if 'metadata' in i and 'target_file' in i.get('metadata', {})]
    if targets:
        print(f"\nTarget files:")
        for file, count in Counter(targets).most_common(5):
            print(f"  {file}: {count}")

if __name__ == "__main__":
    import sys
    
    logs_dir = Path("logs/llm")
    
    if len(sys.argv) > 1:
        # Analyze specific session
        analyze_session(sys.argv[1])
    else:
        # Analyze latest session
        sessions = sorted(logs_dir.glob("session_*.jsonl"))
        if sessions:
            analyze_session(sessions[-1])
        else:
            print("No session logs found")
