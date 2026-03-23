#!/usr/bin/env python3
"""
Clear resolved capability gaps
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.gap_tracker import GapTracker

def clear_resolved_gaps():
    """Clear capability gaps that have been resolved"""
    
    tracker = GapTracker()
    
    # Clear the skill:general gap since we fixed the routing
    print("Clearing resolved capability gaps...")
    
    gaps_to_clear = ["skill:general"]
    
    for gap_name in gaps_to_clear:
        if gap_name in tracker.gaps:
            print(f"Clearing gap: {gap_name}")
            tracker.clear_gap(gap_name)
            print(f"Cleared: {gap_name}")
        else:
            print(f"Gap not found: {gap_name}")
    
    print("\nRemaining gaps:")
    summary = tracker.get_summary()
    for gap in summary["gaps"]:
        print(f"  - {gap['capability']} (occurrences: {gap['occurrences']}, confidence: {gap['confidence']})")
    
    print(f"\nTotal remaining gaps: {summary['total_gaps']}")

if __name__ == "__main__":
    clear_resolved_gaps()