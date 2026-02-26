wget https://github.com/htop-dev/htop/releases/download/3.2.2/htop-3.2.2-x86_64-linux-gnu.tar.xz
tar -xf htop-3.2.2-x86_64-linux-gnu.tar.xz
cd htop-3.2.2-x86_64-linux-gnu
chmod +x htop
mkdir -p ~/.local/bin
mv htop ~/.local/bin/
echo 'export PATH=$HOME/.local/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
htop
