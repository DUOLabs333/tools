import os, pathlib, contextlib, string, random, sys
import contextlib, importlib.util

parent_dir=pathlib.Path(__file__).parent
dependencies_dir=parent_dir / "external"

@contextlib.contextmanager
def cwd_ctx(path=os.getcwd()):
    curdir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(curdir)


def get_dep_folder(dep):
    return dependencies_dir/dep

def get_dep_path(dep, path=""):
    return os.path.join(get_dep_folder(dep), path)

def env_to_bool(key, default):
    env=os.environ.get(key, None)

    if env==None:
        return default
    else:
        if env=="0":
            return False
        else:
            return True

def import_module_from_file(path, globals_aux={}):
    module_name=''.join(random.choices(string.ascii_uppercase, k=5))

    spec=importlib.util.spec_from_file_location(module_name, path)
    mod=importlib.util.module_from_spec(spec)

    globals_env=globals().copy() | globals_aux
    del globals_env['__name__']

    mod.__dict__.update(globals_env)
    sys.modules[module_name]=mod
    spec.loader.exec_module(mod) 

    return mod
