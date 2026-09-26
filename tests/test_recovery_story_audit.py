import json

from scripts.audit_recovery_story import audit


def test_recovery_audit_requires_completed_artifacts_and_preserved_failure(tmp_path):
    root = tmp_path
    source = root / 'outputs' / 'review_source'
    recovery = root / 'outputs' / 'delivery_recovery' / 'review_recovery'
    source.mkdir(parents=True)
    recovery.mkdir(parents=True)
    pdf = recovery / 'report.pdf'
    pdf.write_bytes(b'%PDF-1.7\n')
    (source / 'run.json').write_text(json.dumps({'status': 'failed'}))
    (source / 'citation-review.json').write_text(json.dumps({
        'status': 'incomplete', 'gaps': [{'line_id': 1}]}))
    (recovery / 'recovery.json').write_text(json.dumps({
        'source_review': str(source.resolve()), 'mode': 'saved_citation_checkpoint',
        'resumed_from': 'citation_agent', 'status': 'completed',
        'authenticated_end_to_end': False, 'model_calls': 4,
        'paths': {'latex_pdf': str(pdf.relative_to(root))}}))
    (recovery / 'citation-review.json').write_text(json.dumps({
        'status': 'completed', 'gaps': []}))

    result = audit(source, recovery, root=root)
    assert result['accepted']
    assert result['original_gaps'] == 1
    assert result['recovered_gaps'] == 0
    assert result['recovery_model_calls'] == 4

    (source / 'run.json').write_text(json.dumps({'status': 'completed'}))
    assert not audit(source, recovery, root=root)['accepted']
    (source / 'run.json').write_text(json.dumps({'status': 'failed'}))
    pdf.unlink()
    assert not audit(source, recovery, root=root)['accepted']
