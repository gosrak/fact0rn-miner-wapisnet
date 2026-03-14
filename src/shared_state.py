import multiprocessing

# Shared multiprocessing state (initialized by init())
shared_variables = None
shared_candidates = None
shared_strong_candidate = None
shared_client_list = None
shared_pre_client_list = None
shared_sendQueue = None

# Logger (set by mine() in miner_kafka.py, used by factoring.py)
logMiner = None


def init():
    global shared_variables, shared_candidates, shared_strong_candidate
    global shared_client_list, shared_pre_client_list, shared_sendQueue

    shared_variables = multiprocessing.Manager().dict()
    shared_variables["Version"] = "1.30"
    shared_variables["devFeeYN"] = False
    shared_variables["staticBlockStatus"] = ""
    shared_variables["staticMinerStatus"] = ",Miner : ready"
    shared_variables["staticSubMinerStatus"] = ""
    shared_variables["staticCpuECMStatus"] = ""
    shared_variables["staticGpuECMStatus"] = ""
    shared_variables["staticPrePolyStatus"] = ""
    shared_variables["staticPrePolyNumber"] = "0"
    shared_variables["curruentBlock"] = 0
    shared_variables["block.nBits"] = 0
    shared_variables["factorData.n"] = 0
    shared_variables["factorData.p"] = 0
    shared_variables["factorData.q"] = 0
    shared_variables["factorData.W"] = 0
    shared_variables["factorData.nNonce"] = 0
    shared_variables["factorData.Height"] = 0
    shared_variables["BlockTime"] = 0
    shared_variables["MinerStatus"] = ""
    shared_variables["Candidates Count"] = 0
    shared_variables["Candidates Step"] = 0
    shared_variables["CUDA ECM Client PID"] = 0
    shared_variables["CadoServerStatus"] = "ready"
    shared_variables["CadoServerIndex"] = 0
    shared_variables["Main Shell Script"] = 0
    shared_variables["NextFastEntry"] = False
    shared_variables["Block.W"] = 0
    shared_variables["Block.nNonce"] = 0
    shared_variables["Block.bit"] = 0
    shared_variables["sub factor"] = ""
    shared_variables["Total Cores"] = 0
    shared_variables["nextBlock.Count"] = 0
    shared_variables["nextBlock.nNonce"] = 0
    shared_variables["nextBlock.nTime"] = 0
    shared_variables["nextBlock.nVersion"] = 0
    shared_variables["nextBlock.nBits"] = 0
    shared_variables["nextBlock.W"] = 0

    shared_candidates = multiprocessing.Manager().list()
    shared_strong_candidate = multiprocessing.Manager().list()
    shared_client_list = multiprocessing.Manager().list()
    shared_pre_client_list = multiprocessing.Manager().list()
    shared_sendQueue = multiprocessing.Manager().Queue()
