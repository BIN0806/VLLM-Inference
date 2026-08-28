# Ray (not deployed in Phase 0)

- `ray-single-host`: Ray executor on one physical host. Not multi-node.
- `ray-multinode`: requires at least two independently scheduled Linux GPU machines.

Current status for multi-node: **NOT RUN — HARDWARE UNAVAILABLE**.

Do not add Ray to the single-GPU path just to tick a box. Do not scale Ray workers independently of a complete TP/PP replica.

Pinned KubeRay operator: 1.7.0 (`configs/pins.yaml`). Installation is a later phase.
