import argparse
import os
import re
import sys


HEADER_PATTERN = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(?:\(([a-z0-9]+(?:-[a-z0-9]+)*)\))?(!)?: ([^\n]+)$"
)
REQUIRED_PR_SECTIONS = (
    "## Summary",
    "## Related issue or task",
    "## Verification",
    "## Notes for reviewers",
)


def validate_header(header: str) -> list[str]:
    errors: list[str] = []
    if len(header) > 72:
        errors.append("header exceeds 72 characters")
    if not HEADER_PATTERN.fullmatch(header):
        errors.append("header must use English Angular-style Conventional Commits")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--message-env")
    parser.add_argument("--messages-stdin", action="store_true")
    parser.add_argument("--pr-body-env")
    args = parser.parse_args()
    if bool(args.message_env) == bool(args.messages_stdin):
        parser.error("choose exactly one message source")
    messages = (
        [os.environ.get(args.message_env, "").splitlines()[0]]
        if args.message_env and os.environ.get(args.message_env)
        else [line for line in sys.stdin.read().splitlines() if line]
    )
    failures = [f"{message!r}: {error}" for message in messages for error in validate_header(message)]
    if args.pr_body_env:
        body = os.environ.get(args.pr_body_env, "")
        failures.extend(
            f"PR body is missing required section: {section}"
            for section in REQUIRED_PR_SECTIONS
            if section not in body
        )
    if failures:
        print("Contribution validation failed:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"Contribution validation passed for {len(messages)} message(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

