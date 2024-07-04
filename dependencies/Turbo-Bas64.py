def download():
    git_clone("powturbo/Turbo-Base64")

import subprocess

def build():
    subprocess.run(["make", "libtb64.a"])