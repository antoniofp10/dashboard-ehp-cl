"""
Genera el dashboard interactivo del proyecto EHP (Estadía Hospitalaria Prolongada).

Reproduce el mismo procesamiento de los notebooks del Avance 1 y del Avance 2
(misma limpieza, misma muestra aleatoria con semilla 42 y el mismo modelo de
regresión logística) y guarda los resultados en un único archivo HTML
autocontenido (incluye Plotly), que se abre en cualquier navegador sin
Python ni conexión a internet.

Uso:
    python generar_dashboard.py            # recalcula todo y genera el HTML
    python generar_dashboard.py --html     # solo regenera el HTML desde el caché

Estructura del repositorio:
    ├── generar_dashboard.py               (este script)
    ├── plantilla_dashboard.html           (interfaz: HTML + JavaScript)
    ├── datos/
    │   ├── EGR_DATOS_ABIERTO_2025.csv.gz  (base DEIS 2025, comprimida)
    │   └── Diccionario BD egresos hospitalario.xlsx
    ├── salidas_dashboard/datos_dashboard.json   (caché de resultados)
    └── docs/index.html                    (dashboard; publicado con GitHub Pages)
"""
import json
import os
import re
import sys
import time
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

CARPETA = os.path.dirname(os.path.abspath(__file__))          # raíz del repositorio
DATOS = os.path.join(CARPETA, "datos")
RUTA_CSV = os.path.join(DATOS, "EGR_DATOS_ABIERTO_2025.csv.gz")      # pandas lo descomprime al leer
if not os.path.exists(RUTA_CSV):                                   # alternativa: CSV sin comprimir
    RUTA_CSV = os.path.join(DATOS, "EGR_DATOS_ABIERTO_2025.csv")
RUTA_DICC = os.path.join(DATOS, "Diccionario BD egresos hospitalario.xlsx")
RUTA_PLANTILLA = os.path.join(CARPETA, "plantilla_dashboard.html")
RUTA_CACHE = os.path.join(CARPETA, "salidas_dashboard", "datos_dashboard.json")
RUTA_HTML = os.path.join(CARPETA, "docs", "index.html")

T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:6.1f}s] {msg}", flush=True)


def r(x, d=4):
    """Redondea floats (y listas/arrays) para que el JSON sea liviano."""
    if isinstance(x, (list, tuple, np.ndarray, pd.Series)):
        return [r(v, d) for v in list(x)]
    if x is None:
        return None
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        if not np.isfinite(x):
            return None
        return round(float(x), d)
    return x


