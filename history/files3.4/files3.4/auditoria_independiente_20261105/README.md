# Evidencia de la revisión independiente

Material sintético de auditoría, no resultados de modelos ni datos oficiales.
Los archivos originales del protocolo y del código no fueron modificados.

- `inputs.sha256`: hashes de los originales, relativos a `files22`.
- `analisis_inicial_sellado.md` y `.sha256`: conclusiones guardadas antes de leer las dos asesorías excluidas; registro local, no sello temporal externo.
- `original_tests.txt`: 63 tests originales, todos pasan.
- `power_sim_4000.txt`: simulador original, semilla 20261105.
- `graph_cases.py`: construye y ejecuta 20 pares de microrepos.
- `microrepos/`: código before/after y grafos de cada caso.
- `graph_results.json`: resultados, trazas y decisiones exactas.
- `test_review_regressions.py`: ocho regresiones de defectos y una extensión contractual B09. Las nueve FALLAN intencionalmente sobre v0.1/v0.6.
- `regression_results.txt`: evidencia de esos fallos.
- `prediction_sim.py`: siete escenarios, 20000 simulaciones por escenario; igualdad de fórmula comprobada con la implementación original.
- `prediction_results.json`: resultados numéricos de la simulación.
- `check_prior_advice.py`: comprobaciones separadas, posteriores a la lectura de v2.
- `prior_v2_*_excerpt.py`: fragmentos extraídos de esa asesoría, no parches recomendados ni aplicados.
- `prior_advice_checks.json`: resultados de comprobar esos fragmentos.
- `requirements_observed.txt`: dependencias del entorno utilizado.

## Reproducir

Crear un entorno Python 3.11 y usar las dependencias fijadas en
`requirements_observed.txt`. Los scripts buscan los originales en el
directorio padre. Desde `files3.4`:

```bash
python -m pytest -q test_twinguard.py test_adversarial_regressions.py test_twinguard_graph.py
python auditoria_independiente_20261105/graph_cases.py
python -m pytest -q auditoria_independiente_20261105/test_review_regressions.py
python auditoria_independiente_20261105/prediction_sim.py
python twinguard_power_sim.py --simulations 4000 --seed 20261105
python auditoria_independiente_20261105/check_prior_advice.py
```

La tercera orden sale con error porque codifica el comportamiento deseado.
B01–B03 exigen soporte correcto de la sentencia; si se elige excluir esos
sitios como reparación mínima, adaptar las aserciones para comprobar una
exclusión explícita, sin contar esos casos como mutantes evaluados. B09 es
una decisión de extensión de contrato, no un defecto de la definición de
pérdida de pares de aristas.

Las tasas de la matriz adversarial no son estimaciones de rendimiento real.
Las coberturas G1 dependen de los generadores declarados; no estiman efectos
del modelo ni la correlación real inducida por compartir semillas.

El ZIP de entrega incorpora además una copia de los originales auditados y
las dos asesorías para que estas comprobaciones sean autosuficientes. No
contiene datos de la competencia.
