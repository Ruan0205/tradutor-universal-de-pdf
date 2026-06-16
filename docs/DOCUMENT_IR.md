# Document IR

O `Document IR` e a representacao intermediaria canonica do projeto. Ele descreve o documento de forma rastreavel para que extracao, OCR, traducao, validacao e renderizacao trabalhem sobre o mesmo contrato.

Implementacao inicial:

- Codigo: `engine/document_ir.py`
- Schema: `schemas/document_ir.schema.json`
- Versao atual: `0.1.0`
- Testes: `tests/test_document_ir.py`

## Objetivos

- Preservar rastreabilidade ate a origem de cada bloco.
- Representar PDFs digitais, escaneados e hibridos.
- Manter coordenadas, estilo, idioma, confianca e status por elemento.
- Permitir checkpoints por pagina/bloco.
- Servir como base para memoria de traducao, glossario, revisao humana e relatorios.

## Entidades principais

```text
IRDocument
IRPage
IRBlock
IRTextLine
IRTable
IRTableCell
IRImage
TextStyle
Provenance
BBox
```

## Identificadores

IDs devem ser estaveis e derivados do documento/pagina/ordem quando possivel:

```text
document_id
page_id
block_id
line_id
table_id
cell_id
image_id
```

Exemplo:

```json
{
  "block_id": "page-12-block-8",
  "type": "paragraph",
  "bbox": {
    "x0": 100,
    "y0": 220,
    "x1": 450,
    "y1": 390
  },
  "source": "digital_text",
  "original_text": "Example text",
  "translated_text": "Texto de exemplo",
  "ocr_confidence": null,
  "translation_provider": "ollama",
  "translation_model": "qwen3.5:9b",
  "status": "validated"
}
```

## Status recomendados

```text
new
extracted
ocr_done
planned
translated
validated
needs_review
failed
rendered
published
```

## Classificacao de paginas

Classificacoes minimas:

```text
digital
scanned
hybrid
multi_column
table_dense
image_with_text
cover
formula
code
rotated
low_quality_scan
handwritten
decorative
blank
```

## Proveniencia

Cada elemento pode registrar uma lista de `Provenance`:

```json
{
  "source": "digital_text",
  "tool": "pymupdf",
  "tool_version": "1.27.2",
  "confidence": 1.0,
  "notes": []
}
```

## Compatibilidade

`IRDocument.from_dict()` rejeita versoes desconhecidas. Migracoes futuras devem ser explicitas, por exemplo:

```text
0.1.0 -> 0.2.0
```

Nao altere semanticamente campos existentes sem aumentar a versao do IR e criar teste de migracao.

## Proximas integracoes

1. Extrair paginas digitais do PyMuPDF para `IRPage` e `IRBlock`.
2. Persistir um arquivo `.ir.json` por job.
3. Fazer OCR preencher linhas/blocos com `source = "ocr"`.
4. Fazer tradutores preencher `translated_text`, provider, modelo e confianca.
5. Fazer validadores emitirem warnings e status por bloco.
6. Fazer renderizadores consumir apenas o IR, nao chamadas soltas de PyMuPDF.
