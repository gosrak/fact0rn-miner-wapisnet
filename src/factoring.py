import os
import sys
import json
import subprocess
import signal
import select
import re
import shutil
import uuid
import asyncio
import pickle
import multiprocessing
import multiprocessing as mp
from time import time, sleep
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict
from math import ceil
from pathlib import Path
from sympy.ntheory import isprime
import psutil
import nats

import shared_state
import config
from config import (
    DEBUGGING, WORKER, CADO_SERVER_URL, CADO_CLIENT_BASE_PATH,
    CUDAECM_SERVER_IP, CUDAECM_MAX_LEVEL, GPUECM_SERVER_IP,
    CHECK_CANDIDATE_WITH_CUDA_ECM, USE_MSIEVE, USE_DUAL_PROCESS,
    MINER_MODE, CADO_CLIENT_THREAD_COUNT, POLY_CLIENT_THREAD_COUNT,
    MAX_MSIEVE_COUNT, MSIEVE_DIR_NAME, ECM_ONLY,
    SENTENCE_IN_CADO_NFS_FOR_STOPPING_PROCESS, DISPLAY_MESSAGES,
    PRE_GET_POLY, NAT_MASTER_URL, ECM_STEP_OF_CANDIDATE_SIEVING,
    STOP_CADO_PROCESS_WITH_DUAL,
)
from utils import check_kill_process, SubprocessWorker, get_timeCheck
from bitcoin import IntToUint1024, uint1024ToInt
from network import SendKafka


def cudaecmRun(cand):
    preHeight = shared_state.shared_variables["curruentBlock"]
    currHeight = preHeight
    run_commands = CHECK_CANDIDATE_WITH_CUDA_ECM.split(",")
    for run_command in run_commands:
        run_ecm_command = run_command.replace("$cand", str(cand))
        proc = subprocess.run(run_ecm_command, stdout=subprocess.PIPE, shell=True)
        line = proc.stdout.decode('utf-8')
        currHeight = shared_state.shared_variables["curruentBlock"]
        parse = line.split(" ")
        if preHeight != currHeight:
            return False
        if len(parse) > 1:
            if DEBUGGING == "True":
                print("ecm.with.cuda : bad candidate. : " + line.strip())
            return False
        if len(shared_state.shared_strong_candidate) > 0:
            return False
    if DEBUGGING == "True":
        print("ecm.with.cuda : good candidate. : " + line.strip())
    return True


def cudaecmRunBackGround():
    if len(CHECK_CANDIDATE_WITH_CUDA_ECM) == 0:
        return
    preHeight = shared_state.shared_variables["curruentBlock"]
    currHeight = preHeight
    W = shared_state.shared_variables["Block.W"]
    nonce = shared_state.shared_variables["Block.nNonce"]
    while len(shared_state.shared_strong_candidate) == 0:
        currHeight = shared_state.shared_variables["curruentBlock"]
        if preHeight != currHeight:
            return
        if W != shared_state.shared_variables["Block.W"]:
            return
        if nonce != shared_state.shared_variables["Block.nNonce"]:
            return
        cand = shared_state.shared_candidates[0]
        del shared_state.shared_candidates[0]

        W = shared_state.shared_variables["Block.W"]
        nonce = shared_state.shared_variables["Block.nNonce"]
        run_commands = CHECK_CANDIDATE_WITH_CUDA_ECM.split(",")
        isbadcandidate = False
        for run_command in run_commands:
            run_ecm_command = run_command.replace("$cand", str(cand))
            proc = subprocess.run(run_ecm_command, stdout=subprocess.PIPE, shell=True)
            line = proc.stdout.decode('utf-8')
            parse = line.split(" ")
            currHeight = shared_state.shared_variables["curruentBlock"]
            if preHeight != currHeight:
                isbadcandidate = True
                break
            if W != shared_state.shared_variables["Block.W"]:
                isbadcandidate = True
                break
            if nonce != shared_state.shared_variables["Block.nNonce"]:
                isbadcandidate = True
                break
            if len(parse) > 1:
                isbadcandidate = True
                if DEBUGGING == "True":
                    print("ecm.with.cuda : bad candidate. : " + line.strip())
                break

        if isbadcandidate == True and DEBUGGING == "True":
            print("ecm.with.cuda : good candidate. : " + line.strip())
        if isbadcandidate == True and preHeight == shared_state.shared_variables["curruentBlock"]:
            shared_state.shared_strong_candidate.append(cand)


