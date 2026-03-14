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

## 2. FACT0RN Node Installation
Follow the official guide at [FACT0RN GitHub](https://github.com/FACT0RN/FACT0RN) to install the software on the master PC.

## 3. Master Installation
The master node should have the highest-performance GPU.

### 3-1. Create the Default Directory
```bash
mkdir ~/miners; cd ~/miners
```

### 3-2. Download the Software
```bash
wget http://factorn.iptime.org:32080/download/fact_dist.tar.gz
```

### 3-3. Install the Software
```bash
tar -xvf fact_dist.tar.gz
cd ~/miners/fact_dist
bash install.sh
```

### 3-4. Modify the Master Scripts
#### 3-4-1. Modify `mine.sh`
For setups with more than 60 devices, use the configuration provided in `mine.server.simple.example.sh`.
```bash
mv mine.server.simple.example.sh mine.sh
```
Edit the following parameters in `mine.sh`:
```bash
export RPC_USER=replace  # Change 'replace' to your configured username
export RPC_PASS=replace  # Change 'replace' to your configured password
export GPUECM_SERVER_IP="192.168.0.101"
export GPUECM_SERVER_PORT="19302"
./miner $cpu_cores 0 ValidScriptPubKey  # Change 'ValidScriptPubKey' to your actual wallet ScriptPubKey
```

#### 3-4-2. Modify `cadorun.sh`
`cadorun.sh` runs the external factorization software CADO-NFS.
```bash
cd ~/miners/fact_dist/bin
mv cadorun.example.sh cadorun.sh
```

#### 3-4-3. Auto-Run Script
For convenience, use the following `autorun.sh` script:
```bash
#!/bin/bash
pkill screen
cd ~/miners/fact_dist
screen -dmS miner sh mine.sh
cd ~/miners/fact_dist/gpu-server
screen -dmS gpuecm sh gpuecm.sh
```

## 4. Slave Installation
One of the slave PCs must have a GPU (e.g., `192.168.0.101`). All other slaves should be configured identically.

### 4-1. Create the Default Directory
```bash
mkdir ~/miners; cd ~/miners
```

### 4-2. Download the Software
```bash
wget http://factorn.iptime.org:32080/download/fact_dist.tar.gz
```

### 4-3. Install the Software
```bash
tar -xvf fact_dist.tar.gz
cd ~/miners/fact_dist
bash install.sh
```

### 4-4. Modify the Slave Scripts
#### 4-4-1. Modify `mine.sh`
For setups with more than 60 devices, use the configuration provided in `mine.client.simple.example.sh`.
```bash
mv mine.client.simple.example.sh mine.sh
```
Edit the following parameters in `mine.sh`:
```bash
export CADO_SERVER_URL="http://192.168.0.51:24242"
```

#### 4-4-2. Auto-Run Script
For convenience, use the following `autorun.sh` script:
```bash
#!/bin/bash
pkill screen
cd ~/miners/fact_dist
screen -dmS miner sh mine.sh
cd ~/miners/fact_dist/gpu-server
screen -dmS gpuecm sh gpuecm.sh
```

## 5. Monitoring and Additional Information
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

## 6. Conclusion
This guide provides a streamlined installation process with commonly used options, omitting detailed explanations of additional configurations.

