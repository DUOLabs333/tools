import os, shutil
class asio:
    def download(cls):
        git_clone("chriskohlhoff/asio")

class boost:
    def download(cls):
        curl("https://boostorg.jfrog.io/artifactory/main/release/1.84.0/source/boost_1_84_0.tar.gz", dest_dir="downloads", dest_file="boost.tar.gz")

        untar(os.path.join("downloads", "boost.tar.gz"), strip_components=1)
        
        shutil.rmtree("downloads")

class komnihash:
    def download(cls):
        git_clone("avaneev/komihash")

class lz4:
    def download(cls):
        git_clone("lz4/lz4")
    def build(cls):
        subprocess.run(["make", "liblz4.a"])

class shm_open_anon:
    def download(cls):
        git_clone("lassik/shm_open_anon")

class simdjson:
    def download(cls):
        git_clone("simdjson/simdjson")

class Turbo_Base64:
    def download(cls):
        git_clone("powturbo/Turbo-Base64")

    def build(cls):
        subprocess.run(["make", "libtb64.a"])

class Vulkan_Headers:
    def download(cls):
        git_clone("KhronosGroup/Vulkan-Headers")

class xxHash_3:
    def download(cls):
        git_clone("pombredanne/xxHash-3")
    def build(cls):
        subprocess.run(["make", "libxxhash.a"])
        
class glaze:
    def download(cls):
        git_clone("stephenberry/glaze", branch="v2.6.0")
