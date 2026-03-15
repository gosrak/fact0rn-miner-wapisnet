import os
import sys
import signal
import subprocess
import threading
import queue
import logging
import psutil
import platform
import cpuinfo
from time import time, sleep
from datetime import datetime

import shared_state
from config import DEBUGGING


class SubprocessWorker:
    def __init__(self, idle_timeout=300):
        self.task_queue = queue.Queue()
        self.running = False
        self.worker_thread = None
        self.completed_tasks = 0
        self.total_tasks = 0
        self.idle_timeout = idle_timeout
        self.last_activity_time = time()

    def add_task(self, command, cwd=None, task_id=None, task_data=None):
        if task_id is None:
            task_id = self.total_tasks

        task_info = {
            'id': task_id,
            'command': command,
            'cwd': cwd,
            'data': task_data
        }

        self.task_queue.put(task_info)
        self.total_tasks += 1
        self.last_activity_time = time()

    def start(self):
        if self.running:
            return

        self.running = True
        self.worker_thread = threading.Thread(target=self._process_queue)
        self.worker_thread.daemon = True
        self.worker_thread.start()

        self.idle_timer_thread = threading.Thread(target=self._check_idle_timeout)
        self.idle_timer_thread.daemon = True
        self.idle_timer_thread.start()

    def stop(self):
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=1.0)

    def is_idle(self):
        return self.task_queue.empty()

    def is_completed(self):
        return self.is_idle() and self.completed_tasks == self.total_tasks

    def get_progress(self):
        return {
            'completed': self.completed_tasks,
            'total': self.total_tasks,
            'remaining': self.task_queue.qsize(),
            'is_completed': self.is_completed()
        }

    def _check_idle_timeout(self):
        while self.running:
            if self.is_idle() and (time() - self.last_activity_time) > self.idle_timeout:
                self.running = False
                if hasattr(self, 'on_idle_timeout') and callable(self.on_idle_timeout):
                    self.on_idle_timeout()
                break
            sleep(0.01)

    def _process_queue(self):
        while self.running:
            try:
                task_info = self.task_queue.get(block=True, timeout=1.0)

                self.last_activity_time = time()

                task_id = task_info['id']
                command = task_info['command']
                cwd = task_info['cwd']

                try:
                    result = subprocess.run(
                        command,
                        stderr=subprocess.STDOUT,
                        stdout=subprocess.PIPE,
                        shell=True,
                        cwd=cwd
                    )

                    if hasattr(self, 'on_task_completed') and callable(self.on_task_completed):
                        self.on_task_completed(task_id, result, task_info['data'])

                except Exception as e:
                    if hasattr(self, 'on_task_error') and callable(self.on_task_error):
                        self.on_task_error(task_id, e, task_info['data'])

                self.task_queue.task_done()
                self.completed_tasks += 1

                self.last_activity_time = time()

            except queue.Empty:
                pass
            except Exception as e:
                pass

    def set_task_completed_callback(self, callback_func):
        self.on_task_completed = callback_func

    def set_task_error_callback(self, callback_func):
        self.on_task_error = callback_func

    def set_idle_timeout_callback(self, callback_func):
        self.on_idle_timeout = callback_func

    def reset_idle_timer(self):
        self.last_activity_time = time()

    def wait_until_completed(self, check_interval=0.01):
        while self.running and not self.is_completed():
            sleep(check_interval)
        return self.is_completed()


class ExtendableTimer:
    def __init__(self, process, timeout):
        self.process = process
        self.timeout = timeout
        self.curruentBlock = shared_state.shared_variables["curruentBlock"]
        self.stop_event = threading.Event()
        self.reset_event = threading.Event()
        self.timer_thread = threading.Thread(target=self._timer)

    def _timer(self):
        while not self.stop_event.is_set():
            self.reset_event.clear()
            start_time = time()

            while time() - start_time < self.timeout:
                if self.curruentBlock != shared_state.shared_variables["curruentBlock"]:
                    self.process.kill()
                    self.stop_event.set()
                    return
                if self.reset_event.is_set():
                    break
                sleep(0.1)

            if not self.reset_event.is_set():
                if self.process.poll() is None:
                    self.process.kill()
                self.stop_event.set()

    def reset(self):
        self.reset_event.set()

    def start(self):
        self.timer_thread.start()

    def stop(self):
        self.stop_event.set()

    def join(self):
        self.timer_thread.join()


