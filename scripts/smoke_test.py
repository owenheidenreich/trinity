"""Quick smoke test — validates only the 5 previously-failing test cases."""
import json
import time
import requests

API = "https://api.dubya.ai"
PRINCIPAL = "smoke-test-" + hex(int(time.time()))[-8:]

def send_prompt(prompt, chat_id=None, timeout=120):
    """Send prompt and collect SSE response."""
    payload = {"prompt": prompt, "principal_id": PRINCIPAL}
    if chat_id:
        payload["chat_id"] = chat_id
    start = time.time()
    try:
        resp = requests.post(f"{API}/generate/agent", json=payload, stream=True, timeout=timeout)
        tokens, errors, chat_id_out, done_reason = [], [], None, None
        for line in resp.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data = json.loads(line[6:])
            if "token" in data:
                tokens.append(data["token"])
            if "error" in data:
                errors.append(data["error"])
            if "done" in data and data["done"]:
                done_reason = data.get("done_reason")
                r = data.get("response", {})
                chat_id_out = r.get("chat_id") or chat_id
        return {
            "response": "".join(tokens),
            "errors": errors,
            "chat_id": chat_id_out,
            "latency": round(time.time() - start, 1),
            "done_reason": done_reason,
        }
    except Exception as e:
        return {"response": "", "errors": [str(e)], "latency": round(time.time() - start, 1), "done_reason": "error"}


TESTS = [
    {
        "id": "T15",
        "name": "Calculator tool",
        "prompt": "What is 847 * 293 + 15782? Use the calculator tool.",
        "validate": lambda r: any(c.isdigit() for c in r["response"]) and "<tool_call" not in r["response"],
        "fail_reason": "Should contain numeric result, no raw XML",
    },
    {
        "id": "T16",
        "name": "Web search tool",
        "prompt": "Search the web for the current Bitcoin price.",
        "validate": lambda r: len(r["response"]) > 20 and "<tool_call" not in r["response"],
        "fail_reason": "Should contain search results, no raw XML",
    },
    {
        "id": "T19",
        "name": "Long-form content",
        "prompt": "Write a 3-paragraph blog post about the benefits of meditation.",
        "validate": lambda r: len(r["response"]) > 200,
        "fail_reason": "Should produce substantial content (>200 chars)",
    },
    {
        "id": "T20",
        "name": "Creative writing",
        "prompt": "Write a short poem about the ocean.",
        "validate": lambda r: len(r["response"]) > 50,
        "fail_reason": "Should produce a poem (>50 chars)",
    },
    {
        "id": "T21",
        "name": "Unicode / translation",
        "prompt": "Translate 'Hello, how are you?' into Japanese and French.",
        "validate": lambda r: len(r["response"]) > 20,
        "fail_reason": "Should contain translations (>20 chars)",
    },
]


def main():
    print(f"{'='*60}")
    print(f"SMOKE TEST — 5 previously-failing tests")
    print(f"API: {API}  Principal: {PRINCIPAL}")
    print(f"{'='*60}\n")

    # Health check
    h = requests.get(f"{API}/health", timeout=10).json()
    print(f"Health: {h['status']} | Model: {h['model']} | Build: {h['build_timestamp']}\n")

    results = []
    for t in TESTS:
        print(f"  [{t['id']}] {t['name']}...", end=" ", flush=True)
        r = send_prompt(t["prompt"], timeout=120)
        passed = t["validate"](r)
        status = "PASS" if passed else "FAIL"
        print(f"{status} ({r['latency']}s, {len(r['response'])} chars)")
        if not passed:
            preview = r["response"][:200] if r["response"] else "(empty)"
            print(f"        Reason: {t['fail_reason']}")
            print(f"        Response: {preview}")
            if r["errors"]:
                print(f"        Errors: {r['errors']}")
            print(f"        Done reason: {r['done_reason']}")
        results.append({"id": t["id"], "passed": passed, "latency": r["latency"], "chars": len(r["response"])})

    passed = sum(1 for r in results if r["passed"])
    print(f"\n{'='*60}")
    print(f"RESULTS: {passed}/{len(results)} passed")
    avg_lat = sum(r["latency"] for r in results) / len(results)
    print(f"Avg latency: {avg_lat:.1f}s")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
