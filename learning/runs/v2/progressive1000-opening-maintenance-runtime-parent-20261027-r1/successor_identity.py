"""Study identity: accepted parent lineage and new runtime are separate fields."""
import contracts as c

NEURAL_INPUTS = ('global_feats','entity_feats','entity_types','entity_mask')


def learner_identity(reg,registration_sha):
    return dict(schema='progressive1000_shared_learner_identity_v1',study_id=c.STUDY,
        run_id=reg['run_id'],pair_id=reg['pair_id'],replica=reg['replica'],arm=reg['arm'],
        curriculum_enabled=reg['curriculum_enabled'],backend=reg['backend'],
        parent_lineage=dict(checkpoint_sha256=c.references.ACCEPTED_CHECKPOINT_SHA256,
            receipt_sha256=c.references.PARENT_RECEIPT_SHA256,phase_update=324,cumulative_update=372,
            fingerprints=dict(c.transition.EXPECTED_PARENT)),
        successor_runtime=dict(runtime_manifest_sha256=reg['runtime_manifest_sha256'],
            source_manifest_sha256=reg['source_manifest_sha256'],runtime_versions=reg['runtime_versions']),
        registration_sha256=registration_sha,shared_config=reg['shared_config'],
        seed_vector=reg['vector'],exclusion_union=reg['exclusion_union'],
        neural_inputs=list(NEURAL_INPUTS),schedule=reg['schedule'])


def matched_pair(left,right):
    """Only arm, enablement, run identity and externally pinned claim/output differ."""
    c.need(left['replica']==right['replica'] and left['arm']==c.ARMS[0] and right['arm']==c.ARMS[1],
           'one fixed control/curriculum pair required')
    allowed={'arm','curriculum_enabled','run_id','output','attempt_claim_path','launch_marker_path'}
    differences={key for key in set(left)|set(right) if left.get(key)!=right.get(key)}
    c.need(differences<=allowed,'matched configuration differs beyond enablement/declared identifiers: '+str(sorted(differences-allowed)))
    c.need(left['curriculum_enabled'] is False and right['curriculum_enabled'] is True,'pair enablement differs')
    return sorted(differences)
