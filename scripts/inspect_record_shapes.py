import json
import subprocess
from pathlib import Path
from collections import defaultdict

ROOT = Path("data/cache/repo_metadata")
SAMPLES = [
    (
        "alignment-watermark-0988-claude",
        "logs/execution_claude_transcript.jsonl",
        "claude",
    ),
    (
        "llm-nonsense-commands-codex",
        "logs/execution_codex_transcript.jsonl",
        "codex",
    ),
    (
        "llm-nonsense-commands-gemini",
        "logs/execution_gemini_transcript.jsonl",
        "gemini",
    ), 
]

def read_file(repo, path):
    p = subprocess.run(
        [
            "git", 
            "-C", 
            str(ROOT / repo),
            "show", 
            f"HEAD:{path}",
        ],
        capture_output=True,
        text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(
            f"Failed to read {repo}:{path}\n{p.stderr}"
        )
    return p.stdout

def shape(x, depth=0):
    if depth >= 4:
        return type(x).__name__
    if isinstance(x, dict):
        return {
            k: shape(v, depth + 1)
            for k, v in x.items()
        }
    if isinstance(x, list):
        if not x:
            return []
        variants = []
        for item in x[:10]:
            s = shape(item, depth + 1)
            if s not in variants:
                variants.append(s)
        return variants
    return type(x).__name__

for repo, path, provider in SAMPLES:
    print("\n")
    print("=" * 80)
    print(provider.upper(), repo)
    print(path)
    print("=" * 80)
    text = read_file(repo, path)
    records = []
    bad_lines = []
    for line_no, line in enumerate(
        text.splitlines(),
        start=1,
    ):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            records.append(obj)
        except json.JSONDecodeError as e:
            bad_lines.append(
                (
                    line_no,
                    str(e),
                    repr(line[:120]),
                )
            )
    print(f"\nParsed records: {len(records)}")
    print(f"Non-JSON lines: {len(bad_lines)}")
    for line_no, err, prefix in bad_lines[:5]:
        print(
            f" BAD line {line_no}: "
            f"{err} :: {prefix}"
        )
    by_type = defaultdict(list)
    for r in records:
        if not isinstance(r, dict):
            continue
        typ = str(r.get("type", "<NONE>"))
        if len(by_type[typ]) < 2:
            by_type[typ].append(r)
    print("\nRecord types:", list(by_type.keys()))
    for typ, examples in by_type.items():
        print("\nTYPE:", typ)
        for i, r in enumerate(examples, start=1):
            print(
                f"example {i}:",
                json.dumps(
                    shape(r),
                    indent=2,
                    default=str,
                ),
            )
