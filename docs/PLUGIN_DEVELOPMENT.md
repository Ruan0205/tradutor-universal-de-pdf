# Plugin Development

Provider interfaces are the extension points:

- `InferenceProvider`
- `OCRProvider`
- `LayoutProvider`
- `TableProvider`
- `ImageTranslationProvider`
- `ValidationProvider`
- `StorageProvider`
- `NotificationProvider`

New providers must expose health/status, avoid logging document content, and support deterministic tests with generated fixtures.
