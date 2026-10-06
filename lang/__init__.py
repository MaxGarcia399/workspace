"""WORKSPACE · lang — catálogos de cadenas traducibles del lado CLIENTE.

Cada idioma es un SUB-PAQUETE `lang/<code>/` con UN módulo por pantalla
(`hub.py`, `tono.py`, `onboarding.py`, …); cada uno exporta `STRINGS = {...}`
(claves namespaced por esa pantalla). `lang/es/` es la FUENTE (español actual,
copiado tal cual); los demás son traducciones. `i18n.py` DESCUBRE y MERGEA
todos los módulos de `lang/<code>/*.py` en un solo dict — no se importan a mano
desde las pantallas. Un módulo por pantalla = el fan-out de traducción (un
agente por pantalla) no colisiona. Patrón completo en `lang/README.md`.

Este paquete (y sus sub-paquetes) VIAJA al distro (el cliente necesita EN):
make-dist no lo strippea.
"""
