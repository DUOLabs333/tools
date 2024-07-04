import pathlib, sys, shutil
import importlib.util
import string, random
import os, contextlib
import subprocess
dependencies_dir=pathlib.Path(__file__).parent / "dependencies"

def parse_arguments(): #Parse arguments into the proper format
    result=[]

    for arg in sys.argv[1:]:
        dependency=arg.split("=",1)
        
        dependency[1]=set(dependency[1].split(","))
        
        result.append(dependency)
    return result

@contextlib.contextmanager
def cwd_ctx(new_path):
    curdir = os.getcwd()
    os.chdir(new_path)
    try:
        yield
    finally:
        os.chdir(curdir)

def git_clone(path, host="github.com", dest_dir="."):
    subprocess.run(["git", "clone", "--depth=1", f"{host}/{path}", dest_dir])

def curl(url, dest_dir=".", dest_file=None):
    subprocess.run(["curl", "-L", "--create-dirs", "--output-dir", dest_dir]+(["-o", dest_file] if dest_file else [])+[url])

def untar(path, dest_dir=".", strip_components=0):
    subprocess.run(["tar", "-xvzf", path, "--strip-components", str(strip_components), "-C", dest_dir])

def get_dep_folder(dep):
    return dependencies_dir/dep

def get_dep_path(dep, path):
    return os.path.join(get_dep_folder, path)

def string_to_bool(string):
    if string=="0":
        return False
    else:
        return True

def load_file(file_path, functions):
    exec(file_path.open().read(), globals(), functions)

def execute_dependencies(dependencies):
    for dependency, actions in dependencies:
        dependency_file=dependencies_dir / (dependency+".py")
        dependency_folder= get_dep_folder(dependency)

        if "delete" in actions:
            shutil.rmtree(dependency_folder)
            continue
        
        dependency_folder.mkdir(exist_ok=True, parents=True)

        with cwd_ctx(dependency_folder):
            functions={}
            load_file(dependency_file, functions)
            for action in actions:
                if action in functions:
                    print(f"{action.title()}ing {dependency}...")
                    functions[action]()


if __name__=="__main__":
    execute_dependencies(parse_arguments())


        
        


