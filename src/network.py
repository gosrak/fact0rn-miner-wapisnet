import os
import sys
import json
import subprocess
import socket
import select
import threading
import shutil
from time import time, sleep

import shared_state
import config
from config import (
    DEBUGGING, WORKER, CENTRAL_MN_IP, CENTRAL_MN_PORT, MSG_BIND_PORT,
    GPUECM_SERVER_IP, GPUECM_SERVER_PORT, CUDAECM_SERVER_IP,
    CADO_SERVER_URL, MINER_MODE, FARM_GROUP, MINER_GROUP,
    WALLET_ADDRESS, MSG_SERVER_IP, MSG_SERVER_PORT,
    USE_DUAL_PROCESS, DUAL_MINING_CHECK_PROCESS, MN_BROKER,
    CADO_CLIENT_BASE_PATH, ECM_ONLY, PRE_GET_POLY,
    STOP_CADO_PROCESS_WITH_DUAL,
)
from utils import (
    check_kill_process, check_kill_stop_process, check_kill_resume_process,
    get_checkBlock_logger, getSystemInfo, getCPUUtilityInfo, getMEMUtilityInfo, getGpuInfo,
)
from bitcoin import rpc_getblockcount

# Module-level globals (process-local to checker process)
cadoStatus = "ready"
cadoDoneInx = ""
logCheckBlock = None


def SendMinerText(topic, Msg):
    queueData = {}
    queueData["topic"] = topic
    queueData["senddata"] = Msg
    shared_state.shared_sendQueue.put(queueData)


def SendKafka(topic, eventNm="", eventMsg=""):
    minerInfo = {}
    minerInfo["Version"] = shared_state.shared_variables["Version"]
    minerInfo["Farm"] = FARM_GROUP
    minerInfo["Group"] = MINER_GROUP
    minerInfo["Worker"] = WORKER
    minerInfo["Miner Mode"] = MINER_MODE
    if len(WALLET_ADDRESS) == 45:
        minerInfo["Wallet Address"] = WALLET_ADDRESS
    minerInfo["GPU ECM Server IP Address"] = GPUECM_SERVER_IP
    minerInfo["GPU ECM Server Port Number"] = GPUECM_SERVER_PORT
    minerInfo["CUDA ECM Server IP Address"] = CUDAECM_SERVER_IP
    minerInfo["CADO-NFS Server URL"] = CADO_SERVER_URL

    blockInfo = {}
    blockInfo['CurruentBlock'] = shared_state.shared_variables["curruentBlock"]
    blockInfo['Block nBits'] = shared_state.shared_variables["block.nBits"]
    blockInfo['BlockTime'] = shared_state.shared_variables["BlockTime"]

    senddata = {}
    if topic == "worker.Block.OnStart":
        senddata["Miner Info"] = minerInfo
    if topic == "worker.Block.OnRegistered":
        senddata["Miner Info"] = minerInfo
        senddata["Block Info"] = blockInfo
    if topic == "worker.Master.Alive.Check":
        senddata["Miner Info"] = minerInfo
        senddata["Block Info"] = blockInfo
        minerStatus = {}
        minerStatus["Status"] = shared_state.shared_variables["MinerStatus"]
        minerStatus["Candidates"] = shared_state.shared_variables["Candidates Count"]
        minerStatus["Elected Candidates"] = len(shared_state.shared_strong_candidate)
        senddata["Miner Status"] = minerStatus
    if topic == "worker.Slave.Alive.Check":
        senddata["Miner Info"] = minerInfo
        senddata["Block Info"] = blockInfo
        clientStatus = {}
        run_command = " ps -ef | grep cado-nfs-client.py | grep -v grep | grep -v '/bin' | wc -l"
        proc = subprocess.run(run_command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, shell=True)
        parse = proc.stdout.decode('utf-8').replace("\n", "")
        clientStatus["CADO Client Processes"] = int(parse)
        clientStatus["CADO Master URL"] = CADO_SERVER_URL
        senddata["Miner Status"] = clientStatus
    if topic == "worker.Block.OnEvent":
        senddata["Miner Info"] = minerInfo
        senddata["Block Info"] = blockInfo
        senddata["Event"] = eventNm
        senddata["Message"] = eventMsg

    queueData = {}
    queueData["topic"] = topic
    queueData["senddata"] = senddata
    shared_state.shared_sendQueue.put(queueData)


