from scenario import Scenario as Base

class Scenario(Base):
    message_max_utf8_bytes = 131072
    def observe_team(self, case, group, role):
        case.resources.append({"transport": "process-owned in-memory queues", "actors": dict(case.pids)})
    def assert_cancelled_resources(self, case):
        assert case.resources, "active team was not observed"
        # Message queues reside in process memory; verify.py checks process termination.
    def restore_fault(self, fault):
        pass
    endpoint_fault = True
    def block_recipient(self, case, group, role):
        plan = {"mode": 'unix', "pid": case.pids[(group,role)], "marker": case.payloads[group][0]}
        if plan["mode"] == "tcp":
            sockets = next(e["sockets"] for e in reversed(case.events) if e["role"]==role and e["event"]=="tool_start:slow_work")
            assert len(sockets)==1, "ambiguous team socket"
            plan["port"] = sockets[0]["localPort"]
        case.fault_plan = plan
        case.wait(lambda: case.has(group,"ROOT","endpoint_fault_armed"), "real receiver endpoint armed")
        return None, {"recipient":role,"fault":"SHUT_WR at first real finding write", "mode":'unix'}
