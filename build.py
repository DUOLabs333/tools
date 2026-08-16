from utils import *
import update

from sys import platform as PLATFORM

import itertools, subprocess, glob, re, os, inspect, runpy, functools, collections
import sys

EXE=0
LIB=1
STATIC=2

target_build_stack=[]
targets_dict = {}


#True if it is building, False if something else is building, and None if nothing is building
def is_building(cls):
    if len(target_build_stack)>0:
        current_building_target=target_build_stack[-1]
        return (current_building_target.__class__ == cls)
    return None

#We need a metaclass as an attribute lookup on an instance triggers the _class_'s __getattribute__ --- therefore, since we want to trigger on attribute lookups on classes, we need to declare a __getattribute__ on the _metaclass_ (of which the class is an instance of)
class ClassAttributeLookupInterceptor(type):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        #Ensures that every class has their own distinct set
        self.built_dependencies=set()

    #If a target is requesting a class's attribute during building, then we are assuming that it implies that the target is depending on the class, so we build the class and return from there.
    #Normally, I would build unconditionally, but since class initialization is not lazy, it would mean builds would run just by importing the Buildfile.py
    def __getattribute__(cls, attr):
            #We are only looking for attributes that would be useful during the building of a target
            if (not attr.startswith("__")) and (not attr=="built_dependencies") and (is_building(cls) == False):
                return getattr(build_target("DEPENDENCY", cls), attr)
            return super().__getattribute__(attr)

    def __setattr__(cls, attr, value):
        if is_building(cls):
            #The only reason this would make sense is that you want to do setup that child classes will then use --- however, there's no guarenteed order of unrelated build targets, so you can't rely on that
            raise Exception("Don't set attributes to the class in __init__ --- always write to self. If you need to do setup on the class, either do it in a metaclass or a decorator on the class")
        return super().__setattr__(attr, value)

