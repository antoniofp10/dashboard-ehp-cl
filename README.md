# Estadía hospitalaria prolongada en Chile

Dashboard interactivo sobre los factores asociados a la estadía hospitalaria prolongada (EHP) y la estimación de su probabilidad con regresión logística, a partir de los egresos hospitalarios 2025 del DEIS.


**Autores:** Antonio Freyle · Ignacia Sáez

## Pregunta de investigación

¿Se asocian el grupo etario, el sistema de previsión de salud y la pertenencia del establecimiento al SNSS con la probabilidad de que un egreso hospitalario en Chile presente una estadía prolongada (> 6 días), una vez ajustado por sexo y por el capítulo CIE-10 del diagnóstico principal?

- **Variable respuesta:** EHP = 1 si los días de estada superan el percentil 75 de la base limpia (P75 = 6 días).
- **Hipótesis:** H₀,₁ edad, H₀,₂ previsión, H₀,₃ red (SNSS); sexo y capítulo CIE-10 del diagnóstico como variables de control.
- **Muestra:** 1.000.000 de egresos (muestreo aleatorio simple, semilla 42) de 1.705.514 registros originales.

## Contenido del dashboard

| Pestaña | Contenido |
|---|---|
| 1. Portada | Problema, pregunta, hipótesis y datos |
| 2. Exploración | Distribución de los días de estada, normalidad, EHP por categoría (con filtros) |
| 3. Relaciones y tests | Spearman, Levene, Mann–Whitney, Kruskal–Wallis + Dunn, χ² y V de Cramér |
| 4. Diagnósticos | Linealidad del logit, Hosmer–Lemeshow, residuos, Cook, sobredispersión, sensibilidad |
| 5. Modelo | Coeficientes, OR con IC, razón de verosimilitud, comparación de modelos, ROC y matriz de confusión |
| 6. Simulación *what if* | Probabilidad estimada de EHP para un perfil elegido, con IC por método delta |
| 7. Conclusiones | Contraste de hipótesis, hallazgos, implicancias y limitaciones |

El dashboard es un único archivo HTML autocontenido (`docs/index.html`, incluye Plotly). Solo contiene resultados agregados, no registros individuales.


## Fuente de datos

Departamento de Estadísticas e Información de Salud (DEIS), Ministerio de Salud de Chile (2025). *Egresos hospitalarios*. Datos abiertos. https://deis.minsal.cl
