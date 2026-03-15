#!/bin/sh

rootDir=$(pwd -P)

# =============================================================================
# 1. System packages
# =============================================================================
sudo apt update -y
sudo apt install screen -y
sudo apt install curl -y
sudo apt install git wget -y
sudo apt install software-properties-common -y
sudo add-apt-repository ppa:ubuntu-toolchain-r/test -y
sudo apt update -y
sudo apt install gmp-ecm -y
sudo apt install python3-pip -y
sudo apt install htop -y
sudo apt install openmpi-common -y
sudo apt install libopenmpi-dev -y
sudo apt install hwloc -y
sudo apt install gawk -y
sudo apt install bison -y
sudo apt install netcat -y
sudo apt install cmake -y
sudo apt install gmp-ecm libecm-dev -y
sudo apt install redis -y

# =============================================================================
# 2. Python packages
# =============================================================================
cd $rootDir
pip install gmpy2
pip install base58
pip install sympy
pip install numpy
pip install flask
pip install sphinx-rtd-theme
pip install recommonmark
pip install py-cpuinfo
pip install psutil
pip install nats-py

# =============================================================================
# 3. OpenMPI (source build)
# =============================================================================
cd $rootDir
wget https://download.open-mpi.org/release/open-mpi/v4.1/openmpi-4.1.6.tar.gz
tar -xvf openmpi-4.1.6.tar.gz
cd $rootDir/openmpi-4.1.6
./configure --prefix=/opt/openmpi
make all -j$(nproc)
sudo make install
echo "export PATH=/opt/openmpi/bin:\$PATH" >> $HOME/.bashrc
echo "export LD_LIBRARY_PATH=/opt/openmpi/lib:\$LD_LIBRARY_PATH" >> $HOME/.bashrc
export PATH=/opt/openmpi/bin:$PATH
export LD_LIBRARY_PATH=/opt/openmpi/lib:$LD_LIBRARY_PATH
cd $rootDir
rm openmpi-4.1.6.tar.gz

# =============================================================================
# 4. hwloc (source build)
# =============================================================================
cd $rootDir
wget https://download.open-mpi.org/release/hwloc/v2.10/hwloc-2.10.0.tar.gz
tar -xvf hwloc-2.10.0.tar.gz
cd $rootDir/hwloc-2.10.0
./configure --prefix=/opt/hwloc
make all -j$(nproc)
sudo make install
echo "export PATH=/opt/hwloc/bin:\$PATH" >> $HOME/.bashrc
echo "export LD_LIBRARY_PATH=/opt/hwloc/lib:\$LD_LIBRARY_PATH" >> $HOME/.bashrc
export PATH=/opt/hwloc/bin:$PATH
export LD_LIBRARY_PATH=/opt/hwloc/lib:$LD_LIBRARY_PATH
cd $rootDir
rm hwloc-2.10.0.tar.gz

# =============================================================================
# 5. CADO-NFS (with MPI)
# =============================================================================
cd $rootDir
git clone https://gitlab.inria.fr/cado-nfs/cado-nfs
cd cado-nfs
rm -rf build
rm -f local.sh
cp local.sh.example local.sh
echo "build_tree=$rootDir/cado-nfs/build/cado-nfs-build" >> local.sh
echo "MPI=/opt/openmpi" >> local.sh
echo "HWLOC=/opt/hwloc" >> local.sh
echo "FLAGS_SIZE=\"-DSIZEOF_P_R_VALUES=8\"" >> local.sh
git reset --hard 3ac3cc153ca8f4b219ac2fb45cdbb8cc6d2ca1cd
sed -i 's/time\.sleep(1)/time.sleep(0.01)/g' ./scripts/cadofactor/cadotask.py
make -j $(nproc)

# =============================================================================
# 6. msieve (copy to multiple directories)
# =============================================================================
cd $rootDir
cp -r msieve msieve_nfsathome
for i in 0 1 2 3 4 5; do
    cp -r msieve msieve_nfsathome${i}
done

# =============================================================================
# 7. Copy Python sources to bin
# =============================================================================
cd $rootDir
cp src/*.py bin/

# =============================================================================
# 7-1. Git post-merge hook (auto-copy src/*.py to bin/ on git pull)
# =============================================================================
cat > $rootDir/.git/hooks/post-merge << 'HOOK'
#!/bin/bash
ROOT_DIR="$(git rev-parse --show-toplevel)"
cp "$ROOT_DIR"/src/*.py "$ROOT_DIR"/bin/
echo "post-merge hook: src/*.py copied to bin/"
HOOK
chmod +x $rootDir/.git/hooks/post-merge

# =============================================================================
# 8. Sieve (primorial table generation)
# =============================================================================
cd $rootDir/bin/isieve
./sieverb 28
