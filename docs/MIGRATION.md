# Migration

The new production layer is additive. Existing `engine/` files and Windows scripts are preserved.

Migration path:

1. Backup current data.
2. Start the new Docker stack.
3. Register PDFs through API/CLI/watcher.
4. Compare outputs against legacy behavior.
5. Move stable behavior from `engine/` into provider/stage modules.
6. Keep rollback available through Git ref and backup restore.
