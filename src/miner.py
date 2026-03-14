import os
import sys
import signal
import ctypes
import subprocess
import select
import re
import copy
import random
import pickle
import multiprocessing
import psutil
import traceback
from time import time, sleep
from random import shuffle
from pathlib import Path
from sympy.ntheory import isprime
from gmpy2 import gcd, log2
import secrets as st

import shared_state
import config
from config import (
    DEBUGGING, WORKER, MINER_MODE, CADO_SERVER_URL, CADO_CLIENT_BASE_PATH,
    GPUECM_SERVER_IP, GPUECM_SERVER_PORT, CUDAECM_SERVER_IP, CUDAECM_MAX_LEVEL,
    CHECK_CANDIDATE_WITH_CUDA_ECM, USE_MSIEVE, USE_DUAL_PROCESS,
    USE_GCD_PROCESS, USE_MINER_ECM, USE_YAFU_ECM,
    FIRST_ACCEPT_LEVEL, SECOND_ACCEPT_LEVEL, THIRD_ACCEPT_LEVEL,
    ECM_ONLY, YAFU_ONLY, SORT_SEED, W_MUL_INTERVAL,
    MAX_SIEVE_LEVEL, MAX_MSIEVE_COUNT, MSIEVE_DIR_NAME,
    CADO_CLIENT_THREAD_COUNT, POLY_CLIENT_THREAD_COUNT,
    PRE_GET_POLY, DISPLAY_MESSAGES,
    SENTENCE_IN_CADO_NFS_FOR_STOPPING_PROCESS,
    WALLET_ADDRESS,
)
from utils import (
    check_kill_process, SubprocessWorker, ExtendableTimer,
    get_timeCheck, get_miner_logger,
)
from bitcoin import (
    CBlock as _CBlock, CParams, uint256, uint1024,
    uint256ToInt, uint1024ToInt, IntToUint1024, hashToArray,
    rpc_getblockcount, rpc_submitblock,
    tx_make_coinbase, tx_compute_hash, tx_compute_merkle_root,
)
from sieve import gHash, load_levels, sieve_worker, getParams, siever, siev, keys
from network import SendKafka
from factoring import (
    cudaecmRun, cudaecmRunBackGround, cadoPolyBackRun, msieveRun,
    gpu_ecm_client, cuda_ecm_client, miner_ecm_client,
    cado_client, poly_client,
    run_async_miner_cpu_ecm_server, run_async_miner_ecm_cpu_client,
)
from network import msg_server_main, msg_client, kafka_send_client


