# FACT0RN Mining Program Installation Quick Guide

## 1. Basic Requirements
### 1-1. Operating System
- Ubuntu 20.04 or higher

### 1-2. GPU
- At least two NVIDIA GPUs
- Minimum GPU requirement: RTX 3080 or higher

### 1-3. CPU
- Recommended: Ryzen 7950X

### 1-4. Configuration (Example)
- 1 Master + 70 Slaves

### 1-5. IP Allocation (Example)
- Master PC: `192.168.0.51`
- Slave PCs: `192.168.0.101~192.168.0.170`

## 2. Project Structure
```
fact_dist/
├── install.sh                  # Installation script (packages, OpenMPI, hwloc, CADO-NFS, msieve, sieve)
├── mine.server.simple.example.sh  # Master mine script example
├── mine.client.simple.example.sh  # Slave mine script example
├── src/                        # Python source modules
│   ├── miner.py                # Main miner entry point
│   ├── config.py               # Environment variable configuration
│   ├── shared_state.py         # Multiprocessing shared state
│   ├── bitcoin.py              # Bitcoin data structures and RPC
│   ├── network.py              # TCP/UDP messaging
│   ├── factoring.py            # ECM, CADO-NFS, msieve factoring
│   ├── sieve.py                # Sieving algorithm
│   └── utils.py                # Utilities and process management
├── bin/                        # Runtime binaries and scripts
│   ├── gHash.so                # Hash computation library
│   ├── ecm.with.cpu            # CPU ECM binary
│   ├── cadorun.example.sh      # CADO-NFS run script example
│   ├── msieverun.example.sh    # msieve run script example
│   └── isieve/                 # Sieve binary
│       └── sieverb
├── gpu-ecm-server/             # GPU ECM screening server
│   ├── gpuecm.py
│   ├── gpuecm.sh
│   └── ecm.with.cuda
├── cpu-ecm-server/             # CPU ECM screening server
│   └── ecm.with.cpu
├── cuda-ecm-server/            # CUDA ECM server
│   ├── cuda-ecm
│   ├── cudaecm.sh
│   └── gpu_config_*.ini
└── msieve/                     # msieve binaries
    ├── msieve
    ├── convert_poly
    └── ...
```

## 3. FACT0RN Node Installation
Follow the official guide at [FACT0RN GitHub](https://github.com/FACT0RN/FACT0RN) to install the software on the master PC.

## 4. Master Installation
The master node should have the highest-performance GPU.

### 4-1. Create the Default Directory
```bash
mkdir ~/miners; cd ~/miners
```

### 4-2. Download the Software
```bash
git clone https://github.com/gosrak/fact0rn-miner-wapisnet.git fact_dist
```

### 4-3. Install the Software
The `install.sh` script will install all required system packages, Python packages, OpenMPI, hwloc, CADO-NFS (with MPI), copy msieve directories, copy Python sources to `bin/`, and generate sieve tables.
```bash
cd ~/miners/fact_dist
bash install.sh
```

### 4-4. Modify the Master Scripts
#### 4-4-1. Modify `mine.sh`
For setups with more than 60 devices, use the configuration provided in `mine.server.simple.example.sh`.
```bash
mv mine.server.simple.example.sh mine.sh
```
Edit the following parameters in `mine.sh`:
```bash
export RPC_USER=replace            # Change 'replace' to your configured username
export RPC_PASS=replace            # Change 'replace' to your configured password
export GPUECM_SERVER_IP="127.0.0.1 192.168.0.12 192.168.0.13"
export GPUECM_SERVER_PORT="19302 19302 19302"
python3 miner.py $cpu_cores 0 ValidScriptPubKey  # Change 'ValidScriptPubKey' to your actual wallet ScriptPubKey
```

#### 4-4-2. Modify `cadorun.sh`
`cadorun.sh` runs the external factorization software CADO-NFS.
```bash
cd ~/miners/fact_dist/bin
mv cadorun.example.sh cadorun.sh
```

#### 4-4-3. Modify `msieverun.sh`
`msieverun.sh` runs msieve for the linear algebra and square root steps.
```bash
cd ~/miners/fact_dist/bin
mv msieverun.example.sh msieverun.sh
```

#### 4-4-4. Auto-Run Script
For convenience, use the following `autorun.sh` script:
```bash
#!/bin/bash
pkill screen
cd ~/miners/fact_dist
screen -dmS miner sh mine.sh
cd ~/miners/fact_dist/gpu-ecm-server
screen -dmS gpuecm sh gpuecm.sh
```

## 5. Slave Installation
One of the slave PCs must have a GPU (e.g., `192.168.0.101`). All other slaves should be configured identically.

### 5-1. Create the Default Directory
```bash
mkdir ~/miners; cd ~/miners
```

### 5-2. Download the Software
```bash
git clone https://github.com/gosrak/fact0rn-miner-wapisnet.git fact_dist
```

### 5-3. Install the Software
```bash
cd ~/miners/fact_dist
bash install.sh
```

### 5-4. Modify the Slave Scripts
#### 5-4-1. Modify `mine.sh`
For setups with more than 60 devices, use the configuration provided in `mine.client.simple.example.sh`.
```bash
mv mine.client.simple.example.sh mine.sh
```
Edit the following parameters in `mine.sh`:
```bash
export CADO_SERVER_URL="http://192.168.0.51:24242"
```

#### 5-4-2. Auto-Run Script
For convenience, use the following `autorun.sh` script:
```bash
#!/bin/bash
pkill screen
cd ~/miners/fact_dist
screen -dmS miner sh mine.sh
cd ~/miners/fact_dist/gpu-ecm-server
screen -dmS gpuecm sh gpuecm.sh
```

## 6. Monitoring and Additional Information
To monitor the master PC, use:
```bash
screen -R miner
```
To detach from the screen session, press:
```
Ctrl + a,d
```
For more information on the `screen` command, visit [Linuxize](https://linuxize.com/post/how-to-use-linux-screen).

To check logs:
```bash
tail -f checkblock.log
```

## 7. Conclusion
This guide provides a streamlined installation process with commonly used options, omitting detailed explanations of additional configurations.

