#/bin/bash
SHELL_PATH=$(pwd -P)
CUDA_VISIBLE_DEVICES=0
while :
do
   if [ $(ps augx | grep "cuda-ecm-1" | grep -v grep | wc -l) -eq 0 ]; then
        screen -wipe
        screen -dmS cuda-ecm-1 ./cuda-ecm -c gpu_config_1.ini
        echo "Start cuda-ecm-1 " 
   fi
   if [ $(ps augx | grep "cuda-ecm-2" | grep -v grep | wc -l) -eq 0 ]; then
        screen -wipe
        screen -dmS cuda-ecm-2 ./cuda-ecm -c gpu_config_2.ini
        echo "Start cuda-ecm-2 " 
   fi
   if [ $(ps augx | grep "cuda-ecm-3" | grep -v grep | wc -l) -eq 0 ]; then
        screen -wipe
        screen -dmS cuda-ecm-3 ./cuda-ecm -c gpu_config_3.ini
        echo "Start cuda-ecm-3 " 
   fi
   if [ $(ps augx | grep "cuda-ecm-4" | grep -v grep | wc -l) -eq 0 ]; then
        screen -wipe
        screen -dmS cuda-ecm-4 ./cuda-ecm -c gpu_config_4.ini
        echo "Start cuda-ecm-4 " 
   fi
   #if [ $(ps augx | grep "cuda-ecm-5" | grep -v grep | wc -l) -eq 0 ]; then
   #     screen -wipe
   #     screen -dmS cuda-ecm-5 ./cuda-ecm -c gpu_config_5.ini
   #     echo "Start cuda-ecm-5 " 
   #fi
   #if [ $(ps augx | grep "cuda-ecm-6" | grep -v grep | wc -l) -eq 0 ]; then
   #     screen -wipe
   #     screen -dmS cuda-ecm-6 ./cuda-ecm -c gpu_config_6.ini
   #     echo "Start cuda-ecm-6 " 
   #fi   


   sleep 1
done
