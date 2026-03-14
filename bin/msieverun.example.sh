
#/bin/bash
export LANG=C
inx=$1
cd ../msieve_nfsathome$inx
#mv msieve.dat msieve.dat.bak
#cat msieve.dat.bak | ./remdups4 720 > msieve.dat
#./msieve -g 0 -nc target_density=60 -t 32 -v
#mpirun -np 2 ./msieve -nc2 1,2 -g 2 -t 64 -v
#./msieve -nc3 -t 128 -v
./msieve -nc1 target_density=58.2 -t 32 -v
./msieve -nc2 -g 0 -t 32 -v
#./msieve -nc3 1,16 -t 16 -v

TARGET_STRING=" factor: "
LOG_FILE="process.log"
> "$LOG_FILE"
for i in {0..3}; do
  for j in {1..4}; do
    dep_inx=$((i * 4 + j))
    ./msieve -nc3 $dep_inx,$dep_inx -t 8 -v >>  "$LOG_FILE" &
  done
  wait
  if grep -q "$TARGET_STRING" "$LOG_FILE" ; then
     pkill -P $$
     break
  fi
done


