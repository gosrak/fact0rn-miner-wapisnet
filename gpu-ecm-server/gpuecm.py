import ctypes
import urllib.request
import urllib.error
import urllib.parse
import base64
import json
import hashlib
import struct
import random
import os
import platform
import sys
import struct
import time
import subprocess
import socket
import select
import logging



GPUECM_BIND_PORT = os.environ.get("GPUECM_BIND_PORT", 19302) 
GPU_DEVICE_ID = int(os.environ.get("GPU_DEVICE_ID", 0))
STEP_OF_CANDIDATE_SIEVING=int(os.environ.get("STEP_OF_CANDIDATE_SIEVING", 5))
MULTIPLE_EQUAL_RATIO=int(os.environ.get("MULTIPLE_EQUAL_RATIO", 5))
MINIMUM_B1 = int(os.environ.get("MINIMUM_B1", 1000))

def get_ecm_pids():

    run_command = "ps -a"
    parse = subprocess.run( run_command, capture_output=True, shell=True, timeout = 10 )
    parse = parse.stdout.decode('utf-8').split("\n")
    parse = [ line.split()[0] for line in parse if "ecm.with.cuda" in line ]

    return parse

def renice_pids( pids = [], niceness = 0):

    for pid in pids:
        run_command = "renice " + str(niceness) + " -p " + pid
        parse = subprocess.run( run_command, capture_output=True, shell=True, timeout = 10 )
        parse = parse.stdout.decode('utf-8').split("\n")



def check_kill_process(pstring):
    import os, signal
    for line in os.popen(f"ps ax | grep {pstring} | grep -v grep"):
        fields = line.split()
        pid = fields[0]
        os.kill(int(pid),signal.SIGKILL)

class ServerSocket(object):
    
    def __init__(self, port=GPUECM_BIND_PORT,waittimeout=5):
        
        self.host = '0.0.0.0'
        self.port = int(port)
        self.sock = socket.socket(socket.AF_INET,socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.settimeout(waittimeout)#sec
        self.sock.bind((self.host,self.port))
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
    try:
        data = conn.recv(1024)
    except BlockingIOError:
        return None
    except socket.timeout:
        return None
    return data.decode()


def recv_select(sock,size,timeout_sec):
    r,w,x = select.select([sock,],[],[],timeout_sec)        
    if len(r) <= 0: #timeout
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

def handle_client(conn):
    B1Info=[[2000, 32], [11e3, 74], [5e4, 221], [25e4, 453], [1e6, 984], [3e6, 2541], [11e6, 4949], [43e6, 8266], [11e7, 20158], [26e7, 47173], [85e7, 77666]]
    while True:
        data = recv(conn, 1024)
        if data is not None:
            try:

                if len(data) == 0:
                    print('connection closed')
                    conn.close()
                    return
                else:
                    tokens = data.split(' ')
                    returnMsg=""
                    if len(tokens) >= 2 :
                        now = time
                        print("[" + now.strftime('%Y-%m-%d %H:%M:%S') + "] Recv : " + tokens[1])
                        cand=tokens[1].strip()
                        isbadcandidate=True
                        if len(tokens) > 2 :
                            stepCount=int(tokens[2].strip())
                        else :
                            stepCount=STEP_OF_CANDIDATE_SIEVING
                        for inx in range(stepCount) :
                            B1=int(B1Info[inx][0])
                            gpucurve = int(B1Info[inx][1])
                            run_ecm_command  = 'echo ' + cand + ' | ./ecm.with.cuda  -one -q -gpu -gpudevice ' + str(GPU_DEVICE_ID) + ' ' + str(B1) + ' 0'
                            proc = subprocess.run(run_ecm_command, stdout=subprocess.PIPE, shell=True)
                            line = proc.stdout.decode('utf-8')
                            parse = line.split(" ")
                            if len(parse) > 1 :
                                isbadcandidate = False
                                print("[" + now.strftime('%Y-%m-%d %H:%M:%S') + "] bad candidate. " + line)
                                returnMsg = tokens[0] + " 0"
                                send(conn, returnMsg)
                                break

                        if (isbadcandidate == True) and  (cand.strip() == line.strip()):
                            print("[" + now.strftime('%Y-%m-%d %H:%M:%S') + "] good candidate. ")
                            returnMsg = tokens[0] + " 1"
                            send(conn, returnMsg)
                    conn.close()
                    return
            except Exception as err:
                print(f"Expected {err=}, {type(err)=}")
                conn.close()
                return

        else:
            time.sleep(0.1)
    
def server_main():
    run = True
    server = ServerSocket(waittimeout=1)
    while run:
        conn = server.waitforclient()
        if conn:
            handle_client(conn)
            continue
        else:
            time.sleep(0.1)    
    server.close()
    del server




		
if __name__ == "__main__":
    server_main()


