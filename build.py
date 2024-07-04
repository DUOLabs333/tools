import sys, os
from update import cwd_ctx, get_dep_path, string_to_bool

from sys import platform as PLATFORM



import inspect
class BuildBase(object):
    SRC_FILES=[]
    INCLUDE_PATHS=[]
    FLAGS=[]
    STATIC_LIBS=[]
    SHARED_LIBS_PATHS=[]
    SHARED_LIBS=[]

    OUTPUT_NAME="a.out"

    IS_LIB=True

BUILD_BASE_ATTRS=inspect.getmembers(BuildBase)

classes={}
exec(open("Buildfile.py","r").read(),globals(), classes)

CLEAN=string_to_bool(os.environ.get("CLEAN","0"))
DEBUG=string_to_bool(os.environ.get("DEBUG","1"))

def get_object_file(name):
    if not (name.endswith(".cpp") or name.endswith(".c")):
        return None
    return re.sub(r"^(.*)\.(.*)$",r"\1.o",name)

def build_target(target):
    if hasattr(target, "build"):
        getattr(target, "build")()
        return

    for attr in BUILD_BASE_ATTRS:
        globals()[attr]=getattr(target, attr)
    
    FLAGS=(["-g","-DDEBUG"] if DEBUG else ["-O3","-DNDEBUG"]) + ["-Wfatal-errors","-fPIC","-Winvalid-pch", "-g"]+(["-ggdb"] if PLATFORM=="linux" else [])+(["-mcpu=apple-a14" if PLATFORM=="darwin" else "-march=native"] if not DEBUG else [])+FLAGS

    INCLUDE_PATHS=list(itertools.chain.from_iterable([['-I', x] for x in INCLUDE_PATHS]))
    SHARED_LIBS=["-l"+_ for _ in SHARED_LIBS]
    SHARED_LIBS_PATHS=["-L"+_ for _ in SHARED_LIBS_PATHS]
    
    SRC_FILES=list(itertools.chain.from_iterable(SRC_FILES))

    for i, e in enumerate(STATIC_LIBS):
       STATIC_LIBS[i]=[_ for _ in glob.glob(e) if _.endswith(".a")]
    STATIC_LIBS=list(itertools.chain.from_iterable(STATIC_LIBS))
    STATIC_LIBS=(["-Wl,--start-group"] if PLATFORM!="darwin" else [])+STATIC_LIBS+(["-Wl,--end-group"] if PLATFORM!="darwin" else [])


    for file in SRC_FILES:
        object_file=get_object_file(file)
        if not object_file:
            continue
        
        if CLEAN:
            try:
                os.remove(object_file)
            except OSError:
                pass
            continue
            
        if os.path.exists(object_file):
            if int(os.path.getmtime(object_file))==int(os.path.getmtime(file)):
                continue
            os.remove(object_file)
                
        modified_time=int(os.path.getmtime(file))
        CPP=file.endswith(".cpp")
        
        subprocess.run([("g++" if CPP else "gcc")]+[("-std=c++20" if CPP else "-std=gnu99")]+ FLAGS+ ["-o",object_file,"-c",file]+ INCLUDE_PATHS)
        os.utime(object_file, (modified_time, modified_time))

    if not CLEAN:
        subprocess.run(["g++"]+(["-shared"] if IS_LIB else [])+["-o", OUTPUT_NAME]+[get_object_file(_) for _ in SRC_FILES]+FLAGS+STATIC_LIBS+SHARED_LIBS_PATHS+SHARED_LIBS)



for target in sys.argv[1:]:
    if target not in classes:
        continue

    target=classes[target]()
    
    with cwd_ctx(os.getcwd()):
        build_target(target)
