"""Offline audit of the original run, including preserved failures and cleanup.

Does not contact Kubernetes, read credentials, or convert unavailable cells to PASS.
Usage: python3 acceptance/real_backends/verify_evidence.py /path/to/lane
"""
import hashlib
import json
from pathlib import Path
import re
import sys


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_source(proof):
    require(proof['matches'] is True, 'installed source mismatch')
    require(proof['expected'] and proof['expected'] == proof['actual'], 'source bytes differ')
    require(all(re.fullmatch('[0-9a-f]{64}', x) for x in proof['actual'].values()), 'invalid source hash')


def check_images(proof, wanted):
    require(bool(proof['pod_uid']), 'missing pod UID')
    actual = {row['container']: row for row in proof['images']}
    for container, reference in wanted.items():
        require('@sha256:' in reference, 'image not digest pinned')
        require(actual[container]['image'] == reference, 'wrong requested image')
        require(actual[container]['image_id'].endswith(reference.split('@')[1]), 'wrong running digest')


def check_restart(proof, uid, gateway=False):
    require(proof['passed'] is True and proof['pod_uid'] == uid, 'restart pod UID mismatch')
    before, after = ('restart_before', 'restart_after') if gateway else ('before', 'after')
    require(proof[after] > proof[before], 'restart not observed')
    require(proof['state_bytes_equal'] is True if gateway else proof['same_emptydir_data'] is True,
            'persisted state changed')


def check_phase(receipt, family, mode, phase):
    require(receipt['passed'] is True, 'failed phase selected')
    require((receipt['family'], receipt['mode'], receipt['phase']) == (family, mode, phase), 'wrong phase')
    if phase in ('denied', 'child-denied', 'final-denied'):
        require(receipt['native_state_unchanged'] is True, 'denied write changed state')
        require(receipt['native_before'] == receipt['native_after'], 'denial oracle mismatch')
        require(receipt.get('rpc_error') == -32602 or receipt.get('isError') is True,
                'missing denial error envelope')
        # Earliest Odoo denied receipts predate the reason assertion. The later
        # strict child/final-denied receipts remain mandatory, not inferred.
        if phase != 'denied':
            require(receipt.get('expected_denial_reason') is True, 'unexpected denial error')
    if phase == 'error':
        require(receipt['native_state_unchanged'] is True and receipt.get('expected_error_reason') is True,
                'wrong error or changed backend state')
    if phase == 'create':
        require(receipt['write_read_passed'] is True, 'no permitted write/read proof')
    if phase == 'verify':
        require(receipt['updated_value_read'] is True, 'updated value not read')
    if phase == 'cleanup':
        require(receipt['owned_record_removed'] is True, 'owned record not cleaned')
        native = receipt['native_after']
        require(native['rows'] == [] if family == 'odoo' else native['status'] == 404,
                'native record still exists')


def check_spec(spec):
    require(spec['automountServiceAccountToken'] is False, 'service account token mounted')
    require(not spec.get('hostNetwork') and not spec.get('hostPID'), 'host namespace exposed')
    require(all(set(v) <= {'name', 'secret', 'emptyDir'} for v in spec['volumes']), 'unowned volume')
    for c in spec['containers']:
        require(c['securityContext']['allowPrivilegeEscalation'] is False, 'privilege escalation')
        require(c['securityContext']['capabilities']['drop'] == ['ALL'], 'capabilities retained')