def get_timeCheck(timecheck):
    result = "Elapsed Time : " + str(round(time() - timecheck[0], 1)) + " Sec ["
    lastTime = 0
    if timecheck[1] == 0:
      result = result + ' PS : X '
    else:
      result = result + ' PS : ' + str(round(timecheck[1] - timecheck[0], 1)) + ' '
    if timecheck[2] == 0:
      result = result + 'LS : X '
    else:
      result = result + 'LS : ' + str(round(timecheck[2] - timecheck[1], 1)) + ' '
    if timecheck[3] == 0:
      result = result + 'FT : X '
    else:
      result = result + 'FT : ' + str(round(timecheck[3] - timecheck[2], 1)) + ' '
    if timecheck[4] == 0:
      result = result + 'LA : X '
    else:
      result = result + 'LA : ' + str(round(timecheck[4] - timecheck[3], 1)) + ' '
    if timecheck[5] == 0:
      result = result + 'SR : X ]'
    else:
      result = result + 'SR : ' + str(round(timecheck[5] - timecheck[4], 1)) + ' ]'
    return result


def get_size(bytes, suffix="B"):
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if bytes < factor:
            return f"{bytes:.2f}{unit}{suffix}"
        bytes /= factor


def getSystemInfo():
    systemInfo = {}
    uname = platform.uname()
    systemInfo['System'] = uname.system
    systemInfo['Node Name'] = uname.node
    systemInfo['Release'] = uname.release
    systemInfo['Version'] = uname.version
    systemInfo['Machine'] = uname.machine
    systemInfo['Processor'] = cpuinfo.get_cpu_info()['brand_raw']
    boot_time_timestamp = psutil.boot_time()
    bt = datetime.fromtimestamp(boot_time_timestamp)
    systemInfo['Boot Time'] = f"{bt.year}/{bt.month}/{bt.day} {bt.hour}:{bt.minute}:{bt.second}"
    systemInfo["Physical cores"] = psutil.cpu_count(logical=False)
    systemInfo["Total cores"] = psutil.cpu_count(logical=True)

    with open('/proc/uptime', 'r') as f:
        uptime_seconds = float(f.readline().split()[0])
        systemInfo["Uptime(Sec)"] = uptime_seconds
    return systemInfo


def getCPUUtilityInfo():
    utilityInfo = {}
    cpufreq = psutil.cpu_freq()
    utilityInfo["Max Frequency"] = f"{cpufreq.max:.2f}Mhz"
    utilityInfo["Min Frequency"] = f"{cpufreq.min:.2f}Mhz"
    utilityInfo["Current Frequency"] = f"{cpufreq.current:.2f}Mhz"
    for i, percentage in enumerate(psutil.cpu_percent(percpu=True, interval=1)):
        utilityInfo[f"Core Usage{i}"] = f"{percentage}%"
    utilityInfo[f"Total Core Usage"] = f"{psutil.cpu_percent()}%"
    return utilityInfo


def getMEMUtilityInfo():
    utilityInfo = {}
    svmem = psutil.virtual_memory()
    utilityInfo["Total"] = f"{get_size(svmem.total)}"
    utilityInfo["Available"] = f"{get_size(svmem.available)}"
    utilityInfo["Used"] = f"{get_size(svmem.used)}"
    utilityInfo["Used"] = f"{svmem.percent}%"
    return utilityInfo


