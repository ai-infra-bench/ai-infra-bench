"""Candidate-side worker source: receives code and function inputs, never assertions."""
WORKER = r'''
import sys,json,resource,contextlib,os
resource.setrlimit(resource.RLIMIT_CPU,(4,4))
resource.setrlimit(resource.RLIMIT_FSIZE,(1048576,1048576))
wire=sys.stdout
source=json.loads(sys.stdin.readline())
namespace={'__name__':'candidate'}
with open(os.devnull,'w') as sink:
    try:
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            exec(compile(source['code'],'<candidate>','exec',dont_inherit=True,optimize=0),namespace)
        function=namespace[source['entrypoint']]
        if not callable(function):raise TypeError('Missing function')
        print(json.dumps({'id':source['id'],'status':'READY'}),file=wire,flush=True)
    except BaseException as error:
        print(json.dumps({'id':source['id'],'status':'ERROR','error_type':type(error).__name__}),file=wire,flush=True)
        raise SystemExit(1)
    for line in sys.stdin:
        request=json.loads(line)
        try:
            args=decode(request['args']);kwargs=decode(request['kwargs'])
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                value=function(*args,**kwargs)
                response={'id':request['id'],'status':'RESULT','value':encode(value),
                          'args':encode(args),'kwargs':encode(kwargs)}
        except BaseException as error:
            response={'id':request['id'],'status':'ERROR','error_type':type(error).__name__}
        print(json.dumps(response,allow_nan=False),file=wire,flush=True)
'''