def verify(lane):
    evidence = lane / 'evidence'
    images = read(Path(__file__).with_name('images.json'))
    cells = []
    # The first Nextcloud attempt completed HA before the authenticated PaaS pull.
    roots = [('odoo', 'ha', evidence), ('odoo', 'paas', evidence),
             ('nextcloud', 'ha', evidence / 'nextcloud-ha-attempt1'),
             ('nextcloud', 'paas', evidence), ('emqx', 'ha', evidence)]
    for family, mode, root in roots:
        acceptance = read(root / (family + '-acceptance.json'))
        require(acceptance['passed'] and acceptance['owned_records_cleaned'], 'incomplete acceptance')
        require(acceptance['haos'] is False, 'synthetic identity claimed HAOS')
        require(mode in acceptance['modes'], 'mode not accepted')
        runtime = read(root / (family + '-runtime-images.json'))
        check_images(runtime, {'backend': images[family], mode: images[mode + '_' + family]})
        check_spec(read(root / (family + '-pod-spec.json'))['spec'])
        source = read(root / (family + '-' + mode + '-source-proof.json'))
        check_source(source)
        require(source['source'] == ('28b8317ec12c47c81c946fe9aaec18dd1d5ad852' if mode == 'ha'
                                    else 'f748090eb782bc103edcd99ac9aa821f77294fb0'), 'wrong release source')
        restart = root / (family + '-restart.json')
        gateway = root / (family + '-' + mode + '-gateway-restart.json')
        check_restart(read(restart), runtime['pod_uid'])
        check_restart(read(gateway), runtime['pod_uid'], gateway=True)
        selected = {}
        phases = ['configure', 'denied', 'enable', 'create', 'update', 'error', 'verify',
                  'cleanup', 'revoke', 'final-denied'] + (['child-denied'] if family == 'odoo' else [])
        for phase in phases:
            paths = sorted(p for p in root.glob(f'{family}-{mode}-{phase}-*.json')
                           if re.search(r'-[0-9]+\.json$', p.name) and read(p).get('passed') is True)
            require(bool(paths), 'missing successful phase: ' + family + '/' + mode + '/' + phase)
            if phase not in ('verify', 'final-denied'):
                paths = paths[-1:]
            for p in paths:
                check_phase(read(p), family, mode, phase)
            selected[phase] = [str(p.relative_to(evidence)) for p in paths]
            if phase == 'verify':
                require(len(paths) >= 2, 'missing pre/post restart reads')
                require(paths[0].stat().st_mtime_ns < restart.stat().st_mtime_ns < paths[-1].stat().st_mtime_ns,
                        'no read on both sides of backend restart')
            if phase == 'final-denied':
                require(paths[-1].stat().st_mtime_ns > gateway.stat().st_mtime_ns, 'no denial after gateway restart')
        cleaned = read(root / (family + '-family-cleanup.json'))
        require(cleaned['passed'] and cleaned['pod_absent'] and cleaned['owned_secret_absent'], 'family not cleaned')
        require(cleaned['pod_uid'] == runtime['pod_uid'], 'wrong family cleanup UID')
        cells.append({'family': family, 'mode': mode, 'status': 'passed', 'phases': selected,
                      'pod_uid': runtime['pod_uid'], 'release_source': source['source'],
                      'image': images[mode + '_' + family], 'haos': False})
    baseline = sorted(evidence.glob('odoo-native-baseline-*.json'))
    restored = sorted(evidence.glob('odoo-native-restored-*.json'))
    require(read(baseline[0]) == read(restored[-1]), 'full Odoo partner table not restored')
    gap = read(evidence / 'paas-emqx-gap.json')
    require(gap['tested'] is False and 'emqx' not in gap['released_products'], 'PaaS gap misrepresented')
    cells.append({'family': 'emqx', 'mode': 'paas', 'status': gap['status'], 'tested': False})
    cleaned = sorted(p for p in evidence.glob('cleanup-*.json') if re.fullmatch(r'cleanup-[0-9]+\.json', p.name))
    require(bool(cleaned), 'namespace cleanup missing')
    final = read(cleaned[-1])
    require(all(final[k] is True for k in ['passed', 'namespace_absent', 'pv_claims_absent',
                                         'owned_secrets_removed', 'node_ready']), 'cleanup failed')
    require(read(evidence / 'watchdog-exit.json')['namespace_absent'] is True, 'watchdog not exited')
    files = sorted(evidence.rglob('*.json'))
    failed = [str(p.relative_to(evidence)) for p in files if read(p).get('passed') is False]
    disposition = read(lane / 'failure-dispositions.json')
    require(set(failed) == set(disposition), 'unaccounted failed attempt')
    for name, value in disposition.items():
        require(value.get('classification') and value.get('explanation') and value.get('recovery_evidence'),
                'missing failure disposition: ' + name)
        require(all((evidence / ref).is_file() for ref in value['recovery_evidence']), 'missing recovery evidence')
    return {'passed': True, 'tested_cells_passed': 5, 'unavailable_cells': 1, 'all_six_passed': False,
            'cells': cells, 'preserved_failed_attempts': failed, 'cleanup': final,
            'evidence_sha256': {str(p.relative_to(evidence)): sha(p) for p in files},
            'failure_dispositions_sha256': sha(lane / 'failure-dispositions.json'),
            'ordering_basis': 'preserved local receipt modification times; no cryptographic timestamp claim',
            'haos': False, 'persistence_scope': 'container restart in same pod/emptyDir; no PVC/reschedule claim'}


if __name__ == '__main__':
    print(json.dumps(verify(Path(sys.argv[1])), indent=2))
