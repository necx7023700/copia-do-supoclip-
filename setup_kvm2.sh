#!/bin/bash
# ==============================================================================
# Script de Preparação do Servidor Ubuntu na Hostinger KVM 2 para o SupoClip
# ==============================================================================
set -e

echo "=== 1. Atualizando pacotes do sistema ==="
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y curl git ufw htop

echo "=== 2. Configurando Swap de 4GB (Essencial para estabilidade em compilações) ==="
if [ ! -f /swapfile ]; then
    echo "Criando swapfile de 4GB..."
    sudo fallocate -l 4G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=4096
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    sudo sysctl vm.swappiness=15
    echo 'vm.swappiness=15' | sudo tee -a /etc/sysctl.conf
    echo "Swap configurado com sucesso!"
else
    echo "Swap já existe. Continuando..."
fi

echo "=== 3. Verificando/Instalando Docker e Docker Compose ==="
if ! command -v docker &> /dev/null; then
    echo "Instalando Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
fi

sudo apt-get install -y docker-compose-plugin

echo "=== 4. Ajustes no Kernel para Streaming de Vídeo e Fila ==="
sudo sysctl -w fs.file-max=2097152
sudo sysctl -w net.core.somaxconn=1024

echo "=== 5. Pronto! ==="
echo "Para iniciar o SupoClip otimizado:"
echo "1. cp .env.kvm2.example .env"
echo "2. Edite o .env colocando sua ASSEMBLY_AI_API_KEY e GOOGLE_API_KEY (ou OpenAI)"
echo "3. Execute: docker compose -f docker-compose.kvm2.yml up -d --build"
