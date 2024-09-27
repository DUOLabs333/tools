from utils import *
import update

from sys import platform as PLATFORM

import itertools, subprocess, glob, re, os, inspect, runpy
import sys

import pathlib

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
    DEPENDENCIES=[] #Escape hatch for arbitrary dependencies that aren't describable in any pre-existing model
    FRAMEWORKS=[]

    RPATH=[]

    OUTPUT_NAME=""

    CWD="."

    OUTPUT_TYPE=EXE
    
    def absolute_path(cls, attr):
        obj=getattr(cls, attr)
        if isinstance(attr, str):
            return os.path.join(cls.CWD, obj)
        else:
            return [os.path.join(cls.CWD, _) for _ in obj]

# Type --- EXE, LIB, or OBJ. EXE has nothing, LIB uses "-shared", and OBJ uses "ld -r" 

def _flatten(obj):
    if isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _flatten(item)
    else:
        yield obj

def flatten(obj):
    return [_ for _ in _flatten(obj)]

dependencies=set() #Caching existing dependencies, so a single dependency is not downloaded multiple times in the same invocation
old_get_dep_path=get_dep_path

def get_dep_path(dep, *args, **kwargs):
    if UPDATE_DEPENDENCIES:
        if dep not in dependencies:
            update.execute_target([dep, {"download", "build"}])
            dependencies.add(dep)
        
    return old_get_dep_path(dep, *args, **kwargs)
    
def import_build(path, external=True):
    
    with cwd_ctx(path):
        runpy.run_path(parent_dir / "update.py")
        
        mod=import_module_from_file("Buildfile.py", globals_aux = globals())
        
        
        for name in dir(mod):
            cls = getattr(mod, name)

            if is_buildbase(cls):
                cwd=getattr(cls, "CWD", path)
                cls.CWD=os.path.abspath(cwd)
                cls.EXTERNAL=external
        return mod

CLEAN=env_to_bool("CLEAN", False)
DEBUG=env_to_bool("DEBUG", True)
CLIENT=env_to_bool("CLIENT", False if PLATFORM=="darwin" else True)
CC=os.environ.get("CC", "cc")
CXX=os.environ.get("CXX", "c++")
UPDATE_DEPENDENCIES=env_to_bool("UPDATE_DEPENDENCIES", False)

targets={}
compiled={}

FRAMEWORKS_PATHS=[f"{os.path.expanduser('~')}/.nix-profile/Library/Frameworks"]
FRAMEWORKS_PATHS=[f"-F{_}" for _ in FRAMEWORKS_PATHS]
def is_buildbase(cls):
    return inspect.isclass(cls) and (BuildBase in inspect.getmro(cls)) and (cls!=BuildBase)
    
def get_object_file(name):
    if not (name.endswith(".cpp") or name.endswith(".c")):
        return None
    return re.sub(r"^(.*)\.(.*)$",r"\1.o",name)

