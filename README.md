# 📚 Tradutor Universal de PDFs — v2.0.1

**Traduza livros PDF inteiros automaticamente usando modelos de IA local (Ollama).**

> Pipeline completo de tradução com dashboard web, validação automática, preservação de layout, fontes e cores originais.

---

## 🖥️ Preview

### 🎬 Demonstração em Vídeo

<p align="center">
  <a href="https://www.youtube.com/watch?v=_gnpUDYkeb8">▶ Assistir no YouTube</a>
</p>

<p align="center"><em>Vídeo demonstrativo do Tradutor Universal de PDFs em funcionamento.</em></p>

### 🖼️ Capturas do Projeto

#### 🖼️ Galeria de Telas

#### 🔗 Links diretos (`Imagens-telas`)
- [Tela livros](Imagens-telas/Tela%20livros.png)
- [Tela modelos de IA](Imagens-telas/Tela%20modelos%20de%20IA.png)
- [Tela configurações](Imagens-telas/Tela%20configura%C3%A7%C3%B5es.png)
- [Tela validador](Imagens-telas/Tela%20validador.png)
- [Tela visualizador](Imagens-telas/Tela%20visualizador.png)

#### 📚 Gerenciamento de Livros
<p align="center">
  <img src="Imagens-telas/Tela%20livros.png" alt="Tela de gerenciamento da fila de livros" width="100%">
</p>

#### 🤖 Modelos de IA
<p align="center">
  <img src="Imagens-telas/Tela%20modelos%20de%20IA.png" alt="Tela de seleção e configuração de modelos de IA" width="100%">
</p>

#### ⚙️ Configurações
<p align="center">
  <img src="Imagens-telas/Tela%20configura%C3%A7%C3%B5es.png" alt="Tela de configurações gerais do pipeline" width="100%">
</p>

#### ✅ Validador
<p align="center">
  <img src="Imagens-telas/Tela%20validador.png" alt="Tela de validação automática das traduções" width="100%">
</p>

#### 🔍 Visualizador Comparativo
<p align="center">
  <img src="Imagens-telas/Tela%20visualizador.png" alt="Tela do visualizador comparativo entre original e tradução" width="100%">
</p>

---

## ✨ Funcionalidades

### 🔄 Tradução Inteligente
- **Tradução por blocos de texto** — preserva a estrutura, posição e formato original do PDF
- **OCR integrado** (RapidOCR) — detecta e traduz texto em imagens e páginas escaneadas
- **Reconstrução IA opcional em imagens** — modo `ai_rebuild` usa inpainting para remover texto original e recriar o texto traduzido (modo `legacy` é o padrão)
- **Processamento seletivo de IA em imagens** — evita reconstrução de página OCR inteira quando configurado para páginas não selecionáveis
- **Preservação de fontes** — identifica a categoria da fonte (serif, sans, mono) e aplica a mais semelhante
- **Preservação de cores** — mantém a cor original do texto tanto em páginas de texto quanto em imagens
- **Tradução em lote** — processa múltiplos PDFs automaticamente, em fila com prioridade
- **Re-tradução prioritária** — livros podem ser reenviados para a fila como próximo a ser processado

### 🤖 Modelos de IA
- Compatível com **Ollama** (localhost)
- Suporta qualquer modelo de tradução (ex: TranslateGemma, Llama, Gemma)
- Parâmetros configuráveis: temperatura, top_p, num_ctx, GPU layers, threads, etc.
- Seleção de backend de processamento OCR/imagem: **CPU** ou **GPU** (DirectML/CUDA quando disponível)
- Troca de modelo em tempo real pelo dashboard

### 🌐 Idiomas
- **10+ idiomas** de origem e destino
- Padrão: Inglês → Português Brasileiro
- Inclui: Espanhol, Francês, Alemão, Italiano, Japonês, Chinês, Coreano, Russo

### ✅ Validação Automática
- **3 métodos de validação:**
  - **Estrutural** — foca somente na estrutura/layout (blocos, proporções e sobreposição)
  - **Contagem de Caracteres** — foca somente em caracteres (total e por linha)
  - **Híbrido** — análise completa: estrutura, fontes, cores, tabelas, linhas, sobreposição e texto sobre imagem
- **Modos de cobertura:** 25% distribuído (padrão), 50% distribuído, ou todas as páginas
- **Tolerância de fidelidade** configurável (0-100%, padrão 90%)
- Validação contínua — monitora automaticamente novos livros traduzidos
- Revalidação manual com um clique

