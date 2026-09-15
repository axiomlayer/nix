# Inert upstream workflows

These are byte-for-byte copies of the workflows inherited from `NixOS/nix`.
GitHub only executes workflow files directly under `.github/workflows`, so this
directory preserves upstream history without importing NixOS backport, label,
CI, release, signing, environment, or publisher authority into AxiomLayer.

The expected file set and SHA-256 digests live in
`.github/axiomlayer/fleet-pin.json`. The active integration workflow fails if an
archived file changes or another executable workflow appears.