# ==============================================================================
# 1. CÁLCULO DE TODOS LOS RESULTADOS
# ==============================================================================
def calcular():
    from scipy import stats
    from scipy.special import xlogy
    import statsmodels.api as sm
    from statsmodels.stats.diagnostic import lilliefors
    from sklearn.metrics import roc_auc_score

    out = {}

    # ------------------------------------------------------------------
    # 1.1 Carga y limpieza (idéntica a la sección 5.0 del Avance 1)
    # ------------------------------------------------------------------
    log("Leyendo el CSV de egresos...")
    df = pd.read_csv(RUTA_CSV, sep=";", encoding="utf-8", low_memory=False)
    df.columns = [c.strip().upper() for c in df.columns]
    n0 = len(df)
    df["GRUPO_EDAD"] = df["GRUPO_EDAD"].replace({"menor de un a�o": "menor de un año", "90 y m�s": "90 y más"})
    df["DIAS_ESTADA"] = pd.to_numeric(df["DIAS_ESTADA"], errors="coerce")
    df = df.dropna(subset=["DIAS_ESTADA", "GRUPO_EDAD", "GLOSA_PREVISION", "PERTENENCIA_ESTABLECIMIENTO_SALU"])
    df = df[df["DIAS_ESTADA"] > 0]
    df = df[(df["GRUPO_EDAD"] != "*") & (~df["GLOSA_PREVISION"].isin(["*", "DESCONOCIDO"]))]
    n1 = len(df)
    p75 = float(np.percentile(df["DIAS_ESTADA"], 75))
    df = df.sample(n=1_000_000, random_state=42).reset_index(drop=True)
    df["EHP"] = (df["DIAS_ESTADA"] > p75).astype(int)

    def extraer_marca_edad(valor):
        s = str(valor).lower()
        if "menor" in s:
            return 0.5
        nums = [int(n) for n in re.findall(r"\d+", s)]
        if len(nums) >= 2:
            return (nums[0] + nums[1]) / 2.0
        elif len(nums) == 1:
            return float(nums[0]) + 5.0
        return np.nan

    df["EDAD_APROX"] = df["GRUPO_EDAD"].apply(extraer_marca_edad)
    dias = df["DIAS_ESTADA"]
    log(f"Muestra lista: {len(df):,} egresos (P75 = {p75})")

    out["resumen"] = {
        "n_original": n0, "n_limpio": n1, "n_muestra": len(df), "n_modelo": int((df["SEXO"] != "INTERSEX (INDETERMINDADO)").sum()),
        "media": r(dias.mean(), 2), "mediana": r(dias.median(), 1), "p75": p75, "sd": r(dias.std(), 2),
        "asimetria": r(dias.skew(), 2), "prop_ehp": r(df["EHP"].mean() * 100, 2), "n_ehp": int(df["EHP"].sum()),
        "max": int(dias.max()),
    }

    # ------------------------------------------------------------------
    # 1.2 Capítulo CIE-10 (idéntico al Avance 2)
    # ------------------------------------------------------------------
    log("Asignando capítulos CIE-10...")
    cie = pd.read_excel(RUTA_DICC, sheet_name="codigo CIE-10", header=8)
    cie["CODIGO SUBCATEGORIA"] = cie["CODIGO SUBCATEGORIA"].astype(str).str.strip().str.upper()
    cie["CODIGO CATEGORIA"] = cie["CODIGO CATEGORIA"].astype(str).str.strip().str.upper()
    por_sub = cie.drop_duplicates("CODIGO SUBCATEGORIA").set_index("CODIGO SUBCATEGORIA")["GLOSA CAPITULO"]
    por_cat = cie.drop_duplicates("CODIGO CATEGORIA").set_index("CODIGO CATEGORIA")["GLOSA CAPITULO"]
    cod = df["DIAG1"].astype(str).str.strip().str.upper()
    df["CAPITULO_CIE"] = cod.map(por_sub).fillna(cod.str[:3].map(por_cat))
    sin_cap = df["CAPITULO_CIE"].isna()
    df.loc[sin_cap & df["DIAG1"].str.startswith("U"), "CAPITULO_CIE"] = "Códigos para propósitos especiales"
    df.loc[sin_cap & df["DIAG1"].str.startswith("A"), "CAPITULO_CIE"] = "Ciertas enfermedades infecciosas y parasitarias"
    nombres_cap = {
        "Enfermedades del sistema digestivo": "Digestivo",
        "Embarazo, parto y puerperio": "Embarazo y parto",
        "Traumatismos, envenenamientos y algunas otras consecuencias de causas externas": "Traumatismos",
        "Enfermedades del sistema respiratorio": "Respiratorio",
        "Enfermedades del sistema circulatorio": "Circulatorio",
        "Enfermedades del sistema genitourinario": "Genitourinario",
        "Tumores [Neoplasias]": "Tumores",
        "Enfermedades del sistema osteomuscular y del tejido conjuntivo": "Osteomuscular",
        "Enfermedades endocrinas, nutricionales y metabólicas": "Endocrino-metabólico",
        "Factores que influyen en el estado de salud y contacto con los servicios de salud": "Factores de salud (Z)",
        "Trastornos mentales y del comportamiento": "Trastornos mentales",
        "Enfermedades del sistema nervioso central": "Sistema nervioso",
        "Ciertas enfermedades infecciosas y parasitarias": "Infecciosas",
        "Enfermedades de la piel y del tejido subcutáneo": "Piel",
        "Síntomas, signos y hallazgos anormales clínicos y de laboratorio, no clasificados en otra parte": "Síntomas mal definidos",
        "Ciertas afecciones originadas en el período perinatal": "Perinatal",
        "Malformaciones congénitas, deformidades y anomalías cromosómicas": "Malformaciones congénitas",
        "Enfermedades de la sangre y de los órganos hematopoyéticos, y ciertos trastornos que afectan el mecanismo de la inmunidad": "Sangre e inmunidad",
        "Enfermedades del ojo y sus anexos": "Ojo",
        "Enfermedades del oído y de la apófisis mastoides": "Oído",
        "Códigos para propósitos especiales": "Códigos especiales (U)",
    }
    df["CAPITULO"] = df["CAPITULO_CIE"].str.split().str.join(" ").map(nombres_cap)
    assert df["CAPITULO"].notna().all()
    glosa_corta = {v: k for k, v in nombres_cap.items()}

    # ------------------------------------------------------------------
    # 1.3 Categorías y códigos para los cubos de datos
    # ------------------------------------------------------------------
    df["TRAMO_EDAD"] = df["GRUPO_EDAD"].replace({"menor de un año": "Menor de 1 año"})
    orden_edad = df.groupby("TRAMO_EDAD")["EDAD_APROX"].mean().sort_values().index.tolist()
    marca_edad = df.groupby("TRAMO_EDAD")["EDAD_APROX"].mean().loc[orden_edad].tolist()
    cats_sexo = ["HOMBRE", "MUJER", "INTERSEX (INDETERMINDADO)"]
    cats_prev = ["ISAPRE", "FONASA", "CAPREDENA", "DIPRECA", "SISA", "NINGUNA"]
    cats_red = ["No SNSS", "SNSS"]
    otros_cap = sorted(c for c in df["CAPITULO"].unique() if c != "Digestivo")
    cats_cap = ["Digestivo"] + otros_cap
    regiones = {
        "15": "Arica y Parinacota", "01": "Tarapacá", "02": "Antofagasta", "03": "Atacama", "04": "Coquimbo",
        "05": "Valparaíso", "13": "Metropolitana", "06": "O'Higgins", "07": "Maule", "16": "Ñuble",
        "08": "Biobío", "09": "La Araucanía", "14": "Los Ríos", "10": "Los Lagos", "11": "Aysén",
        "12": "Magallanes", "99": "Ignorada", "EX": "Extranjero",
    }
    # 762 egresos de residentes en el extranjero no traen código de región
    cod_reg = df["REGION_RESIDENCIA"].fillna("EX").astype(str).str.strip().str.zfill(2)
    assert cod_reg.isin(regiones.keys()).all(), cod_reg[~cod_reg.isin(regiones.keys())].unique()
    cats_reg = list(regiones.values())
    df["RED"] = np.where(df["PERTENENCIA_ESTABLECIMIENTO_SALU"].str.startswith("No"), "No SNSS", "SNSS")

    codigos = pd.DataFrame({
        "reg": cod_reg.map({k: cats_reg.index(v) for k, v in regiones.items()}).astype(int),
        "edad": df["TRAMO_EDAD"].map({c: i for i, c in enumerate(orden_edad)}).astype(int),
        "sexo": df["SEXO"].map({c: i for i, c in enumerate(cats_sexo)}).astype(int),
        "prev": df["GLOSA_PREVISION"].map({c: i for i, c in enumerate(cats_prev)}).astype(int),
        "red": df["RED"].map({c: i for i, c in enumerate(cats_red)}).astype(int),
        "cap": df["CAPITULO"].map({c: i for i, c in enumerate(cats_cap)}).astype(int),
    })
    out["categorias"] = {
        "reg": cats_reg, "edad": orden_edad, "edad_marca": marca_edad,
        "sexo": ["Hombre", "Mujer", "Indeterminado"], "prev": cats_prev, "red": cats_red,
        "cap": cats_cap, "cap_glosa": [glosa_corta[c] for c in cats_cap],
    }

    # Cubo A: n, n con EHP y suma de días por combinación de las 6 dimensiones
    log("Construyendo cubos de datos para los filtros...")
    dims_a = ["reg", "edad", "sexo", "prev", "red", "cap"]
    cubo_a = pd.concat([codigos, df[["EHP", "DIAS_ESTADA"]]], axis=1).groupby(dims_a).agg(
        n=("EHP", "size"), e=("EHP", "sum"), s=("DIAS_ESTADA", "sum")).reset_index()
    out["cubo_a"] = {c: cubo_a[c].astype(int).tolist() for c in dims_a + ["n", "e", "s"]}

    # Cubo B: histograma exacto de días (1 a 60 denso; > 60 como lista dispersa)
    dims_b = ["reg", "edad", "sexo", "prev", "red"]
    celda = codigos.groupby(dims_b).ngroup().to_numpy()
    claves = codigos[dims_b].drop_duplicates().assign(_c=lambda t: codigos.groupby(dims_b).ngroup().loc[t.index]).sort_values("_c")
    d_int = dias.to_numpy().astype(np.int64)
    corto = d_int <= 60
    hist = np.zeros((celda.max() + 1, 60), dtype=np.int64)
    np.add.at(hist, (celda[corto], d_int[corto] - 1), 1)
    cola = pd.DataFrame({"c": celda[~corto], "v": d_int[~corto]}).value_counts().reset_index()
    out["cubo_b"] = {
        **{c: claves[c].astype(int).tolist() for c in dims_b},
        "h": hist.tolist(),
        "cola": cola[["c", "v", "count"]].astype(int).values.tolist(),
    }
    log(f"Cubo A: {len(cubo_a):,} celdas | Cubo B: {len(claves):,} celdas, cola: {len(cola):,} valores > 60 días")

    # ------------------------------------------------------------------
    # 1.4 Avance 1: normalidad, dispersión y DIAG1 por letra
    # ------------------------------------------------------------------
    log("Pruebas de normalidad y gráficos del Avance 1...")
    sub = dias.sample(n=5000, random_state=42)
    w_sw, p_sw = stats.shapiro(sub)
    d_ks, p_ks = lilliefors(sub, dist="norm", pvalmethod="table")
    ad = stats.anderson(sub, dist="norm")
    p99 = float(np.percentile(dias, 99))
    vis = dias[dias <= p99]
    dens, bordes = np.histogram(vis, bins=35, density=True)
    xg = np.linspace(vis.min(), vis.max(), 200)
    (osm, osr), (pend, inter, _) = stats.probplot(sub, dist="norm")
    out["normalidad"] = {
        "sw": [r(w_sw), float(p_sw)], "ks": [r(d_ks), float(p_ks)], "ad": [r(ad.statistic, 2), r(ad.critical_values[2], 3)],
        "p99": p99, "hist_x": r((bordes[:-1] + bordes[1:]) / 2, 3), "hist_y": r(dens, 5), "hist_w": r(bordes[1] - bordes[0], 4),
        "norm_x": r(xg, 2), "norm_y": r(stats.norm.pdf(xg, vis.mean(), vis.std()), 5),
        "qq_x": r(osm, 3), "qq_y": [int(v) for v in osr], "qq_linea": [r(pend, 4), r(inter, 4)],
    }

    vis_num = df.loc[dias <= p99, ["EDAD_APROX", "DIAS_ESTADA"]]
    mues = vis_num.sample(n=5000, random_state=42)
    jit = np.random.default_rng(42).uniform(-1.8, 1.8, len(mues))
    out["dispersion"] = {"x": r(mues["EDAD_APROX"].to_numpy() + jit, 2), "y": mues["DIAS_ESTADA"].astype(int).tolist()}

    tasa_global = df["EHP"].mean() * 100
    letra = df["DIAG1"].astype(str).str[0]
    tab_letra = pd.crosstab(letra, df["EHP"])
    chi2_l, p_l, gl_l, esp_l = stats.chi2_contingency(tab_letra)
    tab_cod = pd.crosstab(df["DIAG1"], df["EHP"])
    esp_cod = stats.chi2_contingency(tab_cod)[3]
    tasa_l = (tab_letra[1] / tab_letra.sum(axis=1) * 100).sort_values()
    out["letra"] = {
        "letras": tasa_l.index.tolist(), "tasa": r(tasa_l.values, 2), "n": tab_letra.sum(axis=1).loc[tasa_l.index].astype(int).tolist(),
        "chi2": r(chi2_l, 4), "gl": int(gl_l), "p": float(p_l), "v": r(np.sqrt(chi2_l / tab_letra.values.sum()), 4),
        "emin": r(esp_l.min(), 1), "n_codigos": int(tab_cod.shape[0]), "pct_esp_menor5": r((esp_cod < 5).mean() * 100, 1),
    }

    # ------------------------------------------------------------------
    # 1.5 Avance 2: modelo de regresión logística
    # ------------------------------------------------------------------
    log("Ajustando la regresión logística (modelo completo)...")
    m_sexo = df["SEXO"] != "INTERSEX (INDETERMINDADO)"
    df2 = df[m_sexo].copy()
    otros_edad = [t for t in orden_edad if t != "30 a 39"]
    X_base = pd.DataFrame({
        "EDAD": pd.Categorical(df2["TRAMO_EDAD"], categories=["30 a 39"] + otros_edad),
        "SEXO": pd.Categorical(df2["SEXO"], categories=["HOMBRE", "MUJER"]),
        "PREVISION": pd.Categorical(df2["GLOSA_PREVISION"], categories=cats_prev),
        "RED": pd.Categorical(df2["RED"], categories=cats_red),
        "CAPITULO": pd.Categorical(df2["CAPITULO"], categories=cats_cap),
    }, index=df2.index)
    X = pd.get_dummies(X_base, drop_first=True, dtype="int8")
    y = df2["EHP"].astype(int)
    X_sm = sm.add_constant(X.astype("float64"))
    modelo = sm.Logit(y, X_sm).fit(disp=0)
    assert modelo.mle_retvals["converged"]
    ic = modelo.conf_int()
    nombres = list(X_sm.columns)
    out["modelo"] = {
        "nombres": nombres, "beta": r(modelo.params.values, 6), "ee": r(modelo.bse.values, 6), "z": r(modelo.tvalues.values, 3),
        "p": [float(v) for v in modelo.pvalues.values], "ic_inf": r(np.exp(ic[0]).values, 4), "ic_sup": r(np.exp(ic[1]).values, 4),
        "cov": r(modelo.cov_params().values, 10), "iter": int(modelo.mle_retvals["iterations"]),
        "llf": r(modelo.llf, 2), "llnull": r(modelo.llnull, 2), "nobs": int(modelo.nobs), "eventos": int(y.sum()),
    }

    # VIF
    corr_X = np.corrcoef(X.to_numpy(dtype="float32"), rowvar=False)
    vif = pd.Series(np.diag(np.linalg.inv(corr_X)), index=X.columns).sort_values(ascending=False)
    out["vif"] = {"nombres": vif.index.tolist(), "valor": r(vif.values, 3)}

    # Razón de verosimilitud por variable
    log("Razón de verosimilitud por variable (5 modelos reducidos)...")
    grupos_var = {
        "Diagnóstico (capítulo CIE-10)": [c for c in X.columns if c.startswith("CAPITULO_")],
        "Edad (GRUPO_EDAD)": [c for c in X.columns if c.startswith("EDAD_")],
        "Red (SNSS)": ["RED_SNSS"],
        "Previsión": [c for c in X.columns if c.startswith("PREVISION_")],
        "Sexo": ["SEXO_MUJER"],
    }

    def ajustar(columnas, filas=None):
        yy, XX = (y, X_sm) if filas is None else (y[filas], X_sm[filas])
        m = sm.Logit(yy, XX[columnas]).fit(disp=0)
        assert m.mle_retvals["converged"]
        return m

    D_c, D_0 = -2 * modelo.llf, -2 * modelo.llnull
    lr, reducidos = [], {}
    for var, cols in grupos_var.items():
        reducidos[var] = ajustar([c for c in nombres if c not in cols])
        D_r = -2 * reducidos[var].llf
        G = D_r - D_c
        lr.append({"variable": var, "q": len(cols), "D_red": r(D_r, 2), "G": r(G, 2),
                   "critico": r(stats.chi2.ppf(0.95, len(cols)), 2), "p": float(stats.chi2.sf(G, len(cols))),
                   "pct": r(100 * G / D_0, 2)})

    log("Comparación de modelos (edad lineal) y OR crudos...")
    cols_edad = grupos_var["Edad (GRUPO_EDAD)"]
    X_lin = X_sm.drop(columns=cols_edad).copy()
    X_lin["EDAD_APROX"] = df2["EDAD_APROX"].astype("float64")
    m_lin = sm.Logit(y, X_lin).fit(disp=0)
    m_sd = reducidos["Diagnóstico (capítulo CIE-10)"]

    def res_mod(nombre, m):
        return {"modelo": nombre, "k": int(m.df_model) + 1, "D": r(-2 * m.llf, 2), "aic": r(m.aic, 2), "bic": r(m.bic, 2), "r2": r(m.prsquared, 4)}

    G_edad = 2 * (modelo.llf - m_lin.llf)
    out["lr"] = {
        "tabla": lr, "D_nula": r(D_0, 2), "D_completo": r(D_c, 2), "G_global": r(D_0 - D_c, 2), "q_global": X.shape[1],
        "comparacion": [
            {"modelo": "M0: solo intercepto", "k": 1, "D": r(D_0, 2), "aic": r(D_0 + 2, 2), "bic": r(D_0 + np.log(modelo.nobs), 2), "r2": 0.0},
            res_mod("M1: sin diagnóstico", m_sd),
            res_mod("M2: completo, edad lineal", m_lin),
            res_mod("M3: completo, edad por tramos", modelo),
        ],
        "G_edad": r(G_edad, 2), "q_edad": int(modelo.df_model - m_lin.df_model), "p_edad": float(stats.chi2.sf(G_edad, 9)),
    }

    def or_ic(m, v):
        i = m.conf_int().loc[v]
        return [r(np.exp(m.params[v]), 3), r(np.exp(i[0]), 3), r(np.exp(i[1]), 3)]

    m_cr_prev = ajustar(["const"] + grupos_var["Previsión"])
    m_cr_red = ajustar(["const", "RED_SNSS"])
    m_cr_edad = ajustar(["const"] + cols_edad)
    m_prev_red = ajustar(["const"] + grupos_var["Previsión"] + ["RED_SNSS"])
    crudo = []
    for t in ["60 a 69", "70 a 79", "80 a 89", "90 y más", "Menor de 1 año"]:
        v = f"EDAD_{t}"
        crudo.append({"comp": f"Edad {t} vs. 30 a 39", "crudo": or_ic(m_cr_edad, v), "prev_red": None, "completo": or_ic(modelo, v)})
    for v, m_c, et in [("PREVISION_FONASA", m_cr_prev, "FONASA vs. ISAPRE"), ("RED_SNSS", m_cr_red, "SNSS vs. No SNSS")]:
        crudo.append({"comp": et, "crudo": or_ic(m_c, v), "prev_red": or_ic(m_prev_red, v), "completo": or_ic(modelo, v)})
    pct_snss = (X["RED_SNSS"].groupby(df2["GLOSA_PREVISION"]).mean() * 100).sort_values(ascending=False)
    out["crudo"] = {"tabla": crudo, "pct_snss_prev": pct_snss.index.tolist(), "pct_snss_val": r(pct_snss.values, 1)}

    # Linealidad en el logit
    res_e = df2.groupby("TRAMO_EDAD").agg(edad=("EDAD_APROX", "mean"), tasa=("EHP", "mean"), n=("EHP", "size")).sort_values("edad")
    res_e["logit"] = np.log(res_e["tasa"] / (1 - res_e["tasa"]))
    recta = np.polyval(np.polyfit(res_e["edad"], res_e["logit"], 1, w=np.sqrt(res_e["n"])), res_e["edad"])
    out["linealidad"] = {"tramos": res_e.index.tolist(), "edad": r(res_e["edad"].values, 1), "tasa": r(res_e["tasa"].values, 4),
                         "n": res_e["n"].astype(int).tolist(), "logit": r(res_e["logit"].values, 4), "recta": r(recta, 4)}

    # Hosmer–Lemeshow
    log("Bondad de ajuste, residuos e influencia...")
    p_hat = modelo.predict(X_sm).to_numpy()
    y_np = y.to_numpy()
    dec = pd.qcut(p_hat, 10, labels=False, duplicates="drop")
    hl = pd.DataFrame({"d": dec, "y": y_np, "p": p_hat}).groupby("d").agg(n=("y", "size"), O=("y", "sum"), E=("p", "sum"), pm=("p", "mean"))
    hl["po"] = hl["O"] / hl["n"]
    hl["aporte"] = (hl["O"] - hl["E"]) ** 2 / (hl["E"] * (1 - hl["E"] / hl["n"]))
    C_hl, g = hl["aporte"].sum(), len(hl)
    out["hl"] = {"n": hl["n"].astype(int).tolist(), "O": hl["O"].astype(int).tolist(), "E": r(hl["E"].values, 1),
                 "pm": r(hl["pm"].values, 4), "po": r(hl["po"].values, 4), "aporte": r(hl["aporte"].values, 2),
                 "C": r(C_hl, 2), "gl": g - 2, "critico": r(stats.chi2.ppf(0.95, g - 2), 2), "p": float(stats.chi2.sf(C_hl, g - 2)),
                 "r2": r(modelo.prsquared, 4), "p_media": r(p_hat.mean(), 4), "obs": r(y_np.mean(), 4),
                 "dif_media": r((hl["pm"] - hl["po"]).abs().mean(), 4)}

    # Residuos e influencia por patrón de covariables
    r_ind = (y_np - p_hat) / np.sqrt(p_hat * (1 - p_hat))
    d_ind = np.sign(y_np - p_hat) * np.sqrt(-2 * (xlogy(y_np, p_hat) + xlogy(1 - y_np, 1 - p_hat)))
    id_p = X_base.groupby(list(X_base.columns), observed=True, sort=False).ngroup().to_numpy()
    K = id_p.max() + 1
    n_k = np.bincount(id_p, minlength=K).astype(float)
    O_k = np.bincount(id_p, weights=y_np, minlength=K)
    primera = pd.Series(np.arange(len(id_p))).groupby(id_p).first().to_numpy()
    X_k = X_sm.to_numpy()[primera]
    p_k = p_hat[primera]
    w_k = p_k * (1 - p_k)
    inv_info = np.linalg.inv((X_k * (n_k * w_k)[:, None]).T @ X_k)
    H_k = n_k * w_k * np.einsum("ij,jk,ik->i", X_k, inv_info, X_k)
    r_k = (O_k - n_k * p_k) / np.sqrt(n_k * w_k)
    r_std = r_k / np.sqrt(np.clip(1 - H_k, 1e-10, None))
    cook = r_std ** 2 * H_k / ((1 - H_k + 1e-10) * X_k.shape[1])
    X2 = (r_k ** 2).sum()
    D_g = 2 * (xlogy(O_k, O_k / (n_k * p_k)) + xlogy(n_k - O_k, (n_k - O_k) / (n_k * (1 - p_k)))).sum()
    gl_g = K - X_k.shape[1]
    phi = X2 / gl_g
    fb = X_base.iloc[primera].reset_index(drop=True)
    cod_pat = np.column_stack([
        fb["EDAD"].map({c: i for i, c in enumerate(orden_edad)}).astype(int),
        fb["SEXO"].map({"HOMBRE": 0, "MUJER": 1}).astype(int),
        fb["PREVISION"].map({c: i for i, c in enumerate(cats_prev)}).astype(int),
        fb["RED"].map({c: i for i, c in enumerate(cats_red)}).astype(int),
        fb["CAPITULO"].map({c: i for i, c in enumerate(cats_cap)}).astype(int),
    ])
    out["patrones"] = {
        "cod": cod_pat.tolist(), "n": n_k.astype(int).tolist(), "O": O_k.astype(int).tolist(), "p": r(p_k, 6),
        "r_std": r(r_std, 3), "H": r(H_k, 5), "cook": r(cook, 5),
    }
    out["residuos"] = {
        "pct_pearson2": r((np.abs(r_ind) > 2).mean() * 100, 2), "pct_dev2": r((np.abs(d_ind) > 2).mean() * 100, 2),
        "K": int(K), "suma_H": r(H_k.sum(), 2), "X2": r(X2, 1), "D_g": r(D_g, 1), "gl": int(gl_g), "phi": r(phi, 2),
        "pct_esp5": r(((n_k * p_k >= 5) & (n_k * (1 - p_k) >= 5)).mean() * 100, 1),
        "pct_rstd2": r((np.abs(r_std) > 2).mean() * 100, 1), "pct_egr_rstd2": r(n_k[np.abs(r_std) > 2].sum() / n_k.sum() * 100, 1),
        "cook_max": r(cook.max(), 3), "n_cook1": int((cook > 1).sum()),
    }

    # Sensibilidad
    log("Análisis de sensibilidad (modelo sin patrones influyentes)...")
    ee_esc = modelo.bse * np.sqrt(phi)
    excluir = np.where(cook > 1)[0]
    conservar = ~np.isin(id_p, excluir)
    m_si = ajustar(nombres, filas=conservar)
    out["sensibilidad"] = {
        "ic_inf_esc": r(np.exp(modelo.params - 1.96 * ee_esc).values, 4), "ic_sup_esc": r(np.exp(modelo.params + 1.96 * ee_esc).values, 4),
        "or_sin_infl": r(np.exp(m_si.params).values, 4), "n_excl": int((~conservar).sum()), "pct_excl": r((~conservar).mean() * 100, 1),
        "G_phi": [r(t["G"] / phi, 2) for t in lr],
    }

    # Capacidad predictiva (AUC con error estándar de Hanley–McNeil)
    log("Curva ROC y AUC...")
    auc = roc_auc_score(y_np, p_hat)
    n1e, n0e = int(y_np.sum()), int((1 - y_np).sum())
    Q1, Q2 = auc / (2 - auc), 2 * auc ** 2 / (1 + auc)
    ee_auc = np.sqrt((auc * (1 - auc) + (n1e - 1) * (Q1 - auc ** 2) + (n0e - 1) * (Q2 - auc ** 2)) / (n1e * n0e))
    out["roc"] = {"auc": r(auc, 4), "ic": [r(auc - 1.96 * ee_auc, 4), r(auc + 1.96 * ee_auc, 4)], "prevalencia": r(y_np.mean(), 4)}

    # Tablas de días (Avance 1) que el JS también recalcula: se guardan para verificar
    out["tasa_global"] = r(tasa_global, 2)
    return out


