# Avaliacao Tecnologica

Data: 2026-06-16  
Status: matriz inicial. As escolhas finais de parametros dependem de benchmark no servidor real.

## Fontes consultadas

- PyMuPDF docs: https://pymupdf.readthedocs.io/
- OCRmyPDF docs: https://ocrmypdf.readthedocs.io/
- PaddleOCR/PP-StructureV3: https://github.com/PaddlePaddle/PaddleOCR
- Docling docs/repo: https://github.com/docling-project/docling e https://www.docling.ai/
- Celery docs: https://docs.celeryq.dev/
- Qwen3.5 9B no Ollama: https://ollama.com/library/qwen3.5:9b
- Qwen/Qwen3.5-9B no Hugging Face: https://huggingface.co/Qwen/Qwen3.5-9B
- llama.cpp speculative decoding/MTP: https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md

## Principios de selecao

1. Nao trocar tecnologia que ja funciona sem prova.
2. Preferir ferramentas locais por padrao.
3. Usar servicos externos somente com configuracao explicita e limites de custo.
4. Separar extracao, OCR, traducao, composicao, validacao e publicacao.
5. Registrar licenca, consumo de recursos e qualidade observada.
6. Escolher parametros por benchmark no hardware real, nao por valores arbitrarios.

## Matriz resumida

| Area | Opcao | Papel recomendado | Qualidade esperada | Custo operacional | Licenca/risco | Decisao inicial |
|---|---|---|---|---|---|---|
| PDF | PyMuPDF | Extracao, renderizacao, edicao incremental e fallback atual | Alta para PDFs digitais e manipulacao de paginas | Baixo | Verificar termos da versao usada | Manter e encapsular |
| PDF | pypdf | Metadados, paginas, operacoes simples | Boa para tarefas simples | Baixo | BSD-like | Usar como auxiliar |
| PDF | pdfplumber | Extracao de texto/tabelas para analise | Boa para diagnostico de layout | Baixo/medio | MIT | Avaliar para tabelas digitais |
| PDF | pikepdf/qpdf | Reparos, linearizacao, criptografia, validacao estrutural | Alta em manutencao de PDF | Medio | MPL/Apache-style por componente; verificar | Adicionar como ferramenta opcional |
| OCR pesquisavel | OCRmyPDF | Criar camada de texto pesquisavel em scans | Alta para preservar visual original | Medio; requer binarios | MPL-2.0 | Recomendado para PDF pesquisavel |
| OCR rapido | RapidOCR | Primeiro passe local rapido | Ja usado; bom custo | Baixo | Verificar pacote/modelos | Manter como provider |
| OCR/Layout | PaddleOCR / PP-StructureV3 | OCR, layout, tabelas, estrutura de documentos | Promissor para tabelas e coordenadas | Medio/alto; dependencias pesadas | Apache-2.0 em PaddleOCR; verificar modelos | Avaliar em perfil opcional |
| Layout | Docling | Conversao estruturada e leitura de ordem/tabelas | Forte para Document AI e IR | Medio | MIT segundo materiais do projeto; verificar release | Avaliar como `LayoutProvider` |
| OCR tradicional | Tesseract | Fallback local robusto e conhecido | Bom em scans limpos; pior em layout complexo | Medio; binario externo | Apache-2.0 | Provider fallback |
| Tabelas | pdfplumber | Tabelas digitais simples | Boa quando linhas/texto estao preservados | Baixo | MIT | Primeiro fallback digital |
| Tabelas | PP-StructureV3 | Tabelas complexas e escaneadas | Melhor encaixe para celulas/coordenadas | Alto | Verificar modelos | Benchmark obrigatorio |
| Imagens | Pillow/OpenCV | Recortes, mascaras, inpainting classico, renderizacao | Suficiente para muitos casos | Baixo/medio | Licencas permissivas; verificar wheels | Manter |
| Inpainting | LaMa/IOPaint | Reconstrucao local de imagem com texto | Potencialmente melhor em fundos complexos | Alto; modelos grandes | Verificar licencas/modelos | Opcional, nao padrao |
| Fila | Pastas atuais | Compatibilidade local | Fragil para producao | Baixo | Sem dependencia | Substituir gradualmente |
| Fila | Celery + Redis | Workers distribuidos, retries, scheduling | Madura e flexivel | Medio/alto | BSD | Boa opcao para fase Docker |
| Fila | RQ/Dramatiq | Simples, Redis-based | Boa para menos complexidade | Medio | Verificar | Alternativa se Celery for exagerado |
| Estado | SQLite | Job store local simples | Bom para single-node | Baixo | Public domain | Recomendado para primeira migracao |
| Estado | PostgreSQL | Producao, concorrencia, relatorios | Alta | Medio | PostgreSQL | Recomendado para Compose final |
| Observabilidade | Logs JSON | Base obrigatoria | Alta utilidade imediata | Baixo | N/A | Implementar primeiro |
| Observabilidade | Prometheus/Grafana/Loki | Metricas e logs em producao | Alta | Medio/alto | Verificar imagens | Perfil opcional |
| LLM | Ollama | Backend local simples | Bom para usuario final | Baixo | Modelo separado | Manter como provider |
| LLM | llama.cpp server | Controle fino, MTP, quantizacao | Alto potencial | Medio | MIT; modelos separados | Avaliar para MTP |
| LLM | OpenAI-compatible | Interface comum para local/cloud | Alta flexibilidade | Medio | Depende provider | Implementar interface |
| Modelo | `qwen3.5:9b` | Modelo padrao solicitado | Promissor; precisa benchmark | Medio; 9B | Verificar licenca da variante exata | Configurar apos validar |

