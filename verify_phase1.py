"""Verify Phase 1 database and functionality."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.tool_execution_logger import get_execution_logger
from core.tool_quality_analyzer import ToolQualityAnalyzer


def check_database():
    """Check database structure and contents."""
    print("=" * 60)
    print("DATABASE VERIFICATION")
    print("=" * 60)
    
    db_path = "data/tool_executions.db"
    
    if not Path(db_path).exists():
        print(f"[FAIL] Database not found: {db_path}")
        return False
    
    print(f"[OK] Database exists: {db_path}")
    print(f"[OK] Size: {Path(db_path).stat().st_size} bytes")
    
    with sqlite3.connect(db_path) as conn:
        # Check table structure
        cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='executions'")
        schema = cursor.fetchone()
        if schema:
            print("\n[OK] Table 'executions' exists")
            print("\nSchema:")
            print(schema[0])
        else:
            print("[FAIL] Table 'executions' not found")
            return False
        
        # Check indexes
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='executions'")
        indexes = cursor.fetchall()
        print(f"\n[OK] Indexes: {[idx[0] for idx in indexes]}")
        
        # Count records
        cursor = conn.execute("SELECT COUNT(*) FROM executions")
        count = cursor.fetchone()[0]
        print(f"\n[OK] Total executions logged: {count}")
        
        if count > 0:
            # Show sample records
            cursor = conn.execute("""
                SELECT tool_name, operation, success, execution_time_ms, output_size 
                FROM executions 
                ORDER BY id DESC 
                LIMIT 5
            """)
            print("\nRecent executions:")
            for row in cursor.fetchall():
                tool, op, success, time_ms, size = row
                status = "SUCCESS" if success else "FAILED"
                print(f"  - {tool}.{op}: {status} ({time_ms:.1f}ms, {size} bytes)")
            
            # Show tool breakdown
            cursor = conn.execute("""
                SELECT tool_name, COUNT(*) as count, 
                       SUM(success) as successful,
                       AVG(execution_time_ms) as avg_time
                FROM executions 
                GROUP BY tool_name
                ORDER BY count DESC
            """)
            print("\nTool breakdown:")
            for row in cursor.fetchall():
                tool, count, successful, avg_time = row
                success_rate = (successful / count * 100) if count > 0 else 0
                print(f"  - {tool}: {count} executions, {success_rate:.1f}% success, {avg_time:.1f}ms avg")
    
    return True


def check_logger():
    """Check logger functionality."""
    print("\n" + "=" * 60)
    print("LOGGER VERIFICATION")
    print("=" * 60)
    
    logger = get_execution_logger()
    print(f"[OK] Logger instance created: {logger.__class__.__name__}")
    print(f"[OK] Database path: {logger.db_path}")
    
    # Test logging
    print("\n[TEST] Logging test execution...")
    logger.log_execution(
        tool_name="VerificationTool",
        operation="test",
        success=True,
        error=None,
        execution_time_ms=42.5,
        parameters={"test": "param"},
        output_data={"result": "verified"}
    )
    print("[OK] Test execution logged")
    
    # Verify it was logged
    stats = logger.get_tool_stats("VerificationTool", days=1)
    if stats["total_executions"] > 0:
        print(f"[OK] Verification: {stats['total_executions']} executions found")
        return True
    else:
        print("[WARN] Test execution not found in stats")
        return False


def check_analyzer():
    """Check analyzer functionality."""
    print("\n" + "=" * 60)
    print("ANALYZER VERIFICATION")
    print("=" * 60)
    
    analyzer = ToolQualityAnalyzer()
    print(f"[OK] Analyzer instance created: {analyzer.__class__.__name__}")
    
    # Get summary
    summary = analyzer.get_summary(days=7)
    print(f"\n[OK] Ecosystem Summary:")
    print(f"  Total Tools: {summary['total_tools']}")
    print(f"  Avg Health Score: {summary['avg_health_score']:.1f}/100")
    print(f"  Healthy: {summary.get('healthy_tools', 0)}")
    print(f"  Monitor: {summary.get('monitor_tools', 0)}")
    print(f"  Weak: {summary.get('weak_tools', 0)}")
    print(f"  Quarantine: {summary.get('quarantine_tools', 0)}")
    
    # Get all tools
    reports = analyzer.analyze_all_tools(days=7)
    print(f"\n[OK] Analyzed {len(reports)} tools")
    
    if reports:
        print("\nTop 3 tools by health score:")
        for report in sorted(reports, key=lambda r: r.health_score, reverse=True)[:3]:
            print(f"  {report.health_score:.1f}/100 - {report.tool_name} ({report.recommendation})")
        
        print("\nBottom 3 tools by health score:")
        for report in sorted(reports, key=lambda r: r.health_score)[:3]:
            print(f"  {report.health_score:.1f}/100 - {report.tool_name} ({report.recommendation})")
            if report.issues:
                for issue in report.issues:
                    print(f"    * {issue}")
    
    # Get weak tools
    weak = analyzer.get_weak_tools(days=7, min_usage=2)
    print(f"\n[OK] Weak tools identified: {len(weak)}")
    for tool in weak:
        print(f"  - {tool.tool_name}: {tool.recommendation} (score: {tool.health_score:.1f})")
    
    return True


def check_risk_scoring():
    """Check if risk scoring is implemented."""
    print("\n" + "=" * 60)
    print("RISK SCORING VERIFICATION")
    print("=" * 60)
    
    # Check if risk_score column exists
    db_path = "data/tool_executions.db"
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute("PRAGMA table_info(executions)")
        columns = [row[1] for row in cursor.fetchall()]
        
        print(f"[INFO] Database columns: {columns}")
        
        if "risk_score" in columns:
            print("[OK] risk_score column exists")
            
            # Check if any risk scores are set
            cursor = conn.execute("SELECT COUNT(*) FROM executions WHERE risk_score IS NOT NULL")
            count = cursor.fetchone()[0]
            print(f"[INFO] Executions with risk scores: {count}")
            
            if count > 0:
                cursor = conn.execute("SELECT tool_name, operation, risk_score FROM executions WHERE risk_score IS NOT NULL LIMIT 5")
                print("\nSample risk scores:")
                for row in cursor.fetchall():
                    print(f"  - {row[0]}.{row[1]}: risk={row[2]}")
            
            return True
        else:
            print("[INFO] risk_score column not found (not implemented yet)")
            return False


def main():
    """Run all verification checks."""
    print("\n" + "=" * 60)
    print("PHASE 1 FUNCTIONALITY VERIFICATION")
    print("=" * 60 + "\n")
    
    results = {
        "Database": check_database(),
        "Logger": check_logger(),
        "Analyzer": check_analyzer(),
        "Risk Scoring": check_risk_scoring()
    }
    
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    
    for component, status in results.items():
        status_str = "[PASS]" if status else "[FAIL]"
        print(f"{status_str} {component}")
    
    all_pass = all(results.values())
    
    if all_pass:
        print("\n[SUCCESS] All components functioning correctly!")
    else:
        print("\n[PARTIAL] Some components need attention")
    
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
