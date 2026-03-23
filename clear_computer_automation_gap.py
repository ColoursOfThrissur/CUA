#!/usr/bin/env python3
"""
Clear resolved computer automation capability gap
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.gap_tracker import GapTracker

def clear_computer_automation_gap():
    """Clear the resolved computer_automation:missing_tool gap"""
    
    tracker = GapTracker()
    
    print("Clearing resolved computer_automation capability gap...")
    
    gap_name = "computer_automation:missing_tool"
    
    if gap_name in tracker.gaps:
        print(f"Clearing gap: {gap_name}")
        tracker.clear_gap(gap_name)
        print("Gap cleared successfully")
    else:
        print(f"Gap not found: {gap_name}")
    
    print("\nRemaining gaps:")
    summary = tracker.get_summary()
    for gap in summary["gaps"]:
        print(f"  - {gap['capability']} (occurrences: {gap['occurrences']}, confidence: {gap['confidence']})")
    
    print(f"\nTotal remaining gaps: {summary['total_gaps']}")

if __name__ == "__main__":
    clear_computer_automation_gap()