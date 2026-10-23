#!/usr/bin/env python3
"""Run the pipeline once against a repo copy.

Usage:
  python3 run_demo.py --repo ../hackathon-demo-repo --issue issues/tier1.json --mock --out /tmp/daas-out
  python3 run_demo.py --repo ../hackathon-demo-repo --issue issues/guardrail.json --mock --out /tmp/daas-out2

--mock uses the deterministic MockClient (offline plumbing proof).
Without --mock it uses the Meta Model API (needs MODEL_API_KEY).
Exit code 2 = escalated by the guardrail (expected for the guardrail issue).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from daas import pipeline  # noqa: E402
from daas.llm import default_client  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--issue", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()

    issue = json.loads(Path(args.issue).read_text())
    client = default_client(mock=args.mock)
    try:
        result = pipeline.run(args.repo, issue, client, args.out)
    except pipeline.Escalation as e:
        print(f"ESCALATED: {e.reason} (see {args.out}/escalation.md)")
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
