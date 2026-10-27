# Confirmed 324 source binding repair R4

R4 repairs the remaining source-binding blocker from the R3 independent review. The builder hashes pinned checkpoint, identity, and runner bytes once, compiles definitions without executing modules, and compares loaded functions against those definitions. It checks nested code, constants, instructions, names, arguments, flags, exception tables, source paths, namespace ownership, raw API defaults, the pure `require` dependency, and driver-verified module object identity.

Tests compile only selected AST definitions. They reject same-filename substitutions for `capture_rng`, `restore_learner`, `restore_rng`, `require_complete_update`, and `worker`, mutated defaults, and substituted helper/runtime dependencies. The caller-supplied `capture_module_hash` remains accepted for compatibility but is ignored as proof.

Trust boundary: the future driver must authenticate how checkpoint/runner modules were loaded and verify the provenance of the `copy`, `random`, `numpy`, and `torch` objects already present in `sys.modules`. This builder confirms module object identity only. It does not establish launch authority or runtime readiness.

Frozen transition, claim, fingerprint, RNG reference, and transition-test utilities were copied unchanged from R3. Accepted 324 fingerprints, cumulative 372, saved LR `3e-5`, controllers 373..432, parent receipt SHA `76cb15733e87518cb3b473b7f8ebd847ed206351fb9f17d89b8b92e6bf853f08`, and confirmed acceptance SHA `3e84979c4c8da76d0f98666a23f90eb15c1e813ca5edf1001e19daebaf4d5bbd` remain as previously established. Real RNG reference remains `pending_notrun`.

No MPS/game/environment imports, real RNG reads, production checkpoint deserialization, callbacks against a real checkpoint, launches, training, or evaluation occurred. Independent review and all parent registration/reference gates remain pending.
