# Evidencia de auditoría TwinGuard v3.5

Todos los CSV son sintéticos. Los microrepos son contraejemplos dirigidos, no una muestra de repositorios reales. Los originales en la carpeta superior no se modificaron. El informe está en `../TwinGuard_v3.5_auditoria_adversarial.md`.

## Archivos

- `inputs.sha256`: hashes de los diez originales auditados, relativos a `files3.5`.
- `tests_originales.txt`: 94 tests originales aprobados.
- `test_v35_audit.py`, `regressions.txt`: ocho funciones, diez casos de regresión de comportamiento deseado. **Se espera que fallen sobre la versión entregada.** No son un parche implementado.
- `run_cases.py`: genera los microrepos y CSV sintéticos y ejecuta los testigos; guarda `observations.json`. No contiene resultados de un agente LLM.
- `microrepos/`: fuentes antes/después para reproducir las diferencias de conducta y grafo.
- `cases_stdout.txt`: resumen de la ejecución de los testigos.
- `verify_core.py`, `core_invariance.json`: invariancia de cuatro bloques del informe confirmatorio al añadir la columna secundaria GSC, usando datos sintéticos.
- `valid_gate.csv`, `gate_cli.json`: comprobación del CLI de la compuerta; etiquetas de detector asignadas artificialmente, no rendimiento de detectores.
- `power_sim.txt`: ejecución del simulador original, 4.000 simulaciones, semilla 20261105. Es planificación ilustrativa bajo sus supuestos.
- `requirements_observed.txt`: versiones del entorno utilizado; Python 3.11.

## Comandos

Desde `files3.5`, con un Python que tenga numpy, pandas, scipy, statsmodels y pytest. El entorno utilizado en esta sesión es `/tmp/twinguard_review_env/bin/python`; no es necesario que exista esa misma ruta en otro equipo.

```sh
shasum -a 256 -c auditoria_v35_evidencia/inputs.sha256

python -m pytest -q test_twinguard.py test_twinguard_graph.py test_twinguard_gate.py test_review_regressions.py test_adversarial_regressions.py

python -m pytest -q auditoria_v35_evidencia/test_v35_audit.py

python auditoria_v35_evidencia/run_cases.py
python auditoria_v35_evidencia/verify_core.py

python twinguard_gate.py auditoria_v35_evidencia/valid_gate.csv --detectors gsc ast --compare gsc ast --draws 20 --seed 20261105

python twinguard_power_sim.py --simulations 4000 --seed 20261105
```

El segundo comando pytest termina con código 1 porque reproduce los errores. Tras una reparación se espera que pasen sus diez casos; si se elige exclusión explícita de codificaciones o error explícito de manifest, adaptar las aserciones al contrato documentado, sin permitir la corrupción ni `no_alert` por ausencia de objeto evaluable.

`run_cases.py` regenera sus propios artefactos en esta carpeta. Conservar una copia de la evidencia original al comparar versiones reparadas. La descomposición usa tolerancia numérica y datos con faltantes; el check de invariancia usa 20 draws para verificar identidad computacional, no para inferir cobertura de intervalos.

Los casos seguros de conteo de caminos se documentan como limitaciones del algoritmo, no como una exigencia de rediseñarlo hasta aprobarlos. No agregar esta carpeta al conjunto reservado: todos sus casos son ahora desarrollo.
