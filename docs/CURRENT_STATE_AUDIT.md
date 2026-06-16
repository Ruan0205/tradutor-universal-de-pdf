# Auditoria do Estado Atual

Data da auditoria: 2026-06-16  
Branch de trabalho: `codex/refactor-pdf-platform`  
Commit inicial auditado: `570d55d581cb823d03487fc9dc9ed266297013fa`

## Escopo

Esta auditoria registra o estado do projeto antes das alterações de arquitetura. O objetivo é preservar o que funciona, identificar riscos reais e criar uma base incremental para transformar o projeto em uma aplicação durável de tradução de PDFs.

## Evidências coletadas

Comandos executados:

```powershell
git remote -v
git branch --show-current
git rev-parse HEAD
git status --short --branch
python --version
python -m compileall -q .
```

Resultado:

- Remote confirmado: `https://github.com/Ruan0205/tradutor-universal-de-pdf.git`.
- Branch original: `main`.
- Branch criada para trabalho: `codex/refactor-pdf-platform`.
- Python local: `3.10.11`.
- `compileall`: aprovado.
- Testes automatizados existentes: nao encontrados.
- `requirements.txt`, `pyproject.toml`, Dockerfile e Compose: nao encontrados.

Smoke test executado:

- O servidor `engine/server.py` subiu em porta temporaria.
- `GET /api/status` respondeu com estado `idle`.
- A API basica do dashboard funciona sem iniciar pipeline.
- O Ollama local respondeu em `http://localhost:11434`.
- Modelos vistos no Ollama local: `qwen3.5:cloud`, `kimi-k2.6:cloud`.
- O identificador requerido `qwen3.5:9b` ainda nao foi confirmado como disponivel.

Dependencias importadas pelo codigo e ausentes no ambiente global:

- `numpy`
- `cv2` / OpenCV
- `rapidocr_onnxruntime`
- `onnxruntime`
- `pystray`

Dependencias presentes:

- `fitz` / PyMuPDF
- `PIL` / Pillow

## Estrutura atual

```text
tradutor-universal-de-pdf/
├── iniciar.bat
├── instalador.bat
├── iniciar.py
├── engine/
│   ├── config.json
│   ├── pipeline.py
│   ├── server.py
│   ├── validator.py
│   └── static/index.html
├── INICIO-RAPIDO.txt
├── LEIA-ME.txt
└── README.md
```

## Classificacao dos componentes

| Componente | Decisao | O que faz | Problema encontrado | Justificativa | Risco | Testes necessarios | Estrategia de migracao |
|---|---|---|---|---|---|---|---|
| `engine/server.py` | refatorar | API HTTP, dashboard, upload, controle do pipeline e validador | Servidor baseado em `http.server`, estado global em memoria, subprocessos globais, API sem versao, sem autenticacao, sem health/readiness separados | A API basica funciona, mas precisa ser dividida em aplicacao, rotas, servicos e persistencia | Medio | Smoke de API, testes de rotas, testes de concorrencia, testes de autorizacao | Manter endpoints antigos enquanto adiciona `/api/v1` |
| `engine/pipeline.py` | refatorar | Traduz PDFs, chama Ollama, OCR, edita texto/imagens, move arquivos entre pastas | Arquivo grande, muitas responsabilidades, fila baseada em diretorios, checkpoints fracos, limpeza agressiva de temporarios, falhas por pagina apenas logadas, sem Document IR | Ha valor funcional, mas precisa virar pipeline por etapas idempotentes | Alto | PDFs digitais, escaneados, hibridos, imagens com texto, tabelas, cancelamento e retomada | Extrair etapas gradualmente mantendo o fluxo antigo como compatibilidade |
| `engine/validator.py` | corrigir/refatorar | Compara PDF original e traduzido por estrutura, caracteres e modo hibrido | Heuristicas uteis, mas sem contrato de entrada, sem relatorio estruturado, depende de logs e nomes de arquivos | Pode virar `ValidationProvider` usando Document IR e relatorios JSON/HTML | Medio | Testes de sobreposicao, glifos, paginas amostradas e documentos corrompidos | Preservar validacoes atuais e adicionar saida estruturada |
| `engine/static/index.html` | manter/refatorar | Dashboard SPA | Grande arquivo unico com CSS/JS embutidos, sem build/testes, sem API versionada | UI atual e aproveitavel para operacao local | Medio | Playwright, acessibilidade basica, regressao visual | Manter tela atual e mover JS/CSS por etapas |
| `iniciar.py` | corrigir/refatorar | Launcher Windows, preflight, bandeja, Ollama e dashboard | Mistura instalacao, verificacao, execucao e UX; usa caminhos Windows; nao serve Docker/Linux | Importante para usuarios Windows, mas nao deve ser o runtime de producao | Medio | Preflight em Windows, servidor offline, Ollama offline, modelo ausente | Manter launcher Windows e criar CLI/API multiplataforma separada |
| `instalador.bat` | manter/corrigir | Instalacao Windows automatizada | Sem arquivo declarativo de dependencias; dificil testar em CI | Util para instalacao local, mas nao substitui Docker | Medio | Execucao em VM Windows, idempotencia | Gerar dependencias a partir de `requirements.txt` |
| `engine/config.json` | corrigir | Configuracoes persistidas | Configuracao local versionada no Git; mistura defaults com estado do usuario | Precisa separar defaults, `.env`, secrets e estado persistente | Alto | Migracao de config, validacao de schema | Criar `.env.example`, schema e migrador |
| Pastas de fila | substituir gradualmente | Entrada, traduzindo, traduzidos, originais | Estado real depende de moves de arquivos e memoria do processo; retomada limitada | Para producao precisa de banco/manifestos/checkpoints | Alto | Falha no meio do livro, restart, arquivo parcial, duplicidade | Introduzir tabela/manifest de jobs e manter pastas como storage |
| Ollama direto | refatorar | Chamada local ao LLM | Acoplamento direto a Ollama; resposta livre sem JSON Schema; cache em memoria | Precisa de interface `InferenceProvider` e saida estruturada | Medio | Timeout, JSON invalido, modelo ausente, retry | Criar providers e mock provider antes de trocar pipeline |
| OCR RapidOCR direto | refatorar | OCR de paginas/imagens | Provider unico e dependencia importada tardiamente; sem cascata ou confianca composta | Precisa de `OCRProvider` intercambiavel | Alto | OCR digital, escaneado, baixa qualidade, regioes duvidosas | Criar interface e adaptar RapidOCR como primeiro provider |