def PrintStatus():
    cmdline = shared_state.shared_variables["staticBlockStatus"]
    if "SERVER" in MINER_MODE:
        cmdline = cmdline + " " + ",Slaves : " + str(len(shared_state.shared_client_list)) + " " + ",Candidates : " + str(len(shared_state.shared_candidates)) + "[" + str(len(shared_state.shared_strong_candidate)) + "] " + shared_state.shared_variables["staticMinerStatus"]
        SendKafka("worker.Master.Alive.Check")
        if USE_DUAL_PROCESS == "True":
            cmdline = cmdline + " " + shared_state.shared_variables["staticSubMinerStatus"]
        if PRE_GET_POLY == "True":
            cmdline = cmdline + " " + shared_state.shared_variables["staticPrePolyStatus"]
    if "CLIENT" in MINER_MODE:
        SendKafka("worker.Slave.Alive.Check")
        run_command = " ps -ef | grep cado-nfs-client.py | grep -v grep | grep -v '/bin' | wc -l"
        if "SERVER" not in MINER_MODE:
            proc = subprocess.run(run_command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, shell=True)
            parse = proc.stdout.decode('utf-8').replace("\n", "")
            cmdline = cmdline + " " + ",Clients : " + parse + " , Master : " + CADO_SERVER_URL + " " + shared_state.shared_variables["CadoServerStatus"] + " " + str(shared_state.shared_variables["CadoServerIndex"])
    sys.stdout.write(f"\033[K\r" + cmdline)
    sys.stdout.flush()