def cadoPolyBackRun(cand, cadoInx):
    execute_path = os.path.dirname(os.path.abspath(__file__))
    parent_path = os.path.abspath(os.path.join(execute_path, os.pardir))
    shared_state.shared_variables["staticPrePolyNumber"] = cand
    run_command = execute_path + "/cadorun.sh " + cand + " poly " + str(CADO_CLIENT_THREAD_COUNT) + " " + str(POLY_CLIENT_THREAD_COUNT) + " " + str(cadoInx)
    shared_state.shared_variables["cado-nfs polynominal selection process id"] = 1

    preHeight = shared_state.shared_variables["curruentBlock"]
    currHeight = preHeight
    W = shared_state.shared_variables["Block.W"]
    nonce = shared_state.shared_variables["Block.nNonce"]

    proc = subprocess.Popen(run_command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, shell=True)
    poll_obj = select.poll()
    poll_obj.register(proc.stdout, select.POLLIN)

    shared_state.shared_variables["cado-nfs polynominal selection process id"] = proc.pid
    polyFileName = ""
    readlineTime = time()
    START = time()
    active_jobs = {}
    start_pattern = re.compile(r"Info:HTTP server:\s+(\d+\.\d+\.\d+\.\d+).*Sending workunit\s+(\S+)")
    end_pattern = re.compile(r"Info:Polynomial Selection.*Marking workunit\s+(\S+)\s+as ok")
    workdir = ""
    timeout = 240

    try:
        while True:
            if proc.poll() is not None:
                break
            poll_result = poll_obj.poll(0)

            if poll_result:
                currHeight = shared_state.shared_variables["curruentBlock"]
                if preHeight != currHeight or W != shared_state.shared_variables["Block.W"] or nonce != shared_state.shared_variables["Block.nNonce"]:
                    poll_obj.unregister(proc.stdout)
                    check_kill_process(cand)
                    proc.kill()
                    shared_state.shared_variables["staticPrePolyStatus"] = ""
                    return

                if (time() - readlineTime) > timeout:
                    poll_obj.unregister(proc.stdout)
                    check_kill_process(cand)
                    proc.kill()
                    print("read line time out")
                    for task_id, info in list(active_jobs.items()):
                        print(f"Task Delay: {task_id} @ {info['ip']}  (Incomplete for over 60 sec)")
                    shared_state.shared_variables["staticPrePolyStatus"] = ""
                    shared_state.shared_variables["staticPrePolyNumber"] = "0"
                    if len(workdir) > 10:
                        shutil.rmtree(workdir)
                    break
                nextline = proc.stdout.readline().decode('unicode_escape')
                if DEBUGGING == "True":
                    print(nextline)
                if len(nextline) > 0:
                    readlineTime = time()

                start_match = start_pattern.search(nextline)
                if start_match:
                    ip, task_id = start_match.groups()
                    active_jobs[task_id] = {"ip": ip, "start_time": time()}
                end_match = end_pattern.search(nextline)
                if end_match:
                    task_id = end_match.group(1)
                    if task_id in active_jobs:
                        del active_jobs[task_id]

                if "Command line parameters" in nextline:
                    match = re.search(r'tasks\.workdir=([^\s]+)', nextline)
                    if match:
                        workdir = match.group(1)

                if "Info:Polynomial Selection (size optimized): Starting" in nextline:
                    timeout = 60
                    shared_state.shared_variables["staticPrePolyStatus"] = ",Next Poly : Polynomial Selection(size)"
                if "Info:Polynomial Selection (size optimized): Marking workunit" in nextline:
                    try:
                        shared_state.shared_variables["staticPrePolyStatus"] = ",Next Poly : Polynomial Selection(size " + nextline.split("as ok (")[1].split(" ")[0] + ")"
                    except:
                        pass
                if "Info:Polynomial Selection (root optimized): Starting" in nextline:
                    shared_state.shared_variables["staticPrePolyStatus"] = ",Next Poly : Polynomial Selection(root optimized)"
                if "Info:Polynomial Selection (root optimized): Marking workunit" in nextline:
                    try:
                        shared_state.shared_variables["staticPrePolyStatus"] = ",Next Poly : Polynomial Selection(root optimized " + nextline.split("as ok (")[1].split(" ")[0] + ")"
                    except:
                        pass

                if USE_MSIEVE == "True" and "Info:Lattice Sieving: Starting" in nextline:
                    poll_obj.unregister(proc.stdout)
                    check_kill_process(cand)
                    proc.kill()
                    sleep(1)
                    shared_state.shared_variables["NextFastEntry"] = True
                    check_kill_process(cand)
                    sleep(1)
                    break

                if USE_MSIEVE == "True" and "Info:Polynomial Selection (root optimized): Best polynomial is " in nextline:
                    polyFileName = nextline.replace("Info:Polynomial Selection (root optimized): Best polynomial is ", "")
                    polyFileName = polyFileName.strip()

                if USE_MSIEVE == "True" and "Info:Polynomial Selection (root optimized): Importing file " in nextline:
                    polyFileName = nextline.replace("Info:Polynomial Selection (root optimized): Importing file ", "")
                    polyFileName = polyFileName.strip()

        if len(polyFileName) > 0:
            run_convert_poly = "cat " + polyFileName + "  | ./convert_poly  -if ggnfs -of msieve  > msieve.fb"
            if not os.path.exists(parent_path + MSIEVE_DIR_NAME + str(cadoInx % MAX_MSIEVE_COUNT)):
                os.system("cp -r " + parent_path + MSIEVE_DIR_NAME + " " + parent_path + MSIEVE_DIR_NAME + str(cadoInx % MAX_MSIEVE_COUNT))
            subprocess.run(run_convert_poly, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, shell=True, cwd=parent_path + MSIEVE_DIR_NAME + str(cadoInx % MAX_MSIEVE_COUNT))
        shared_state.shared_variables["staticPrePolyStatus"] = ",Next Poly : Complete " + str(round(time() - START)) + " Sec"

    except Exception as err:
        import traceback
        exc_type, exc_value, exc_tb = sys.exc_info()
        tb = traceback.extract_tb(exc_tb)
        for frame in tb:
            print(f"File: {frame.filename}, Line: {frame.lineno}, Function: {frame.name}")
        print(f"Error Type: {type(err).__name__}, Message: {err}")
        pass

    shared_state.shared_variables["staticPrePolyNumber"] = "0"


