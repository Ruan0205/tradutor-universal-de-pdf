# 📚 Tradutor Universal de PDFs — v1.0

**Traduza livros PDF inteiros automaticamente usando modelos de IA local (Ollama).**

> Pipeline completo de tradução com dashboard web, validação automática, preservação de layout, fontes e cores originais.

---

## 🖥️ Preview

<p align="center">
  <img src="Tela%20do%20projeto.png" alt="Tela inicial do Tradutor Universal de PDFs — Dashboard em funcionamento" width="100%">
</p>

<p align="center"><em>Dashboard web do projeto em funcionamento — tradução de PDFs com IA local em tempo real.</em></p>

---

## ✨ Funcionalidades

### 🔄 Tradução Inteligente
- **Tradução por blocos de texto** — preserva a estrutura, posição e formato original do PDF
- **OCR integrado** (RapidOCR) — detecta e traduz texto em imagens e páginas escaneadas
- **Preservação de fontes** — identifica a categoria da fonte (serif, sans, mono) e aplica a mais semelhante
- **Preservação de cores** — mantém a cor original do texto tanto em páginas de texto quanto em imagens
- **Tradução em lote** — processa múltiplos PDFs automaticamente, em fila com prioridade
- **Re-tradução prioritária** — livros podem ser reenviados para a fila como próximo a ser processado

### 🤖 Modelos de IA
- Compatível com **Ollama** (localhost)
- Suporta qualquer modelo de tradução (ex: TranslateGemma, Llama, Gemma)
- Parâmetros configuráveis: temperatura, top_p, num_ctx, GPU layers, threads, etc.
- Troca de modelo em tempo real pelo dashboard

### 🌐 Idiomas
- **10+ idiomas** de origem e destino
- Padrão: Inglês → Português Brasileiro
- Inclui: Espanhol, Francês, Alemão, Italiano, Japonês, Chinês, Coreano, Russo

### ✅ Validação Automática
- **3 métodos de validação:**
  - **Estrutural** — compara blocos, fontes, contagem de caracteres e sobreposição
  - **Contagem de Caracteres** — verifica proporção de caracteres original vs tradução
  - **Híbrido** — análise completa: fontes, cores, tabelas, sobreposição e trechos não traduzidos
- **Modos de cobertura:** 25% aleatório (padrão), 50% aleatório, ou todas as páginas
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

## 🚀 Como Usar

### Pré-requisitos
1. **Python 3.11+** instalado
2. **Ollama** instalado e rodando em `http://localhost:11434`
3. Um modelo de tradução instalado no Ollama (ex: `ollama pull translategemmma`)

### Instalação

```bash
# 1. Clone ou copie o projeto
git clone <url-do-repositório>
cd tradutor-universal-de-pdfs

# 2. Crie um ambiente virtual
python -m venv .venv

# 3. Ative o ambiente virtual
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# 4. Instale as dependências
pip install PyMuPDF Pillow rapidocr-onnxruntime
```

### Estrutura de Pastas

```
projeto/
├── tradutor-universal-de-pdf/        # Código do projeto
│   ├── iniciar.py                    # Launcher (inicia tudo)
│   ├── iniciar.bat                   # Atalho Windows
│   └── engine/
│       ├── pipeline.py               # Motor de tradução
│       ├── validator.py              # Motor de validação
│       ├── server.py                 # Servidor web + API
│       ├── config.json               # Configurações
│       └── static/
│           └── index.html            # Dashboard (SPA)
├── livros-para-traduzir/             # ← Coloque os PDFs aqui
├── traduzindo/                       # Livro sendo processado
├── traduzidos/                       # ← Livros traduzidos saem aqui
├── em-inges/                         # Originais após tradução
└── .venv/                            # Ambiente virtual Python
```

### Executando

```bash
# Opção 1: Pelo launcher
python tradutor-universal-de-pdf/iniciar.py

# Opção 2: Windows — duplo clique em iniciar.bat
```

O dashboard abre automaticamente em `http://localhost:8050`.

1. Coloque os PDFs em inglês na pasta `livros-para-traduzir/`
2. Clique em **▶ Iniciar** no dashboard
3. Acompanhe o progresso em tempo real
4. Livros traduzidos aparecem em `traduzidos/`

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

## 📋 Changelog v1.0

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

*Desenvolvido com ❤️ usando IA local — Tradutor Universal de PDFs v1.0*

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
