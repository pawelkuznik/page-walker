import platform
import struct
import os
from os.path import dirname
from pagewalker.utilities import console_utils


version_info = (1, 1, 0)
version = '.'.join(str(c) for c in version_info)


def print_version():
    arch = struct.calcsize("P") * 8
    print("Page Walker: %s" % version)
    print("Python: %s (%s-bit)" % (platform.python_version(), arch))
    console_utils.finish(True)


def get_project_root():
    file_path = os.path.abspath(__file__)
    root_path = dirname(dirname(dirname(file_path)))
    return root_path
