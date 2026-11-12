"""Reject false acceptance claims at the evidence boundary; no live credentials."""
import copy
import unittest
from verify_evidence import check_images, check_phase, check_restart, check_source


class EvidenceBoundaryTests(unittest.TestCase):
    def test_source_flag_cannot_hide_changed_installed_bytes(self):
        proof = {'matches': True, 'expected': {'gateway.py': 'a' * 64}, 'actual': {'gateway.py': 'b' * 64}}
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            check_source(proof)
        proof['actual'] = copy.deepcopy(proof['expected'])
        check_source(proof)

    def test_requested_digest_cannot_hide_different_running_image(self):
        image = 'registry/product@sha256:' + 'a' * 64
        proof = {'pod_uid': 'owned', 'images': [{'container': 'ha', 'image': image, 'image_id': 'sha256:' + 'b' * 64}]}
        with self.assertRaisesRegex(ValueError, 'running digest'):
            check_images(proof, {'ha': image})

    def test_tag_only_is_not_exact_image_evidence(self):
        with self.assertRaisesRegex(ValueError, 'digest pinned'):
            check_images({'pod_uid': 'owned', 'images': []}, {'ha': 'image:latest'})

    def test_denial_flag_cannot_hide_native_mutation(self):
        proof = {'passed': True, 'family': 'nextcloud', 'mode': 'ha', 'phase': 'denied',
                 'native_state_unchanged': True, 'expected_denial_reason': True,
                 'native_before': {'status': 404}, 'native_after': {'status': 200}}
        with self.assertRaisesRegex(ValueError, 'oracle mismatch'):
            check_phase(proof, 'nextcloud', 'ha', 'denied')

    def test_cleanup_flag_cannot_hide_remaining_record(self):
        proof = {'passed': True, 'family': 'emqx', 'mode': 'ha', 'phase': 'cleanup',
                 'owned_record_removed': True, 'native_after': {'status': 200}}
        with self.assertRaisesRegex(ValueError, 'still exists'):
            check_phase(proof, 'emqx', 'ha', 'cleanup')

    def test_restart_requires_same_uid_and_increased_count(self):
        proof = {'passed': True, 'pod_uid': 'owned', 'before': 1, 'after': 2, 'same_emptydir_data': True}
        check_restart(proof, 'owned')
        with self.assertRaisesRegex(ValueError, 'UID mismatch'):
            check_restart(proof, 'replacement')
        proof['after'] = 1
        with self.assertRaisesRegex(ValueError, 'not observed'):
            check_restart(proof, 'owned')


if __name__ == '__main__':
    unittest.main()
