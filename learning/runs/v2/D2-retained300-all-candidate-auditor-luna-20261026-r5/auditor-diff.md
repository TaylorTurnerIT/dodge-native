# Retained300 auditor rebinding

Reuses the accepted retained276 all-candidate auditor structure and binds it to frozen registration `8a60dc80f1ebe03c43bf18eebf75199e14f207b677570ac2d6d4368ddfcb0f79`.

- Audits updates 300, 312, 324, 336, 348, and 360; cumulative updates must begin at 348 and end at 408.
- Requires LR `3e-5` unchanged. No new LR-transition artifact or historical LR-transition audit is required.
- Binds entry300 model, Adam, and RNG exactly to selected checkpoint `e2c8fbe4…214710`; validates every candidate identity, optimizer LR, counter chain, progress, next episode indices, journal prefix, and raw-frame conservation.
- Checks each 64-row evaluation cohort, JSON/JSONL conservation, boundary flags, death causes, survival means, score summaries, and pinned runner performance. Best candidate is max mean survival including entry300. No score/competence threshold applies; endpoint360 need not win.
- Full mode reuses frozen launcher `validate_outputs`, then independently checks observer raw exits, resources, wall, process/group absence, source/cache postflight, publication-failure absence, observer source and instantiation hashes.
- Parent retains authority for lease release, final publication absence, and acceptance. Every candidate remains provisional; auditor cannot change best or lease.

No retained300 continuation outputs were read. No full candidate audit ran.
