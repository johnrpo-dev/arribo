"""Versión del contrato de la API del conductor (`docs/api-conductor.md`).

Va en el campo `version` de toda respuesta con cuerpo. Sube solo si un cambio rompe a una app ya
instalada (quitar o renombrar un campo, cambiar su tipo o su significado); agregar un campo nuevo
no la cambia, y la app ignora los campos que no conoce.
"""
VERSION = 1
