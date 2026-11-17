# Estadía hospitalaria prolongada en Chile

Dashboard interactivo sobre los factores asociados a la estadía hospitalaria prolongada (EHP) y la estimación de su probabilidad con regresión logística, a partir de los egresos hospitalarios 2025 del DEIS.

**Dashboard en línea:** https://antoniofp10.github.io/dashboard-ehp-cl/

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

## Estructura del repositorio

```
├── generar_dashboard.py          # limpieza, pruebas, modelo y construcción del HTML
├── plantilla_dashboard.html      # interfaz (HTML + JavaScript + Plotly)
├── requirements.txt
├── datos/
│   ├── EGR_DATOS_ABIERTO_2025.csv.gz            # base DEIS 2025 comprimida (gzip)
│   └── Diccionario BD egresos hospitalario.xlsx # diccionario y códigos CIE-10
├── salidas_dashboard/
│   └── datos_dashboard.json      # resultados calculados (caché)
├── docs/
│   └── index.html                # dashboard publicado con GitHub Pages
├── notebooks/
│   ├── proyecto_analisis_Avance1_estadistico.ipynb   # Avance 1: limpieza, EDA y pruebas bivariadas
│   └── proyecto_avance2_estadistico.ipynb            # Avance 2: regresión logística y diagnóstico
└── informe/
    └── Paper_Certamen2_EHP.pdf   # informe final (paper)
```

El script `generar_dashboard.py` reproduce la misma limpieza, muestra (semilla 42) y modelo de los notebooks, por lo que las cifras del dashboard coinciden con las del paper.

## Cómo reproducirlo

```bash
pip install -r requirements.txt
python generar_dashboard.py          # recalcula todo desde la base (varios minutos)
python generar_dashboard.py --html   # solo regenera docs/index.html desde el caché
```

pandas lee el archivo `.csv.gz` directamente; no es necesario descomprimirlo.

## Fuente de datos

Departamento de Estadísticas e Información de Salud (DEIS), Ministerio de Salud de Chile (2025). *Egresos hospitalarios*. Datos abiertos. https://deis.minsal.cl
