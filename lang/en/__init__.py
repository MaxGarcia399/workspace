"""WORKSPACE · lang/en — ENGLISH catalog, as a per-screen PACKAGE.

Mirror of `lang/es/`: same module layout, same keys, translated values. A key
missing here falls back to `es` automatically (i18n.t), so a half-translated
screen degrades to Spanish rather than breaking. One module per screen; `i18n`
discovers and merges them all. See `lang/README.md`.
"""
