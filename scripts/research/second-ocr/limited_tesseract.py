import json,os,resource,sys,ctypes,signal
parent=os.getppid()
if parent==1:sys.exit(125)
if ctypes.CDLL(None,use_errno=True).prctl(1,signal.SIGKILL,0,0,0)!=0:sys.exit(125)
if os.getppid()!=parent:sys.exit(125)
with open(sys.argv[1]) as source:
    config=json.load(source)
if sys.argv[1].startswith('/proc/self/fd/'):
    os.close(int(sys.argv[1].rsplit('/',1)[1]))
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024))
resource.setrlimit(resource.RLIMIT_CPU,(2,2))
resource.setrlimit(resource.RLIMIT_FSIZE,(65536,65536))
resource.setrlimit(resource.RLIMIT_NOFILE,(32,32))
env={'PATH':'/usr/bin:/bin','LD_LIBRARY_PATH':config['libdir'],'OMP_THREAD_LIMIT':'1','OMP_NUM_THREADS':'1','TESSDATA_PREFIX':config['data'],'LANG':'C'}
os.execve(config['binary'],[config['binary'],sys.argv[2],'stdout','--psm','10','--oem','1','-l','eng','tsv'],env)
