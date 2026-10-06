"""WORKSPACE · lang/es — catálogo ESPAÑOL (la FUENTE), como PAQUETE por pantalla.

Español es el idioma por default y la fuente de verdad: cada cadena es el texto
EXACTO que el harness mostraba hardcodeado. UN módulo por pantalla
(`hub.py`, `tono.py`, `onboarding.py`, …) — cada uno exporta `STRINGS = {...}`.
`i18n` descubre y MERGEA todos los módulos de este paquete en un solo dict
(falla-suave: un módulo roto/ausente no tumba a los demás).

Por qué paquete y no un `es.py` plano: el fan-out de traducción asigna UN
agente por pantalla (un módulo cada uno) → sin colisiones de merge. Convención
completa en `lang/README.md`.
"""
