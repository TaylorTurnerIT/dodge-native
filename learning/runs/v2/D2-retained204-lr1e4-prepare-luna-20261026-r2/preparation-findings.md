# r2 preparation findings

- Frozen r1 review found helper import was not pin-bound before execution, optimizer digest timing was invalid, and copied checkpoint optimizer LR was unchecked.
- r2 verifies every registration pin, checks helper path and digest binding, then executes only exact bytes read from that bound path. Runner has no ordinary helper import.
- Actual BEST204 model and Adam restore passed on CPU. Immutable pre-override hashes detect an injected Adam moment mutation. Serialized optimizer LR check detects a changed copied checkpoint group.
- All seven embedded checkpoints, update counters, resume indices, and evaluation bindings are checked by the parent-owned output validator.
- CPU-only preparation used no MPS, environment, game-weight step, launch, lease installation, or sampling RNG restore. Actual worker must restore full MPS RNG before environment construction.
- Haiku's final review of actual frozen r1 source was absent at candidate freeze. Parent review, lease, full preflight, and one launch remain parent gates.
