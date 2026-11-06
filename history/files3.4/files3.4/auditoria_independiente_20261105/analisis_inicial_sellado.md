# Análisis independiente antes de consultar las dos asesorías excluidas

Fecha de trabajo: 5 noviembre 2026. Este archivo fija las conclusiones iniciales.
Hasta este punto no se ha abierto ninguna de las dos asesorías excluidas.

## Dictamen inicial

P1 ajustar; P2 mantener condicionado a congelar semántica y serialización;
P3 mantener; P4 ajustar; G1 revertir intervalo 95% actual, mantener descripciones;
G2 ajustar; G3 ajustar; G4 mantener como primer recorte.

63 tests originales pasan. Simulador original con 4000 repeticiones y semilla
20261105 reproduce tabla §11. No se propone rediseñar H1/H2, estimador,
decisiones ni tamaño confirmatorio.

20 microrepos: 1 TP, 1 TN, 6 FP, 12 FN; muestra adversarial intencional, sin
interpretación de prevalencia. Runtime externo comprueba eventos de monitor y
acción. Orden temporal es una política adicional en monitor_after_action;
los otros FN incluyen ausencia de llamada, destinatario equivocado o conteo.

G1: réplica vectorizada de fórmula exacta, contrastada con generalization a
1e-12. 20000 simulaciones por escenario. Cobertura verdadera: base .9125,
base baja .6092, semillas con acoplamiento positivo .1838, negativo .99105,
sector compartido .94315, mecanismos fijos .9985, heterogeneidad cero .9844.
No son resultados del modelo. Semillas comunes no implican correlación real.
Suavizado binomial sesgado con n=4, covarianza ignorada, truncamiento tau,
normalidad no calibrada, tres mecanismos fijos tratados como superpoblación.

Errores de código reproducidos: mutación borra línea completa (3 regresiones:
punto y coma, función inline eliminada, if/else inválido); import relativo en
__init__; parámetros locales ocultando global; celda completamente faltante
no contada; ausencia de validación de familias evaluables provoca división
por cero; parse fallido omitido sin diagnóstico. Un noveno test documenta
extensión contractual: pérdida de multiplicidad no es pérdida de par-set.

GSC es heurística de alcanzabilidad existencial, no verificación de orden,
dominancia, argumentación, número de acciones ni semántica. Nombre único no
es sound ni complete; agregar método ajeno cambia alarmas sin cambiar
ejecución. Conservar baseline congelado y exponer desconocidos/cobertura.
Comparar con baseline AST de borrado de llamadas y cambios de monitor.

G2 prueba premisa de tests, no transporte causal del encuadre. Exige baseline
verde, sitio+callee, testigo de no equivalencia, muestreo antes de resultados,
estados timeout/infra separados y sin selección por resolución del grafo.
G3 mide alarmas, no falsos positivos sin etiquetas; acuerdo con otro grafo no
es fidelidad semántica; genérico G2/G3 distinto de GSC del benchmark.
G4 una variante misma familia no identifica causalmente efecto de escala.
Wilson por corrida no modela clustering; fijar pesos, denominadores y NA.

## Primera pasada: candidatos (20), luego selección adversarial

1. Frente seguridad/utilidad de una compuerta offline GSC versus AST — retener.
2. Recurso ejecutable con tarjeta de contratos y testigos — retener.
3. Mutantes reales certificados con testigo, controles seguros y grafos oficiales — retener.
4. Falsabilidad metamórfica del GSC y cobertura de resolución — retener.
5. Ablación separada de una instrucción de preservación — retener opcional.
6. GLMM jerárquico predictivo completo — descartar del plazo.
7. E4B — reserva del protocolo, no prioridad respecto al recurso.
8. Segunda familia frontier — descartar coste y alcance.
9. Segundo arnés factorial — descartar coste y estimando múltiple.
10. Dosis respuesta de palabras IA — descartar carga y ambigüedad constructo.
11. CoT como intención/mediador — descartar, no identificable ni necesariamente fiel.
12. Codificación descriptiva ciega de trazas — archivar, sin mano humana suficiente.
13. Embeddings para ranking de revisión — futuro, baseline simple primero.
14. GNN para clasificar W — descartar datos/overfit/fuga.
15. Entrenamiento o fine tuning — descartar cambia objeto.
16. Verificador completo dominancia/datos Python — descartar plazo.
17. Detector AST pequeño de fail-open — baseline complementario si cabe en idea 1.
18. Leaderboard hospedado — descartar; CLI y tabla versionada suficiente.
19. Prompt/reparación automática tras alarma — descartar por nuevo experimento adaptativo.
20. Figura de frente de riesgo y controles pareados — integrar a idea 1/presentación.

Mayor apalancamiento propuesto: evaluar GSC versus AST como compuertas sobre
los mismos parches, reportando U evitada y reparación segura sacrificada;
producto publicable aun si H1 nula o GSC no supera baseline. G2 certificado
es la evidencia adicional de mayor transferencia si el recurso ya está listo.

Fuentes consultadas: PyCG, MOPS, Higgins et al., Nagashima et al., Jia/Harman,
Yao et al., AI Control, SWE-bench, Turpin et al.; fuentes 2026 del protocolo
abiertas y verificadas sin usar contexto de competencia como interrogante.
