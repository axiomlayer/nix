#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)


def fail(message: str) -> None:
    raise SystemExit(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((root / ".github/axiomlayer/fleet-pin.json").read_text())

    workflow_dir = root / ".github/workflows"
    active = sorted(
        path.relative_to(root).as_posix()
        for path in workflow_dir.iterdir()
        if path.is_file() and path.suffix in {".yml", ".yaml"}
    )
    expected_active = sorted(manifest["activeWorkflows"])
    if active != expected_active:
        fail(f"active workflow set mismatch: expected {expected_active}, got {active}")

    for relative, expected_digest in manifest["archivedUpstreamWorkflows"].items():
        path = root / relative
        if not path.is_file():
            fail(f"missing archived upstream workflow: {relative}")
        actual = sha256(path)
        if actual != expected_digest:
            fail(f"archived workflow changed: {relative}: expected {expected_digest}, got {actual}")

    action_pins = {
        name: details["commit"] for name, details in manifest["actions"].items()
    }
    used_actions: set[str] = set()
    for relative in active:
        text = (root / relative).read_text()
        lowered = text.lower()
        forbidden = {
            "pull_request_target": "privileged pull-request trigger",
            "secrets.": "repository or organization secret",
            "environment:": "deployment environment",
            "id-token: write": "OIDC write permission",
            "packages: write": "package write permission",
            "contents: write": "content write permission",
            "pull-requests: write": "pull-request write permission",
            "actions/upload-artifact@": "artifact publication",
            "actions/attest@": "attestation publication",
            "docker/login-action@": "registry login",
            "maintainers/upload-release": "upstream release program",
            "gh release": "GitHub release command",
            "git push": "Git push command",
        }
        for needle, label in forbidden.items():
            if needle in lowered:
                fail(f"{relative} contains forbidden {label}: {needle}")

        for reference in USES.findall(text):
            if reference.startswith("./"):
                continue
            if "@" not in reference:
                fail(f"external action has no ref: {reference}")
            name, commit = reference.rsplit("@", 1)
            if not FULL_SHA.fullmatch(commit):
                fail(f"external action is not pinned to a full SHA: {reference}")
            expected = action_pins.get(name)
            if expected is None:
                fail(f"external action is not declared in fleet-pin.json: {name}")
            if commit != expected:
                fail(f"action pin mismatch for {name}: expected {expected}, got {commit}")
            used_actions.add(name)

    if used_actions != set(action_pins):
        fail(
            "declared/used action set mismatch: "
            f"declared {sorted(action_pins)}, used {sorted(used_actions)}"
        )

    text_suffixes = {".json", ".md", ".py", ".sh", ".yaml", ".yml"}
    scoped_text = "\n".join(
        path.read_text()
        for base in (root / ".github/axiomlayer", root / "ci/axiomlayer")
        for path in base.rglob("*")
        if path.is_file() and path.suffix in text_suffixes
    ).lower()
    retired_name = "codex" + "_security" + "_gate"
    if retired_name in scoped_text:
        fail("retired security gate reintroduced")

    print(f"active_workflows={len(active)}")
    print(f"archived_upstream_workflows={len(manifest['archivedUpstreamWorkflows'])}")
    print(f"full_sha_action_pins={len(used_actions)}")
    print("workflow_isolation=verified")


if __name__ == "__main__":
    main()