def compile_target(target):
    if target in compiled:
        return
    
    target=target()
    is_client=target.CLIENT if hasattr(target, "CLIENT") else CLIENT

    if target.OUTPUT_NAME=="":
        target.OUTPUT_NAME=target.__class__.__name__
    
    if (target.EXTERNAL):
        target.CLEAN=False
    else:
        target.CLEAN=CLEAN

    target.FLAGS=(["-g","-DDEBUG"] if DEBUG else ["-O3","-DNDEBUG"]) + ["-Wfatal-errors","-fPIC","-Winvalid-pch", "-g"]+(["-ggdb"] if PLATFORM=="linux" else [])+(["-march=native"] if not DEBUG else [])+(["-DCLIENT"] if is_client else [])+target.FLAGS

    for i, e in enumerate(target.INCLUDE_PATHS):
        if is_buildbase(e):
            target.INCLUDE_PATHS[i]=build_target("DEPENDENCY", e).CWD

    target.INCLUDE_PATHS=flatten([['-I', x] for x in target.INCLUDE_PATHS])

    target.SHARED_LIBS=["-l"+_ for _ in target.SHARED_LIBS]
    target.SHARED_LIBS_PATHS=["-L"+_ for _ in target.SHARED_LIBS_PATHS]

    target.RPATH = ["-Wl,-rpath,"+_ for _ in target.RPATH]

    for i, e in enumerate(target.SRC_FILES):
       target.SRC_FILES[i]=[_ for _ in glob.glob(e) if get_object_file(_)]
    target.SRC_FILES=list(itertools.chain.from_iterable(target.SRC_FILES))
    
    for i, e in enumerate(target.STATIC_LIBS):
        if is_buildbase(e):
            target.STATIC_LIBS[i]=build_target("DEPENDENCY", e).absolute_path("OUTPUT_NAME")

    target.STATIC_LIBS=flatten([[_ for _ in glob.glob(e) if _.endswith(".a")] for e in target.STATIC_LIBS])
    
    target.FRAMEWORKS=flatten([["-framework", _] for _ in target.FRAMEWORKS])
    
    for dep in target.DEPENDENCIES:
        build_target("DEPENDENCY", dep)
        
    FILE_EXTENSION=""
    
    if target.OUTPUT_TYPE==LIB:
        if PLATFORM=="linux":
            FILE_EXTENSION=".so"
        elif PLATFORM=="darwin":
            FILE_EXTENSION=".dylib"
    elif target.OUTPUT_TYPE==STATIC:
        FILE_EXTENSION=".a"
        
    target.OUTPUT_NAME+=FILE_EXTENSION

    compiled[target.__class__]=target

cached_targets=set()
def build_target(prefix, target):
    with cwd_ctx(target.CWD):
        compile_target(target)
            
        target=compiled[target]

        if target not in cached_targets:
            cached_targets.add(target.__class__)
            print(f"{prefix}: {'Cleaning' if target.CLEAN else 'Building'} target {target.__class__.__name__}...")
            
            if hasattr(target, "build"):
                getattr(target, "build")()
            else:
                for file in target.SRC_FILES:
                    object_file=get_object_file(file)
                    if not object_file:
                        continue
                    
                    if target.CLEAN:
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
                    
                    subprocess.run([(CXX if CPP else CC)]+[("-std=c++20" if CPP else "-std=gnu99")]+ target.FLAGS+ ["-o",object_file,"-c",file]+ target.INCLUDE_PATHS)
                    os.utime(object_file, (modified_time, modified_time))

                
                if not target.CLEAN:
                    OBJECT_FILES=[get_object_file(_) for _ in target.SRC_FILES]
                    if (target.OUTPUT_TYPE in [EXE, LIB]):
                        subprocess.run([CXX]+(["-shared"] if target.OUTPUT_TYPE==LIB else [])+["-o", target.OUTPUT_NAME]+OBJECT_FILES+target.FLAGS+(["-Wl,--start-group"] if PLATFORM!="darwin" else [])+target.STATIC_LIBS+(["-Wl,--end-group"] if PLATFORM!="darwin" else [])+target.SHARED_LIBS_PATHS+target.SHARED_LIBS+(FRAMEWORKS_PATHS+target.FRAMEWORKS if PLATFORM=="darwin" else [])+target.RPATH)
                    else:
                        pathlib.Path(target.OUTPUT_NAME).unlink(missing_ok=True)
                        if PLATFORM=="darwin":
                            ar=["libtool", "-static", "-o"]
                        else:
                            ar=["ar", "-rcT"]

                        subprocess.run(ar+[target.OUTPUT_NAME]+OBJECT_FILES+target.STATIC_LIBS)
                        subprocess.run(["ar", "-M"], input="\n".join([f'create "{target.OUTPUT_NAME}"']+[f'addlib "{target.OUTPUT_NAME}"']+["save", "end"]),text=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
                else:
                    if os.path.exists(target.OUTPUT_NAME):
                        os.remove(target.OUTPUT_NAME)

        return target

for target in sys.argv[1:]:
    main=import_build(os.getcwd(), external=False)

    target=getattr(main, target, None)
    if (target==None) or (not is_buildbase(target)):
        print(f"Warning: Target {target} not found in file!")
        continue

    build_target("REQUESTED", target)
