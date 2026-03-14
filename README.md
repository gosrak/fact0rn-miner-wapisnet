# Fact0rn Miner - WAPISNET

A modular Python pipeline for mining [Fact0rn](https://github.com/FACT0RN/FACT0RN), a cryptocurrency based on semiprime factorization proof-of-work.

## Overview

Fact0rn uses integer factorization as its proof-of-work algorithm instead of traditional hash-based mining. This miner implements a multi-stage pipeline:

1. **Sieving** - Generate candidate semiprimes using primorial-based sieving
2. **ECM Screening** - Filter candidates with Elliptic Curve Method (GPU/CUDA/CPU)
3. **Factoring** - Full factorization via CADO-NFS and msieve
4. **Submission** - Submit valid blocks to the Fact0rn network

## Architecture

```
Master Node (SERVER)
├── miner.py ─── Block Template ──► Candidate Generation ──► ECM Screening ──► CADO-NFS ──► msieve ──► Submit
├── GPU ECM Server (port 19302)
├── CUDA ECM Server
├── CADO-NFS Master (port 24242)
└── Message Server (TCP port 29291)

Slave Nodes (CLIENT) x N
├── CADO-NFS Client (lattice sieving)
├── GPU/CUDA/CPU ECM Client
└── Message Client
```

**Master** generates candidates, screens them via ECM, and distributes factoring work to slaves via CADO-NFS. **Slaves** perform polynomial selection and lattice sieving, returning results to the master for final linear algebra and square root steps.

## Project Structure

```
fact0rn-miner-wapisnet/
├── src/                            # Python source modules
│   ├── miner.py                    # Main entry point (CBlock.mine() algorithm)
│   ├── config.py                   # Environment variable configuration
│   ├── shared_state.py             # Multiprocessing shared state (Manager proxies)
│   ├── bitcoin.py                  # Bitcoin RPC, CBlock, tx/merkle functions
│   ├── network.py                  # TCP/UDP messaging, status monitoring
│   ├── factoring.py                # ECM, CADO-NFS, msieve integration
│   ├── sieve.py                    # Primorial-based sieving algorithm
│   └── utils.py                    # SubprocessWorker, timers, system info
├── bin/                            # Runtime directory
│   ├── gHash.so                    # Hash computation C library
│   ├── ecm.with.cpu                # CPU ECM binary
│   ├── isieve/sieverb              # Sieve table generator
│   ├── cadorun.example.sh          # CADO-NFS run script template
│   └── msieverun.example.sh        # msieve run script template
├── gpu-ecm-server/                 # GPU ECM screening server
│   ├── gpuecm.py                   # TCP server using ecm.with.cuda
│   ├── gpuecm.sh                   # Launch script
│   └── ecm.with.cuda               # GPU ECM binary
├── cpu-ecm-server/                 # CPU ECM screening server
│   └── ecm.with.cpu                # CPU ECM binary
├── cuda-ecm-server/                # CUDA ECM server
│   ├── cuda-ecm                    # CUDA ECM binary
│   ├── cudaecm.sh                  # Multi-instance launch script
│   └── gpu_config_*.ini            # GPU configuration files
├── msieve/                         # msieve binaries (LA/SR solver)
│   ├── msieve                      # msieve executable
│   ├── convert_poly                # Polynomial format converter
│   ├── lanczos_kernel.fatbin       # CUDA Lanczos kernel
│   └── stage1_core.fatbin          # CUDA stage1 kernel
├── install.sh                      # Full installation script
├── mine.server.simple.example.sh   # Master node script template
└── mine.client.simple.example.sh   # Slave node script template
```

## Requirements

- **OS**: Ubuntu 20.04 or higher
- **GPU**: NVIDIA RTX 3080 or higher (minimum 2 GPUs recommended)
- **CPU**: High core count recommended (e.g., Ryzen 7950X)
- **Fact0rn Node**: Running [FACT0RN](https://github.com/FACT0RN/FACT0RN) full node on the master

## Installation

### Quick Start

```bash
mkdir ~/miners && cd ~/miners
git clone https://github.com/gosrak/fact0rn-miner-wapisnet.git fact_dist
cd fact_dist
bash install.sh
```

The `install.sh` script automatically installs:
- System packages (build tools, GMP-ECM, Redis, etc.)
- Python packages (gmpy2, sympy, numpy, flask, etc.)
- OpenMPI 4.1.6 (source build to `/opt/openmpi`)
- hwloc 2.10.0 (source build to `/opt/hwloc`)
- CADO-NFS with MPI support
- msieve directory copies for parallel instances
- Sieve lookup tables (primorial level up to 28)
- Python sources deployed to `bin/`

### Detailed Installation

See [readme.install.en.md](readme.install.en.md) for step-by-step instructions including master/slave configuration.

## Configuration

### Master Node

```bash
cp mine.server.simple.example.sh mine.sh
```

Edit `mine.sh`:

| Variable | Description | Example |
|----------|-------------|---------|
| `RPC_USER` | Fact0rn node RPC username | `myuser` |
| `RPC_PASS` | Fact0rn node RPC password | `mypass` |
| `RPC_URL` | Fact0rn node RPC endpoint | `http://127.0.0.1:8332` |
| `GPUECM_SERVER_IP` | GPU ECM server IPs (space-separated) | `"127.0.0.1 192.168.0.12"` |
| `GPUECM_SERVER_PORT` | GPU ECM server ports (space-separated) | `"19302 19302"` |
| `MINER_MODE` | Mining mode | `"SERVER"` |
| `USE_MSIEVE` | Enable msieve for LA/SR | `"True"` |
| `USE_DUAL_PROCESS` | Enable dual-mining suspension | `"True"` |
| `MAX_MSIEVE_COUNT` | Max parallel msieve instances | `4` |
| `CADO_CLIENT_THREAD_COUNT` | CADO client threads | `8` |
| `ECM_STEP_OF_CANDIDATE_SIEVING` | ECM B1 screening levels | `6` |

Update the wallet ScriptPubKey:
```bash
python3 miner.py $cpu_cores 0 YourScriptPubKey
```

### Slave Node

```bash
cp mine.client.simple.example.sh mine.sh
```

Edit `mine.sh`:

| Variable | Description | Example |
|----------|-------------|---------|
| `MINER_MODE` | Mining mode | `"CLIENT"` |
| `CADO_SERVER_URL` | Master CADO-NFS URL | `"http://192.168.0.51:24242"` |
| `CADO_CLIENT_THREAD_COUNT` | CADO client threads | `8` |

### Script Setup

```bash
cd bin
cp cadorun.example.sh cadorun.sh
cp msieverun.example.sh msieverun.sh
```

## Running

### Auto-Run Script (Master)

```bash
#!/bin/bash
pkill screen
cd ~/miners/fact_dist
screen -dmS miner sh mine.sh
cd ~/miners/fact_dist/gpu-ecm-server
screen -dmS gpuecm sh gpuecm.sh
```

### Auto-Run Script (Slave)

```bash
#!/bin/bash
pkill screen
cd ~/miners/fact_dist
screen -dmS miner sh mine.sh
```

### Monitoring

```bash
screen -R miner          # View live mining status (Ctrl+a,d to detach)
tail -f checkblock.log   # Block height changes
tail -f finds.log        # Successful factorizations
tail -f execute.log      # Debug log
```

### Sample Output

```
!!!! Fact0rn Miner rebuild by gosrak !!!!
Version : 1.30
NAT_MASTER_URL = nats://localhost:4222
DevFee : 7%
Block : 172932 ,Diff : 400 ,Block Time: 321 ,Slaves : 16 ,Candidates : 1315[6] ,Miner : Lattice Sieving(302,58.6%)  ,Next Poly : Complete 66 Sec
2026-03-14 13:50:01,847 - INFO - Block : 172932  Block Time: 321.473867893219
2026-03-14 13:50:02,847 - INFO - New block found : 172933
Block : 172933 ,Diff : 400 ,Block Time: 677 ,Slaves : 16 ,Candidates : 1386[5] ,Miner : Lattice Sieving(222,46.9%) ,BackEnd : MSIEVE(idx : 1) multiply complete ,Next Poly : Complete 67 Sec
2026-03-14 14:01:19,648 - INFO - recv: Elapsed Time : 602.2 Sec [ PS : 61.3 LS : 363.8 FT : 99.0 LA : 59.0 SR : 19.0 ]  |p1|_2=146 |p2|_2=254 |n|_2=400
2026-03-14 14:08:15,763 - INFO - recv: Elapsed Time : 591.1 Sec [ PS : 7.3 LS : 405.8 FT : 98.0 LA : 61.0 SR : 19.0 ]  |p1|_2=184 |p2|_2=216 |n|_2=400
2026-03-14 14:13:50,787 - INFO - recv: Elapsed Time : 511.0 Sec [ PS : 7.6 LS : 413.3 FT : 44.0 LA : 37.0 SR : 9.0 ]  |p1|_2=123 |p2|_2=277 |n|_2=400
2026-03-14 14:28:50,245 - INFO - Block : 172933  Block Time: 2328.397544145584
2026-03-14 14:28:51,245 - INFO - New block found : 172934
```

**Status Line Fields:**
- `Block` - Current block height
- `Diff` - Block difficulty (bit length of n)
- `Block Time` - Seconds since block started
- `Slaves` - Connected slave nodes
- `Candidates[N]` - Total candidates generated [remaining to factor]
- `Miner` - Current CADO-NFS stage and progress
- `BackEnd` - msieve status
- `Next Poly` - Polynomial selection status

**Timing Breakdown (Elapsed Time):**
- `PS` - Polynomial Selection
- `LS` - Lattice Sieving
- `FT` - Filtering
- `LA` - Linear Algebra
- `SR` - Square Root
- `|p1|_2`, `|p2|_2` - Bit lengths of factors p and q

## Mining Pipeline

```
Block Template (RPC)
    │
    ▼
Hash-based Candidate Generation (sieve.py + gHash.so)
    │
    ▼
Primorial Sieving (levels 0-28)
    │
    ▼
ECM Screening (multi-stage, B1: 2000 → 850M)
    ├── GPU ECM (ecm.with.cuda)
    ├── CUDA ECM (cuda-ecm)
    └── CPU ECM (ecm.with.cpu)
    │
    ▼
CADO-NFS Factorization
    ├── Polynomial Selection
    ├── Lattice Sieving (distributed to slaves)
    └── Filtering
    │
    ▼
msieve (Linear Algebra + Square Root)
    │
    ▼
Verify p × q = n (semiprime check)
    │
    ▼
Submit Block (RPC)
```

## Network Ports

| Port | Protocol | Service |
|------|----------|---------|
| 8332 | TCP | Fact0rn node RPC |
| 19302 | TCP | GPU ECM server |
| 19303 | TCP | CPU ECM server |
| 24242 | TCP | CADO-NFS master |
| 29291 | TCP | Inter-node messaging |

## License

This project is provided as-is for Fact0rn mining purposes.

## Acknowledgments

- [FACT0RN](https://github.com/FACT0RN/FACT0RN) - The Fact0rn cryptocurrency
- [CADO-NFS](https://gitlab.inria.fr/cado-nfs/cado-nfs) - Number Field Sieve implementation
- [GMP-ECM](https://gitlab.inria.fr/zimMDMAN/ecm) - Elliptic Curve Method
- [msieve](https://github.com/radii/msieve) - Integer factorization library