def checkBlock(preHeight):
    try:
        if rpc_getblockcount() > preHeight:
            preHeight = rpc_getblockcount()
            check_kill_process('yafu')
            check_kill_process('cado-nfs')
            check_kill_process('msieverun.sh')
            check_kill_process('msieve')
            check_kill_process('cuda-ecm')
            check_kill_process('ecm.with.cpu')
            check_kill_process('/sieve/las')

            try:
                subprocess.run(f"fuser -k 10401/tcp", shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
                subprocess.run(f"fuser -k 10402/tcp", shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
                subprocess.run(f"fuser -k 10403/tcp", shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
                subprocess.run(f"fuser -k 10404/tcp", shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
                subprocess.run(f"fuser -k 10405/tcp", shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
                subprocess.run(f"fuser -k 10406/tcp", shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
            except:
                pass

    except Exception as err:
        import traceback
        exc_type, exc_value, exc_tb = sys.exc_info()
        tb = traceback.extract_tb(exc_tb)
        for frame in tb:
            print(f"File: {frame.filename}, Line: {frame.lineno}, Function: {frame.name}")
        print(f"Error Type: {type(err).__name__}, Message: {err}")
    return preHeight


class ServerSocket(object):

    def __init__(self, port=MSG_BIND_PORT, waittimeout=0.01):
        self.host = '0.0.0.0'
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.settimeout(waittimeout)
        self.sock.bind((self.host, self.port))
        self.sock.listen()

    def waitforclient(self):
        try:
            conn, addr = self.sock.accept()
            conn.setblocking(False)
            return conn
        except socket.timeout:
            return None

    def close(self):
        self.sock.close()

    def __enter__(self):
        return self.waitforclient()

    def __exit__(self, *args):
        self.close()


def recv(conn, len):
    ret = ""
    try:
        data = conn.recv(1024)
        ret = data.decode()
    except BlockingIOError:
        return None
    except socket.timeout:
        return None
    except:
        return None
    return ret


def recv_select(sock, size, timeout_sec):
    r, w, x = select.select([sock, ], [], [], timeout_sec)
    if len(r) <= 0:
        return None
    if r[0].getsockname() != sock.getsockname():
        return None
    try:
        data = sock.recv(size)
        if data is not None:
            return data.decode()
    except BlockingIOError:
        return None

    return None


def send(conn, data):
    conn.send(data.encode())


def msg_handle_client(conn, status, block):
    global cadoStatus
    global cadoDoneInx
    global logCheckBlock

    terminate_cmd = False
    timeout_start = time()
    while True:
        data = recv(conn, 1024)
        if data is not None:
            timeout_start = time()
            try:
                if len(data) == 0:
                    print('connection closed')
                    conn.close()
                    return terminate_cmd
                else:
                    if data[:18] == 'set cado-nfs ready':
                        cadoStatus = 'ready'
                        cadoDoneInx = ''
                        conn.close()
                        return cadoStatus
                    elif data[:17] == 'set cado-nfs done':
                        cadoStatus = 'done'
                        strings = data.split('done')
                        cadoDoneInx = strings[1].strip()
                        conn.close()
                        return cadoStatus
                    elif data[:19] == 'get cado-nfs status':
                        host, port = conn.getpeername()
                        if host not in shared_state.shared_client_list:
                            shared_state.shared_client_list.append(host)
                            if len(data.split()) > 3:
                                cores = int(data.split()[3])
                                shared_state.shared_variables["Total Cores"] = shared_state.shared_variables["Total Cores"] + cores
                        sendData = status + ' ' + cadoDoneInx
                        send(conn, sendData.strip())
                        conn.close()
                        return status
                    elif data[:14] == 'get blockCount':
                        sendData = str(shared_state.shared_variables["curruentBlock"])
                        send(conn, sendData.strip())
                        conn.close()
                        return status
                    else:
                        if "Elapsed Time : " in data:
                            logCheckBlock.info('recv: ' + data.strip())
                        else:
                            print("")
                            logCheckBlock.info('recv: ' + data.strip())
                        jsonData = {}
                        jsonData["block"] = block
                        jsonData["worker"] = WORKER
                        if "Elapsed Time : " in data:
                            jsonData["cmd"] = "T"
                            jsonData["data"] = data.strip()
                            subprocess.run(f"echo '" + json.dumps(jsonData) + "' | nc -w 5 " + CENTRAL_MN_IP + " " + str(CENTRAL_MN_PORT), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if "Complete Factorization / Discrete logarithm" in data:
                            jsonData["cmd"] = "C"
                            jsonData["data"] = data.strip()
                            subprocess.run(f"echo '" + json.dumps(jsonData) + "' | nc -w 5 " + CENTRAL_MN_IP + " " + str(CENTRAL_MN_PORT), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        if "Find block" in data:
                            jsonData["cmd"] = "F"
                            jsonData["data"] = data.strip()
                            subprocess.run(f"echo '" + json.dumps(jsonData) + "' | nc -w 5 " + CENTRAL_MN_IP + " " + str(CENTRAL_MN_PORT), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

                        conn.close()
                        return status
            except Exception as err:
                import traceback
                exc_type, exc_value, exc_tb = sys.exc_info()
                tb = traceback.extract_tb(exc_tb)
                for frame in tb:
                    print(f"File: {frame.filename}, Line: {frame.lineno}, Function: {frame.name}")
                print(f"Error Type: {type(err).__name__}, Message: {err}")
        else:
            if time() - timeout_start > 30:
                conn.close()
                return status
            sleep(0.05)
    return status


def msg_server_main():
    global cadoStatus
    global logCheckBlock

    logCheckBlock = get_checkBlock_logger("Check Block")
    preHeight = 0
    try:
        preHeight = rpc_getblockcount()
    except:
        pass

    curHeight = preHeight
    shared_state.shared_variables["curruentBlock"] = curHeight
    blockStarTime = time()
    run = True
    server = ServerSocket(port=MSG_BIND_PORT, waittimeout=1)
    ConnStarTime = 0
    while run:
        conn = server.waitforclient()
        if conn:
            t = threading.Thread(target=msg_handle_client, args=(conn, cadoStatus, curHeight))
            t.start()
        if time() - ConnStarTime > 0.9:
            if "SERVER" in MINER_MODE:
                shared_state.shared_variables["staticBlockStatus"] = "Block : " + str(preHeight) + " ,Diff : " + str(shared_state.shared_variables["Block.bit"]) + " ,Block Time: " + str(round(time() - blockStarTime))
            else:
                shared_state.shared_variables["staticBlockStatus"] = "Block : " + str(preHeight) + " ,Block Time: " + str(round(time() - blockStarTime))
            shared_state.shared_variables["BlockTime"] = time() - blockStarTime
            ConnStarTime = time()
            PrintStatus()
            curHeight = checkBlock(preHeight)
            if curHeight > preHeight:
                jsonData = {}
                jsonData["block"] = curHeight
                jsonData["worker"] = WORKER
                jsonData["cmd"] = "R"
                jsonData["mode"] = MINER_MODE
                shared_state.shared_variables["curruentBlock"] = curHeight
                subprocess.run(f"echo '" + json.dumps(jsonData) + "' | nc -w 5 " + CENTRAL_MN_IP + " " + str(CENTRAL_MN_PORT), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                SendKafka("worker.Block.OnRegistered")

                print()
                logCheckBlock.info("Block : " + str(preHeight) + "  Block Time: " + str(time() - blockStarTime))
                blockStarTime = time()
                sleep(1)
                logCheckBlock.info("New block found : " + str(curHeight))
                preHeight = curHeight
                continue
            sleep(0.01)

    server.close()
    del server


def msg_client():
    preOnOff = False
    processOnOff = True
    preBlock = 0
    blockStarTime = time()

    while True:
        try:
            if "SERVER" not in MINER_MODE:
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                client_socket.settimeout(2)
                server_address = (MSG_SERVER_IP, MSG_SERVER_PORT)
                client_socket.connect(server_address)
                message = "get blockCount"
                client_socket.send(message.encode())
                data = client_socket.recv(1024)
                received_message = data.decode()
                client_socket.close()
                if len(received_message) > 0:
                    shared_state.shared_variables["curruentBlock"] = int(received_message)
                    if preBlock != shared_state.shared_variables["curruentBlock"]:
                        blockStarTime = time()
                        preBlock = shared_state.shared_variables["curruentBlock"]
                        shutil.rmtree(CADO_CLIENT_BASE_PATH + "/cado-client", ignore_errors=True)
                        shutil.rmtree(CADO_CLIENT_BASE_PATH + "/poly-client", ignore_errors=True)
                        shared_state.shared_variables["BlockTime"] = 0
                        check_kill_process('cado-nfs-client')
                        jsonData = {}
                        jsonData["block"] = shared_state.shared_variables["curruentBlock"]
                        jsonData["worker"] = WORKER
                        jsonData["cmd"] = "R"
                        jsonData["mode"] = MINER_MODE
                        subprocess.run(f"echo '" + json.dumps(jsonData) + "' | nc -w 5 " + CENTRAL_MN_IP + " " + str(CENTRAL_MN_PORT), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        SendKafka("worker.Block.OnRegistered")
                    shared_state.shared_variables["staticBlockStatus"] = "Block : " + str(preBlock) + " ,Block Time: " + str(round(time() - blockStarTime))
                    shared_state.shared_variables["BlockTime"] = time() - blockStarTime
                sleep(0.5)

            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(2)
            server_address = (MSG_SERVER_IP, MSG_SERVER_PORT)
            client_socket.connect(server_address)

            message = "get cado-nfs status " + sys.argv[1]
            client_socket.send(message.encode())
            data = client_socket.recv(1024)
            received_message = data.decode()
            if "SERVER" not in MINER_MODE:
                print("")
                PrintStatus()
            client_socket.close()
            parse = received_message.split(" ")
            dual_process = DUAL_MINING_CHECK_PROCESS.split()
            for mine_process in dual_process:
                try:
                    if processOnOff:
                        subprocess.run(f" if [ $(ps augx | grep {mine_process} | grep -v grep | wc -l) -ne 0 ]; then  ps augx | grep {mine_process} | grep -v grep  | awk '{{print $2}}' |  xargs kill -CONT;fi", shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
                    else:
                        subprocess.run(f" if [ $(ps augx | grep {mine_process} | grep -v grep | wc -l) -ne 0 ]; then  ps augx | grep {mine_process} | grep -v grep  | awk '{{print $2}}' |  xargs kill -STOP;fi", shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
                except:
                    pass

            if len(parse) > 0:
                if (shared_state.shared_variables["CadoServerStatus"] != parse[0]) and (parse[0] == 'ready'):
                    shutil.rmtree(CADO_CLIENT_BASE_PATH + "/cado-client", ignore_errors=True)
                    shutil.rmtree(CADO_CLIENT_BASE_PATH + "/poly-client", ignore_errors=True)
                    check_kill_process('cado-nfs-client')

                shared_state.shared_variables["CadoServerStatus"] = parse[0]
            if len(parse) > 1:
                shared_state.shared_variables["CadoServerIndex"] = int(parse[1])

            if shared_state.shared_variables["CadoServerStatus"] == 'ready':
                shared_state.shared_variables["CadoServerIndex"] = 0
            if "SERVER" not in MINER_MODE:
                run_command = " ps -ef | grep cado-nfs-client.py | grep -v grep | grep -v '/bin' | wc -l"
                proc = subprocess.run(run_command, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, shell=True)
                parse = proc.stdout.decode('utf-8').replace("\n", "")
                cados = int(parse)
                if (cados < 3) or (shared_state.shared_variables["CadoServerStatus"] == 'ready'):
                    if preOnOff:
                        dual_process = DUAL_MINING_CHECK_PROCESS.split()
                        processOnOff = True
                        if len(dual_process) > 0:
                            print("")
                        for mine_process in dual_process:
                            print("RESUME PROCESS : " + mine_process)
                    preOnOff = False
                else:
                    if not preOnOff:
                        dual_process = DUAL_MINING_CHECK_PROCESS.split()
                        if processOnOff:
                            check_kill_process('ecm.with.cpu')
                        processOnOff = False
                        if len(dual_process) > 0:
                            print("")
                        for mine_process in dual_process:
                            print("STOP PROCESS : " + mine_process)
                            try:
                                subprocess.run(f" if [ $(ps augx | grep {mine_process} | grep -v grep | wc -l) -ne 0 ]; then  ps augx | grep {mine_process} | grep -v grep  | awk '{{print $2}}' |  xargs kill -STOP;fi", shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
                            except:
                                pass
                    preOnOff = True
        except Exception as err:
            sleep(5)
            pass

        sleep(1)


def kafka_send_client():
    while True:
        if shared_state.shared_sendQueue.empty():
            sleep(0.01)
        else:
            broker = MN_BROKER
            jsonData = shared_state.shared_sendQueue.get()
            if len(MN_BROKER) > 5:
                topic = jsonData["topic"]
                senddata = jsonData["senddata"]
                if topic == "worker.Block.OnStart":
                    senddata["System Info"] = getSystemInfo()
                    senddata["CPU Info"] = getCPUUtilityInfo()
                    senddata["GPU Info"] = getGpuInfo()
                    senddata["Memory Info"] = getMEMUtilityInfo()
                if topic == "worker.Block.OnRegistered":
                    senddata["System Info"] = getSystemInfo()
                    senddata["CPU Info"] = getCPUUtilityInfo()
                    senddata["GPU Info"] = getGpuInfo()
                    senddata["Memory Info"] = getMEMUtilityInfo()
                if topic == "worker.Master.Alive.Check":
                    senddata["System Info"] = getSystemInfo()
                    senddata["CPU Info"] = getCPUUtilityInfo()
                    senddata["GPU Info"] = getGpuInfo()
                    senddata["Memory Info"] = getMEMUtilityInfo()
                if topic == "worker.Slave.Alive.Check":
                    senddata["System Info"] = getSystemInfo()
                    senddata["CPU Info"] = getCPUUtilityInfo()
                    senddata["GPU Info"] = getGpuInfo()
                    senddata["Memory Info"] = getMEMUtilityInfo()

                try:
                    udp_server_split = MN_BROKER.split((':'))
                    udp_server_ip = udp_server_split[0].replace("//", "")
                    udp_server_port = int(udp_server_split[1])
                    server_address = (udp_server_ip, udp_server_port)
                    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    bytes_to_send = str.encode(json.dumps(jsonData))
                    client_socket.sendto(bytes_to_send, server_address)
                    client_socket.close()
                except Exception:
                    pass

            else:
                sleep(0.01)
