# Inventario Inicial do Servidor

Data: 2026-06-16  
Host: `10.0.0.64`  
Usuario testado: `server`  
Metodo usado: SSH com chave ja configurada. Nenhuma senha foi gravada ou usada em comando.

## Sistema

- Distribuicao: Ubuntu 24.04.4 LTS
- Kernel: Linux 6.8.0-111-generic
- Arquitetura: x86_64
- Hostname: `server`

## CPU

- Modelo: AMD Ryzen 5 5500U with Radeon Graphics
- Nucleos fisicos: 6
- Threads: 12
- Virtualizacao: AMD-V
- Recursos relevantes: AVX2, FMA, AES, SHA extensions

## Memoria

- RAM total: 9.6 GiB
- RAM disponivel durante a coleta: 5.6 GiB
- Swap total: 4.0 GiB
- Swap em uso durante a coleta: 1.3 GiB

## Disco

- Raiz: 437 GiB, 91% em uso, 41 GiB livres
- Disco adicional montado: 916 GiB, 15% em uso, 742 GiB livres

Observacao: a raiz esta com pouco espaco livre para imagens Docker, OCR e artefatos temporarios de livros grandes. O processamento deve usar o disco adicional ou outro volume com folga.

## GPU e aceleracao

- GPU detectada: AMD Radeon Graphics integrada, RADV Renoir
- NVIDIA/CUDA: nao detectado (`nvidia-smi` ausente)
- ROCm: nao detectado (`rocminfo` ausente)
- Vulkan: disponivel via Mesa RADV
- OpenCL: loader presente, mas sem plataformas detectadas

Conclusao inicial: tratar como servidor CPU-first. Vulkan pode ser avaliado para llama.cpp, mas nao deve ser assumido como caminho padrao sem benchmark.

## Docker

- Docker: 29.3.0
- Docker Compose: v5.1.0

## Rede e portas

Portas ocupadas observadas:

```text
22
3000-3004
8080
8082
8083
8111
8443
9090
9100
9101
9113
9115
9181
1234
```

Recomendacao: evitar `8080`, `8082`, `8083`, `3000-3004` e `8443`. Usar uma porta interna configuravel, por exemplo `8050`, e publicar somente em rede local ate haver autenticacao/TLS.

## Firewall

- `ufw`: inactive

Nao expor a aplicacao publicamente nesse estado.

## Ollama

O comando `ollama` nao foi encontrado no servidor durante a coleta inicial. O Ollama local da maquina Windows respondeu durante o smoke test, mas o servidor ainda precisa de backend de inferencia instalado/configurado.

## Limites

- `ulimit -n`: 1024

Para processamento paralelo de muitos arquivos, esse limite pode precisar de ajuste, mas isso deve ser feito somente durante a etapa de implantacao e com rollback documentado.

## Decisao inicial de perfil

- Perfil recomendado agora: CPU, baixa concorrencia.
- `MAX_CONCURRENT_BOOKS=1`
- `MAX_MEMORY_PERCENT=85`
- `MIN_FREE_DISK_GB` deve ser maior que 20 GiB se usar a particao raiz.
- Preferir volume no disco adicional para `input`, `work`, `output`, `reports` e `backups`.

## Bloqueios antes de implantar

1. Definir volume de dados fora da raiz quase cheia.
2. Instalar/configurar backend de inferencia no servidor.
3. Confirmar se `qwen3.5:9b` cabe com qualidade aceitavel em CPU/RAM.
4. Rodar benchmark curto antes de iniciar livro real.
5. Adicionar autenticacao antes de publicar dashboard.
6. Configurar backup/restore antes de processar colecao grande.
