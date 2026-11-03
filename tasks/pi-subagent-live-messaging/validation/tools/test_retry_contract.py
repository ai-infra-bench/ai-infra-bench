"""Local retry fixture regressions; full Pi retry behavior needs the real trial."""
import json
from pathlib import Path
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))
from verify import Case, CASES, make_handler

class RetryContract(unittest.TestCase):
    def test_existing_inventory_and_retry_cases_coexist(self):
        self.assertEqual(len(CASES),32)
        self.assertTrue({'queued_steering_ordered','broadcast_pressure','transport_fault','retry_recovery','retry_exhausted'} <= set(CASES))

    def test_http_503_is_bound_before_failure_and_records_exact_native_input(self):
        case=Case('retry_exhausted');case.pids[('one','C')]=321
        observed=[]
        class Runtime:
            def consume_provider_request(self,pid,raw): observed.append((pid,raw))
        case.runtime=Runtime()
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(case))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        body={'messages':[{'role':'user','content':'private original context'}]}
        raw=json.dumps(body).encode()
        try:
            for _ in range(3):
                req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/faux',data=raw,headers={'X-Pi-Test-Pid':'321'})
                with self.assertRaises(urllib.error.HTTPError) as raised:urllib.request.urlopen(req)
                self.assertEqual(raised.exception.code,503)
                self.assertIn(b'503 server overloaded',raised.exception.read())
            self.assertEqual(observed,[(321,raw)]*3)
            self.assertEqual([r['body'] for r in case.failed_provider_requests],[body]*3)
            self.assertEqual(case.steps,{}) # failed attempts do not consume model-script steps
            self.assertFalse(case.errors or case.infrastructure_errors)
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_recovery_fails_only_one_correct_worker_request(self):
        case=Case('retry_recovery');case.pids[('one','B')]=321
        self.assertFalse(case.provider_failure(321,{}))
        case.steps[('one','B')]=1
        self.assertFalse(case.provider_failure(654,{}))
        self.assertTrue(case.provider_failure(321,{}))
        self.assertFalse(case.provider_failure(321,{}))

    def test_exhausted_recipient_is_invalid_but_healthy_peer_is_still_targeted(self):
        case=Case('retry_exhausted')
        # Discovery supplies the actual public IDs; no role alias repair.
        case.discovered[('one','A')]=list(case.ids.values())
        plan=case.plan_sender('one')
        self.assertEqual(plan[0][0],'finished')
        self.assertEqual(plan[0][1]['to'],case.ids['C'])
        self.assertEqual(plan[1][1]['to'],case.ids['B'])

    def test_retry_error_cannot_pass_without_actual_error_turn(self):
        case=Case('retry_exhausted');case.pids[('one','C')]=321
        for _ in range(3):case.provider_failure(321,{})
        with self.assertRaisesRegex(AssertionError,'missing real error turn'):case.check_retry()

    def test_false_broadcast_is_not_a_mandatory_rejection_fixture(self):
        case=Case('malformed')
        case.discovered[('one','A')]=list(case.ids.values())
        plan=case.plan_sender('one')
        invalid=[args for purpose,args in plan if purpose=='invalid']
        self.assertIn({'to':'','broadcast':True,'message':'ambiguous-empty-to'},invalid)
        self.assertFalse(any(args.get('broadcast') is False for args in invalid))

if __name__=='__main__':unittest.main()
