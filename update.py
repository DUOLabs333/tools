import pathlib, sys, shutil, subprocess

from utils import *

FORCE=env_to_bool("FORCE", False)

def get_targets(): #Parse arguments into the proper format
    targets=[]

    for arg in sys.argv[1:]:
        target=arg.split("=",1)
        
        target[1]=set(target[1].split(","))
        
        targets.append(target)
    return targets


def git_clone(path, host="github.com", dest_dir=".", keep_dot_git=False):
    subprocess.run(["git", "clone", "--depth=1", f"{host}/{path}", dest_dir])

    if not keep_dot_git:
        shutil.rmtree(os.path.join(dest_dir, ".git"))

def curl(url, dest_dir=".", dest_file=None):
    subprocess.run(["curl", "-L", "--create-dirs", "--output-dir", dest_dir]+(["-o", dest_file] if dest_file else [])+[url])

def untar(path, dest_dir=".", strip_components=0):
    subprocess.run(["tar", "-xvzf", path, "--strip-components", str(strip_components), "-C", dest_dir])

def execute_target(target):

    name, actions=target
    
    name=name.replace("-", "_")
    formula=formulas[name]
    dest_dir=get_dep_folder(name)

    if "delete" in actions:
        shutil.rmtree(dest_dir)
        return

    dest_dir.mkdir(exist_ok=True, parents=True)

    with cwd_ctx(dest_dir):
        for action in actions:
            action_file=pathlib.Path(f".{action}.action")

            if FORCE:
                action_file.unlink(missing_ok=True)

            if action_file.exists():
                print(f"WARNING: Action {action} is already completed for dependency {name}. Skipping...")
                continue
            func=getattr(formula, action, None)
            if func==None:
                print(f"WARNING: Action {action} does not exist for dependency {name}! Skipping...")
            else:
                print(f"EXECUTING action {action} for dependency {name}...")
                func()
                action_file.touch(exist_ok=True)


if __name__=="__main__":

    formulas=import_module_from_file(parent_dir / "Formulafile.py", globals_aux=globals())
    if len(sys.argv)<2:
        if not os.path.exists("Depfile"):
            print("WARNING: No Depfile found! Exiting")
            sys.exit()
        else:
            sys.argv.extend([f"{_.strip()}=download,build" for _ in open("Depfile", "r").read()])
            
    actions=get_targets()
    for target in targets:
        execute_target(target)


        
        


