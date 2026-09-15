#!/usr/bin/env python3
"""Scan .vue files and report structural signals that usually point at
performance or code-reuse problems. It is a detector, not a judge: every
finding must be confirmed by reading the file before it goes in a report.

Usage: python3 scan_components.py [client/src]  (default: client/src)
"""
import json
import os
import re
import sys
from collections import defaultdict

ROOT = sys.argv[1] if len(sys.argv) > 1 else "client/src"
LARGE_COMPONENT_LINES = 400
LARGE_STYLE_LINES = 200

# Helpers that are defined locally in several components. The script counts
# where each name is defined so duplicates surface without hard-coding names.
# Only functions and computeds count as helpers. Plain refs (`loading`,
# `error`), `props`/`emit` and `new Date()` locals are state, not reuse.
DEF_RE = re.compile(
    r"^\s*(?:function\s+([A-Za-z_]\w*)\s*\("
    r"|const\s+([A-Za-z_]\w*)\s*=\s*(?:async\s*)?(?:\([^)]*\)\s*=>|[A-Za-z_]\w*\s*=>|computed\())",
    re.M,
)
# Generic handler names that every modal defines and nobody should share.
IGNORED_HELPERS = {"close", "open", "toggle", "handleClose", "handleSubmit"}
INDEX_KEY_RE = re.compile(r':key="\s*(?:index|idx|i|n)\s*"')
TEMPLATE_CALL_RE = re.compile(r"\{\{[^}]*?\b([a-zA-Z_]\w*)\([^}]*\}\}")
BOUND_CALL_RE = re.compile(r':(?:class|style|src|href|value|disabled)="[^"]*?\b([a-zA-Z_]\w*)\(')
# Formatting/translation helpers are cheap; calling them in templates is fine.
# Aggregation helpers are the ones that hurt when called from a v-for.
CHEAP_CALL_PREFIXES = ("format", "translate", "t", "get", "is", "has")


def section(src, tag):
    m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", src, re.S)
    return m.group(1) if m else ""


def scan(path):
    src = open(path, encoding="utf-8").read()
    template = section(src, "template")
    script = section(src, "script")
    style = section(src, "style")
    lines = src.count("\n") + 1
    names = [a or b for a, b in DEF_RE.findall(script) if (a or b) not in IGNORED_HELPERS]
    calls = [c for c in TEMPLATE_CALL_RE.findall(template) + BOUND_CALL_RE.findall(template)]
    heavy_calls = sorted({c for c in calls if not c.startswith(CHEAP_CALL_PREFIXES) and c != "$t"})
    return {
        "file": path,
        "lines": lines,
        "api_style": "script setup" if "<script setup" in src else ("options" if "<script" in src else "none"),
        "style_lines": style.count("\n"),
        "index_keys": len(INDEX_KEY_RE.findall(template)),
        "template_calls": len(calls),
        "heavy_template_calls": heavy_calls,
        "v_for_count": template.count("v-for="),
        "watch_count": len(re.findall(r"\bwatch(?:Effect)?\(", script)),
        "direct_axios": "from 'axios'" in script or 'from "axios"' in script,
        "uses_api_module": "from '../api'" in script or "from './api'" in script,
        "defined_names": names,
    }


def main():
    files = []
    for dirpath, _, filenames in os.walk(ROOT):
        for f in filenames:
            if f.endswith(".vue"):
                files.append(os.path.join(dirpath, f))
    results = [scan(f) for f in sorted(files)]

    defined_in = defaultdict(list)
    for r in results:
        for n in set(r["defined_names"]):
            defined_in[n].append(r["file"])
    # A helper defined in 2+ components is a code-reuse candidate.
    duplicates = {n: fs for n, fs in defined_in.items() if len(fs) >= 2}

    report = {
        "root": ROOT,
        "components": [{k: v for k, v in r.items() if k != "defined_names"} for r in results],
        "large_components": [r["file"] for r in results if r["lines"] > LARGE_COMPONENT_LINES],
        "large_style_blocks": [r["file"] for r in results if r["style_lines"] > LARGE_STYLE_LINES],
        "index_key_files": [r["file"] for r in results if r["index_keys"]],
        "direct_axios_files": [r["file"] for r in results if r["direct_axios"]],
        "options_api_files": [r["file"] for r in results if r["api_style"] == "options"],
        "duplicated_helpers": dict(sorted(duplicates.items(), key=lambda kv: -len(kv[1]))),
    }
    json.dump(report, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
