import argparse
import datetime
import json
import os

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", required=True)
    parser.add_argument("--files", default="")
    parser.add_argument("--rationale", default="")
    parser.add_argument("--kind", default="change")
    args = parser.parse_args()

    entry = f"\n## [{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {args.kind.upper()}: {args.summary}\n"
    if args.files:
        entry += f"- **Files**: {args.files}\n"
    if args.rationale:
        entry += f"- **Rationale**: {args.rationale}\n"

    with open("AGENT_LOG.md", "a", encoding="utf-8") as f:
        f.write(entry)

if __name__ == "__main__":
    main()
