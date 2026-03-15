#/bin/bash

cd bin
SHELL_PATH=$(pwd -P)

export MINER_MODE="CLIENT"
#192.168.0.101 : cado-nfs master
export CADO_SERVER_URL="http://192.168.0.101:24242"
#192.168.0.101 : central monitoring server
export CENTRAL_MN_IP="192.168.0.11"
export CENTRAL_MN_PORT=19201
export CADO_CLIENT_THREAD_COUNT=8
#192.168.0.101 : NATS server (ECM master)
export NAT_MASTER_URL="nats://192.168.0.101:4222"

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
python3 miner.py $cpu_cores 0
sleep 5
done

