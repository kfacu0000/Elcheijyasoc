import streamlit as st
import pandas as pd

st.set_page_config(page_title="Calculadora de Movilidad", layout="wide", page_icon="⚖️")

# ==========================================
# 1. CAPA DE EXTRACCIÓN (Datos Oficiales + CSV Local)
# ==========================================
@st.cache_data(ttl=86400) # Se actualiza una vez al día
def obtener_datos_reales():
    # 1. Extracción de IPC y RIPTE vivos (Datos del Estado)
    url_ripte = "https://infra.datos.gob.ar/catalog/sspm/dataset/173/distribution/173.1/download/remuneracion-imponible-promedio-trabajadores-estables-ripte-total-pais-pesos-serie-mensual.csv"
    url_ipc = "https://infra.datos.gob.ar/catalog/sspm/dataset/145/distribution/145.3/download/indice-precios-al-consumidor-nivel-general-base-diciembre-2016-mensual.csv"
    
    try:
        # Procesar RIPTE
        df_ripte = pd.read_csv(url_ripte)
        df_ripte['indice_tiempo'] = pd.to_datetime(df_ripte['indice_tiempo'])
        df_ripte.set_index('indice_tiempo', inplace=True)
        df_ripte = df_ripte.rename(columns={'ripte': 'RIPTE'})
        
        # Procesar IPC
        df_ipc = pd.read_csv(url_ipc)
        df_ipc['indice_tiempo'] = pd.to_datetime(df_ipc['indice_tiempo'])
        df_ipc.set_index('indice_tiempo', inplace=True)
        df_ipc = df_ipc[['ipc_ng_nacional']].rename(columns={'ipc_ng_nacional': 'IPC'})
        
        df_oficial = pd.merge(df_ipc, df_ripte, left_index=True, right_index=True, how='outer')
        df_oficial.index = df_oficial.index.to_period('M')
        
    except Exception as e:
        st.error(f"Error al conectar con el servidor del gobierno (datos.gob.ar): {e}")
        st.stop()

    # 2. Extracción de tu archivo CSV para Aumentos ANSES
    try:
        df_anses_raw = pd.read_csv("aumentos_anses_2010_2026_v2.csv")
        meses = {'Enero': 1, 'Febrero': 2, 'Marzo': 3, 'Abril': 4, 'Mayo': 5, 'Junio': 6, 
                 'Julio': 7, 'Agosto': 8, 'Septiembre': 9, 'Octubre': 10, 'Noviembre': 11, 'Diciembre': 12}
        
        df_anses_raw['Mes_num'] = df_anses_raw['Mes'].map(meses)
        df_anses_raw['Fecha'] = pd.to_datetime(df_anses_raw['Año'].astype(str) + '-' + df_anses_raw['Mes_num'].astype(str) + '-01')
        df_anses_raw.set_index('Fecha', inplace=True)
        
        # Limpieza inteligente del porcentaje
        if df_anses_raw['Aumento (%)'].dtype == 'object':
            df_anses_raw['factor'] = 1 + df_anses_raw['Aumento (%)'].str.replace('%', '').astype(float) / 100
        else:
            df_anses_raw['factor'] = 1 + df_anses_raw['Aumento (%)'] / 100
            
        # Generar serie continua mensual para ANSES
        min_date = df_anses_raw.index.min()
        max_date = pd.Timestamp.today() + pd.DateOffset(months=12)
        idx_mensual = pd.date_range(start=min_date, end=max_date, freq='MS')
        
        df_factores = pd.DataFrame(1.0, index=idx_mensual, columns=['factor'])
        df_factores.update(df_anses_raw[['factor']])
        
        # Calcular el acumulado
        df_factores['ANSES'] = df_factores['factor'].cumprod() * 100
        df_factores.index = df_factores.index.to_period('M')
        
        df_final = pd.merge(df_oficial, df_factores[['ANSES']], left_index=True, right_index=True, how='outer')
        
    except Exception as e:
        st.error(f"Falla crítica al leer 'aumentos_anses_2010_2026_v2.csv': {e}")
        st.stop()

    df_final.sort_index(inplace=True)
    df_final.ffill(inplace=True) 
    df_final.bfill(inplace=True) # Cubre meses antiguos vacíos por desfasajes de publicación
    
    return df_final

# ==========================================
# 2. MOTOR JURISPRUDENCIAL DE EMPALME
# ==========================================
def empalme_tramos(df, tramos, desde, hasta):
    """
    Función algorítmica que ensambla matemáticamente el haber atravesando distintos
    índices según los hitos (fechas de corte) dictados en las sentencias.
    """
    factor_total = 1.0
    fecha_actual = desde
    
    for fin_tramo, columna in tramos:
        if fecha_actual > fin_tramo:
            continue
            
        fecha_fin_calculo = min(hasta, fin_tramo)
        
        if fecha_actual != fecha_fin_calculo:
            try:
                factor_tramo = df.loc[fecha_fin_calculo, columna] / df.loc[fecha_actual, columna]
                factor_total *= factor_tramo
            except KeyError:
                return None
            
        fecha_actual = fecha_fin_calculo
        if fecha_actual == hasta:
            break
            
    return factor_total

