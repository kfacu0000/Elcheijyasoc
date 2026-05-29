import streamlit as st
import pandas as pd
import requests
import io

st.set_page_config(page_title="Calculadora de Movilidad", layout="wide", page_icon="⚖️")

# ==========================================
# 1. CAPA DE EXTRACCIÓN (Datos Oficiales + CSV Local)
# ==========================================
@st.cache_data(ttl=86400) # Se actualiza una vez al día
def obtener_datos_reales():
    # URLs Oficiales del Portal de Datos Abiertos de Argentina
    url_ripte = "https://infra.datos.gob.ar/catalog/sspm/dataset/173/distribution/173.1/download/remuneracion-imponible-promedio-trabajadores-estables-ripte-total-pais-pesos-serie-mensual.csv"
    url_ipc = "https://infra.datos.gob.ar/catalog/sspm/dataset/145/distribution/145.3/download/indice-precios-al-consumidor-nivel-general-base-diciembre-2016-mensual.csv"
    
    # "Disfraz" de Google Chrome para saltar el Error 403 del Gobierno
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        # --- Procesar RIPTE con requests ---
        respuesta_ripte = requests.get(url_ripte, headers=headers)
        respuesta_ripte.raise_for_status() # Verifica si hay error
        df_ripte = pd.read_csv(io.StringIO(respuesta_ripte.text))
        
        df_ripte['indice_tiempo'] = pd.to_datetime(df_ripte['indice_tiempo'])
        df_ripte.set_index('indice_tiempo', inplace=True)
        df_ripte = df_ripte.rename(columns={'ripte': 'RIPTE'})
        
        # --- Procesar IPC con requests ---
        respuesta_ipc = requests.get(url_ipc, headers=headers)
        respuesta_ipc.raise_for_status()
        df_ipc = pd.read_csv(io.StringIO(respuesta_ipc.text))
        
        df_ipc['indice_tiempo'] = pd.to_datetime(df_ipc['indice_tiempo'])
        df_ipc.set_index('indice_tiempo', inplace=True)
        df_ipc = df_ipc[['ipc_ng_nacional']].rename(columns={'ipc_ng_nacional': 'IPC'})
        
        # Unificar
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
    df_final.bfill(inplace=True) 
    
    return df_final

# ==========================================
# 2. MOTOR JURISPRUDENCIAL DE EMPALME
# ==========================================
def empalme_tramos(df, tramos, desde, hasta):
    factor_total = 1.0
    fecha_actual = desde
    
    for fin_tramo, columna in tramos:
        if fecha_actual > fin_tramo:
            continue
            
        fecha_fin_calculo = min(hasta, fin_tramo)
        
        if