class BuildBase(object, metaclass=ClassAttributeLookupInterceptor):
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
    OUTPUT_FILE=""
    OUTPUT_FILES = []

    CWD="."

    OUTPUT_TYPE=EXE
    
    def get_compile_command_for_source(self, src):
        CPP=src.endswith(".cpp")
        return [(CXX if CPP else CC)]+[("-std=c++20" if CPP else "-std=gnu99")]+ self.FLAGS+ ["-c",src]+ self.INCLUDE_PATHS


    #chdir on CWD change when building --- we don't need a check on is_building here, since there is no reason to be modifying an instance outside of building
    def __setattr__(self, attr, value):
        cls = self.__class__
        if attr=="CWD":
            os.chdir(value)
        return super().__setattr__(attr, value)

    @property
    #Whether this class encodes some generic non-C++ action
    #This is for cases where "utility" classes do something like (f(e) for e in SRC_FILES)
    #Could solve all of these problems by just splitting the C++ build into its own Build class (where it derives from BuildBase), and leave BuildBase as default, but that means that I would have to rework a good chunk of my build files, so... no.
    def is_non_build(self):
        return any(not getattr(getattr(self, method), "_is_default", False) for method in wrapped_methods)

    def get_output_file(self, name):
        if not (name.endswith(".cpp") or name.endswith(".c")):
            return None
        return re.sub(r"^(.*)\.(.*)$",r"\1.o",name)

    #If this becomes too slow, we may switch to using an lru_cache --- however, if that's true, then it must return a list, not a generator
    #Get all files that the given source file depends on
    def get_src_depends(self, src):
        #-fsyntax-only instead of -E also works, but -E is significantly faster
        p = subprocess.Popen(self.get_compile_command_for_source(src)+["-E", "-H"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        #Each line is <some amount of dots><space><path>
        pattern = re.compile(r"(?:.*?)\s(.*)")
        #It needs to end in the path separator
        cwd=os.path.join(os.getcwd(), "")

        for line in p.stderr:
            match = pattern.fullmatch(line.strip("\n"))
            if match is None:
                continue
            path = os.path.abspath(match.group(1))
            if (not path.startswith(cwd)) or (not os.path.exists(path)):
                continue

            yield path
                
        p.wait()

    def get_output_depends(self, dest):
        #Get locations of static_libs and shared_libs to use (if it doesn't exist, just send all static_libs and resolved shared_libs paths --- it's not implemented as of yet since it seems like the only way to get them (-Wl,-t) is by doing a full linking, defeating the purpose. Maybe I can do something with -print-file-name?
        return self.STATIC_LIBS

    def build_source(self, src, dest):
        run(self.get_compile_command_for_source(src)+["-o", dest])
    
    def link(self, dests):
        if (self.OUTPUT_TYPE in [EXE, LIB]):
            run([CXX]+(["-shared"] if self.OUTPUT_TYPE==LIB else [])+["-o", self.OUTPUT_FILE]+dests+self.FLAGS+(["-Wl,--start-group"] if PLATFORM!="darwin" else [])+self.STATIC_LIBS+(["-Wl,--end-group"] if PLATFORM!="darwin" else [])+self.SHARED_LIBS_PATHS+self.SHARED_LIBS+(self.FRAMEWORKS if PLATFORM=="darwin" else [])+self.RPATH)
        else:
            remove(self.OUTPUT_FILE)
            if PLATFORM=="darwin":
                ar=["libtool", "-static", "-o"]
            else:
                ar=["ar", "-rcT"]

            run(ar+[self.OUTPUT_FILE]+dests+self.STATIC_LIBS)
            run(["ar", "-M"], input="\n".join([f'create "{self.OUTPUT_FILE}"']+[f'addlib "{self.OUTPUT_FILE}"']+["save", "end"]),text=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    def build(self):
        dests=[]

        def was_modified(src, dest, is_building_src):
            dest=convert_to_iterable(dest)

            #If the dest doesn't exist, then by its very nature, the file must be newer than it
            if not all(os.path.exists(_) for _ in dest):
                return True

            min_mtime=min(int(os.path.getmtime(_)) for _ in dest)

            def check_for_invalidation(lst):
                if lst is None:
                    lst=[]
                return any((min_mtime <= int(os.path.getmtime(file))) for file in convert_to_iterable(lst))

            if check_for_invalidation(src):
                return True

            lst = []
            aux_function = lambda _: ""

            if is_building_src:
                lst=src
                aux_function=self.get_src_depends
            else:
                #You're linking now
                lst=dest
                aux_function=self.get_output_depends

            return any(check_for_invalidation(aux_function(file)) for file in convert_to_iterable(lst))

        for src in self.SRC_FILES:
            dest=self.get_output_file(src);

            if not dest:
                continue

            if self.CLEAN:
                remove(dest)
                continue

            dests.append(dest)

            if not was_modified(src, dest, True):
                continue

            #I'm not sure whether this is needed since most/(all?) compilers will just overwrite this file
            remove(dest)

            self.build_source(src, dest)

        if self.is_non_build and hasattr(self.link, "_is_default", False):
            if self.OUTPUT_FILES == []:
                self.OUTPUT_FILES.extend(dests)
        if self.CLEAN:
            for file in self.OUTPUT_FILES:
                remove(file)
        #Currently, the default get_aux_files_for_dest doesn't return anything --- this is not because there are not any auxiliary files, but because we don't have a good way of getting them. Therefore, to be on the safe side, we always should re-link if this is a build.
        elif (not self.is_non_build) or was_modified(dests, self.OUTPUT_FILES, False): 
            self.link(dests)

    def absolute_path(cls, attr):
        obj=getattr(cls, attr)
        if isinstance(obj, str):
            return os.path.join(cls.CWD, obj)
        else:
            return [os.path.join(cls.CWD, _) for _ in obj]
def default(func):
    method_name = func.__name__
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if getattr(getattr(self, method_name), "_is_default", False):
            #If this is a non-build, skip almost all of the functions, as they are not useful
            if self.is_non_build and (method_name != "build"):
                return None
        else:
            #To support this (calling the base properly, I could try some complicated things like adding a flag to track whether the Base build_source has been called and conditionally enable the default link if that's true, but that's more involved and for my usecases, I should never run into that scenario --- I only need to implement what I need, not what I _think_ I will need.
            #Maybe add warning for case where build_source and/or link are explicitly defined, yet not called by build (would have to be done by overriding them (only in the cases where they are explictly defined) in compile_target with wrapper that keeps track of times it was called
            #The idea is that the C++ system should not be tampered with at all
            raise Exception(f"You should not be calling super().{method_name} on an explicitly-overriden {method_name} (as it implies that you are not doing a standard C++ build) --- there are almost certainly better ways to accomplish what you want!")

        return func(self, *args, **kwargs)
    #Wanted to use double underscore, but Python automatically mangles them into _BuildBase__is_default, with no way to turn it off (at least, not that I know of)
    wrapper._is_default = True
    return wrapper

wrapped_methods=[]
for name, value in vars(BuildBase).items():
    if callable(value) and (not name.startswith("_")):
        wrapped_methods.append(name)
        setattr(BuildBase, name, default(value))

# Type --- EXE, LIB, or OBJ. EXE has nothing, LIB uses "-shared", and OBJ uses "ld -r" 

def _flatten(obj):
    if isinstance(obj, (list, tuple)):
        for item in obj:
            yield from _flatten(item)
    else:
        yield obj

def flatten(obj):
    return [_ for _ in _flatten(obj)]

def remove(file):
    try:
        os.remove(file)
    except OSError:
        pass

def convert_to_iterable(obj):
    if isinstance(obj, collections.abc.Iterable) and (not isinstance(obj, str)):
        return obj
    else:
        return [obj]

dependencies=set() #Caching existing dependencies, so a single dependency is not downloaded multiple times in the same invocation
old_get_dep_path=get_dep_path

def run(*args, **kwargs):
    kwargs["check"]=True

    try:
        subprocess.run(*args, **kwargs)
    except subprocess.CalledProcessError:
        exit()

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

def is_buildbase(cls):
    return inspect.isclass(cls) and (BuildBase in inspect.getmro(cls)) and (cls!=BuildBase)
 
def compile_target(target):
    for i, e in enumerate(target.SRC_FILES):
       target.SRC_FILES[i]=[_ for _ in glob.glob(e) if target.get_output_file(_)]
    target.SRC_FILES=list(itertools.chain.from_iterable(target.SRC_FILES))

    for dep in target.DEPENDENCIES:
        #Needed in order to trigger the build
        dep.CWD

    if target.is_non_build:
        return

    is_client=getattr(target, "CLIENT", CLIENT)

    if target.OUTPUT_NAME=="":
        target.OUTPUT_NAME=target.__class__.__name__

    target.FLAGS=(["-g","-DDEBUG"] if DEBUG else ["-O3","-DNDEBUG"]) + ["-Wfatal-errors","-fPIC","-Winvalid-pch","-Werror=integer-overflow","-Werror=format", "-g"]+(["-ggdb"] if PLATFORM=="linux" else [])+(["-march=native"] if not DEBUG else [])+(["-DCLIENT"] if is_client else [])+target.FLAGS

    for i, e in enumerate(target.INCLUDE_PATHS):
        if is_buildbase(e):
            target.INCLUDE_PATHS[i]=e.CWD

    target.INCLUDE_PATHS=flatten([['-I', x] for x in target.INCLUDE_PATHS])

    target.SHARED_LIBS=["-l"+_ for _ in target.SHARED_LIBS]
    target.SHARED_LIBS_PATHS=["-L"+_ for _ in target.SHARED_LIBS_PATHS]

    target.RPATH = ["-Wl,-rpath,"+_ for _ in target.RPATH]
    
    for i, e in enumerate(target.STATIC_LIBS):
        if is_buildbase(e):
            target.STATIC_LIBS[i]=e.absolute_path("OUTPUT_FILES")

    target.STATIC_LIBS=flatten([[_ for _ in glob.glob(e) if _.endswith(".a")] for e in flatten(target.STATIC_LIBS)])
    
    target.FRAMEWORKS=flatten([["-framework", _] for _ in target.FRAMEWORKS])
        
    FILE_EXTENSION=""
    
    if target.OUTPUT_TYPE==LIB:
        if PLATFORM=="linux":
            FILE_EXTENSION=".so"
        elif PLATFORM=="darwin":
            FILE_EXTENSION=".dylib"
    elif target.OUTPUT_TYPE==STATIC:
        FILE_EXTENSION=".a"
    
    if target.OUTPUT_FILE == "":
        target.OUTPUT_FILE = target.OUTPUT_NAME + FILE_EXTENSION

    if target.OUTPUT_FILES == []:
        target.OUTPUT_FILES.append(target.OUTPUT_FILE)

def build_target(prefix, target):
    is_dependency = (prefix == "DEPENDENCY")
    tab="\t"
    prefix=f"{tab*len(target_build_stack)}{prefix}:"
    if target in targets_dict:
        target = targets_dict[target]
        #Should not show the same dependency for a target multiple times
        if not (is_dependency and (is_building(target.__class__) != None) and (target in target_build_stack[-1].built_dependencies)):
            print(f"{prefix} Target {target.__class__.__name__} has already been initialized; skipping...")
        return target
    with cwd_ctx(target.CWD):
        print(f"{prefix} Target {target.__name__} has not been initialized yet; working...")

        target_build_stack.append(target)
        prefix="\t"+prefix

        print(f"{prefix} Initializing {target.__name__}...")
        target = target()
        targets_dict[target.__class__]=target

        if target.EXTERNAL:
            target.CLEAN=False
        elif target.__class__.__module__ != main.__name__:
             #Clean should only apply to current directory (support recursive can come later)
            target.CLEAN = False
            print(f"{target.__class__.__module__ } {main.__name__} Was imported... don't clean")
        else:
            target.CLEAN=CLEAN

        print(f"{prefix} {'Cleaning' if target.CLEAN else 'Building'} target {target.__class__.__name__}...")

        compile_target(target)

        target.build()

        target_build_stack.pop()

        #Add built dependency to set of dependents
        if is_dependency and (is_building(cls) != None):
            target_build_stack[-1].built_dependencies.add(target)

        return target

main=import_build(os.getcwd(), external=False)
targets=sys.argv[1:]
targets_all=[_[0] for _ in inspect.getmembers(main, is_buildbase)]

if "all" in targets:
    targets=targets_all

for i, target in enumerate(targets):
    print("")
    target=getattr(main, target, None)
    if (target==None) or (not is_buildbase(target)):
        print(f"Warning: Target {target} not found in file!")
        continue

    build_target("REQUESTED", target)