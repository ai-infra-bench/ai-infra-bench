"""In-memory implementation of the external NIXL IO API used by the frozen connector.

This substitutes the transfer/notification provider, never vLLM's metadata,
read-dispatch or receive-completion logic. Descriptors carry real CPU buffers.
"""
import ctypes
import importlib.machinery
import sys
import types
from types import SimpleNamespace

class IO:
    agents={}; lists={}; transfers={}; serial=0
    fail_notifications=False
    notification_attempts=0
    @classmethod
    def identifier(cls):cls.serial+=1;return cls.serial
    def __init__(self,name,*a,**k):
        self.name=name;IO.agents[name]=self;self.notifs=[];self.fail_notif=False;self.calls=0;self.reads=0
    def get_reg_descs(self,data,*a):return list(data)
    def register_memory(self,*a,**k):pass
    def deregister_memory(self,*a):pass
    def get_xfer_descs(self,data,*a):return list(data)
    def prep_xfer_dlist(self,agent,descs):
        i=IO.identifier();IO.lists[i]=(agent,descs);return i
    def get_agent_metadata(self):return self.name.encode()
    def add_remote_agent(self,data):return data.decode()
    def get_new_notifs(self):
        value={self.name:self.notifs[:]};self.notifs.clear();return value
    def send_notif(self,agent_name,notif_msg):
        self.calls+=1
        IO.notification_attempts+=1
        if IO.fail_notifications:raise RuntimeError('test producer notification unavailable')
        IO.agents[agent_name].notifs.append(notif_msg)
    def make_prepped_xfer(self,kind,lh,li,rh,ri,notif_msg=None):
        i=IO.identifier();IO.transfers[i]=(lh,list(li),rh,list(ri),notif_msg,False);self.reads+=1;return i
    def transfer(self,handle):
        lh,li,rh,ri,msg,_=IO.transfers[handle]
        _,ld=IO.lists[lh];agent,rd=IO.lists[rh]
        for a,b in zip(li,ri):ctypes.memmove(ld[int(a)][0],rd[int(b)][0],min(ld[int(a)][1],rd[int(b)][1]))
        if msg:IO.agents[agent].notifs.append(msg)
        IO.transfers[handle]=(lh,li,rh,ri,msg,True)
        return 'PROC'
    def check_xfer_state(self,handle):return 'DONE' if IO.transfers[handle][-1] else 'PROC'
    def release_xfer_handle(self,handle):type(self).transfers.pop(handle,None)
    def release_dlist_handle(self,handle):type(self).lists.pop(handle,None)
    def remove_remote_agent(self,*a):pass
    def get_xfer_telemetry(self,*a):return SimpleNamespace(xferDuration=1.,postDuration=1.,totalBytes=1,descCount=1)


def install():
    package = types.ModuleType('nixl')
    package.__path__ = []
    package.__spec__ = importlib.machinery.ModuleSpec('nixl', loader=None, is_package=True)
    api = types.ModuleType('nixl._api')
    api.__spec__ = importlib.machinery.ModuleSpec('nixl._api', loader=None)
    api.nixl_agent = IO
    api.nixl_agent_config = lambda **kwargs: SimpleNamespace(**kwargs)
    bindings = types.ModuleType('nixl._bindings')
    bindings.__spec__ = importlib.machinery.ModuleSpec('nixl._bindings', loader=None)
    bindings.nixlXferTelemetry = SimpleNamespace
    package._api = api
    package._bindings = bindings
    sys.modules.update({'nixl': package, 'nixl._api': api, 'nixl._bindings': bindings})
