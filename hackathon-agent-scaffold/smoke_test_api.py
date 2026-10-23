"""Day-0 hello-world check for the Meta Model API.

Run this the moment a key exists, before any sprint code:

    MODEL_API_KEY=... python3 smoke_test_api.py
    python3 smoke_test_api.py --mock     # offline plumbing check, no key

It calls the exact path the pipeline uses — MetaModelClient.complete_json
(chat completions at https://api.meta.ai/v1, model muse-spark-1.3,
JSON-object response) — with a triage-shaped prompt, and verifies the
reply parses as JSON with the expected keys. Exit code 0 = the Day-0
exit criterion "API key works on a hello-world call" is met.
The key itself is never printed.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from daas.llm import LLMError, MetaModelClient, MockClient  # noqa: E402

SYSTEM = "TRIAGE agent: classify the GitHub issue and reply as JSON only."
USER = ('Issue: "paginate() drops the last item of every full page — '
        '20 items, page size 10, page 2 returns 9." '
        'Reply with keys: kind, summary, acceptance (list).')


def main():
    mock = "--mock" in sys.argv
    try:
        client = MockClient() if mock else MetaModelClient()
    except LLMError as exc:
        print(f"FAIL: {exc}")
        return 2
    start = time.time()
    try:
        reply = client.complete_json(SYSTEM, USER)
    except Exception as exc:  # network, auth, JSON-mode, model errors land here
        print(f"FAIL: API call errored after {time.time() - start:.1f}s: {exc}")
        return 1
    elapsed = time.time() - start
    missing = [k for k in ("kind", "summary", "acceptance") if k not in reply]
    if missing:
        print(f"FAIL: reply parsed as JSON but is missing keys {missing}: {reply}")
        return 1
    mode = "mock (offline plumbing only)" if mock else f"Meta Model API, model {client.model}"
    print(f"OK: {mode} answered in {elapsed:.1f}s with valid JSON keys "
          f"{sorted(reply)} — kind={reply['kind']!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