def calcular_factor(df, desde, hasta, metodo):
    try:
        # Métodos Directos Lineales
        if metodo == "IPC":
            return df.loc[hasta, 'IPC'] / df.loc[desde, 'IPC']
            
        elif metodo == "RIPTE":
            return df.loc[hasta, 'RIPTE'] / df.loc[desde, 'RIPTE']
            
        elif metodo == "Aumentos ANSES":
            return df.loc[hasta, 'ANSES'] / df.loc[desde, 'ANSES']

        # Fórmulas Jurisprudenciales Complejas
        elif metodo == "Aumentos Gral. + Cier + Gimenez + IPC":
            tramos = [
                (pd.Period('2019-12', 'M'), 'ANSES'), # Hasta Dic 2019: Movilidad General
                (pd.Period('2020-12', 'M'), 'IPC'),   # Año 2020: Fallo Cier (Reemplaza DNU por IPC)
                (pd.Period('2024-03', 'M'), 'IPC'),   # 2021 a Mar 2024: Fallo Gimenez (Reemplaza Ley 27.609 por IPC)
                (pd.Period('2050-12', 'M'), 'IPC')    # Tramo actual
            ]
            return empalme_tramos(df, tramos, desde, hasta)

        elif metodo == "Aumentos Gral. + Cier + Gimenez + RIPTE":
            tramos = [
                (pd.Period('2019-12', 'M'), 'ANSES'),
                (pd.Period('2020-12', 'M'), 'RIPTE'), # Año 2020: Variante RIPTE
                (pd.Period('2024-03', 'M'), 'RIPTE'), # 2021 a Mar 2024: Variante RIPTE
                (pd.Period('2050-12', 'M'), 'RIPTE')  # Tramo actual
            ]
            return empalme_tramos(df, tramos, desde, hasta)
                
        else:
            return 1.0
            
    except KeyError:
        return None

# ==========================================
# 3. INTERFAZ DE USUARIO (UI)
# ==========================================
st.title("⚖️ Calculadora de Movilidad Previsional (Pro)")
st.markdown("---")

with st.spinner("Descargando IPC/RIPTE oficiales y procesando tu tabla de ANSES..."):
    df_indices = obtener_datos_reales()

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Parámetros del Beneficio")
    monto_inicial = st.number_input("Haber original a actualizar ($)", min_value=0.0, value=150000.0, step=1000.0)
    
    fecha_desde = st.date_input("Fecha de origen", value=pd.to_datetime("2017-01-01"))
    fecha_hasta = st.date_input("Fecha de liquidación", value=pd.to_datetime("today"))
    
    st.markdown("### Jurisprudencia a evaluar")
    metodos_disponibles = [
        "Aumentos ANSES",
        "Aumentos Gral. + Cier + Gimenez + IPC",
        "Aumentos Gral. + Cier + Gimenez + RIPTE",
        "IPC", 
        "RIPTE"
    ]
    metodos_seleccionados = st.multiselect(
        "Seleccione los métodos para contrastar", 
        options=metodos_disponibles,
        default=["Aumentos ANSES", "Aumentos Gral. + Cier + Gimenez + IPC"]
    )
    
    calcular_btn = st.button("Ejecutar Cálculo Comparativo", type="primary", use_container_width=True)

with col2:
    if calcular_btn and metodos_seleccionados:
        st.subheader("Resultados de la Comparativa")
        
        periodo_desde = pd.Period(fecha_desde, 'M')
        periodo_hasta = pd.Period(fecha_hasta, 'M')
        
        resultados = []
        for metodo in metodos_seleccionados:
            factor = calcular_factor(df_indices, periodo_desde, periodo_hasta, metodo)
            
            if factor is not None:
                haber_actualizado = monto_inicial * factor
                resultados.append({
                    "Método / Fallo": metodo,
                    "Coeficiente Acumulado": round(factor, 4),
                    "Haber Reajustado ($)": f"${haber_actualizado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                })
            else:
                st.error(f"⚠️ Faltan datos oficiales o en tu CSV para calcular: '{metodo}' en las fechas indicadas.")
                
        if resultados:
            df_resultados = pd.DataFrame(resultados)
            st.dataframe(df_resultados, use_container_width=True, hide_index=True)
            
            st.markdown("### Evolución Histórica Real")
            mask = (df_indices.index >= periodo_desde) & (df_indices.index <= periodo_hasta)
            df_grafico = df_indices.loc[mask]
            
            if not df_grafico.empty:
                df_grafico_norm = (df_grafico / df_grafico.iloc[0]) * 100
                df_grafico_norm.index = df_grafico_norm.index.to_timestamp()
                
                # Gráfica interactiva de la carrera de índices
                st.line_chart(df_grafico_norm[['ANSES', 'IPC', 'RIPTE']])

    elif not metodos_seleccionados:
        st.info("👈 Selecciona al menos un método y haz clic en Ejecutar Cálculo.")
