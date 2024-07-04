import shutil, pathlib
def download():
    curl("https://boostorg.jfrog.io/artifactory/main/release/1.84.0/source/boost_1_84_0.tar.gz", dest_dir="downloads", dest_file="boost.tar.gz")

    untar(pathlib.Path("downloads")/ "boost.tar.gz", strip_components=1)
    
    shutil.rmtree("downloads")

