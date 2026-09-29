from __future__ import annotations

import argparse
import json
import sys

from .core import BananaMe


def _json(value: str):
    return json.loads(value)


def main() -> None:
    parser = argparse.ArgumentParser(prog="bananame", description="Headless AI-to-AI code interface")
    parser.add_argument("--workspace", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    p_understand = sub.add_parser("understand")
    p_understand.add_argument("--query", default="")
    p_understand.add_argument("--hot-file", action="append", default=[])
    p_understand.add_argument("--max-context-bytes", type=int, default=8192)
    p_understand.add_argument("--max-results", type=int, default=20)

    p_mutate = sub.add_parser("mutate")
    p_mutate.add_argument("--edits-json", type=_json, default=[])
    p_mutate.add_argument("--expected-head")
    mode = p_mutate.add_mutually_exclusive_group()
    mode.add_argument("--rollback")
    mode.add_argument("--recover")

    p_verify = sub.add_parser("verify")
    p_verify.add_argument("--path", action="append", default=[])
    p_verify.add_argument("--transaction-id")
    p_verify.add_argument("--command-json", action="append", type=_json, default=[])
    p_verify.add_argument("--timeout", type=int, default=60)

    args = parser.parse_args()
    tool = BananaMe(args.workspace)
    if args.command == "understand":
        result = tool.understand(
            query=args.query,
            hot_files=args.hot_file,
            max_context_bytes=args.max_context_bytes,
            max_results=args.max_results,
        )
    elif args.command == "mutate":
        action = "recover" if args.recover else "rollback" if args.rollback else "apply"
        transaction_id = args.recover or args.rollback
        result = tool.mutate(
            action=action,
            transaction_id=transaction_id,
            edits=args.edits_json,
            expected_head=args.expected_head,
        )
    else:
        result = tool.verify(
            paths=args.path,
            transaction_id=args.transaction_id,
            commands=args.command_json,
            timeout_seconds=args.timeout,
        )
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    raise SystemExit(0 if result.get("ok") else 2)


if __name__ == "__main__":
    main()
