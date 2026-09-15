#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


def fail(message: str) -> None:
    raise SystemExit(message)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: Any) -> str:
    encoded = (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        + "\n"
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def one(items: list[dict[str, Any]], key: str, value: str) -> dict[str, Any]:
    matches = [item for item in items if item.get(key) == value]
    if len(matches) != 1:
        fail(f"expected exactly one {key}={value!r}, found {len(matches)}")
    return matches[0]


def expect(actual: Any, expected: Any, label: str) -> None:
    if actual != expected:
        fail(f"{label} mismatch: expected {expected!r}, got {actual!r}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--control", type=Path)
    args = parser.parse_args()

    manifest = load_json(args.manifest)
    expect(manifest.get("schema"), "axiom-nix-upstream-integration-v1", "schema")
    expect(manifest.get("fork"), "AxiomLayer/nix", "fork")
    expect(manifest.get("upstream", {}).get("repository"), "NixOS/nix", "upstream")

    pin = manifest["fleetPin"]
    commit = pin["commit"]
    expect(git(args.source, "rev-parse", "HEAD"), commit, "source commit")
    expect(git(args.source, "rev-parse", f"{pin['tag']}^{{}}"), commit, "tag target")
    expect(git(args.source, "rev-parse", pin["tag"]), pin["tagObject"], "tag object")
    expect(git(args.source, "show", "-s", "--format=%T", commit), pin["tree"], "tree")
    expect((args.source / ".version").read_text().strip(), pin["version"], "version")
    expect(sha256(args.source / "flake.lock"), pin["flakeLockSha256"], "source lock")

    source_lock = load_json(args.source / "flake.lock")
    for name, expected_input in pin["flakeInputs"].items():
        locked = source_lock["nodes"][name]["locked"]
        expect(locked.get("rev"), expected_input["revision"], f"source lock {name} rev")
        expect(locked.get("narHash"), expected_input["narHash"], f"source lock {name} narHash")

    control = manifest["control"]
    if not re.fullmatch(r"[0-9a-f]{40}", control["commit"]):
        fail("control commit is not a full Git SHA")
    for relative, expected_digest in control["files"].items():
        if not re.fullmatch(r"[0-9a-f]{64}", expected_digest):
            fail(f"control file digest is invalid: {relative}")
    if not re.fullmatch(r"[0-9a-f]{64}", control["canonicalPolicySha256"]):
        fail("canonical policy digest is invalid")

    if args.control is None:
        print(f"fleet_nix_commit={commit}")
        print(f"fleet_nix_version={pin['version']}")
        print(f"source_flake_lock_sha256={pin['flakeLockSha256']}")
        print(f"control_commit={control['commit']}")
        print("private_control=declared-digest-only")
        print("fleet_pin_contract=verified")
        return

    expect(git(args.control, "rev-parse", "HEAD"), control["commit"], "control commit")
    for relative, expected_digest in control["files"].items():
        expect(sha256(args.control / relative), expected_digest, f"control file {relative}")

    policy = load_json(args.control / "config/upstream-promotion-policy.json")
    bootstrap = load_json(args.control / "config/nix-bootstrap.json")
    inputs = load_json(args.control / "config/nix-integration-inputs.json")
    control_lock = load_json(args.control / "flake.lock")
    candidate = load_json(args.control / "promotion/candidate.json")

    policy_pin = one(policy["sources"], "id", "nix")
    expect(policy_pin.get("acquisition"), "fork", "policy acquisition")
    expect(policy_pin.get("upstream"), manifest["upstream"]["repository"], "policy upstream")
    expect(policy_pin.get("repository"), manifest["fork"], "policy fork")
    expect(policy_pin.get("version"), pin["version"], "policy version")
    expect(policy_pin.get("commit"), commit, "policy commit")

    installer_pin = bootstrap["binaryTarballInstaller"]
    expect(bootstrap.get("nixVersion"), pin["version"], "bootstrap version")
    expect(installer_pin.get("repository"), manifest["fork"], "bootstrap repository")
    expect(installer_pin.get("commit"), commit, "bootstrap commit")
    expect(bootstrap.get("embeddedNixPayload"), True, "embedded Nix payload")

    candidate_pin = one(candidate["sourceSnapshots"], "id", "nix")
    expect(candidate_pin.get("repository"), manifest["fork"], "candidate repository")
    expect(candidate_pin.get("version"), pin["version"], "candidate version")
    expect(candidate_pin.get("commit"), commit, "candidate commit")

    policy_digest = canonical_digest(policy)
    expect(policy_digest, control["canonicalPolicySha256"], "canonical policy digest")
    expect(candidate.get("policySha256"), policy_digest, "candidate policy digest")
    graph = candidate["deviceGraph"]
    expect(
        graph["flakeLock"]["sha256"],
        control["files"]["flake.lock"],
        "candidate Dotfiles lock digest",
    )
    expect(
        graph["nixIntegrationInputs"]["sha256"],
        control["files"]["config/nix-integration-inputs.json"],
        "candidate integration-input digest",
    )

    activation = inputs["activation"]
    expect(activation.get("allowLockMutation"), False, "lock mutation policy")
    expect(activation.get("allowRegistryLookup"), False, "registry lookup policy")
    expect(activation.get("acceptFlakeConfig"), False, "flake config policy")
    for name, expected_input in inputs["inputs"].items():
        locked = control_lock["nodes"][name]["locked"]
        expect(locked.get("url"), expected_input["url"], f"control lock {name} url")
        expect(locked.get("narHash"), expected_input["narHash"], f"control lock {name} narHash")
        if expected_input["revision"] not in expected_input["url"]:
            fail(f"control input {name} URL does not contain its exact revision")

    print(f"fleet_nix_commit={commit}")
    print(f"fleet_nix_version={pin['version']}")
    print(f"source_flake_lock_sha256={pin['flakeLockSha256']}")
    print(f"control_commit={control['commit']}")
    print(f"control_policy_sha256={policy_digest}")
    print("fleet_pin_contract=verified")


if __name__ == "__main__":
    main()
