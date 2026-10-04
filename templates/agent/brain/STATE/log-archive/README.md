# log-archive/ — archivo frío de bitácoras (COLD, never-delete)

Rotación de `STATE/log-recent.md` y changelogs de `STATE/brain-version.md`.

## Cuándo va algo aquí

- `log-recent.md` — el cron nocturno rota el contenido cuando supera 4k chars o 7 días
  de antigüedad. El archivo de destino sigue la convención `log-YYYY-MM.md`.
- `brain-version.md` — el changelog con entradas >30 días se mueve aquí para mantener el
  archivo HOT dentro del tope de 2.5k chars.
- Legados de boot y otros archivos de identidad deprecados pueden vivir aquí con prefijo
  `legado/` (ej. `legado/boot.md`) — never-delete, solo archivado.

## Convención de nombres

```
log-archive/
  log-YYYY-MM.md          ← rotaciones mensuales de log-recent
  changelog-hasta-YYYY-MM.md  ← overflow del changelog de brain-version
  legado/                 ← archivos de identidad/boot deprecados
```

## Regla madre: nunca borrar

Olvidar = degradar de capa, no destruir. Todo lo que baja aquí es COLD: solo se accede
bajo consulta explícita (grep o FTS5 en E3). Git guarda el historial completo de todos modos.
