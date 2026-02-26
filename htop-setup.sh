wget https://github.com/htop-dev/htop/archive/refs/tags/3.2.2.tar.gz
tar -xzf 3.2.2.tar.gz
cd htop-3.2.2
./autogen.sh
./configure --prefix=$HOME/.local
make
make install
echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
