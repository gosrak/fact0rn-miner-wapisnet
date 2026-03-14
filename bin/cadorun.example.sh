#/bin/bash
#example : 60 PC Over Setting , mine.sh 8 Thread Setting
export LANG=C
SHELL_PATH=$(pwd -P)
workdir="/tmp/wdir"
PortNum=24242
find $workdir -mindepth 1 -maxdepth 1 -mmin +30 -type d -exec rm -rf {} \;
cand=$1
mode=$2
Mthreads=$3
Sthreads=$4
CadoInx=$5

if [ "$mode" = "" ]; then
   #addOpt="tasks.sieve.run=false $addOpt"
   mode="normal"
fi

if [ "$Mthreads" = "" ]; then
   Mthreads=8
fi

workdir="$workdir/$cand"
if [ "$CadoInx" -eq 1 ]; then
addOpt="tasks.polyselect.P=120000 \
tasks.polyselect.admin=1e2 \
tasks.polyselect.admax=42e3 \
tasks.polyselect.adrange=480 \
tasks.polyselect.degree=5 \
tasks.polyselect.incr=60 \
tasks.polyselect.nq=15625 \
tasks.polyselect.nrkeep=35 \
tasks.polyselect.ropteffort=7 \
tasks.polyselect.sopteffort=1 \
tasks.wutimeout=120 \
tasks.maxtimedout=100 "
else
addOpt="tasks.polyselect.P=180000 \
tasks.polyselect.admin=1e2 \
tasks.polyselect.admax=7e4 \
tasks.polyselect.adrange=480 \
tasks.polyselect.degree=5 \
tasks.polyselect.incr=60 \
tasks.polyselect.nq=15625 \
tasks.polyselect.nrkeep=35 \
tasks.polyselect.ropteffort=7 \
tasks.polyselect.sopteffort=1 \
tasks.wutimeout=120 \
tasks.maxtimedout=100 "
fi

if [ "$mode" = "poly" ]; then
   PortNum=$(($PortNum + 1))
