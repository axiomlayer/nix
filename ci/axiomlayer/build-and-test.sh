#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 5 ]]; then
  echo "usage: build-and-test.sh SOURCE COMMIT VERSION SYSTEM LOCK_SHA256|auto" >&2
  exit 2
fi

source_dir=$(cd "$1" && pwd)
expected_commit=$2
expected_version=$3
expected_system=$4
expected_lock_sha=$5

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{ print $1 }'
  else
    shasum -a 256 "$1" | awk '{ print $1 }'
  fi
}

actual_commit=$(git -C "$source_dir" rev-parse HEAD)
[[ "$actual_commit" == "$expected_commit" ]] || {
  echo "source commit mismatch: expected $expected_commit, got $actual_commit" >&2
  exit 1
}

actual_version=$(tr -d '\r\n' < "$source_dir/.version")
[[ "$actual_version" == "$expected_version" ]] || {
  echo "source version mismatch: expected $expected_version, got $actual_version" >&2
  exit 1
}

bootstrap_version=$(nix --version | awk '{ print $NF }')
[[ "$bootstrap_version" == "2.35.2" ]] || {
  echo "bootstrap Nix mismatch: expected 2.35.2, got $bootstrap_version" >&2
  exit 1
}

actual_system=$(nix eval --raw --impure --expr builtins.currentSystem)
[[ "$actual_system" == "$expected_system" ]] || {
  echo "native system mismatch: expected $expected_system, got $actual_system" >&2
  exit 1
}

lock_before=$(sha256_file "$source_dir/flake.lock")
if [[ "$expected_lock_sha" != auto && "$lock_before" != "$expected_lock_sha" ]]; then
  echo "flake.lock mismatch: expected $expected_lock_sha, got $lock_before" >&2
  exit 1
fi

flake="path:$source_dir"
nix flake metadata \
  --no-update-lock-file \
  --json \
  "$flake" >/dev/null
nix flake check \
  --no-build \
  --no-update-lock-file \
  --no-write-lock-file \
  "$flake"

out=$(nix build \
  --no-link \
  --print-out-paths \
  --no-update-lock-file \
  --no-write-lock-file \
  "$flake#packages.$expected_system.nix")

[[ -x "$out/bin/nix" ]] || {
  echo "built output has no executable nix: $out" >&2
  exit 1
}

built_version=$("$out/bin/nix" --version | awk '{ print $NF }')
[[ "$built_version" == "$expected_version" ]] || {
  echo "built Nix mismatch: expected $expected_version, got $built_version" >&2
  exit 1
}

[[ "$("$out/bin/nix" eval --raw --expr 'toString (1 + 1)')" == 2 ]]

lock_after=$(sha256_file "$source_dir/flake.lock")
[[ "$lock_after" == "$lock_before" ]] || {
  echo "build mutated flake.lock: before $lock_before, after $lock_after" >&2
  exit 1
}

git -C "$source_dir" diff --exit-code -- flake.lock
printf 'source_commit=%s\n' "$actual_commit"
printf 'source_version=%s\n' "$actual_version"
printf 'native_system=%s\n' "$actual_system"
printf 'source_flake_lock_sha256=%s\n' "$lock_after"
printf 'built_output=%s\n' "$out"
printf 'integration_result=accepted\n'
