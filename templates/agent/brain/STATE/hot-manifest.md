# Manifiesto HOT — superficies que gastan tokens

<!-- Cada línea declara un archivo que se CARGA en contexto (la moneda cara).
     Formato (una línea por superficie):
       - boot <ruta>              → se lee en CADA arranque
       - session <ruta> — nota    → se carga durante la sesión (p. ej. un
                                    índice que se retrievea en cada tarea)
     El boot estándar (CLAUDE.md + BOOT/NN-*.md + STATE vivo: brain-version,
     MEMORY, PENDIENTES, MILESTONES, log-recent, users/<socio>) se
     AUTO-DETECTA — no lo listes; declara aquí solo lo EXTRA de este cerebro.
     Rutas relativas al cerebro, sin `..` ni absolutas (se ignoran).
     Lo leen `workspace doctor` (fase 8b) y `python3 brain_vitals.py` — SOLO
     miden, jamás editan. Mantén cada superficie esbelta: cada char se paga
     en cada carga. -->

- boot STATE/INDEX.md — contrato de retrieval (se lee tras BOOT)
- session skills/INDEX-LITE.md — catálogo HOT de skills