def msieveRun(cand, msieveLogfile, backup_run_command, run_command, serialized_data, put_nonce, put_W, START, cadoStarTime, startf, idxStr, timecheck):
    factorStr = ""
    if timecheck[2] == 0:
        timecheck[2] = time()
    tmpPQlines = []
    completeline = ""
    block = None
    nonce = put_nonce
    displayMsg = "MSIEVE(idx : " + idxStr + ") start"
    W = put_W
    if USE_DUAL_PROCESS == "True":
        block = pickle.loads(serialized_data)
    else:
        block = serialized_data

    proc = subprocess.Popen(run_command, stderr=subprocess.STDOUT, stdout=subprocess.DEVNULL, shell=True)
    procLog = subprocess.Popen('tail -F --pid=' + str(proc.pid) + ' ' + msieveLogfile, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, universal_newlines=True)
    lineCnt = 0
    while True:
        if proc.poll() is not None:
            break
        if procLog.poll() is not None:
            break
        nextline = procLog.stdout.readline()[26:]
        lineCnt = lineCnt + 1
        if lineCnt > 10 and "commencing relation filtering" in nextline:
            displayMsg = "MSIEVE(idx : " + idxStr + ") " + nextline.strip()
        if lineCnt > 10 and "commencing linear algebra" in nextline:
            if timecheck[3] == 0:
                timecheck[3] = time()
            displayMsg = "MSIEVE(idx : " + idxStr + ") " + nextline.strip()
        if lineCnt > 10 and "commencing square root phase" in nextline:
            if timecheck[4] == 0:
                timecheck[4] = time()
            displayMsg = "MSIEVE(idx : " + idxStr + ") " + nextline.strip()
        if lineCnt > 10 and "commencing duplicate removal" in nextline:
            displayMsg = "MSIEVE(idx : " + idxStr + ") " + nextline.strip()
        if lineCnt > 10 and "commencing in-memory singleton removal" in nextline:
            displayMsg = "MSIEVE(idx : " + idxStr + ") " + nextline.strip()
        if lineCnt > 10 and "commencing 2-way merge" in nextline:
            displayMsg = "MSIEVE(idx : " + idxStr + ") " + nextline.strip()
        if lineCnt > 10 and "weight of" in nextline:
            displayMsg = "MSIEVE(idx : " + idxStr + ") " + nextline.strip()
        if lineCnt > 10 and "using GPU" in nextline:
            displayMsg = "MSIEVE(idx : " + idxStr + ") " + nextline.strip()
        if lineCnt > 10 and "multiply complete, coefficients" in nextline:
            displayMsg = "MSIEVE(idx : " + idxStr + ") " + nextline.strip()
        if USE_DUAL_PROCESS == "True":
            shared_state.shared_variables["staticSubMinerStatus"] = ",BackEnd : " + displayMsg
        else:
            shared_state.shared_variables["staticMinerStatus"] = ",Miner : " + displayMsg
            shared_state.shared_variables["MinerStatus"] = displayMsg
        if lineCnt > 10 and "CUDA_ERROR" in nextline:
            print("")
            print(nextline)
        if lineCnt > 10 and "filtering wants" in nextline:
            print("")
            print(nextline)
        if lineCnt > 10 and "found factor: " in nextline:
            tmpPQlines.append(nextline.split("found factor: ")[1])
            p = int(tmpPQlines[0].strip())
            q = int(cand / p)
            tmpPQlines.append(str(q))
        if lineCnt > 10 and " factor: " in nextline:
            if len(nextline.split(" factor: ")) >= 2:
                tmpPQlines.append(nextline.split(" factor: ")[1])
        if lineCnt > 10 and len(tmpPQlines) > 0 and ("elapsed time " in nextline or "found factor: " in nextline):
            if timecheck[5] == 0:
                timecheck[5] = time()
            displayMsg = "MSIEVE(idx : " + idxStr + ") " + nextline.strip()
            if USE_DUAL_PROCESS == "True":
                shared_state.shared_variables["staticSubMinerStatus"] = ",BackEnd : " + displayMsg
            else:
                shared_state.shared_variables["staticMinerStatus"] = ",Miner : " + displayMsg
                shared_state.shared_variables["MinerStatus"] = displayMsg
            if len(tmpPQlines) >= 2:
                tp, tq = int(tmpPQlines[0].strip()), int(tmpPQlines[1].strip())
                p = min(tp, tq)
                q = max(tp, tq)
                n = p * q
                factorStr = "|p1|_2=" + str(p.bit_length()) + " |p2|_2=" + str(q.bit_length()) + " |n|_2=" + str(n.bit_length())
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
                completeline = "Info:Complete Factorization / Discrete logarithm: Total cpu/elapsed time for entire Complete Factorization 0/" + str(round((time() - cadoStarTime), 3))
                proc.kill()
                procLog.kill()
                break

        if DEBUGGING == "True":
            sys.stdout.write(nextline)
            sys.stdout.flush()

        if shared_state.shared_variables["curruentBlock"] > block.blocktemplate["height"]:
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

    if len(completeline) > 50:
        subprocess.run(f"echo '" + completeline + "' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(f"echo '" + get_timeCheck(timecheck) + "  " + factorStr + "' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        SendKafka("worker.Block.OnEvent", 'Complete Factorization', completeline)
    else:
        subprocess.run(f"echo 'Info:Not completed Factorization, Total Factoring Time: " + str(time() - startf) + "' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(f"echo '" + get_timeCheck(timecheck) + "' | nc -w 5 localhost 29291", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shared_state.shared_variables["staticSubMinerStatus"] = ""


def gpu_ecm_client(hostip, hostPort):
    bConnected = False
    preHeight = shared_state.shared_variables["curruentBlock"]
    currHeight = preHeight
    W = shared_state.shared_variables["Block.W"]
    nonce = shared_state.shared_variables["Block.nNonce"]

    while True:
        if not (preHeight == shared_state.shared_variables["curruentBlock"] and W == shared_state.shared_variables["Block.W"] and nonce == shared_state.shared_variables["Block.nNonce"]):
            return

        cand = 0
        facCnt = 0
        parse = []
        if len(shared_state.shared_candidates) > 0:
            try:
                cand = shared_state.shared_candidates[0]
                del shared_state.shared_candidates[0]
                while (PRE_GET_POLY == "True" and len(shared_state.shared_strong_candidate) > 1) or (PRE_GET_POLY == "False" and len(shared_state.shared_strong_candidate) > 0):
                    if bConnected:
                        shared_state.shared_variables["staticCpuECMStatus"] = ",GPU-ECM : exists candidate"
                    else:
                        shared_state.shared_variables["staticCpuECMStatus"] = ",GPU-ECM : not connected"
                    if ECM_ONLY == "True":
                        shared_state.shared_variables["staticCpuECMStatus"] = ",GPU-ECM : ecm only continue"
                        break
                    sleep(1)
                    if not (preHeight == shared_state.shared_variables["curruentBlock"] and W == shared_state.shared_variables["Block.W"] and nonce == shared_state.shared_variables["Block.nNonce"]):
                        return

                if not (preHeight == shared_state.shared_variables["curruentBlock"] and W == shared_state.shared_variables["Block.W"] and nonce == shared_state.shared_variables["Block.nNonce"]):
                    return

            except Exception as err:
                pass
                continue
            try:
                stepOfCandidateSieving = ECM_STEP_OF_CANDIDATE_SIEVING
                ecmtime = time()
                run_command = "echo 'gpuecm " + str(cand) + "' | nc -W 1 " + hostip + " " + str(hostPort)

                if bConnected:
                    shared_state.shared_variables["staticCpuECMStatus"] = ",GPU-ECM : looking candidate"
                while True:
                    if not (preHeight == shared_state.shared_variables["curruentBlock"] and W == shared_state.shared_variables["Block.W"] and nonce == shared_state.shared_variables["Block.nNonce"]):
                        return
                    proc = subprocess.run(run_command, stdout=subprocess.PIPE, shell=True, timeout=1000)
                    parse = proc.stdout.decode('utf-8').split(" ")
                    if len(parse) > 1:
                        break
                    else:
                        sleep(1)

                if not (preHeight == shared_state.shared_variables["curruentBlock"] and W == shared_state.shared_variables["Block.W"] and nonce == shared_state.shared_variables["Block.nNonce"]):
                    return

                if len(parse) > 1:
                    now = time
                    bConnected = True
                    if int(parse[1]) == 1 and (time() - ecmtime) > 10:
                        if DEBUGGING == "True":
                            print("gpu-ecm : good candidate. : " + str(cand))
                        shared_state.shared_variables["staticCpuECMStatus"] = ",GPU-ECM : found candidate"
                        if preHeight == shared_state.shared_variables["curruentBlock"]:
                            shared_state.shared_strong_candidate.append(cand)
                    else:
                        if DEBUGGING == "True":
                            print("gpu-ecm :  bad candidate. : " + str(cand))
                        shared_state.shared_variables["staticCpuECMStatus"] = ",GPU-ECM : looking candidate"
                        if len(parse) > 3:
                            nBits = shared_state.shared_variables["block.nBits"]
                            tp, tq = int(parse[2].strip()), int(parse[3].strip())
                            p = min(tp, tq)
                            q = max(tp, tq)
                            n = p * q
                            if ((isprime(p) == isprime(q)) and (isprime(p) == True)):
                                if n == cand:
                                    if p.bit_length() == (nBits // 2 + (nBits & 1)) and (isprime(p) == isprime(q)) == True:
                                        shared_state.shared_variables["factorData.n"] = n
                                        shared_state.shared_variables["factorData.p"] = p
                                        shared_state.shared_variables["factorData.q"] = q
                                        shared_state.shared_variables["factorData.W"] = W
                                        shared_state.shared_variables["factorData.nNonce"] = nonce

                                        check_kill_process('yafu')
                                        check_kill_process('cado-nfs')
                else:
                    bConnected = False
                    shared_state.shared_variables["staticCpuECMStatus"] = ",GPU-ECM : not connected"
                    raise ValueError

            except Exception as err:
                if bConnected:
                    shared_state.shared_variables["staticCpuECMStatus"] = ",GPU-ECM : error"
                shared_state.shared_candidates.insert(0, cand)
                sleep(1)
                pass
        else:
            shared_state.shared_variables["staticCpuECMStatus"] = ",GPU-ECM : ready"
            sleep(1)


class EcmCPUEventHandler:
    def __init__(self, config_file="env.json"):
        if os.path.exists(config_file):
            with open(config_file) as f:
                self.config = json.load(f)
        else:
            self.config = {}

        self.nats_url = self.config.get("master_nats_url", NAT_MASTER_URL)
        self.nats_client = None
        self.result_received = asyncio.Event()
        self.last_result = None

    async def start(self):
        try:
            self.nats_client = await nats.connect(self.nats_url)
            await self.nats_client.subscribe(
                "ecm.result.final",
                cb=self._handle_result
            )
        except Exception as e:
            raise

    async def _handle_result(self, msg):
        try:
            data = json.loads(msg.data.decode())
            self.last_result = data
            self.result_received.set()
        except Exception as e:
            self.result_received.set()

    async def send_candidate(self, number):
        try:
            message = {
                "candidate": str(number),
                "timestamp": datetime.now().isoformat()
            }
            await self.nats_client.publish(
                "ecm.candidate",
                json.dumps(message).encode()
            )
        except Exception as e:
            pass

    async def close(self):
        if self.nats_client:
            await self.nats_client.drain()
            await self.nats_client.close()


def miner_ecm_client():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_async_miner_ecm_client())
    finally:
        loop.close()


async def run_async_miner_ecm_client():
    if len(shared_state.shared_pre_client_list) == 0:
        await asyncio.sleep(5)

    ecm_handler = EcmCPUEventHandler()
    await ecm_handler.start()

    preHeight = shared_state.shared_variables["curruentBlock"]
    currHeight = preHeight
    W = shared_state.shared_variables["Block.W"]
    nonce = shared_state.shared_variables["Block.nNonce"]
    while True:
        if not (preHeight == shared_state.shared_variables["curruentBlock"] and W == shared_state.shared_variables["Block.W"] and nonce == shared_state.shared_variables["Block.nNonce"]):
            await ecm_handler.close()
            return
        cand = 0
        parse = []
        if len(shared_state.shared_candidates) > 0:
            try:
                while (len(shared_state.shared_strong_candidate) > 0) or ("run cado-nfs" in shared_state.shared_variables["staticMinerStatus"] or "Polynomial Selection" in shared_state.shared_variables["staticMinerStatus"] or "Lattice Sieving" in shared_state.shared_variables["staticMinerStatus"]):
                    await asyncio.sleep(1)
                    if not (preHeight == shared_state.shared_variables["curruentBlock"] and W == shared_state.shared_variables["Block.W"] and nonce == shared_state.shared_variables["Block.nNonce"]):
                        await ecm_handler.close()
                        return
                cand = shared_state.shared_candidates[0]
                if DEBUGGING == "True":
                    print("Start miner-ecm : " + str(cand))
                del shared_state.shared_candidates[0]
            except Exception as err:
                pass
                continue

            try:
                ecms = []
                ecmtime = time()

                ecm_handler.result_received.clear()
                ecm_handler.last_result = None

                await ecm_handler.send_candidate(cand)

                while True:
                    try:
                        await asyncio.wait_for(ecm_handler.result_received.wait(), timeout=1)
                        if ecm_handler.last_result:
                            if ecm_handler.last_result["status"] == "failed":
                                if DEBUGGING == "True":
                                    print("miner-ecm : good candidate. : " + str(cand))
                                if (preHeight == shared_state.shared_variables["curruentBlock"] and W == shared_state.shared_variables["Block.W"] and nonce == shared_state.shared_variables["Block.nNonce"]):
                                    shared_state.shared_strong_candidate.append(cand)
                            else:
                                if DEBUGGING == "True":
                                    print(f"miner-ecm : bad candidate. : {cand}")
                            break
                        if ("run cado-nfs" in shared_state.shared_variables["staticMinerStatus"] or "Polynomial Selection" in shared_state.shared_variables["staticMinerStatus"] or "Lattice Sieving" in shared_state.shared_variables["staticMinerStatus"]):
                            break
                        if not (preHeight == shared_state.shared_variables["curruentBlock"] and W == shared_state.shared_variables["Block.W"] and nonce == shared_state.shared_variables["Block.nNonce"]):
                            break

                    except asyncio.TimeoutError:
                        if DEBUGGING == "True":
                            print(f"miner-ecm : waiting for result... candidate: {cand}")
                        continue

            except Exception as err:
                shared_state.shared_candidates.insert(0, cand)
                pass


def cuda_ecm_client(hostip, cutLimit):
    bConnected = False
    preHeight = shared_state.shared_variables["curruentBlock"]
    currHeight = preHeight
    shared_state.shared_variables["staticGpuECMStatus"] = ",CUDA-ECM : ready"
    shared_state.shared_variables["Candidates Step"] = 0
    W = shared_state.shared_variables["Block.W"]
    nonce = shared_state.shared_variables["Block.nNonce"]

    loopCnt = 1
    try:
        for inx in (10401, 10402, 10403, 10404, 10405, 10406):
            isValid = True
            if cutLimit < loopCnt:
                break
            currHeight = shared_state.shared_variables["curruentBlock"]
            if preHeight != currHeight:
                break
            if W != shared_state.shared_variables["Block.W"]:
                break
            if nonce != shared_state.shared_variables["Block.nNonce"]:
                break
            if bConnected:
                shared_state.shared_variables["staticGpuECMStatus"] = ",CUDA-ECM : looking candidate LEVEL(" + str(shared_state.shared_variables["Candidates Step"]) + ")"

            if len(shared_state.shared_candidates) > 0:
                sendData = []
                sendTxt = ""
                for idx, val in enumerate(shared_state.shared_candidates):
                    sendData.append(val)
                    if idx == 0:
                        sendTxt = str(idx) + " " + str(val)
                    else:
                        sendTxt = sendTxt + "\\n" + str(idx) + " " + str(val)
                totalCnt = len(sendData)
                run_command = "echo '" + sendTxt + "' | nc -W " + str(totalCnt) + " " + hostip + " " + str(inx)
                idx = 0
                shared_state.shared_variables["staticGpuECMStatus"] = ",CUDA-ECM : looking candidate LEVEL(" + str(shared_state.shared_variables["Candidates Step"]) + ")"
                proc = subprocess.Popen(run_command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, shell=True)
                currHeight = shared_state.shared_variables["curruentBlock"]
                if not (W == shared_state.shared_variables["Block.W"] and nonce == shared_state.shared_variables["Block.nNonce"]):
                    break
                if preHeight != currHeight:
                    break

                while True:
                    if proc.poll() is not None:
                        break
                    nextline = proc.stdout.readline().decode('unicode_escape')
                    currHeight = shared_state.shared_variables["curruentBlock"]
                    if preHeight != currHeight:
                        try:
                            proc.kill()
                        except:
                            pass
                        break
                    if len(nextline) > 0:
                        bConnected = True
                        parse = nextline.split(" ")
                        if len(parse) > 1:
                            if int(parse[1]) != 1:
                                if sendData[int(parse[0])] in shared_state.shared_candidates:
                                    nBits = shared_state.shared_variables["block.nBits"]
                                    n = sendData[int(parse[0])]
                                    p = int(parse[1].strip())
                                    q = n / p
                                    tp = p
                                    tq = q
                                    p = min(tp, tq)
                                    q = max(tp, tq)
                                    n = p * q

                                    if ((isprime(p) == isprime(q)) and (isprime(p) == True)):
                                        if p.bit_length() == (nBits // 2 + (nBits & 1)) and (isprime(p) == isprime(q)) == True:
                                            shared_state.shared_variables["factorData.n"] = n
                                            shared_state.shared_variables["factorData.p"] = p
                                            shared_state.shared_variables["factorData.q"] = q
                                            shared_state.shared_variables["factorData.W"] = W
                                            shared_state.shared_variables["factorData.nNonce"] = nonce
                                            check_kill_process('yafu')
                                            check_kill_process('cado-nfs')

                                    shared_state.shared_candidates.remove(sendData[int(parse[0])])
                        idx = idx + 1
                        if totalCnt <= idx:
                            try:
                                proc.kill()
                            except:
                                pass
                            break
                    if nextline == '':
                        continue
                if idx > 0:
                    shared_state.shared_variables["Candidates Step"] = inx + 1 - 10400
                    shared_state.shared_variables["staticGpuECMStatus"] = ",CUDA-ECM : Level " + str(shared_state.shared_variables["Candidates Step"] - 1)
            loopCnt = loopCnt + 1
    except Exception as err:
        pass


def cado_client():
    origin_path = os.getcwd()
    parent_path = os.path.abspath(os.path.join(origin_path, os.pardir))
    execute_path = parent_path + "/cado-nfs"
    preret = "ready"
    preInx = 0
    while True:
        curret = shared_state.shared_variables["CadoServerStatus"]
        curInx = shared_state.shared_variables["CadoServerIndex"]
        try:
            if shared_state.shared_variables["BlockTime"] < 2:
                sleep(1)
                check_kill_process('cado-nfs-client')
                check_kill_process('/sieve/las')
                continue

            if preret != curret or preInx != curInx:
                if curret == 'done':
                    if "SERVER" in MINER_MODE and USE_DUAL_PROCESS == "True" and STOP_CADO_PROCESS_WITH_DUAL == "True" and curInx > 1:
                        sleep(1)
                        continue

                    run_command = "make show | grep build_tree"
                    proc = subprocess.run(run_command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, shell=True, cwd=execute_path)
                    parse = proc.stdout.decode('utf-8')
                    if len(parse) > 0:
                        buid_dir = parse.replace("build_tree=", "")
                        buid_dir = buid_dir.replace("\n", "")
                        iuuid = uuid.uuid1()
                        suuid = str(iuuid)
                        cado_servers = CADO_SERVER_URL.split()
                        servers_command = ""
                        for cado_server in cado_servers:
                            servers_command = servers_command + " --server=" + cado_server
                        run_command = 'NICENESS=10;' + execute_path + '/cado-nfs-client.py ' + servers_command + ' --niceness 10 --bindir=' + buid_dir + ' --basepath="' + CADO_CLIENT_BASE_PATH + '/cado-client/' + suuid + '"'
                        proc = subprocess.run(run_command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, shell=True, cwd=execute_path)
            preret = curret
            preInx = curInx
        except Exception as err:
            sleep(5)
            pass
        sleep(1)


def poly_client():
    origin_path = os.getcwd()
    parent_path = os.path.abspath(os.path.join(origin_path, os.pardir))
    execute_path = parent_path + "/cado-nfs"
    preret = "ready"
    preInx = 0
    while True:
        curret = shared_state.shared_variables["CadoServerStatus"]
        curInx = shared_state.shared_variables["CadoServerIndex"]
        try:
            if preret != curret or preInx != curInx:
                if curret == 'done':
                    run_command = "make show | grep build_tree"
                    proc = subprocess.run(run_command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, shell=True, cwd=execute_path)
                    parse = proc.stdout.decode('utf-8')
                    if len(parse) > 0:
                        buid_dir = parse.replace("build_tree=", "")
                        buid_dir = buid_dir.replace("\n", "")
                        iuuid = uuid.uuid1()
                        suuid = str(iuuid)
                        cado_servers = CADO_SERVER_URL.split()
                        servers_command = ""
                        for cado_server in cado_servers:
                            polyservers = cado_server.split(':')
                            polyserver = polyservers[0] + ":" + polyservers[1] + ":" + str(int(polyservers[2]) + 1)
                            servers_command = servers_command + " --server=" + polyserver
                        run_command = 'NICENESS=11;' + execute_path + '/cado-nfs-client.py ' + servers_command + ' --niceness 10 --bindir=' + buid_dir + ' --basepath="' + CADO_CLIENT_BASE_PATH + '/poly-client/' + suuid + '"'
                        proc = subprocess.run(run_command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, shell=True, cwd=execute_path)
            preret = curret
            preInx = curInx
        except Exception as err:
            print(err)
            sleep(5)
            pass
        sleep(1)


@dataclass
class ECMResult:
    height: int
    nonce: int
    n: str
    factors: List[str]
    tool: str
    start_time: datetime
    end_time: datetime


class EcmMaster:
    def __init__(self, config_file="env.json"):
        B1Info = [[2000, 32], [11e3, 74], [5e4, 221], [25e4, 453], [1e6, 984], [3e6, 2541], [11e6, 4949], [43e6, 8266], [11e7, 20158], [26e7, 47173], [85e7, 77666]]

        if os.path.exists(config_file):
            with open(config_file) as f:
                self.config = json.load(f)
        else:
            self.config = {}

        print("NAT_MASTER_URL = " + NAT_MASTER_URL)

        self.nats_url = self.config.get("master_nats_url", NAT_MASTER_URL)
        self.nats_client = None
        self.slaves: Dict[str, int] = {}
        self.slaves_heartbeat = {}
        self.heartbeat_interval = 5
        self.total_cores = 0
        self.active_tasks = {}
        self.current_candidate = None
        self.current_step = 0
        self.b1_info = self.config.get("B1Info", B1Info)
        self.cpu_ecm_step = self.config.get("cpuEcmStep", ECM_STEP_OF_CANDIDATE_SIEVING)

    async def start(self):
        try:
            self.nats_client = await nats.connect(self.nats_url)
            await self.setup_subscriptions()
            self.heartbeat_task = asyncio.create_task(self._check_heartbeats())
        except Exception as e:
            raise

    async def _check_heartbeats(self):
        while True:
            current_time = datetime.now()
            dead_workers = []
            for slave_id, last_beat in self.slaves_heartbeat.items():
                if (current_time - last_beat).total_seconds() > self.heartbeat_interval * 2:
                    dead_workers.append(slave_id)
            for slave_id in dead_workers:
                self.remove_worker(slave_id)
            await asyncio.sleep(self.heartbeat_interval)

    def remove_worker(self, slave_id):
        if slave_id in self.slaves:
            del self.slaves[slave_id]
            del self.slaves_heartbeat[slave_id]
            self.total_cores = sum(self.slaves.values())
            if self.current_candidate and self.active_tasks:
                asyncio.create_task(self.start_ecm_step())

    async def setup_subscriptions(self):
        await self.nats_client.subscribe("ecm.register", cb=self._handle_registration)
        await self.nats_client.subscribe("ecm.candidate", cb=self._handle_candidate)
        await self.nats_client.subscribe("ecm.result", cb=self._handle_result)
        await self.nats_client.subscribe("ecm.heartbeat", cb=self._handle_heartbeat)

    async def _handle_registration(self, msg):
        try:
            data = json.loads(msg.data.decode())
            slave_id = data["worker_id"]
            cores = data["capabilities"]["cpu_cores"]
            self.slaves[slave_id] = cores
            self.total_cores = sum(self.slaves.values())
            if msg.reply:
                await self.nats_client.publish(msg.reply, json.dumps({"status": "registered"}).encode())
        except Exception as e:
            pass

    async def _handle_candidate(self, msg):
        try:
            data = json.loads(msg.data.decode())
            candidate = data["candidate"]
            if self.current_candidate:
                await self.stop_all_workers()
            self.current_candidate = candidate
            self.current_step = 0
            self.active_tasks.clear()
            await self.start_ecm_step()
        except Exception as e:
            pass

    async def stop_all_workers(self):
        stop_message = {"command": "stop", "reason": "new_candidate"}
        for slave_id in self.slaves:
            try:
                await self.nats_client.publish(f"ecm.control.{slave_id}", json.dumps(stop_message).encode())
            except Exception as e:
                pass

    async def start_ecm_step(self):
        if self.current_step >= self.cpu_ecm_step:
            await self.report_failure()
            return
        b1, total_curves = self.b1_info[self.current_step]
        curve_assignments = self._distribute_curves(total_curves)
        for slave_id, curves in curve_assignments.items():
            task = {"candidate": self.current_candidate, "b1": b1, "curves": curves}
            topic = f"ecm.task.{slave_id}"
            try:
                await self.nats_client.publish(topic, json.dumps(task).encode())
                self.active_tasks[slave_id] = "running"
            except Exception as e:
                pass

    def _distribute_curves(self, total_curves: int) -> Dict[str, int]:
        assignments = {}
        for slave_id, cores in self.slaves.items():
            curves = max(1, ceil(total_curves / self.total_cores * cores))
            assignments[slave_id] = curves
        return assignments

    async def _handle_result(self, msg):
        try:
            data = json.loads(msg.data.decode())
            slave_id = data["worker_id"]
            success = data.get("success", False)
            factors = data.get("factors", [])
            if success and len(factors) >= 2:
                try:
                    product = 1
                    for factor in factors:
                        product *= int(factor)
                    if str(product) == self.current_candidate:
                        await self.stop_all_slaves()
                        await self.report_success(factors)
                        return
                except Exception as e:
                    pass
            self.active_tasks[slave_id] = "failed"
            failed = sum(1 for status in self.active_tasks.values() if status == "failed")
            if len(self.active_tasks) > 0 and failed / len(self.slaves) >= 0.95:
                self.current_step += 1
                await self.start_ecm_step()
        except Exception as e:
            pass

    async def stop_all_slaves(self):
        stop_msg = json.dumps({"command": "stop"}).encode()
        for slave_id in self.slaves:
            await self.nats_client.publish(f"ecm.control.{slave_id}", stop_msg)

    async def report_success(self, factors):
        result = {
            "status": "success",
            "candidate": self.current_candidate,
            "factors": factors,
            "timestamp": datetime.now().isoformat()
        }
        await self.nats_client.publish("ecm.result.final", json.dumps(result).encode())

    async def report_failure(self):
        result = {"status": "failed", "candidate": self.current_candidate}
        await self.nats_client.publish("ecm.result.final", json.dumps(result).encode())

    async def _handle_heartbeat(self, msg):
        try:
            data = json.loads(msg.data.decode())
            slave_id = data["worker_id"]
            self.slaves_heartbeat[slave_id] = datetime.now()
            if slave_id not in self.slaves and "cores" in data:
                self.slaves[slave_id] = data["cores"]
                self.total_cores = sum(self.slaves.values())
        except Exception as e:
            pass


class EcmWorker:
    def __init__(self, config_file="env.json"):
        if os.path.exists(config_file):
            with open(config_file) as f:
                self.config = json.load(f)
        else:
            self.config = {}

        self.nats_url = self.config.get("master_nats_url", NAT_MASTER_URL)
        self.nats_client = None
        self.worker_id = str(uuid.uuid4())
        self.cores = os.cpu_count()
        self.active_processes = []
        self.current_task = None
        self.shared_result = mp.Array('c', 1000)
        self.heartbeat_interval = 5
        self.master_alive = True
        self.stop_event = asyncio.Event()

    async def start(self):
        try:
            self.nats_client = await nats.connect(self.nats_url)
            await self.register_with_master()
            await self.setup_subscriptions()
            self.heartbeat_task = asyncio.create_task(self._send_heartbeats())
        except Exception as e:
            raise

    async def register_with_master(self):
        registration = {
            "worker_id": self.worker_id,
            "capabilities": {"cpu_cores": self.cores}
        }
        await self.nats_client.publish("ecm.register", json.dumps(registration).encode())

    async def setup_subscriptions(self):
        await self.nats_client.subscribe(f"ecm.task.{self.worker_id}", cb=self._handle_task)
        await self.nats_client.subscribe(f"ecm.control.{self.worker_id}", cb=self._handle_control)

    async def _handle_task(self, msg):
        try:
            self.stop_event.clear()
            data = json.loads(msg.data.decode())
            result = await self.run_ecm(data["candidate"], data["b1"], data["curves"])
            if self.stop_event.is_set():
                return
            response = {
                "worker_id": self.worker_id,
                "success": len(result.get("factors", [])) >= 2,
                "factors": result.get("factors", []),
                "timestamp": datetime.now().isoformat()
            }
            await self.nats_client.publish("ecm.result", json.dumps(response).encode())
        except Exception as e:
            pass

    async def run_ecm(self, candidate: str, b1: int, curves: int) -> dict:
        try:
            self.shared_result.value = b''
            self.active_processes.clear()
            curves_per_core = max(1, curves // self.cores)
            for _ in range(self.cores):
                if self.stop_event.is_set():
                    return {"factors": []}
                p = mp.Process(target=self._ecm_process, args=(candidate, b1, curves_per_core))
                self.active_processes.append(p)
                p.start()
            while True:
                if self.stop_event.is_set():
                    self._terminate_processes()
                    return {"factors": []}
                if self.shared_result.value:
                    factors = self.shared_result.value.decode().strip().split()
                    self._terminate_processes()
                    return {"factors": factors}
                if not any(p.is_alive() for p in self.active_processes):
                    return {"factors": []}
                await asyncio.sleep(0.1)
        except Exception as e:
            return {"factors": []}

    async def _handle_control(self, msg):
        try:
            data = json.loads(msg.data.decode())
            command = data.get("command")
            if command == "stop":
                self.stop_event.set()
                self._terminate_processes()
                self.current_task = None
                self.shared_result.value = b''
        except Exception as e:
            pass

    def _ecm_process(self, candidate: str, b1: int, curves: int):
        try:
            cmd = f"echo {candidate} | ./ecm.with.cpu -one -q -c {curves} {b1}"
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            output = proc.stdout.strip()
            factors = self._parse_factors(output)
            if len(factors) >= 2:
                result_str = ' '.join(factors)
                self.shared_result.value = result_str.encode()
        except Exception as e:
            pass

    def _parse_factors(self, output: str) -> List[str]:
        try:
            numbers = []
            tokens = output.strip().split()
            if len(tokens) >= 2:
                for token in tokens:
                    try:
                        int(token)
                        numbers.append(token)
                    except ValueError:
                        continue
            if len(numbers) >= 2:
                return numbers
            else:
                return []
        except Exception as e:
            return []

    def _terminate_processes(self):
        if self.active_processes:
            for p in self.active_processes:
                if p.is_alive():
                    p.terminate()
            self.active_processes.clear()
        check_kill_process('ecm.with.cpu')

    async def _send_heartbeats(self):
        while True:
            try:
                if self.nats_client and self.nats_client.is_connected:
                    heartbeat = {
                        "worker_id": self.worker_id,
                        "cores": self.cores,
                        "timestamp": datetime.now().isoformat()
                    }
                    await self.nats_client.publish("ecm.heartbeat", json.dumps(heartbeat).encode())
                else:
                    await self.reconnect()
            except Exception as e:
                await self.reconnect()
            await asyncio.sleep(self.heartbeat_interval)

    async def reconnect(self):
        try:
            if self.nats_client:
                await self.nats_client.close()
            self.nats_client = await nats.connect(
                self.nats_url,
                reconnect_time_wait=2,
                max_reconnect_attempts=5
            )
            await self.register_with_master()
            await self.setup_subscriptions()
        except Exception as e:
            pass


async def ecm_cpu_server():
    master = EcmMaster()
    await master.start()
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        raise
    finally:
        if master.nats_client:
            await master.nats_client.drain()
            await master.nats_client.close()


async def ecm_cpu_client():
    worker = EcmWorker()
    await worker.start()
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        raise
    finally:
        if worker.nats_client:
            await worker.nats_client.drain()
            await worker.nats_client.close()


def run_async_miner_cpu_ecm_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(ecm_cpu_server())
    finally:
        loop.close()


def run_async_miner_ecm_cpu_client():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(ecm_cpu_client())
    finally:
        loop.close()