### 📊 Dashboard Web
- Interface moderna e responsiva (dark theme)
- **Progresso em tempo real** — acompanhe qual livro está sendo traduzido, página atual, ETA
- **Estatísticas** — velocidade (s/MB), tempo total, previsão de término
- **Gerenciamento de fila** — ordene por tamanho, customize a ordem ou arraste para reordenar
- **Visualizador comparativo** — veja original e tradução lado a lado
- **Notificações** — som e alerta do navegador quando um livro é concluído
- **Controles** — iniciar, pausar, continuar, parar pipeline pelo dashboard

### ⚙️ Configurações
- Parâmetros do Ollama editáveis em tempo real
- DPI de renderização para OCR
- Tamanho de batch, font size mínima, font ratio
- Todas as configurações persistem em `config.json`

---

## 🚀 Como Instalar e Usar

### ✅ Instalação recomendada (Windows)

1. Baixe/clone o projeto.
2. Clique com o botão direito em `instalador.bat`.
3. Execute como **Administrador**.
4. Aguarde a conclusão.

O instalador faz automaticamente:
- instala/configura Python portável (quando necessário);
- cria o ambiente virtual;
- instala/atualiza dependências Python (pode rodar novamente para atualizar para novas versões);
- tenta habilitar aceleração GPU para OCR/imagem via DirectML (quando disponível no Windows);
- baixa um pacote extra de fontes em `assets/fonts`;
- verifica/instala Ollama;
- baixa automaticamente o modelo `translategemma` (com fallback para `TranslateGemma`);
- cria as pastas de trabalho do projeto.

### ▶ Execução diária

1. Execute `iniciar.bat`.
2. O sistema inicia em segundo plano (ícone na bandeja do Windows).
3. O dashboard abre automaticamente no navegador em `http://localhost:8050/`.
4. Coloque os PDFs em `livros-para-traduzir`.
5. Clique em **Iniciar** no dashboard.

### 📁 Estrutura atual do projeto

```
tradutor-universal-de-pdf/
├── iniciar.bat
├── instalador.bat
├── iniciar.py
├── engine/
│   ├── pipeline.py
│   ├── validator.py
│   ├── server.py
│   ├── config.json
│   └── static/index.html
├── .venv/                           # criado automaticamente
├── python-portable/                 # criado automaticamente quando necessário
├── livros-para-traduzir/
├── traduzindo/
├── traduzidos/
└── na-lingua-anterior/
```

### 🧩 Instalação manual (somente se precisar)

Se o `instalador.bat` não puder ser usado, você pode instalar manualmente:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install --upgrade pip
pip install PyMuPDF Pillow rapidocr-onnxruntime tqdm pystray opencv-python onnxruntime
# opcional para GPU no Windows (AMD/NVIDIA/Intel):
pip install onnxruntime-directml
ollama pull translategemma
```

---

## 🛠️ Tecnologias

| Tecnologia | Uso |
|---|---|
| **Python 3.11** | Linguagem principal |
| **PyMuPDF (fitz)** | Leitura, manipulação e escrita de PDFs |
| **Pillow (PIL)** | Processamento de imagens |
| **RapidOCR** | Reconhecimento óptico de caracteres |
| **Ollama** | Inferência de IA local (LLMs) |
| **HTML/CSS/JS** | Dashboard web (SPA) |

---

## 📋 Changelog v2.0.1

- Correção da inicialização do dashboard em ambientes com Python 3.13
- Upload `multipart/form-data` compatível sem depender do módulo removido `cgi`
- Tratamento de desconexões do cliente no dashboard para evitar tracebacks `WinError 10053/10054`
- Continuação das melhorias da v2.0:

- Escrita de texto no PDF com fontes Unicode embutidas para evitar `?` no lugar de acentos e glifos válidos
- Validador reforçado com detecção de glifos corrompidos, blocos não traduzidos e amostragem distribuída ao longo do livro
- Lista de livros traduzidos ordenada do mais recente para o mais antigo
- Ajuste de encaixe de texto por bloco com redução de fonte mais agressiva para caber no mesmo espaço
- Continuação das melhorias da v1.9:

- Modo novo em imagens: `ai_rebuild` (inpainting + reconstrução de texto) com `legacy` mantido como padrão
- Controle de processamento OCR/imagem por configuração (`CPU` ou `GPU`)
- Estratégia para evitar reconstrução IA massiva em páginas escaneadas inteiras (por padrão, somente pontos de imagem em páginas selecionáveis)
- Instalação/atualização de pacote de fontes extras em `assets/fonts`
- Instalador atualizado para ser reexecutável e atualizar dependências em novas versões
- README atualizado com galeria de imagens do diretório `Imagens-telas` e vídeo via YouTube
- Seleção de PDFs por explorador de arquivos do Windows com suporte a múltiplos arquivos
- Inicialização em segundo plano com ícone na bandeja do Windows (sem terminal fixo aberto)
- Dashboard fixado em `http://localhost:8050/` ao iniciar
- Pasta de originais renomeada para `na-lingua-anterior` (com migração automática da pasta antiga)
- Modo híbrido reforçado com controle de linhas e maior fidelidade de encaixe de texto no layout
- Modo estrutural focado apenas em estrutura/layout
- Modo contagem de caracteres focado apenas em caracteres (total e por linha)
- Temperatura padrão do Ollama alterada para `0.4`
- Pipeline completo de tradução de PDFs com IA local
- Dashboard web com controles em tempo real
- 3 métodos de validação (estrutural, contagem, híbrido)
- Validação híbrida com análise de fontes, cores e tabelas
- Modos de cobertura: 25%, 50% ou todas as páginas
- Tolerância de fidelidade configurável
- OCR integrado para páginas escaneadas e imagens com texto
- Preservação de fontes (serif/sans/mono) e cores do original
- Re-tradução com prioridade na fila
- 10+ idiomas de origem e destino
- Parâmetros do Ollama configuráveis pelo dashboard
- Ordem de tradução personalizável (drag & drop)
- Notificação sonora e push ao completar livros
- Visualizador comparativo lado a lado
- Vinculação manual de originais
- Remoção dinâmica de livros da fila

