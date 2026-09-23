"""Coordinator contract regressions. Actual Pi controls exercise the integration."""
import json
from pathlib import Path
import sys
import threading
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tests'))
from verify import Case

class SchedulerContractTests(unittest.TestCase):
    def test_results_preserve_public_ids(self):
        case = Case('direct')
        raw = {'self':case.ids['A'], 'members':[{'id':case.ids['B']}], 'accepted':[case.ids['B']], 'failed':[]}
        self.assertEqual(case.last_result([{'role':'tool','content':json.dumps(raw)}]), raw)

    def test_call_does_not_repair_an_incorrect_public_address(self):
        case = Case('direct')
        call = case.tool('team_send', {'to':'B','message':'body'})
        self.assertEqual(json.loads(call['function']['arguments'])['to'], 'B')

    def test_native_error_needs_no_second_error_event(self):
        case=Case('invalid_recipient')
        self.assertTrue(case.events_error([{'role':'tool','tool_call_id':'bad','isError':True,'content':'Invalid recipient'}]))

    def test_ordinary_tool_finishes_without_send_results(self):
        case=Case('ordered')
        values=[]
        worker=threading.Thread(target=lambda: values.append(case.work('one','B','slow_work')),daemon=True)
        worker.start();worker.join(2)
        finished=not worker.is_alive()
        with case.condition:
            case.closed=True;case.condition.notify_all()
        worker.join(1)
        self.assertTrue(finished, 'external work must not wait for all sends to return')
        self.assertEqual(values,['External work completed normally.'])

    def root_call(self,name):
        case=Case(name);case.pids[('one','ROOT')]=123
        result=case.respond({'messages':[],'tools':[{'function':{'name':'subagent'}}]},123)
        return json.loads(result['tool_calls'][0]['function']['arguments'])

    def test_legacy_parallel_has_no_new_required_fields(self):
        args=self.root_call('plain_parallel')
        self.assertNotIn('communication',args)
        self.assertTrue(all('id' not in t for t in args['tasks']))

    def ledger_case(self):
        case = Case('ordered')
        case.request_context.actor = ('one', 'A')
        calls = [case.tool('team_send', {'to':case.ids['B'], 'message':body}) for body in case.payloads['one']]
        for call in calls:
            case.record_result('one', 'A', call['id'], 'team_send', {'content':[{'type':'text','text':json.dumps({'accepted':[case.ids['B']], 'failed':[]})}]})
        return case

    def test_missed_existing_deadline_is_not_forgiven_by_later_boundary(self):
        case=self.ledger_case();case.steps[('one','B')]=3;case.arm_due('one','B')
        case.steps[('one','B')]=4;case.arm_due('one','B')
        with self.assertRaisesRegex(AssertionError,'required next model call'):
            case.observe_ledger('one','B',[],3)

    def test_gap_acceptance_gets_fresh_fence_only_after_current_input(self):
        case=self.ledger_case()
        case.observe_ledger('one','B',[],2)
        case.steps[('one','B')]=3;case.arm_due('one','B')
        with self.assertRaisesRegex(AssertionError,'required next model call'):
            case.observe_ledger('one','B',[],3)

    def test_same_input_reversed_fifo_fails(self):
        case=self.ledger_case()
        messages=[{'role':'user','content':'Message from '+case.ids['A']+':\n'+'\n'.join(reversed(case.payloads['one']))}]
        with self.assertRaisesRegex(AssertionError,'sender order changed'):
            case.observe_ledger('one','B',messages,3)

    def test_retained_history_is_allowed_but_later_copy_fails(self):
        case=self.ledger_case()
        messages=[{'role':'user','content':'Message from '+case.ids['A']+':\n'+'\n'.join(case.payloads['one'])}]
        case.observe_ledger('one','B',messages,3)
        case.observe_ledger('one','B',messages,4)
        with self.assertRaisesRegex(AssertionError,'duplicated'):
            case.observe_ledger('one','B',messages+messages,5)

    def test_native_result_must_belong_to_issued_actor_and_call(self):
        case=Case('direct');case.request_context.actor=('one','A')
        call=case.tool('team_send',{'to':case.ids['B'],'message':'finding'})
        with self.assertRaisesRegex(AssertionError,'another call or worker'):
            case.record_result('one','B',call['id'],'team_send',{'content':[]})

    def test_legacy_off_actually_attempts_registered_send(self):
        case=Case('plain_parallel');case.pids[('one','A')]=123
        case.event('one','B','work:off_work')
        response=case.respond({'messages':[{'role':'user','content':'ROLE:A GROUP:one Investigate.'}],
                               'tools':[{'function':{'name':'team_send'}}]},123)
        self.assertEqual(response['tool_calls'][0]['function']['name'],'team_send')

    def test_pending_size_handoff_is_not_a_rejection(self):
        case=Case('size_at');case.request_context.actor=('one','A')
        payload=case.oversize
        call=case.tool('team_send',{'to':case.ids['B'],'message':payload})
        messages=[{'role':'user','content':'Message from '+case.ids['A']+':\n'+payload}]
        case.audit_input('one','B',messages)
        case.observe_ledger('one','B',messages,3)
        case.record_result('one','A',call['id'],'team_send',{'content':[{'type':'text','text':json.dumps({'accepted':[case.ids['B']],'failed':[]})}]})
        case.audit_input('one','B',messages)

    def test_use_finding_reads_losslessly_escaped_endpoint(self):
        case=Case('use_finding');case.request_context.actor=('one','A')
        payload=case.payloads['one'][0]
        call=case.tool('team_send',{'to':case.ids['B'],'message':payload})
        case.record_result('one','A',call['id'],'team_send',{'content':[{'type':'text','text':json.dumps({'accepted':[case.ids['B']],'failed':[]})}]})
        encoded='"'+''.join('\\u%04x'%ord(ch) for ch in payload)+'"'
        messages=[{'role':'user','content':'{"sender":'+json.dumps(case.ids['A'])+',"text":'+encoded+'}'}]
        case.observe_ledger('one','B',messages,3)
        case.event('one','A','all_sends_returned')
        case.states[('one','B')]={'followup':True}
        case.request_context.actor=('one','B')
        response=case.respond_receiver(('one','B'),messages)
        self.assertEqual(response['tool_calls'][0]['function']['name'],'test_probe')
        self.assertEqual(json.loads(response['tool_calls'][0]['function']['arguments'])['path'],payload.removeprefix('Use endpoint '))

    def test_malformed_member_schema_is_a_contract_failure(self):
        case=Case('direct')
        for members in [None, {}, [{}], ['address']]:
            with self.subTest(members=members), self.assertRaises(AssertionError):
                case.last_result([{'role':'tool','toolName':'team_members','content':json.dumps({'self':case.ids['A'],'members':members})}])

    def test_malformed_send_schema_is_a_contract_failure(self):
        case=Case('direct')
        for result in [None, [], 'accepted', {'accepted':[{}],'failed':[]}, {'accepted':[],'failed':[{}]}]:
            with self.subTest(result=result), self.assertRaises(AssertionError):
                case.last_result([{'role':'tool','toolName':'team_send','content':json.dumps(result)}])

if __name__=='__main__':unittest.main()