def getGpuInfo():
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )

        gpu_info = []
        def safe_int(val, default=-1):
            val = val.strip()
            if val.startswith("[") or not val.isdigit():
                return default
            return int(val)

        for line in result.stdout.strip().split("\n"):
            try:
                parts = line.split(", ")
                if len(parts) != 7:
                    print(f"Warning: Skipping malformed line: '{line}'")
                    continue
                index, name, memory_total, memory_used, memory_free, utilization_gpu, temperature_gpu = parts
                gpu_info.append({
                    "index": safe_int(index, 0),
                    "name": name.strip(),
                    "memory_total_MB": safe_int(memory_total, 0),
                    "memory_used_MB": safe_int(memory_used, 0),
                    "memory_free_MB": safe_int(memory_free, 0),
                    "utilization_gpu_percent": safe_int(utilization_gpu, -1),
                    "temperature_gpu_C": safe_int(temperature_gpu, -1)
                })
            except ValueError as ve:
                print(f"Warning: Skipping malformed line: '{line}'. Error: {ve}")

        return gpu_info

    except (FileNotFoundError, subprocess.CalledProcessError):
        return []
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        return []


def runasyncio(runcmd, path):
    subprocess.run(runcmd, stderr=subprocess.STDOUT, stdout=subprocess.PIPE, shell=True, cwd=path)


def check_kill_process(pstring):
    proc = subprocess.run(f"ps ax | grep '{pstring}' | grep -v grep", shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for line in proc.stdout.decode().splitlines():
        fields = line.split()
        pid = fields[0]
        try:
            os.kill(int(pid), signal.SIGKILL)
        except:
            pass


def check_kill_interrup(pstring):
    proc = subprocess.run(f"ps ax | grep '{pstring}' | grep -v grep", shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for line in proc.stdout.decode().splitlines():
        fields = line.split()
        pid = fields[0]
        try:
            os.kill(int(pid), signal.SIGTERM)
        except:
            pass


def check_kill_stop_process(pstring):
    proc = subprocess.run(f"ps ax | grep '{pstring}' | grep -v grep", shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for line in proc.stdout.decode().splitlines():
        fields = line.split()
        pid = fields[0]
        try:
            os.kill(int(pid), signal.SIGTSTP)
        except:
            pass


def check_kill_resume_process(pstring):
    proc = subprocess.run(f"ps ax | grep '{pstring}' | grep -v grep", shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for line in proc.stdout.decode().splitlines():
        fields = line.split()
        pid = fields[0]
        try:
            os.kill(int(pid), signal.SIGCONT)
        except:
            pass


def get_checkBlock_logger(name=None):
    execute_path = os.path.dirname(os.path.abspath(__file__))
    base_path = os.path.dirname(execute_path)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console = logging.StreamHandler()
    file_handler_info = logging.FileHandler(filename=base_path + "/checkblock.log")
    console.setLevel(logging.INFO)
    file_handler_info.setLevel(logging.INFO)
    console.setFormatter(formatter)
    file_handler_info.setFormatter(formatter)
    logger.addHandler(console)
    logger.addHandler(file_handler_info)
    return logger


def get_miner_logger(name=None):
    execute_path = os.path.dirname(os.path.abspath(__file__))
    base_path = os.path.dirname(execute_path)
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console = logging.StreamHandler()
    file_handler_debug = logging.FileHandler(filename=base_path + "/execute.log")
    file_handler_info = logging.FileHandler(filename=base_path + "/finds.log")
    file_handler_debug.setLevel(logging.DEBUG)
    file_handler_info.setLevel(logging.INFO)
    file_handler_debug.setFormatter(formatter)
    file_handler_info.setFormatter(formatter)
    logger.addHandler(file_handler_debug)
    logger.addHandler(file_handler_info)
    return logger


def delete_rows_with_string(file_path, target_string):
    with open(file_path, 'r') as file:
        lines = [line for line in file if target_string not in line]
    with open(file_path, 'w') as file:
        for line in lines:
            file.write(line)
