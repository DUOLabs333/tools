import pathlib, sys, shutil, subprocess

from utils import *

def get_targets(): #Parse arguments into the proper format
    targets=[]

    for arg in sys.argv[1:]:
        target=arg.split("=",1)
        
        target[1]=set(target[1].split(","))
        
        targets.append(target)
    return targets


def git_clone(path, host="github.com", dest_dir="."):
    subprocess.run(["git", "clone", "--depth=1", f"{host}/{path}", dest_dir])

def curl(url, dest_dir=".", dest_file=None):
    subprocess.run(["curl", "-L", "--create-dirs", "--output-dir", dest_dir]+(["-o", dest_file] if dest_file else [])+[url])

def untar(path, dest_dir=".", strip_components=0):
    subprocess.run(["tar", "-xvzf", path, "--strip-components", str(strip_components), "-C", dest_dir])

def execute_target(target):

    name, actions=target

    formula=formulas[name]
    dest_dir=get_dep_folder(name)

    if "delete" in actions:
        shutil.rmtree(dest_dir)
        return

    dest_dir.mkdir(exist_ok=True, parents=True)

    with cwd_ctx(dest_dir):
        for action in actions:
            func=getattr(formula, action, None)
            if func==None:
                print(f"WARNING: Action {action} does not exist for dependency {name}! Skipping...")
            else:
                print(f"EXECUTING action {action} for dependency {name}...")
                func()


if __name__=="__main__":

    formulas=import_module_from_file("Formulafile.py")
    
    actions=get_targets()
    for target in targets:
        execute_target(target)


        
        


