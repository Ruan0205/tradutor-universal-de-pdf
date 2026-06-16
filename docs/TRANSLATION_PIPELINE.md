# Translation Pipeline

The staged pipeline records every job stage in durable storage. Current implementation covers:

- global analysis
- page classification
- digital text extraction
- Document IR generation
- translation through provider interface
- translated PDF composition
- text validation
- report and manifest generation
- publication of output artifacts

The full 32-stage list is defined in `translator/domain.py`. Stages that are not fully implemented yet are marked completed as compatibility checkpoints, not as proof of advanced OCR/layout quality.
