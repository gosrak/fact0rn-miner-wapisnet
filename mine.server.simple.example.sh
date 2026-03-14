#/bin/bash
cd bin
export RPC_URL=http://127.0.0.1:8332
export RPC_USER=replace
export RPC_PASS=replace
SHELL_PATH=$(pwd -P)

export GPUECM_SERVER_IP="127.0.0.1 192.168.0.12 192.168.0.13"
export GPUECM_SERVER_PORT="19302 19302 19302"
export MINER_MODE="SERVER"
export CADO_SERVER_URL="http://127.0.0.1:24242"
#192.168.0.101 : central monitoring server
#export CENTRAL_MN_IP="192.168.0.11"
#export CENTRAL_MN_PORT=19201
export USE_MSIEVE="True"
export USE_DUAL_PROCESS="True"
export SORT_SEED="True"
export SENTENCE_IN_CADO_NFS_FOR_STOPPING_PROCESS="Info:Complete Factorization / Discrete logarithm: Lattice Sieving"
export MAX_MSIEVE_COUNT=4
export CADO_CLIENT_THREAD_COUNT=8
export PRE_GET_POLY="True"
export ECM_STEP_OF_CANDIDATE_SIEVING=6

#
cd $SHELL_PATH
cpu_cores=$(lscpu | grep '^CPU(s):' | awk '{print $2}')
echo "cpu core : $cpu_cores"
softSMTon=$(cat /sys/devices/system/cpu/smt/control)
echo "SMT on/off : $softSMTon"
if [ "$softSMTon" = "off" ]; then
  cpu_cores=$(( cpu_cores / 2 ))
fi
echo "thread : $cpu_cores"

while :
do
python3 miner.py $cpu_cores 0 ValidScriptPubKey
sleep 5
done
