#!/usr/bin/env python3
import sqlite3

conn = sqlite3.connect("/home/flip/.hermes/kanban.db")
c = conn.cursor()
# Get table info
c.execute("PRAGMA table_info(tasks)")
cols = c.fetchall()
print("=== TASKS TABLE SCHEMA ===")
for col in cols:
    print(f"  {col[1]:20s} | {col[2]}")

# Get all tasks
c.execute("SELECT * FROM tasks WHERE board='cryptotrader' ORDER BY priority ASC")
rows = c.fetchall()
print(f"\nTotal cryptotrader tasks: {len(rows)}")
print()
for r in rows:
    print(f"  {r}")

conn.close()