# ==============================================================================
# 2. CONSTRUCCIÓN DEL HTML
# ==============================================================================
def construir_html(datos):
    import plotly
    ruta_js = os.path.join(os.path.dirname(plotly.__file__), "package_data", "plotly.min.js")
    with open(ruta_js, encoding="utf-8") as f:
        plotly_js = f.read()
    with open(RUTA_PLANTILLA, encoding="utf-8") as f:
        plantilla = f.read()
    json_datos = json.dumps(datos, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = plantilla.replace("/*__PLOTLY__*/", plotly_js).replace("/*__DATOS__*/null", json_datos)
    os.makedirs(os.path.dirname(RUTA_HTML), exist_ok=True)
    with open(RUTA_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"HTML generado: {RUTA_HTML} ({os.path.getsize(RUTA_HTML) / 1e6:.1f} MB)")


if __name__ == "__main__":
    if "--html" in sys.argv and os.path.exists(RUTA_CACHE):
        with open(RUTA_CACHE, encoding="utf-8") as f:
            datos = json.load(f)
    else:
        datos = calcular()
        os.makedirs(os.path.dirname(RUTA_CACHE), exist_ok=True)
        with open(RUTA_CACHE, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, separators=(",", ":"))
        log(f"Resultados guardados en {RUTA_CACHE} ({os.path.getsize(RUTA_CACHE) / 1e6:.1f} MB)")
    construir_html(datos)