## Principais riscos tecnicos

- Falta de persistencia transacional para jobs, paginas e etapas.
- Possivel perda de trabalho ao limpar `traduzindo/`.
- Sem protecao contra arquivo parcialmente copiado.
- Sem API versionada.
- Sem autenticacao.
- Sem testes automatizados.
- Sem Docker/Compose.
- Sem schema para configuracao, relatorios ou documentos.
- Sem controle formal de licencas de dependencias/modelos.
- Sem separacao entre configuracao publica, privada e secrets.
- Sem validacao deterministica de respostas do LLM.
- Sem memoria terminologica persistente.
- Sem relatorios JSON/HTML por livro.

## Problemas reproduzidos ou observados

1. Nao ha suite de testes existente para executar.
2. O projeto compila, mas o pipeline completo nao pode rodar no ambiente global por dependencias ausentes.
3. A API basica sobe e responde, mas sem autenticacao e sem endpoint versionado.
4. O modelo padrao do config atual e `TranslateGemma`, diferente do modelo solicitado.
5. O modelo solicitado `qwen3.5:9b` nao foi encontrado localmente durante a auditoria.
6. O estado da fila depende de arquivos e subprocessos, nao de armazenamento duravel.

## Linha de base de benchmark

Benchmark real de traducao de livro ainda nao foi executado, porque:

- Nao ha dependencias completas instaladas em ambiente isolado.
- Nao ha documento de teste versionado no repositorio.
- O modelo solicitado ainda precisa ser validado no hardware real.

Linha de base disponivel nesta etapa:

- Smoke test da API: `GET /api/status` respondeu em poucos segundos.
- `compileall`: aprovado.

## Decisoes iniciais

1. Preservar o pipeline atual enquanto uma arquitetura por etapas e introduzida.
2. Introduzir `Document IR` como contrato canônico antes de alterar extração, OCR e renderizacao.
3. Adicionar testes unitarios sem exigir dependencias pesadas.
4. Documentar limitacoes em vez de declarar suporte nao testado.
5. Nao registrar credenciais, caminhos pessoais, PDFs ou modelos no repositorio.

## Proxima migracao recomendada

1. Formalizar dependencias e ambiente de desenvolvimento.
2. Adicionar `Document IR` ao fluxo de extracao em modo experimental.
3. Criar `JobStore` persistente com SQLite ou PostgreSQL.
4. Criar API `/api/v1/jobs`.
5. Extrair provider de inferencia com `MockProvider` testavel.
6. Criar golden dataset sintetico, publico e pequeno.
7. Criar Dockerfile e Compose com perfis CPU/GPU.
