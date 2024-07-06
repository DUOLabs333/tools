import sys, os
from update import cwd_ctx, get_dep_path, string_to_bool

from sys import platform as PLATFORM

import itertools, subprocess, glob, re

import inspect

EXE=0
LIB=1
STATIC=2

class BuildBase(object):
    SRC_FILES=[]
    INCLUDE_PATHS=[]
    FLAGS=[]
    STATIC_LIBS=[]
    SHARED_LIBS_PATHS=[]
    SHARED_LIBS=[]

    OUTPUT_NAME="a.out"

    OUTPUT_TYPE=EXE

# Type --- EXE, LIB, or OBJ. EXE has nothing, LIB uses "-shared", and OBJ uses "-r" (or maybe uses ac rcs)
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
    
    target.FLAGS=(["-g","-DDEBUG"] if DEBUG else ["-O3","-DNDEBUG"]) + ["-Wfatal-errors","-fPIC","-Winvalid-pch", "-g"]+(["-ggdb"] if PLATFORM=="linux" else [])+(["-mcpu=apple-a14" if PLATFORM=="darwin" else "-march=native"] if not DEBUG else [])+target.FLAGS

    target.INCLUDE_PATHS=list(itertools.chain.from_iterable([['-I', x] for x in target.INCLUDE_PATHS]))
    target.SHARED_LIBS=["-l"+_ for _ in target.SHARED_LIBS]
    target.SHARED_LIBS_PATHS=["-L"+_ for _ in target.SHARED_LIBS_PATHS]

    for i, e in enumerate(target.SRC_FILES):
       target.SRC_FILES[i]=[_ for _ in glob.glob(e) if get_object_file(_)]
    target.SRC_FILES=list(itertools.chain.from_iterable(target.SRC_FILES))

    for i, e in enumerate(target.STATIC_LIBS):
       target.STATIC_LIBS[i]=[_ for _ in glob.glob(e) if _.endswith(".a")]
    target.STATIC_LIBS=list(itertools.chain.from_iterable(target.STATIC_LIBS))
    target.STATIC_LIBS=(["-Wl,--start-group"] if PLATFORM!="darwin" else [])+target.STATIC_LIBS+(["-Wl,--end-group"] if PLATFORM!="darwin" else [])


    for file in target.SRC_FILES:
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
        
        subprocess.run([("g++" if CPP else "gcc")]+[("-std=c++20" if CPP else "-std=gnu99")]+ target.FLAGS+ ["-o",object_file,"-c",file]+ target.INCLUDE_PATHS)
        os.utime(object_file, (modified_time, modified_time))

    if not CLEAN:
        OBJECT_FILES=[get_object_file(_) for _ in target.SRC_FILES]
        if (target.OUTPUT_TYPE in [EXE, LIB]):
            subprocess.run(["g++"]+(["-shared"] if target.OUTPUT_TYPE==LIB else [])+["-o", target.OUTPUT_NAME]+OBJECT_FILES+target.FLAGS+target.STATIC_LIBS+target.SHARED_LIBS_PATHS+target.SHARED_LIBS)
        else:
            subprocess.run(["ar", "-rcs", target.OUTPUT_NAME]+OBJECT_FILES)
        



for target in sys.argv[1:]:
    if target not in classes:
        continue

    target=classes[target]()
    
    with cwd_ctx(os.getcwd()):
        build_target(target)
