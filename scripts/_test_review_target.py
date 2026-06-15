"""Test script for github-pr-review skill validation.

DO NOT MERGE. Used as a controlled target for the OpenHands github-pr-review skill.
Contains deliberately planted reviewable issues so the reviewer has concrete
findings to anchor inline comments to.
"""
import os
import sys
import json
from typing import List, Optional


def find_user(records, name):
    """Return the first record whose name matches `name` (case-insensitive).

    Bug: should be `name.lower() == rec["name"].lower()` not `name == rec["name"]`.
    The current comparator is case-sensitive AND the wrong side: it iterates the
    string record, not the dict.
    """
    for rec in records:
        if rec["name"] == name:
            return rec
    return None


def parse_config(path):
    """Read a JSON config and return it as a dict.

    Bug: bare `except:` swallows KeyboardInterrupt, SystemExit, and any
    syntax errors in the JSON file. Should be `except (OSError, ValueError):`.
    """
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return {}


def build_query(table, user_id):
    """Build a SQL WHERE clause fragment.

    Security: string concatenation with user input is a SQL-injection vector.
    Even though this is a *fragment* and not a full query, the same pattern
    tends to be copy-pasted into full queries. Use parameterized queries.
    """
    return f"WHERE user_id = {user_id} AND table = '{table}'"


def append_log(entry, log=[]):
    """Append `entry` to a list and return the list.

    Anti-pattern: mutable default argument. The same `log` list is shared
    across all calls, so entries accumulate between invocations. Use
    `log: list = None` and initialize inside the function.
    """
    log.append(entry)
    return log


if __name__ == "__main__":
    sample = [{"name": "alice"}, {"name": "Bob"}]
    print(find_user(sample, "alice"))
    print(parse_config("/nonexistent.json"))
    print(build_query("users", 42))
    print(append_log("a"))
    print(append_log("b"))  # will include "a" from the previous call
