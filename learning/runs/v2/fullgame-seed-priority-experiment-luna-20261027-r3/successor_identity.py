"""Matched learner identity for the full-game static-priority ablation."""
import contracts as c

NEURAL_INPUTS = ("global_feats","entity_feats","entity_types","entity_mask")

def learner_identity(reg,registration_sha):
    return dict(schema="dodge_fullgame_seed_priority_learner_identity_v1",study_id=c.STUDY,
        run_id=reg["run_id"],pair_id=reg["pair_id"],replica=reg["replica"],arm=reg["arm"],
        backend=reg["backend"],parent_lineage=dict(checkpoint_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256,
            receipt_sha256=c.references.PARENT_RECEIPT_SHA256,phase_update=324,cumulative_update=372,
            fingerprints=dict(c.transition.EXPECTED_PARENT)),
        successor_runtime=dict(runtime_manifest_sha256=reg["runtime_manifest_sha256"],
            source_manifest_sha256=reg["source_manifest_sha256"],runtime_versions=reg["runtime_versions"]),
        registration_sha256=registration_sha,shared_config=reg["shared_config"],seed_vector=reg["vector"],
        training_pool_sha256=reg["training_pool_sha256"],slot_stream_sha256=reg["slot_stream_sha256"],
        native_seed_mode="evaluation_explicit_seed_list",training_pool_role="training_only",
        exclusion_union=reg["exclusion_union"],neural_inputs=list(NEURAL_INPUTS),schedule=reg["schedule"])

def matched_pair(left,right):
    c.need(left["replica"]==right["replica"] and left["arm"]==c.ARMS[0] and right["arm"]==c.ARMS[1],
           "one fixed uniform/priority pair required")
    allowed=set(c.PAIR_DIFF_FIELDS)
    differences={key for key in set(left)|set(right) if left.get(key)!=right.get(key)}
    c.need(differences<=allowed,"matched experiment differs beyond arm and owned run identifiers: "+str(sorted(differences-allowed)))
    return sorted(differences)
