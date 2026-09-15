# AxiomLayer Nix integration

This fork is an integration boundary, not a second Nix release authority.
The fleet pin is declared in `fleet-pin.json`. Its committed digests were
verified against the exact policy, bootstrap contract, candidate, and flake
lock from `AxiomLayer/dotfiles` pull request 49 at the recorded commit.

The active workflow has read-only repository permissions. It does not use
environments, secrets, OIDC, attestations, artifact uploads, package writes,
release APIs, publisher credentials, or a token capable of reading the private
Dotfiles repository. Every external action is pinned to a full commit SHA.

The four workflows inherited from `NixOS/nix` are retained byte-for-byte in
`.github/upstream-workflows` so upstream history remains reviewable while those
workflows are inert in this fork. `verify_workflows.py` refuses any additional
file under `.github/workflows` and checks the archived bytes.

The lane has two duties:

1. Build and run the tests included by `packages.<system>.nix` for Nix 2.35.2 at
   commit `2c73b59da29606068c0c98db015dd3a66955525d` on native Linux x86_64,
   Linux ARM64, macOS Intel, and macOS ARM64 runners. Evaluation is scoped to
   that native package and lock mutation is disabled; unrelated Hydra jobsets
   are deliberately outside this integration contract.
2. On the schedule or an explicit dispatch, resolve `NixOS/nix` `master` once
   to a full commit SHA and run the same native build/test contract. This is an
   alarm for an upstream change that the fleet's pinned Nix cannot build; it is
   never a promotion or publication path.

Update `fleet-pin.json` only after the corresponding Dotfiles promotion policy
and candidate are updated. The public hosted lane validates the committed
digests without private-repository access. Before proposing a refresh, run
`ci/axiomlayer/test-contracts.sh` with clean checkouts of this repository, the
pinned Nix source, and the pinned private Dotfiles control commit; supplying
that third checkout turns on the cross-repository verification.
