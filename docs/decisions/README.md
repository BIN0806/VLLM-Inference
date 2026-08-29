# Architecture decision records

ADRs explain why the system has its current shape. They are not transcripts of
an agent's private reasoning. They preserve the context and tradeoffs another
engineer would need to review, operate, or defend the design.

The completed system and claim matrix are in
[Final project status](../project-status.md).

## Index

| ADR | Decision | Final state |
|---|---|---|
| [0001](0001-primary-deployment-profile.md) | Remote NVIDIA profiles; Mac is authoring only | Exercised through Phase 4 |
| [0002](0002-baseline-models-and-revisions.md) | Pinned 1.5B AWQ baseline and 9B topology model | Both exercised |
| [0003](0003-dependency-version-policy.md) | Immutable versions and digests | Live pins recorded; KubeRay is a future goal |
| [0004](0004-autoscaling-boundary.md) | Scale complete replicas; durable front door at zero | 1→2 and 0→1 proven separately |
| [0005](0005-trust-remote-code.md) | Keep remote model code disabled | Preserved |
| [0006](0006-phase3-1.5b-disk-exception.md) | Narrow disk exception for one Phase 3 profile | Exercised once; not a general policy change |
| [0007](0007-phase4-replica-storage-and-observability-order.md) | Per-ordinal cache PVCs; observe before scaling | Exercised |
| [0008](0008-phase4b-keda-waiting-queue.md) | Scale 1→2 on total waiting work | Exercised |
| [0009](0009-phase4c-http-interceptor-scale-to-zero.md) | Use HTTP interceptor for 0→1 | Exercised as a single-node lab |

## Required sections

Every consequential ADR should contain:

1. **Status** — proposed, accepted, superseded, or rejected, including the gate.
2. **Context** — the constraint or problem that forced a choice.
3. **Decision** — the chosen behavior and its boundary.
4. **Alternatives considered** — at least the credible alternatives and why
   they were not selected for this gate.
5. **Evidence** — measurements, logs, documentation, or acceptance results that
   support the decision. Mark estimates as estimates.
6. **Consequences** — benefits, costs, risks, follow-up work, and claim limits.

## When an ADR is required

- Changing model, image, revision, CUDA, chart, or infrastructure pins.
- Changing TP, PP, Ray, replica, scheduling, storage, or autoscaling topology.
- Accepting a hardware exception or security exception.
- Enabling remote model code, public networking, credential transport, or TLS
  overrides.
- Choosing an autoscaling signal or changing the scale-to-zero boundary.
- Adopting a workaround that changes supported modalities, context, batching,
  memory use, or failure behavior.

Operational commands belong in runbooks. Raw logs and rental-specific details
belong in gitignored artifacts. System-level topology belongs in
`docs/architecture.md`.