## Escolhas iniciais

### PDF e renderizacao

Manter PyMuPDF como nucleo inicial porque o projeto ja o utiliza e ele cobre leitura, renderizacao e edicao. A mudanca imediata deve ser encapsular operacoes em interfaces internas, nao trocar a biblioteca.

### Document IR

Criar um Document IR proprio e versionado. Docling e PP-StructureV3 podem alimentar esse IR, mas nao devem substituir o contrato interno. Isso evita acoplamento a um fornecedor ou formato especifico.

### OCR

Usar provider `auto` com cascata:

1. Digital text confiavel: sem OCR completo.
2. RapidOCR para regioes simples.
3. Tesseract ou PaddleOCR para fallback local.
4. OCRmyPDF para camada pesquisavel de scans.
5. Google Vision/Document AI apenas quando explicitamente habilitado.

### Tabelas

Comecar com extracao digital via PyMuPDF/pdfplumber. Para tabelas escaneadas ou sem bordas, avaliar PP-StructureV3 antes de prometer alta fidelidade.

### Fila e persistencia

Migracao em duas fases:

1. SQLite local com jobs, paginas, etapas, artefatos e retries.
2. PostgreSQL + Redis/Celery no Docker Compose, se o benchmark operacional justificar.

### LLM

Criar `InferenceProvider` antes de mudar o modelo. Providers iniciais:

- `MockProvider` para testes.
- `OllamaProvider` para compatibilidade.
- `OpenAICompatibleProvider` para backends locais/cloud.
- `LlamaCppProvider` para avaliar MTP.

O modelo solicitado `qwen3.5:9b` existe no catalogo do Ollama e no Hugging Face, mas a instalacao local auditada ainda nao o tinha carregado como `qwen3.5:9b`.

### MTP

MTP deve ser tratado como otimizacao experimental. O llama.cpp documenta `--spec-type draft-mtp`, mas a ativacao so deve ocorrer apos benchmark A/B:

- baseline sem MTP;
- `draft-mtp` com diferentes `--spec-draft-n-max`;
- diferentes contextos;
- medicao de tokens/s, TTFT, RAM, VRAM, estabilidade e qualidade.

## Decisoes adiadas

- Escolha final entre Celery e alternativa mais simples.
- Uso padrao de Docling ou PaddleOCR como layout provider.
- Uso de inpainting neural local.
- Configuracao exata de `qwen3.5:9b`.
- Quantizacao e contexto maximo.
- Perfil CPU/GPU.
- Exposicao externa do dashboard.

## Benchmarks necessarios

1. PDF digital simples.
2. PDF escaneado limpo.
3. PDF hibrido.
4. Duas colunas.
5. Tabela com bordas.
6. Tabela sem bordas.
7. Imagem com texto.
8. Livro grande.
9. Comparacao RapidOCR vs PaddleOCR vs Tesseract.
10. Comparacao Ollama vs llama.cpp.
11. MTP ligado/desligado.
12. Persistencia apos `docker compose down` e `up -d`.
