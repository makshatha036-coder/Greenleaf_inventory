"""Runs the full test suite and writes TEST_REPORT.md (submit this as your test report)."""
import datetime
import subprocess
import sys

proc = subprocess.run([sys.executable, "-m", "pytest", "-v", "--tb=short", "-p", "no:cacheprovider"],
                      capture_output=True, text=True)
lines = [l for l in proc.stdout.splitlines() if "PASSED" in l or "FAILED" in l or "ERROR" in l]
summary = (proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "no output").strip("= ")
with open("TEST_REPORT.md", "w", encoding="utf-8") as f:
    f.write(f"# Test report\n\nGenerated: {datetime.datetime.now():%Y-%m-%d %H:%M}\n\n")
    f.write(f"**Result:** {summary}\n\nTests use a separate temporary SQLite database, never `greenleaf.db`.\n\n")
    f.write("| Test | Result |\n|---|---|\n")
    for l in lines:
        name = l.split("::", 1)[-1].rsplit(" ", 1)[0].split(" ")[0]
        f.write(f"| `{name}` | {'PASSED' if 'PASSED' in l else 'FAILED'} |\n")
    if proc.returncode:
        f.write("\n## Failure details\n```\n" + proc.stdout[-3000:] + "\n```\n")
print(proc.stdout[-600:])
print("Report written to TEST_REPORT.md")
sys.exit(proc.returncode)