fi
if [ "$mode" = "normal" ]; then
  if [ -d "$workdir" ]; then
      for polyfile in "$workdir"/*.poly; do
         if [ -f "$polyfile" ]; then
            addOpt="tasks.polyselect.import=$polyfile $addOpt tasks.polyselect.admin=0 tasks.polyselect.admax=0 tasks.polyselect.adrange=0"
            break
         fi
      done
  fi
fi

workdir="$workdir/$cand"
PolyTimeOut=0
if [ "$CadoInx" -eq 1 ]; then
    PolyTimeOut=55
elif [ "$CadoInx" -eq 2 ]; then    
    PolyTimeOut=55
else
    PolyTimeOut=55
fi

if [ "$CadoInx" -eq 1 ]; then
  cd ../msieve_nfsathome
  rm *.poly
  bash polysect.with.cuda.sh $cand $PolyTimeOut
  mkdir $workdir
  cp *.poly $workdir/.
else
  if [ "$mode" = "poly" ]; then      
     if ssh node18 "cd ~/miners/fact_dist/msieve_nfsathome; rm *.poly; bash polysect.with.cuda.sh $cand $PolyTimeOut"; then
        mkdir -p "$workdir"
        scp node18:~/miners/fact_dist/msieve_nfsathome/*.poly "$workdir"/.
        if [ -d "$workdir" ]; then
           for polyfile in "$workdir"/*.poly; do
              if [ -f "$polyfile" ]; then
                 addOpt="tasks.polyselect.import=$polyfile $addOpt tasks.polyselect.admin=0 tasks.polyselect.admax=0 tasks.polyselect.adrange=0"
                 break
              fi
          done
        fi
     fi
  fi
fi



cd $SHELL_PATH
cd ../cado-nfs
kill $(lsof -t -i:$PortNum)
if [ "$CadoInx" -ge 2 ]; then
   sleep 2
fi
kill $(lsof -t -i:$PortNum)


if [ "$CadoInx" -eq 1 ]; then
	./cado-nfs.py --server $cand tasks.workdir=$workdir server.port=$PortNum server.ssl=no server.whitelist=0.0.0.0/0 $addOpt \
	tasks.lim0=5200000 \
	tasks.lim1=7000000 \
	tasks.lpb0=28 \
	tasks.lpb1=29 \
	tasks.sieve.lambda0=1.80 \
	tasks.sieve.lambda1=1.90 \
	tasks.sieve.mfb0=55 \
	tasks.sieve.mfb1=58 \
	tasks.sieve.ncurves0=10 \
	tasks.sieve.ncurves1=15 \
	tasks.I=13 \
	tasks.sieve.qrange=10000 \
	tasks.sieve.rels_wanted=30500000 \
	tasks.polyselect.threads=10 --client-threads 10 -t all --no-colors
else
	./cado-nfs.py --server $cand tasks.workdir=$workdir server.port=$PortNum server.ssl=no server.whitelist=0.0.0.0/0 $addOpt \
	tasks.lim0=5500000 \
	tasks.lim1=7000000 \
	tasks.lpb0=29 \
	tasks.lpb1=29 \
	tasks.sieve.mfb0=54 \
	tasks.sieve.mfb1=56 \
	tasks.sieve.lambda0=1.85 \
	tasks.sieve.lambda1=1.92 \
	tasks.sieve.ncurves0=20 \
	tasks.sieve.ncurves1=25 \
	tasks.I=13 \
	tasks.sieve.qrange=10000 \
	tasks.sieve.rels_wanted=39500000 \
	tasks.polyselect.threads=11 --client-threads 11 -t all --no-colors
fi


./cado-nfs.py --server $cand tasks.workdir=$workdir server.port=$PortNum server.ssl=no server.whitelist=0.0.0.0/0 $addOpt \
tasks.filter.required_excess=0.07 tasks.filter.target_density=120.0 tasks.filter.purge.keep=170 \
tasks.polyselect.threads=8 --client-threads 4 -t all --no-colors


# -------------------------------------------------------------------------------------------------------------------------
# 464 bit tested
# Adjust according to the performance of your GPU and the number of slaves
# -------------------------------------------------------------------------------------------------------------------------
# ./cado-nfs.py --server $cand tasks.workdir=$workdir server.port=$PortNum server.ssl=no server.whitelist=0.0.0.0/0 $addOpt \
# tasks.filter.required_excess=0.07 tasks.filter.target_density=120.0 tasks.filter.purge.keep=170 \
# tasks.lim0=4000000 \
# tasks.lim1=5500000 \
# tasks.lpb0=27 \
# tasks.lpb1=28 \
# tasks.sieve.lambda0=1.85 \
# tasks.sieve.lambda1=1.92 \
# tasks.sieve.mfb0=54 \
# tasks.sieve.mfb1=57 \
# tasks.sieve.ncurves0=13 \
# tasks.sieve.ncurves1=18 \
# tasks.sieve.qrange=6000 \
# tasks.sieve.rels_wanted=21000000 \
# tasks.polyselect.threads=11 --client-threads 11 -t all --no-colors


# -------------------------------------------------------------------------------------------------------------------------
# 464 bit tested
# Adjust according to the performance of your GPU and the number of slaves
# -------------------------------------------------------------------------------------------------------------------------
# ./cado-nfs.py --server $cand tasks.workdir=$workdir server.port=$PortNum server.ssl=no server.whitelist=0.0.0.0/0 $addOpt \
# tasks.lim0=4000000 \
# tasks.lim1=5400000 \
# tasks.lpb0=27 \
# tasks.lpb1=28 \
# tasks.sieve.lambda0=1.84 \
# tasks.sieve.lambda1=1.915 \
# tasks.sieve.mfb0=55 \
# tasks.sieve.mfb1=58 \
# tasks.sieve.ncurves0=15 \
# tasks.sieve.ncurves1=20 \
# tasks.I=14 \
# tasks.sieve.qrange=5000 \
# tasks.sieve.rels_wanted=17500000 \
# tasks.polyselect.threads=10 --client-threads 10 -t all --no-colors

# -------------------------------------------------------------------------------------------------------------------------
# 464 bit tested
# Adjust according to the performance of your GPU and the number of slaves
# -------------------------------------------------------------------------------------------------------------------------
#./cado-nfs.py --server $cand tasks.workdir=$workdir server.port=$PortNum server.ssl=no server.whitelist=0.0.0.0/0 $addOpt \
#tasks.lim0=5500000 \
#tasks.lim1=7000000 \
#tasks.lpb0=29 \
#tasks.lpb1=29 \
#tasks.sieve.mfb0=54 \
#tasks.sieve.mfb1=56 \
#tasks.sieve.lambda0=1.85 \
#tasks.sieve.lambda1=1.92 \
#tasks.sieve.ncurves0=20 \
#tasks.sieve.ncurves1=25 \
#tasks.I=13 \
#tasks.sieve.qrange=10000 \
#tasks.sieve.rels_wanted=39500000 \
#tasks.polyselect.threads=11 --client-threads 11 -t all --no-colors

# -------------------------------------------------------------------------------------------------------------------------
# parameter 135 base
# Adjust according to the performance of your GPU and the number of slaves
# -------------------------------------------------------------------------------------------------------------------------
# ./cado-nfs.py --server $cand tasks.workdir=$workdir server.port=$PortNum server.ssl=no server.whitelist=0.0.0.0/0 $addOpt \
# tasks.lim0=5500000 \
# tasks.lim1=7000000 \
# tasks.lpb0=27 \
# tasks.lpb1=28 \
# tasks.sieve.mfb0=54 \
# tasks.sieve.mfb1=56 \
# tasks.sieve.lambda0=1.85 \
# tasks.sieve.lambda1=1.92 \
# tasks.sieve.ncurves0=20 \
# tasks.sieve.ncurves1=25 \
# tasks.I=13 \
# tasks.sieve.qrange=10000 \
# tasks.sieve.rels_wanted=19000000 \
# tasks.polyselect.threads=11 --client-threads 11 -t all --no-colors

# -------------------------------------------------------------------------------------------------------------------------
# 464 bit tested
# Adjust according to the performance of your GPU and the number of slaves
# -------------------------------------------------------------------------------------------------------------------------
#./cado-nfs.py --server $cand tasks.workdir=$workdir server.port=$PortNum server.ssl=no server.whitelist=0.0.0.0/0 $addOpt \
#tasks.lim0=5200000 \
#tasks.lim1=7000000 \
#tasks.lpb0=28 \
#tasks.lpb1=29 \
#tasks.sieve.lambda0=1.80 \
#tasks.sieve.lambda1=1.90 \
#tasks.sieve.mfb0=55 \
#tasks.sieve.mfb1=58 \
#tasks.sieve.ncurves0=10 \
#tasks.sieve.ncurves1=15 \
#tasks.I=13 \
#tasks.sieve.qrange=10000 \
#tasks.sieve.rels_wanted=30000000 \
#tasks.polyselect.threads=11 --client-threads 11 -t all --no-colors