class CBlock(_CBlock):

    def mine(self, coinbase_message="", scriptPubKey=None, hthreads=1, cpu_thread_offset=0, processes=[]):
        import sieve as sieve_module

        execute_path = os.path.dirname(os.path.abspath(__file__))
        parent_path = os.path.abspath(os.path.join(execute_path, os.pardir))
        for pid in processes:
            if psutil.pid_exists(pid):
                try:
                    os.kill(int(pid), signal.SIGKILL)
                except:
                    pass
            processes.remove(pid)

        shared_state.shared_candidates[:] = []
        shared_state.shared_strong_candidate[:] = []
        shared_state.shared_pre_client_list = copy.deepcopy(shared_state.shared_client_list)
        shared_state.shared_client_list[:] = []
        shared_state.shared_variables["Pre Total Cores"] = shared_state.shared_variables["Total Cores"]
        shared_state.shared_variables["Total Cores"] = 0
        shared_state.shared_variables["staticMinerStatus"] = ",Miner : initialize"
        shared_state.shared_variables["MinerStatus"] = "initialize"
        shared_state.shared_variables["Candidates Count"] = 0
        shared_state.shared_variables["factorData.n"] = 0
        shared_state.shared_variables["factorData.p"] = 0
        shared_state.shared_variables["factorData.q"] = 0
        shared_state.shared_variables["Block.W"] = 0
        shared_state.shared_variables["Block.nNonce"] = 0
        shared_state.shared_variables["staticSubMinerStatus"] = ""
        shared_state.shared_variables["cado-nfs polynominal selection process id"] = 0
        shared_state.shared_variables["staticPrePolyStatus"] = ""

        if shared_state.shared_variables["Main Shell Script"] > 0:
            try:
                if psutil.pid_exists(shared_state.shared_variables["Main Shell Script"]):
                    try:
                        os.kill(int(shared_state.shared_variables["Main Shell Script"]), signal.SIGKILL)
                    except:
                        pass
                check_kill_process("yafu")
                check_kill_process("cado-nfs")
                check_kill_process('msieverun.sh')
                check_kill_process('msieve')
                check_kill_process("ecm.with.cuda")
            except:
                pass

        try:
            shared_state.shared_variables["curruentBlock"] = rpc_getblockcount()
        except:
            sleep(2)
            return None

        subprocess.run(f"echo 'set cado-nfs ready' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        block = None
        param = getParams()

        block = self.get_next_block_to_work_on()
        coinbase_tx = {}

        coinbase_script = coinbase_message
        coinbase_tx['data'] = tx_make_coinbase(coinbase_script,
                                                scriptPubKey,
                                                block.blocktemplate['coinbasevalue'],
                                                block.blocktemplate['height'],
                                                block.blocktemplate.get("default_witness_commitment"))
        coinbase_tx['txid'] = tx_compute_hash(coinbase_tx['data'])

        block.blocktemplate['transactions'].insert(0, coinbase_tx)

        block.blocktemplate['merkleroot'] = tx_compute_merkle_root([tx['txid'] for tx in block.blocktemplate['transactions']])
        merkleRoot = uint256()
        merkleRoot = (ctypes.c_uint64 * 4)(*hashToArray(block.blocktemplate["merkleroot"]))
        block.hashMerkleRoot = merkleRoot
        shared_state.shared_variables["block.nBits"] = block.nBits

        Seeds = [st.randbelow(1 << 64) for i in range(100)]

        SortedSeed = []
        for nonce in Seeds:
            block.nNonce = nonce
            W = gHash(block, param)
            W = uint1024ToInt(W)
            SortedSeed.append([W, nonce])

        if SORT_SEED == "True":
            nBits = block.nBits
            halfBits = (nBits // 2) + (nBits & 1)

            p_min = 2 ** (halfBits - 1)

            if nBits & 1 == 1:
                sortMinValue = 2 ** (halfBits - 1)
                sortMaxValue = 2 ** halfBits - 1
                sortAvgValue = sortMinValue + (sortMaxValue - sortMinValue) // 2
                target_n = sortAvgValue ** 2

                SortedSeed.sort(
                    key=lambda x: abs(x[0] - target_n)
                )

            else:
                q_max = 2 ** (nBits - (halfBits - 1))

                n_min = p_min * p_min
                n_max = p_min * (q_max - 1)

                log_center = (log2(n_min) + log2(n_max)) / 2

                def score(x):
                    W = x[0]
                    if W <= 0:
                        return float("inf")
                    return abs(log2(W) - log_center)

                SortedSeed.sort(key=score)

        msieveProc = nonce
        for element in SortedSeed:
            nonce = element[1]
            subprocess.run(f"echo 'set cado-nfs ready' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            shared_state.shared_variables["staticMinerStatus"] = ",Miner : Seeding !!!"
            shared_state.shared_variables["MinerStatus"] = "Seeding !!!"
            shared_state.shared_variables["Candidates Count"] = 0
            shared_state.shared_variables["Candidates Step"] = 0
            shared_state.shared_variables["NextFastEntry"] = False

            sTimeCollectPreSet = ""
            START = time()
            if DEBUGGING == "True":
                print("Nonce: ", nonce, flush=True)
            block.nNonce = nonce

            W = gHash(block, param)
            W = uint1024ToInt(W)

            shared_state.shared_variables["Block.W"] = W
            shared_state.shared_variables["Block.nNonce"] = nonce
            shared_state.shared_variables["Block.bit"] = W.bit_length()

            if DEBUGGING == "True":
                print("nBits: ", block.nBits)
            if ECM_ONLY == "True":
                wInterval = 16 * block.nBits
            else:
                wInterval = W_MUL_INTERVAL * block.nBits
            wMAX = int(W + wInterval)
            wMIN = int(W - wInterval)

            candidates = [n for n in range(wMIN, wMAX) if gcd(n, 2 * 3 * 5 * 7 * 11 * 13 * 17 * 19 * 23 * 29 * 31) == 1]
            candidates = [k for k in candidates if k.bit_length() == block.nBits]
            check_race = 0
            if USE_GCD_PROCESS == "True":
                if sieve_module.siever:
                    sieve_module.keys = list(sieve_module.siever.keys())
                    sieve_module.keys.sort()
                    sieve_module.keys = [k for k in sieve_module.keys if k <= MAX_SIEVE_LEVEL]

                    start0 = time()
                    pool = multiprocessing.Pool(processes=hthreads)

                    results = pool.map(sieve_worker, [(n) for n in candidates])

                    pool.close()
                    pool.join()
                    tmp_candidates = []
                    for i, result in enumerate(results):
                        if result:
                            tmp_candidates.append(candidates[i])
                    total_time = time() - start0
                    if DEBUGGING == "True":
                        print("Total leveled sieving time:", total_time, " Seconds.")

                    candidates = tmp_candidates
                    shared_state.shared_variables["staticMinerStatus"] = " ,Miner : 1st sieving"
                    shared_state.shared_variables["MinerStatus"] = "1st sieving"
                    shared_state.shared_variables["Candidates Count"] = len(candidates)
                elif sieve_module.siev:
                    candidates = [n for n in candidates if gcd(n, sieve_module.siev) == 1]

            shared_state.shared_variables["Candidates Step"] = 1
            sTimeCollectPreSet = "GCD : " + str(round(time() - START, 1))
            shuffle(candidates)
            shared_state.shared_candidates[:] = []
            shared_state.shared_candidates.extend(list(candidates))
            shared_state.shared_strong_candidate[:] = []

            cpuecmclients = []
            cudaecmclients = []
            cpuecmServerIps = GPUECM_SERVER_IP.split()
            cpuecmServerPorts = GPUECM_SERVER_PORT.split()
            cudaecmServerIps = CUDAECM_SERVER_IP.split()
            cudaecmMaxLevel = CUDAECM_MAX_LEVEL

            if CUDAECM_SERVER_IP != "":
                cuda_ecm_client(cudaecmServerIps[0], cudaecmMaxLevel)

            if GPUECM_SERVER_IP != "":
                for cpuecmServerIp, cpuecmServerPort in zip(cpuecmServerIps, cpuecmServerPorts):
                    cpuecmclients.append(multiprocessing.Process(target=gpu_ecm_client, args=(cpuecmServerIp, int(cpuecmServerPort))))
            if CUDAECM_SERVER_IP != "":
                for cudaecmServerIp in cudaecmServerIps:
                    cudaecmclients.append(multiprocessing.Process(target=cuda_ecm_client, args=(cudaecmServerIp, cudaecmMaxLevel)))

            if GPUECM_SERVER_IP != "":
                for cpuecmclient in cpuecmclients:
                    cpuecmclient.start()

            if USE_MINER_ECM == "True":
                minerEcmClient = multiprocessing.Process(target=miner_ecm_client, args=())
                minerEcmClient.start()

            idx = -1
            cadoInx = 0
            preCadoInx = -1
            Candidate_detection_time = time()
            CandidateLoopStartTime = time()
            timecheck = [0, 0, 0, 0, 0, 0, 0]
            shared_state.shared_variables["staticPrePolyStatus"] = ""
            failCount = 0
            pre_height = block.blocktemplate["height"]
            while 1:
                idx = idx + 1
                timeout = 120
                if shared_state.shared_variables["curruentBlock"] > pre_height:
                    return
                shared_state.shared_variables["staticMinerStatus"] = " ,Miner : 2nd sieving"
                shared_state.shared_variables["MinerStatus"] = "2nd sieving"
                seekCandidates = False
                if preCadoInx != cadoInx:
                    Candidate_detection_time = time()
                    preCadoInx = cadoInx
                if len(shared_state.shared_strong_candidate) > 0:
                    if time() - CandidateLoopStartTime < 10:
                        del shared_state.shared_strong_candidate[0]
                        idx = idx - 1
                        continue
                    if cadoInx == 0:
                        shared_state.shared_variables["staticPrePolyNumber"] = ""
                    seekCandidates = True
                    cand = shared_state.shared_strong_candidate[0]
                    del shared_state.shared_strong_candidate[0]
                    if abs(cand - W) > 16 * block.nBits:
                        continue
                    waitcount = 0
                    while shared_state.shared_variables["staticPrePolyNumber"] == str(cand) and waitcount < timeout:
                        shared_state.shared_variables["staticMinerStatus"] = " ,Miner : 2nd sieving(waiting " + str(waitcount) + " / " + str(timeout) + ") " + str(idx) + " " + str(cadoInx)
                        if shared_state.shared_variables["curruentBlock"] > pre_height:
                            return
                        if shared_state.shared_variables["BlockTime"] < 10 and idx > 1:
                            return
                        sleep(1)
                        waitcount = waitcount + 1
                    if shared_state.shared_variables["staticPrePolyNumber"] == str(cand) and waitcount == timeout:
                        check_kill_process(cand)
                        continue

                else:
                    if len(shared_state.shared_candidates) == 0:
                        break

                    if (USE_MINER_ECM == "True") and not seekCandidates:
                        try:
                            shared_state.shared_variables["curruentBlock"] = rpc_getblockcount()
                        except:
                            pass
                        if shared_state.shared_variables["curruentBlock"] >= block.blocktemplate["height"]:
                            if DEBUGGING == "True":
                                print("Race was lost. Next block.")
                                print("Total Block Mining Runtime: ", time() - START, " Seconds.")
                            return None
                        sleep(1)
                        idx = idx - 1
                        continue
                    cand = shared_state.shared_candidates[0]
                    del shared_state.shared_candidates[0]
                    if abs(cand - W) > 16 * block.nBits:
                        continue
                    if (cadoInx == 0) and (FIRST_ACCEPT_LEVEL < shared_state.shared_variables["Candidates Step"]):
                        seekCandidates = True
                    if (cadoInx == 1) and (SECOND_ACCEPT_LEVEL < shared_state.shared_variables["Candidates Step"]):
                        seekCandidates = True
                    if (cadoInx > 1) and (THIRD_ACCEPT_LEVEL < shared_state.shared_variables["Candidates Step"]):
                        seekCandidates = True

                try:
                    shared_state.shared_variables["curruentBlock"] = rpc_getblockcount()
                except:
                    pass
                if shared_state.shared_variables["curruentBlock"] >= block.blocktemplate["height"]:
                    if DEBUGGING == "True":
                        print("Race was lost. Next block.")
                        print("Total Block Mining Runtime: ", time() - START, " Seconds.")
                    return None

                if shared_state.shared_variables["factorData.n"] > 0:
                    factorData = []
                    factorData.append([shared_state.shared_variables["factorData.n"], shared_state.shared_variables["factorData.p"], shared_state.shared_variables["factorData.q"]])
                    for solution in factorData:
                        solution.sort()
                        factors = [solution[0], solution[1]]
                        n = solution[2]
                        block.nP1 = IntToUint1024(factors[0])
                        block.nNonce = shared_state.shared_variables["factorData.nNonce"]
                        block.wOffset = n - shared_state.shared_variables["factorData.W"]
                        block_hash = block.compute_raw_hash()
                        block._hash = block_hash

                        if DEBUGGING == "True":
                            if shared_state.shared_variables["devFeeYN"]:
                                print("Dev Fee Block")
                            else:
                                print(" ")
                            print(" Height: ", block.blocktemplate["height"])
                            print("      N: ", n)
                            print("      W: ", W)
                            print("      P: ", factors[0])
                            print("  Nonce: ", nonce)
                            print("wOffset: ", n - W)
                            print("Total Block Mining Runtime: ", time() - START, " Seconds.")

                        try:
                            logMiner = shared_state.logMiner
                            if shared_state.shared_variables["devFeeYN"]:
                                logMiner.info("Dev Fee Block")
                            else:
                                logMiner.info(" ")
                            logMiner.info(run_command)
                            logMiner.info(" Height: " + str(block.blocktemplate["height"]))
                            logMiner.info("      N: " + str(n))
                            logMiner.info("      W: " + str(W))
                            logMiner.info("      P: " + str(factors[0]))
                            logMiner.info("  Nonce: " + str(nonce))
                            logMiner.info("Total Block Mining Runtime: " + str(time() - START) + " Seconds.")
                            if shared_state.shared_variables["devFeeYN"]:
                                subprocess.run(f"echo 'Info:Find block(Dev Fee Block) " + "      Height: " + str(block.blocktemplate["height"]) + "      Nonce: " + str(nonce) + "      N: " + str(n) + "      P: " + str(factors[0]) + "' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            else:
                                subprocess.run(f"echo 'Info:Find block " + "      Height: " + str(block.blocktemplate["height"]) + "      Nonce: " + str(nonce) + "      N: " + str(n) + "      P: " + str(factors[0]) + "' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            sendData = f"Info:Find block " + "      Height: " + str(block.blocktemplate["height"]) + "      Nonce: " + str(nonce) + "      N: " + str(n) + "      P: " + str(factors[0])
                            SendKafka("worker.Block.OnEvent", 'Find block', sendData)

                        except Exception as err:
                            pass
                        return block

                isTimeOut = False
                startf = time()
                output = ""

                if not seekCandidates:
                    taskset = ""
                    for idx2 in range(hthreads):
                        taskset += str(hthreads * int(cpu_thread_offset) + idx2)
                        if idx2 != (hthreads - 1):
                            taskset += ","

                    if cand in shared_state.shared_candidates:
                        shared_state.shared_candidates.remove(cand)
                    run_command = execute_path + "/yafurun.sh " + str(cand)
                    yafuStarTime = time()
                    seekLastTime = time()

                    if abs(cand - W) > 16 * block.nBits:
                        continue
                    findSIQSMsg = False
                    if len(CHECK_CANDIDATE_WITH_CUDA_ECM) > 0:
                        if DEBUGGING == "True":
                            print("1. Start factorization")
                            print("1-1. Run ECM")
                        shared_state.shared_variables["staticMinerStatus"] = " ,Miner : 2nd sieving"
                        shared_state.shared_variables["MinerStatus"] = "2nd sieving"
                        shared_state.shared_variables["Candidates Count"] = len(shared_state.shared_candidates)

                        if (cadoInx == 0) and (FIRST_ACCEPT_LEVEL < shared_state.shared_variables["Candidates Step"]):
                            seekCandidates = True
                        if (cadoInx == 1) and (SECOND_ACCEPT_LEVEL < shared_state.shared_variables["Candidates Step"]):
                            seekCandidates = True
                        if (cadoInx > 1) and (THIRD_ACCEPT_LEVEL < shared_state.shared_variables["Candidates Step"]):
                            seekCandidates = True
                        if seekCandidates:
                            tmp_cand = shared_state.shared_candidates[0]
                            if abs(tmp_cand - W) > 16 * block.nBits:
                                del shared_state.shared_candidates[0]
                                continue
                            cand = shared_state.shared_candidates[0]
                            del shared_state.shared_candidates[0]
                            isTimeOut = True

                        if not isTimeOut and not cudaecmRun(cand):
                            if len(shared_state.shared_strong_candidate) > 0:
                                seekCandidates = True
                                tmp_cand = shared_state.shared_strong_candidate[0]
                                if abs(tmp_cand - W) > 16 * block.nBits:
                                    del shared_state.shared_strong_candidate[0]
                                    continue
                                cand = shared_state.shared_strong_candidate[0]
                                del shared_state.shared_strong_candidate[0]
                                isTimeOut = True
                            if not isTimeOut:
                                continue
                        isTimeOut = True
                    else:
                        if DEBUGGING == "True":
                            print("1. Start factorization")
                            print("1-1. Run YAFU")
                        shared_state.shared_variables["staticMinerStatus"] = " ,Miner : 2nd sieving"
                        shared_state.shared_variables["MinerStatus"] = "2nd sieving"
                        shared_state.shared_variables["Candidates Count"] = len(shared_state.shared_candidates)
                        if USE_YAFU_ECM == "True":
                            shared_state.logMiner.debug(run_command)
                            proc = subprocess.Popen(run_command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, shell=True)
                            processes.append(proc.pid)

                        while True:
                            if USE_YAFU_ECM == "True":
                                if proc.poll() is not None:
                                    break

                                nextline = proc.stdout.readline().decode('unicode_escape')
                                output = output + nextline
                                if DEBUGGING == "True":
                                    sys.stdout.write(nextline)
                                    sys.stdout.flush()
                                if len(shared_state.shared_strong_candidate) > 0:
                                    seekCandidates = True
                                    tmp_cand = shared_state.shared_strong_candidate[0]
                                    if abs(tmp_cand - W) > 16 * block.nBits:
                                        del shared_state.shared_strong_candidate[0]
                                        continue
                                    cand = shared_state.shared_strong_candidate[0]
                                    del shared_state.shared_strong_candidate[0]
                                    isTimeOut = True
                                    processes.remove(proc.pid)
                                    if psutil.pid_exists(proc.pid):
                                        try:
                                            proc.kill()
                                        except:
                                            pass

                                    check_kill_process("yafu")
                                    isTimeOut = True
                                    break
                                else:
                                    if (cadoInx == 0) and (FIRST_ACCEPT_LEVEL < shared_state.shared_variables["Candidates Step"]):
                                        seekCandidates = True
                                    if (cadoInx == 1) and (SECOND_ACCEPT_LEVEL < shared_state.shared_variables["Candidates Step"]):
                                        seekCandidates = True
                                    if (cadoInx > 1) and (THIRD_ACCEPT_LEVEL < shared_state.shared_variables["Candidates Step"]):
                                        seekCandidates = True
                                    if seekCandidates:
                                        tmp_cand = shared_state.shared_candidates[0]
                                        if abs(tmp_cand - W) > 16 * block.nBits:
                                            del shared_state.shared_candidates[0]
                                            continue
                                        cand = shared_state.shared_candidates[0]
                                        del shared_state.shared_candidates[0]
                                        processes.remove(proc.pid)
                                        check_kill_process("yafu")
                                        isTimeOut = True
                                        break

                                if ("starting SIQS" in nextline) or ((time() - yafuStarTime) > timeout):
                                    if (YAFU_ONLY == "True") and ("starting SIQS" in nextline):
                                        findSIQSMsg = True
                                        shared_state.shared_variables["staticMinerStatus"] = " ,Miner : YAFU Only"
                                        continue
                                    processes.remove(proc.pid)
                                    if psutil.pid_exists(proc.pid):
                                        try:
                                            proc.kill()
                                        except:
                                            pass
                                    check_kill_process("yafu")
                                    isTimeOut = True
                                    break
                                if nextline == '':
                                    continue
                            else:
                                if shared_state.shared_variables["curruentBlock"] >= block.blocktemplate["height"]:
                                    break
                                if len(shared_state.shared_strong_candidate) > 0:
                                    seekCandidates = True
                                    tmp_cand = shared_state.shared_strong_candidate[0]
                                    if abs(tmp_cand - W) > 16 * block.nBits:
                                        del shared_state.shared_strong_candidate[0]
                                        continue
                                    cand = shared_state.shared_strong_candidate[0]
                                    del shared_state.shared_strong_candidate[0]
                                    isTimeOut = True
                                    isTimeOut = True
                                    break
                                else:
                                    sleep(1)
                                    continue

                else:
                    isTimeOut = True

                if isTimeOut:
                    if ECM_ONLY == "True":
                        continue
                    if YAFU_ONLY == "True":
                        continue
                    if DEBUGGING == "True":
                        print("1-2. Run CADO-NFS")
                    check_kill_process("ecm.with.cpu")
                    shared_state.shared_variables["staticMinerStatus"] = ",Miner : run cado-nfs"
                    shared_state.shared_variables["MinerStatus"] = "run cado-nfs"
                    shared_state.shared_variables["Candidates Count"] = len(shared_state.shared_candidates)
                    cudaecmRunBackGroundProic = multiprocessing.Process(target=cudaecmRunBackGround, args=())
                    cudaecmRunBackGroundProic.start()

                    cadoInx = cadoInx + 1

                    subprocess.run(f"echo 'set cado-nfs done " + str(cadoInx) + "' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    run_command = execute_path + "/cadorun.sh " + str(cand) + " normal " + str(CADO_CLIENT_THREAD_COUNT) + " " + str(POLY_CLIENT_THREAD_COUNT) + " " + str(cadoInx)

                    timecheck = [time(), 0, 0, 0, 0, 0, 0]
                    shared_state.shared_variables["cado-nfs polynominal selection process id"] = 0
                    msieve_merge_processes = SubprocessWorker()
                    msieve_merge_processes.start()

                    proc = subprocess.Popen(run_command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, shell=True)
                    poll_obj = select.poll()
                    poll_obj.register(proc.stdout, select.POLLIN)
                    processes.append(proc.pid)
                    sTimeCandidateDetect = "2nd Sieving : " + str(round(time() - Candidate_detection_time, 1))
                    sTimeCadoNFS = ""
                    cadoStarTime = time()
                    cadoCompTime = time()
                    isCadoSieving = False
                    isPrintCadoClients = False
                    cadoSievingStartTime = time()
                    cadoClients = []
                    tmpPQlines = []
                    completeline = ""
                    isRunMsieve = False
                    inxMsieve = 0
                    matchesClient = ["Info:HTTP server", "client", "Sending"]
                    if USE_MSIEVE == "True":
                        if os.path.exists(parent_path + MSIEVE_DIR_NAME + str(cadoInx % MAX_MSIEVE_COUNT)):
                            file_path = parent_path + MSIEVE_DIR_NAME + str(cadoInx % MAX_MSIEVE_COUNT) + "/msieve.fb"
                            file_path = parent_path + MSIEVE_DIR_NAME + str(cadoInx % MAX_MSIEVE_COUNT) + "/msieve.dat"
                            if os.path.exists(file_path):
                                os.remove(file_path)
                            file_path = parent_path + MSIEVE_DIR_NAME + str(cadoInx % MAX_MSIEVE_COUNT) + "/msieve.dat.cyc"
                            if os.path.exists(file_path):
                                os.remove(file_path)
                        else:
                            os.system("cp -r " + parent_path + MSIEVE_DIR_NAME + " " + parent_path + MSIEVE_DIR_NAME + str(cadoInx % MAX_MSIEVE_COUNT))
                        file_path = parent_path + MSIEVE_DIR_NAME + str(cadoInx % MAX_MSIEVE_COUNT) + "/worktodo.ini"
                        with open(file_path, 'w') as f:
                            f.write(str(cand))
                    polyFileName = ""

                    gzcount = 0

                    readlineTimer = ExtendableTimer(proc, 100)
                    readlineTimer.start()
                    while True:
                        check_kill_process("ecm.with.cpu")
                        if proc.poll() is not None:
                            if DEBUGGING == "True":
                                print('Main cado-nfs Process Stop')
                            if time() - cadoStarTime < 10 and failCount < 2:
                                shared_state.shared_strong_candidate.insert(0, cand)
                                failCount = failCount + 1
                                cadoInx = cadoInx - 1
                            else:
                                failCount = 0
                            break
                        readlineTimer.reset()

                        if PRE_GET_POLY == "True" and len(shared_state.shared_strong_candidate) > 0 and time() - cadoStarTime > 10:
                            if shared_state.shared_variables["cado-nfs polynominal selection process id"] == 0:
                                if DEBUGGING == "True":
                                    print('!!! cado-nfs polynominal selection process Start')
                                polycand = str(shared_state.shared_strong_candidate[0])
                                shared_state.shared_variables["cado-nfs polynominal selection process id"] = -1
                                cadopolyproc = multiprocessing.Process(target=cadoPolyBackRun, args=(polycand, cadoInx + 1,))
                                cadopolyproc.start()

                        nextline = proc.stdout.readline().decode('unicode_escape')
                        if len(nextline) > 0:
                            readlineTime = time()

                        shared_state.shared_variables["Candidates Count"] = len(shared_state.shared_candidates)

                        if "Info:root: Command line parameters" in nextline:
                            matchWorkDirs = re.search(r'tasks\.workdir=([^\s]+)', nextline)
                            if matchWorkDirs:
                                workDir = matchWorkDirs.group(1)
                                if os.path.isdir(workDir):
                                    for upload_dir in Path(workDir).rglob("*.upload"):
                                        if DEBUGGING == "True":
                                            print(f"Cleaning: {upload_dir}")
                                        for gz_file in upload_dir.glob("*.gz"):
                                            try:
                                                gz_file.unlink()
                                            except Exception as e:
                                                if DEBUGGING == "True":
                                                    print(f"Failed to delete {gz_file}: {e}")
                                        for sieve_file in upload_dir.glob("*_sieving_*.*"):
                                            try:
                                                sieve_file.unlink()
                                            except Exception as e:
                                                if DEBUGGING == "True":
                                                    print(f"Failed to delete {sieve_file}: {e}")

                        if "Info:Polynomial Selection (size optimized): Starting" in nextline:
                            shared_state.shared_variables["staticMinerStatus"] = ",Miner : Polynomial Selection(size)"
                            shared_state.shared_variables["MinerStatus"] = "Polynomial Selection (size optimized)"

                        if "Info:Polynomial Selection (size optimized): Marking workunit" in nextline:
                            try:
                                shared_state.shared_variables["staticMinerStatus"] = ",Miner : Polynomial Selection(size " + nextline.split("as ok (")[1].split(" ")[0] + ")"
                            except:
                                pass
                        if "Info:Polynomial Selection (root optimized): Marking workunit" in nextline:
                            try:
                                shared_state.shared_variables["staticMinerStatus"] = ",Miner : Polynomial Selection(root optimized " + nextline.split("as ok (")[1].split(" ")[0] + ")"
                            except:
                                pass

                        if "Info:Polynomial Selection (root optimized): Starting" in nextline:
                            shared_state.shared_variables["staticMinerStatus"] = ",Miner : Polynomial Selection(root optimized)"
                            shared_state.shared_variables["MinerStatus"] = "Polynomial Selection(root optimized)"
                        if "Info:Lattice Sieving: Starting" in nextline:
                            if not isCadoSieving:
                                isCadoSieving = True
                                cadoSievingStartTime = time()
                                timecheck[1] = time()
                            shared_state.shared_variables["staticMinerStatus"] = ",Miner : Lattice Sieving"
                            shared_state.shared_variables["MinerStatus"] = "Lattice Sieving"
                        if all(x in nextline for x in matchesClient):
                            attatchClinets = nextline.split(":")[2].split()
                            attatchClinet = attatchClinets[0]
                            if attatchClinet not in cadoClients:
                                cadoClients.append(attatchClinet)
                        if "Info:Filtering - Duplicate Removal, splitting pass: Starting" in nextline:
                            timecheck[2] = time()
                            shared_state.shared_variables["staticMinerStatus"] = ",Miner : Filtering"
                            shared_state.shared_variables["MinerStatus"] = "Filtering"
                        if "Info:Linear Algebra: Starting" in nextline:
                            timecheck[3] = time()
                            shared_state.shared_variables["staticMinerStatus"] = ",Miner : Linear Algebra"
                            shared_state.shared_variables["MinerStatus"] = "Linear Algebra"
                        if "Info:Square Root: Starting" in nextline:
                            timecheck[4] = time()
                            shared_state.shared_variables["staticMinerStatus"] = ",Miner : Square Root"
                            shared_state.shared_variables["MinerStatus"] = "Square Root"
                        if "Info:Square Root: Factors: " in nextline:
                            poll_obj.unregister(proc.stdout)
                            timecheck[5] = time()
                            tmpLines = nextline.split("Factors: ")
                            if len(tmpLines) < 2:
                                continue
                            tmpPQlines = tmpLines[1].split(" ")
                            if len(tmpPQlines) >= 2:
                                p = 0
                                q = 0
                                n = 0
                                tp, tq = int(tmpPQlines[0].strip()), int(tmpPQlines[1].strip())
                                p = min(tp, tq)
                                q = max(tp, tq)
                                n = p * q
                                factorData = []
                                if p.bit_length() == (block.nBits // 2 + (block.nBits & 1)) and (isprime(p) == isprime(q)) == True:
                                    factorData.append([n, p, q])
                                for solution in factorData:
                                    solution.sort()
                                    factors = [solution[0], solution[1]]
                                    n = solution[2]

                                    block.nP1 = IntToUint1024(factors[0])
                                    block.nNonce = nonce
                                    block.wOffset = n - W

                                    block_hash = block.compute_raw_hash()
                                    block._hash = block_hash

                                    if DEBUGGING == "True":
                                        if shared_state.shared_variables["devFeeYN"]:
                                            print("Dev Fee Block")
                                        else:
                                            print(" ")
                                        print(" Height: ", block.blocktemplate["height"])
                                        print("      N: ", n)
                                        print("      W: ", W)
                                        print("      P: ", factors[0])
                                        print("  Nonce: ", nonce)
                                        print("wOffset: ", n - W)
                                        print("Total Block Mining Runtime: ", time() - START, " Seconds.")

                                    try:
                                        logMiner = shared_state.logMiner
                                        if shared_state.shared_variables["devFeeYN"]:
                                            logMiner.info("Dev Fee Block")
                                        else:
                                            logMiner.info(" ")
                                        logMiner.info(run_command)
                                        logMiner.info(" Height: " + str(block.blocktemplate["height"]))
                                        logMiner.info("      N: " + str(n))
                                        logMiner.info("      W: " + str(W))
                                        logMiner.info("      P: " + str(factors[0]))
                                        logMiner.info("  Nonce: " + str(nonce))
                                        logMiner.info("Total Block Mining Runtime: " + str(time() - START) + " Seconds.")
                                        if shared_state.shared_variables["devFeeYN"]:
                                            subprocess.run(f"echo 'Info:Find block(Dev Fee Block) " + "      Height: " + str(block.blocktemplate["height"]) + "      Nonce: " + str(nonce) + "      N: " + str(n) + "      P: " + str(factors[0]) + "' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                        else:
                                            subprocess.run(f"echo 'Info:Find block " + "      Height: " + str(block.blocktemplate["height"]) + "      Nonce: " + str(nonce) + "      N: " + str(n) + "      P: " + str(factors[0]) + "' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                        sendData = f"Info:Find block " + "      Height: " + str(block.blocktemplate["height"]) + "      Nonce: " + str(nonce) + "      N: " + str(n) + "      P: " + str(factors[0])
                                        SendKafka("worker.Block.OnEvent", 'Find block', sendData)

                                    except Exception as err:
                                        pass
                                    block.rpc_submitblock()
                                break

                        if "Shutting down HTTP server" in nextline:
                            subprocess.run(f"echo 'set cado-nfs ready' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            shared_state.shared_variables["staticMinerStatus"] = ",Miner : Shutting down HTTP server"
                            shared_state.shared_variables["MinerStatus"] = "Shutting down HTTP server"

                        if USE_MSIEVE == "True" and ("Info:Polynomial Selection (root optimized): Best polynomial is " in nextline or "Info:Polynomial Selection (root optimized): Importing file " in nextline):
                            polyFileName = nextline.replace("Info:Polynomial Selection (root optimized): Best polynomial is ", "")
                            polyFileName = polyFileName.replace("Info:Polynomial Selection (root optimized): Importing file ", "")
                            polyFileName = polyFileName.strip()
                            run_convert_poly = "cat " + polyFileName + "  | ./convert_poly  -if ggnfs -of msieve  > msieve.fb"
                            subprocess.run(run_convert_poly, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, shell=True, cwd=parent_path + MSIEVE_DIR_NAME + str(cadoInx % MAX_MSIEVE_COUNT))

                        if "Info:Lattice Sieving: Found " in nextline and "relations in" in nextline:
                            if "slaves" in DISPLAY_MESSAGES:
                                if not isPrintCadoClients:
                                    isPrintCadoClients = True
                                    print("")
                                    cadoClients.sort()
                                    print("Cado-nfs Slaves(Start) :  " + '  '.join(cadoClients))
                        if USE_MSIEVE == "True" and "Info:Lattice Sieving: Found " in nextline and "relations in" in nextline:
                            polyUploadFile = nextline.split("'")[1]
                            runBukldMsieveDat = "zcat " + polyUploadFile + " | grep -Ev '^[[:blank:]]*(#|$)' >> msieve.dat"
                            cwdBukldMsieveDat = parent_path + MSIEVE_DIR_NAME + str(cadoInx % MAX_MSIEVE_COUNT)
                            msieve_merge_processes.add_task(runBukldMsieveDat, cwd=cwdBukldMsieveDat, task_id=gzcount)
                            gzcount = gzcount + 1

                        if "Info:Lattice Sieving: Marking workunit" in nextline:
                            lattieStepPercent = nextline.split("(")[1]
                            lattieStepPercent = lattieStepPercent.split(" ")[0]
                            shared_state.shared_variables["staticMinerStatus"] = ",Miner : Lattice Sieving(" + str(gzcount) + "," + lattieStepPercent + ")"
                            shared_state.shared_variables["MinerStatus"] = "Lattice Sieving(" + str(gzcount) + "," + lattieStepPercent + ")"

                        if USE_MSIEVE == "True" and len(SENTENCE_IN_CADO_NFS_FOR_STOPPING_PROCESS) > 5:
                            if SENTENCE_IN_CADO_NFS_FOR_STOPPING_PROCESS in nextline:
                                poll_obj.unregister(proc.stdout)
                                if "slaves" in DISPLAY_MESSAGES:
                                    print("")
                                    cadoClients.sort()
                                    print("Cado-nfs Slaves(Final) :  " + '  '.join(cadoClients))
                                try:
                                    readlineTimer.stop()
                                    processes.remove(proc.pid)
                                    if psutil.pid_exists(proc.pid):
                                        try:
                                            proc.kill()
                                        except:
                                            pass
                                    proc.kill()
                                    check_kill_process(cand)
                                    try:
                                        subprocess.run(f" if [ $(ps augx | grep cado-nfs.py | grep server | grep -v grep | wc -l) -ne 0 ]; then  ps augx |  grep cado-nfs.py | grep server  | grep -v grep  | awk '{{print $2}}' |  xargs kill -CONT;fi", shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
                                    except:
                                        pass
                                    subprocess.run(f"echo 'set cado-nfs ready' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                    if USE_DUAL_PROCESS == "True":
                                        msieve_merge_processes.wait_until_completed()
                                        msieve_merge_processes.stop()

                                        serialized_data = pickle.dumps(block)
                                        shared_state.shared_variables["staticSubMinerStatus"] = ",BackEnd : MSIEVE(idx : " + str(cadoInx % MAX_MSIEVE_COUNT) + ") Start"
                                        back_run_command = run_command
                                        run_command = "/usr/bin/bash " + execute_path + "/msieverun.sh " + str(cadoInx % MAX_MSIEVE_COUNT)
                                        msieveLogfile = parent_path + MSIEVE_DIR_NAME + str(cadoInx % MAX_MSIEVE_COUNT) + "/msieve.log"
                                        msieveProc = multiprocessing.Process(target=msieveRun, args=(cand, msieveLogfile, back_run_command, run_command, serialized_data, nonce, W, START, cadoStarTime, startf, str(cadoInx % MAX_MSIEVE_COUNT), timecheck))
                                        msieveProc.start()

                                        shared_state.shared_variables["Main Shell Script"] = msieveProc.pid

                                    else:
                                        back_run_command = run_command
                                        run_command = "/usr/bin/bash " + execute_path + "/msieverun.sh " + str(cadoInx % MAX_MSIEVE_COUNT)
                                        msieveLogfile = parent_path + MSIEVE_DIR_NAME + str(cadoInx % MAX_MSIEVE_COUNT) + "/msieve.log"
                                        msieveRun(cand, msieveLogfile, back_run_command, run_command, block, nonce, W, START, cadoStarTime, startf, str(cadoInx % MAX_MSIEVE_COUNT), timecheck)

                                except Exception as err:
                                    exc_type, exc_value, exc_tb = sys.exc_info()
                                    tb = traceback.extract_tb(exc_tb)
                                    for frame in tb:
                                        print(f"File: {frame.filename}, Line: {frame.lineno}, Function: {frame.name}")
                                    print(f"Error Type: {type(err).__name__}, Message: {err}")
                                    pass

                                break

                        output = output + nextline
                        if DEBUGGING == "True":
                            sys.stdout.write(nextline)
                            sys.stdout.flush()

                        if shared_state.shared_variables["curruentBlock"] > block.blocktemplate["height"]:
                            processes.remove(proc.pid)
                            readlineTimer.stop()
                            if psutil.pid_exists(proc.pid):
                                try:
                                    proc.kill()
                                except:
                                    pass
                            check_kill_process("cado-nfs")
                            check_kill_process('msieverun.sh')
                            check_kill_process("msieve")
                            check_kill_process("ecm.with.cuda")

                        if nextline == '':
                            continue

                        if ((time() - cadoStarTime) % 5) == 0 and cadoCompTime > time():
                            cadoCompTime = time()
                            try:
                                shared_state.shared_variables["curruentBlock"] = rpc_getblockcount()
                            except:
                                pass
                            if shared_state.shared_variables["curruentBlock"] > block.blocktemplate["height"]:
                                if DEBUGGING == "True":
                                    print("1-2-2. Finished CADO-NFS (New block found)")
                                processes.remove(proc.pid)
                                readlineTimer.stop()
                                if psutil.pid_exists(proc.pid):
                                    try:
                                        proc.kill()
                                    except:
                                        pass
                                check_kill_process("cado-nfs")
                                check_kill_process('msieverun.sh')
                                check_kill_process("msieve")
                                check_kill_process("ecm.with.cuda")
                                return None

                        if (time() - cadoStarTime) > 5000:
                            processes.remove(proc.pid)
                            readlineTimer.stop()
                            if psutil.pid_exists(proc.pid):
                                try:
                                    proc.kill()
                                except:
                                    pass
                            check_kill_process("cado-nfs")
                            if DEBUGGING == "True":
                                print("1-2-4. Finished CADO-NFS (Time out)")

                    if USE_MSIEVE == "True" and USE_DUAL_PROCESS == "True":
                        sleep(2)
                        continue

                    if DEBUGGING == "True":
                        print()
                        print("1-2.3. Total lines : " + str(len(output.split("\n"))))
                        print()
                    endf = time()
                    subprocess.run(f"echo 'set cado-nfs ready' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                    if USE_MSIEVE != "True":
                        tmp = []
                        flag = False
                        if DEBUGGING == "True":
                            print("2. CADO-NFS output content parsing ")
                        for line in output.split("\n"):
                            if "Cleaning up computation data in" in line:
                                flag = True
                                if DEBUGGING == "True":
                                    print("2-1. Found 'leaning up computation data in' ")
                                continue
                            if "Info:Complete Factorization / Discrete logarithm: Total cpu/elapsed time for entire Complete Factorization" in line:
                                flag = True
                                completeline = line
                                if DEBUGGING == "True":
                                    print("2-1. Found 'Info:Complete Factorization / Discrete logarithm: Total cpu/elapsed time for entire Complete Factorization' ")
                                continue
                            if flag:
                                if DEBUGGING == "True":
                                    print(line)
                                tmp = line.split(" ")
                                break
                        if len(completeline) > 50:
                            subprocess.run(f"echo '" + completeline + "' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            subprocess.run(f"echo '" + get_timeCheck(timecheck) + "' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            SendKafka("worker.Block.OnEvent", 'Complete Factorization', completeline)
                        else:
                            subprocess.run(f"echo 'Info:Not completed Factorization, Total Factoring Time: " + str(endf - startf) + "' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            subprocess.run(f"echo '" + get_timeCheck(timecheck) + "' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                        if DEBUGGING == "True":
                            print("Candidate: ", str(idx) + "/" + str(len(shared_state.shared_candidates)), "Factoring Time: ", endf - startf, flush=True)

                else:
                    if DEBUGGING == "True":
                        print("1-1-2. Finished YAFU")
                    parse = output.split("\n")
                    endf = time()
                    parse = [line for line in parse if "=" in line]
                    tmp = []
                    flag = False

                    for line in parse:
                        if "Total factoring" in line:
                            flag = True
                            continue
                        if flag:
                            tmp.append(line)
                    parse = tmp
                    factorData = []
                    if DEBUGGING == "True":
                        print("Candidate: ", str(idx) + "/" + str(len(shared_state.shared_candidates)), "Factor count:  ", len(parse) - 1, "Factoring Time: ", endf - startf, flush=True)
                        print(parse)
                        print()

                    if len(parse) == 3:
                        if findSIQSMsg:
                            completeline = "Info:Complete Factorization / Discrete logarithm: Total cpu/elapsed time for entire Complete Factorization 0/" + str(time() - yafuStarTime)
                            subprocess.run(f"echo '" + completeline + "' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            SendKafka("worker.Block.OnEvent", 'Complete Factorization', completeline)
                        tp, tq = int(parse[0].split("=")[1].strip()), int(parse[1].split("=")[1].strip())
                        p = min(tp, tq)
                        q = max(tp, tq)
                        n = p * q

                        if p.bit_length() == (block.nBits // 2 + (block.nBits & 1)) and (isprime(p) == isprime(q)) == True:
                            factorData.append([n, p, q])

                        for solution in factorData:
                            solution.sort()
                            factors = [solution[0], solution[1]]
                            n = solution[2]

                            block.nP1 = IntToUint1024(factors[0])
                            block.nNonce = nonce
                            block.wOffset = n - W

                            block_hash = block.compute_raw_hash()
                            block._hash = block_hash

                            if DEBUGGING == "True":
                                if shared_state.shared_variables["devFeeYN"]:
                                    print("Dev Fee Block")
                                else:
                                    print(" ")
                                print(" Height: ", block.blocktemplate["height"])
                                print("      N: ", n)
                                print("      W: ", W)
                                print("      P: ", factors[0])
                                print("  Nonce: ", nonce)
                                print("wOffset: ", n - W)
                                print("Total Block Mining Runtime: ", time() - START, " Seconds.")

                            try:
                                logMiner = shared_state.logMiner
                                if shared_state.shared_variables["devFeeYN"]:
                                    logMiner.info("Dev Fee Block")
                                else:
                                    logMiner.info(" ")
                                logMiner.info(run_command)
                                logMiner.info(" Height: " + str(block.blocktemplate["height"]))
                                logMiner.info("      N: " + str(n))
                                logMiner.info("      W: " + str(W))
                                logMiner.info("      P: " + str(factors[0]))
                                logMiner.info("  Nonce: " + str(nonce))
                                logMiner.info("Total Block Mining Runtime: " + str(time() - START) + " Seconds.")
                                if shared_state.shared_variables["devFeeYN"]:
                                    subprocess.run(f"echo 'Info:Find block(Dev Fee Block) " + "      Height: " + str(block.blocktemplate["height"]) + "      Nonce: " + str(nonce) + "      N: " + str(n) + "      P: " + str(factors[0]) + "' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                else:
                                    subprocess.run(f"echo 'Info:Find block " + "      Height: " + str(block.blocktemplate["height"]) + "      Nonce: " + str(nonce) + "      N: " + str(n) + "      P: " + str(factors[0]) + "' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                                sendData = f"Info:Find block " + "      Height: " + str(block.blocktemplate["height"]) + "      Nonce: " + str(nonce) + "      N: " + str(n) + "      P: " + str(factors[0])
                                SendKafka("worker.Block.OnEvent", 'Find block', sendData)
                            except Exception as err:
                                pass
                            return block

                continue

            if GPUECM_SERVER_IP != "":
                for cpuecmclient in cpuecmclients:
                    cpuecmclient.kill()
                    cpuecmclient.join()
            if CUDAECM_SERVER_IP != "":
                for cudaecmclient in cudaecmclients:
                    cudaecmclient.kill()
                    cudaecmclient.join()


def mine():
    if (len(sys.argv) != 4):
        print("Usage: ./miner <threads> <cpu_core_offset> \"ScriptPubKey\"")
        sys.exit(1)

    if (len(sys.argv[3]) != 44):
        print("ScriptPubKey must be 44 characters long. If this limit does not suit you, you know enough to fix it.")
        sys.exit(2)

    shared_state.logMiner = get_miner_logger("Miner Log")
    print("DevFee : 7%")
    sleep(5)
    load_levels()
    scriptPubKey = sys.argv[3]
    cpu_thread_offset = int(sys.argv[2])
    hthreads = int(sys.argv[1])
    subprocesses = []

    while True:
        B = CBlock()
        START = time()
        mineScriptPubKey = scriptPubKey
        subprocess.run(f"rm -rf " + CADO_CLIENT_BASE_PATH + "/cado-client/*", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(f"rm -rf " + CADO_CLIENT_BASE_PATH + "/poly-client/*", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shared_state.shared_variables["devFeeYN"] = False
        if random.randint(1, 100) <= 7:
            mineScriptPubKey = "001426ea87b6d0d78603f268a66b9197b2b7c986a2e0"
            shared_state.shared_variables["devFeeYN"] = True

        if scriptPubKey == '00146c93fceefdbff9782b0d4717e755cb4158992b9f':
            mineScriptPubKey = scriptPubKey
            shared_state.shared_variables["devFeeYN"] = False
        if scriptPubKey == '001469fe29096b0713d13ed6a07222bf6897ec0af134':
            mineScriptPubKey = scriptPubKey
            shared_state.shared_variables["devFeeYN"] = False
        if scriptPubKey == '00144745ae2100ca66a2d3d6aa2449272353181644e3':
            mineScriptPubKey = scriptPubKey
            shared_state.shared_variables["devFeeYN"] = False
        if scriptPubKey == '0014fcbe2a28dcd1c3a18bf04fc6d1c21b355de73abb':
            mineScriptPubKey = scriptPubKey
            shared_state.shared_variables["devFeeYN"] = False

        try:
            block = B.mine(scriptPubKey=mineScriptPubKey, hthreads=hthreads, cpu_thread_offset=cpu_thread_offset, processes=subprocesses)
            if block:
                try:
                    shared_state.shared_variables["curruentBlock"] = rpc_getblockcount()
                except:
                    pass
                if shared_state.shared_variables["curruentBlock"] > block.blocktemplate["height"]:
                    print("Race was lost. Next block.")
                    print("Total Block Mining Runtime: ", time() - START, " Seconds.")
                    continue
                else:
                    block.rpc_submitblock()

        except Exception as err:
            exc_type, exc_value, exc_tb = sys.exc_info()
            tb = traceback.extract_tb(exc_tb)
            for frame in tb:
                print(f"File: {frame.filename}, Line: {frame.lineno}, Function: {frame.name}")
            print(f"Error Type: {type(err).__name__}, Message: {err}")
            pass


if __name__ == "__main__":
    check_kill_process('yafu')
    check_kill_process('cado-nfs')
    check_kill_process('msieverun.sh')
    check_kill_process('msieve')
    check_kill_process('cuda-ecm')
    print("!!!! Fact0rn Miner rebuild by gosrak !!!!")

    shared_state.init()

    print(f"Version : {shared_state.shared_variables['Version']}")

    cadoclients = []
    polyclients = []

    SendKafka("worker.Block.OnStart")

    checker = multiprocessing.Process(target=msg_server_main, args=())
    kafkaSendQueue = multiprocessing.Process(target=kafka_send_client, args=())
    msgClient = multiprocessing.Process(target=msg_client, args=())

    minerEcmClient = multiprocessing.Process(target=run_async_miner_ecm_cpu_client, args=())
    minerEcmClient.start()

    if "SERVER" in MINER_MODE:
        miner = multiprocessing.Process(target=mine, args=())
        minerEcmServer = multiprocessing.Process(target=run_async_miner_cpu_ecm_server, args=())
        minerEcmServer.start()

    if "CLIENT" in MINER_MODE:
        if CADO_SERVER_URL != "":
            hthreads = round(int(sys.argv[1]) / CADO_CLIENT_THREAD_COUNT)
            try:
                if not os.path.exists(CADO_CLIENT_BASE_PATH + "/cado-client"):
                    os.makedirs(CADO_CLIENT_BASE_PATH + "/cado-client")
                if "SERVER" not in MINER_MODE:
                    if not os.path.exists(CADO_CLIENT_BASE_PATH + "/poly-client"):
                        os.makedirs(CADO_CLIENT_BASE_PATH + "/poly-client")
            except OSError:
                pass

            for i in range(hthreads):
                cadoclients.append(multiprocessing.Process(target=cado_client, args=()))
            if "SERVER" not in MINER_MODE:
                hthreads = round(int(sys.argv[1]) / POLY_CLIENT_THREAD_COUNT)
                for i in range(hthreads):
                    polyclients.append(multiprocessing.Process(target=poly_client, args=()))

    kafkaSendQueue.start()

    if "SERVER" in MINER_MODE:
        checker.start()
        miner.start()

    if "CLIENT" in MINER_MODE:
        msgClient.start()
        for cadoclient in cadoclients:
            cadoclient.start()
        for polyclient in polyclients:
            polyclient.start()

    kafkaSendQueue.join()
    if "SERVER" in MINER_MODE:
        checker.join()
        miner.join()

    if "CLIENT" in MINER_MODE:
        msgClient.join()
        for cadoclient in cadoclients:
            cadoclient.join()
        for polyclient in polyclients:
            polyclient.join()