---

## 💚 Apoie o Projeto

Se este projeto foi útil para você, considere fazer uma doação:

**Chave Pix:** `9fa4a0b4-1b1d-46ab-b26f-3961f22a3bd3`

---

## 📝 Licença

Projeto de código aberto. Livre para uso pessoal e educacional.

---

*Desenvolvido com ❤️ usando IA local — Tradutor Universal de PDFs v2.0.1*

## 🙏 Créditos e Reconhecimentos

Este projeto só foi possível graças ao trabalho incrível das seguintes equipes e projetos open-source:

### Inteligência Artificial e Tradução
| Projeto | Criadores | Link |
|---------|-----------|------|
| **Ollama** | Jeffrey Morgan e equipe | [github.com/ollama/ollama](https://github.com/ollama/ollama) |
| **TranslateGemma** | Google DeepMind | [ai.google.dev/gemma](https://ai.google.dev/gemma) |

### Processamento de PDF
| Projeto | Criadores | Link |
|---------|-----------|------|
| **PyMuPDF (fitz)** | Artifex Software, Inc. | [github.com/pymupdf/PyMuPDF](https://github.com/pymupdf/PyMuPDF) |
| **MuPDF** | Artifex Software, Inc. | [mupdf.com](https://mupdf.com/) |

### OCR (Reconhecimento Óptico de Caracteres)
| Projeto | Criadores | Link |
|---------|-----------|------|
| **RapidOCR** | RapidAI Community | [github.com/RapidAI/RapidOCR](https://github.com/RapidAI/RapidOCR) |
| **PaddleOCR** | Baidu Inc. | [github.com/PaddlePaddle/PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) |
| **ONNX Runtime** | Microsoft | [github.com/microsoft/onnxruntime](https://github.com/microsoft/onnxruntime) |

### Interface Web e Dashboard
| Projeto | Criadores | Link |
|---------|-----------|------|
| **Tailwind CSS** | Adam Wathan e equipe | [tailwindcss.com](https://tailwindcss.com/) |
| **PDF.js** | Mozilla Foundation | [github.com/nicbarker/libpdf](https://mozilla.github.io/pdf.js/) |

### Linguagem e Runtime
| Projeto | Criadores | Link |
|---------|-----------|------|
| **Python** | Python Software Foundation | [python.org](https://www.python.org/) |
| **Pillow (PIL)** | Jeffrey A. Clark (Alex) e contribuidores | [github.com/python-pillow/Pillow](https://github.com/python-pillow/Pillow) |
| **NumPy** | NumPy Community | [numpy.org](https://numpy.org/) |

### Desenvolvimento
| Projeto | Criadores | Link |
|---------|-----------|------|
| **Visual Studio Code** | Microsoft | [code.visualstudio.com](https://code.visualstudio.com/) |
| **GitHub Copilot (Claude Opus 4.6)** | Anthropic / GitHub | [github.com/features/copilot](https://github.com/features/copilot) |

---

> **Nota:** Este projeto é uma ferramenta de integração que conecta e orquestra essas tecnologias.
> Todo o mérito das tecnologias base pertence aos seus respectivos criadores e comunidades.
> Se você utiliza este projeto, considere também apoiar e dar ⭐ nos repositórios listados acima.

---

**Desenvolvido por Ruan** utilizando **GitHub Copilot com Claude Opus 4.6** como assistente de desenvolvimento.
