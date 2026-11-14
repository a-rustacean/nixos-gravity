#!/usr/bin/env python3
"""Look up the Gravity-supported Mac mini M4 installer kits."""

import argparse
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
MANIFEST = HERE / "devices.json"


def load() -> dict:
    return json.loads(MANIFEST.read_text())


def kit(kit_id: str) -> dict:
    matches = [item for item in load()["kits"] if item["id"] == kit_id]
    if len(matches) != 1:
        raise ValueError(f"unknown or ambiguous release kit: {kit_id}")
    return matches[0]


def models(kit_id: str) -> list:
    return kit(kit_id)["models"]


def package_name(kit_id: str) -> str:
    return f"nixos-gravity-{kit_id}.zip"


def supported_lines() -> list:
    return [
        f"{model['product_type']} {item['id']}"
        for item in load()["kits"]
        for model in item["models"]
    ]


def supported_text() -> str:
    return "\n".join(supported_lines()) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", help="release kit id")
    parser.add_argument(
        "--field",
        choices=("dtb", "package", "models", "supported"),
        help="value to print",
    )
    args = parser.parse_args()
    if args.field == "supported":
        print(supported_text(), end="")
        return
    if not args.kit or not args.field:
        parser.error("--kit and --field are required unless --field supported is used")
    if args.field == "dtb":
        entries = models(args.kit)
        if len(entries) != 1:
            raise SystemExit(
                f"kit {args.kit} lists {len(entries)} models; "
                "multi-model stage-two packaging is not implemented"
            )
        print(entries[0]["dtb"])
    elif args.field == "package":
        print(package_name(args.kit))
    elif args.field == "models":
        print("\n".join(model["product_type"] for model in models(args.kit)))


if __name__ == "__main__":
    main()
