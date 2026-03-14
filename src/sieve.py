import os
import ctypes
from time import time
from gmpy2 import mpz, gcd
from sympy.ntheory import isprime

from config import MAX_SIEVE_LEVEL, DEBUGGING
from bitcoin import uint1024, CParams

# Module-level globals (process-local)
siever = None
siev = None
keys = []

# Load gHash from shared library
gHash = ctypes.CDLL("./gHash.so").gHash
gHash.restype = uint1024


def getParams():
    param = CParams()
    param.hashRounds = 1
    param.MillerRabinRounds = 50
    return param


def load_levels():
    global siever
    global siev
    global MAX_SIEVE_LEVEL
    execute_path = os.path.dirname(os.path.abspath(__file__))

    filenames = [level_file for level_file
                 in next(os.walk(execute_path + "/isieve/"), (None, None, []))[2]
                 if "primorial_level_" in level_file]

    filenames.sort(key=lambda x: int(x.split("_")[-1].split(".")[0]))

    if filenames:
        siever = {}
        START = time()
        for File in filenames:
            level = int(File.split("_")[-1].split(".")[0])
            if level > MAX_SIEVE_LEVEL:
                break
            start = time()
            f = open(execute_path + "/isieve/" + File, "r")
            line = f.readlines()[0]
            siever[level] = mpz(int(line, 16))
            if DEBUGGING == "True":
                print("Level loaded: ", level, "  | ", time() - start, " Seconds.")
        if DEBUGGING == "True":
            print("Total time: ", time() - START, " Seconds.")


def sieve_worker(n):
    global siever
    global keys
    for level in keys:
        if gcd(n, siever[level]) != 1:
            return False
    if isprime(n):
        return False
    return True
