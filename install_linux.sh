#!/bin/bash

# Script de instalação offline para OrisBot no Linux
# Certifique-se de estar na pasta raiz do projeto (onde está este arquivo)

echo "Iniciando a instalação das dependências do OrisBot..."

# Verifica se o pip está instalado
if ! command -v pip &> /dev/null
then
    echo "Erro: pip não encontrado. Por favor, instale o python3-pip."
    exit 1
fi

# Instala as dependências usando os arquivos locais na pasta linux_dependencies
pip install --no-index --find-links=linux_dependencies -r requirements.txt

if [ $? -eq 0 ]; then
    echo "--------------------------------------------------"
    echo "Instalação concluída com sucesso!"
    echo "Para rodar o bot, use: python3 bot.py"
    echo "--------------------------------------------------"
else
    echo "--------------------------------------------------"
    echo "Ocorreu um erro durante a instalação."
    echo "Verifique se a versão do Python é compatível (recomendado 3.11)."
    echo "--------------------------------------------------"
fi
