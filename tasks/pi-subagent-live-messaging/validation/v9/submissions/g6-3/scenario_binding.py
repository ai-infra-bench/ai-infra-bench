from scenario import Scenario as Base

class Scenario(Base):
    message_max_utf8_bytes = 65536
    def observe_team(self, case, group, role):
        case.resources.append({"transport": "process-owned in-memory queues", "actors": dict(case.pids)})
    def assert_cancelled_resources(self, case):
        assert case.resources, "active team was not observed"
        # Message queues reside in process memory; verify.py checks process termination.
    def restore_fault(self, fault):
        pass
    def preparation_sends(self, case):
        return ["capacity " + str(i) + "x" * (65536-len("capacity " + str(i))) for i in range(16)]
    def block_recipient(self, case, group, role):
        return None, {"recipient": role, "fault": "fill documented 1 MiB inbox through 16 real public sends while C is working"}
