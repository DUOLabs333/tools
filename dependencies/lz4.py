def download():
    git_clone("lz4/lz4")

import subprocess
def build():
    subprocess.run(["make", "liblz4.a"])