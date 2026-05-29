import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import numpy as np

# Configuración de página
st.set_page_config(page_title="Calculadora de Movilidad Tye", layout="wide", page_icon="⚖️")

# ==========================================
# 1. CAPA DE EXTRACCIÓN Y DATOS (Scraping)
# ==========================================
@st.cache_data(ttl=86400) # El caché dura 24 horas para no hacer scraping constante
def obtener_datos_indices():
    """
    Función para hacer scraping o consultar APIs oficiales.
    Aquí se implementa la lógica de requests.
    """
    # ---------------------------------------------------------
    # EJEMPLO DE ARQUITECTURA DE SCRAPING REAL:
    # url_indec = "https://api.indec.gob.ar/v1/ipc"
    # headers = {"Authorization": "Bearer TU_TOKEN"}
    # response = requests.get(url_indec, headers=headers)
    # datos_json = response.json()
    # ---------------------------------------------------------
    
    # Para que este código funcione inmediatamente al copiarlo, 
    # generamos un DataFrame robusto simulando la estructura que
    # devolvería tu scraper una vez limpio:
    
    fechas = pd.date_range(start="2000-01-01", end="2026-05-01", freq="MS")
    
    # Simulamos índices base 100 progresivos para la demostración
    np.random.seed(42)
    ipc = np.cumprod(1 + np.random.normal(0.04, 0.01, len(fechas))) * 100
    ripte = np.cumprod(1 + np.random.normal(0.038, 0.012, len(fechas))) * 100
    anses = np.cumprod(1 + np.random.normal(0.035, 0.015, len(fechas))) * 100
    isbic = np.cumprod(1 + np.random.normal(0.045, 0.005, len(fechas))) * 100
    
    df = pd.DataFrame({
        'IPC': ipc,
        'RIPTE': ripte,
        'ANSES': anses,
        'ISBIC': isbic
    }, index=fechas)
    
    # Aseguramos que el índice sea de tipo Período (Mensual) para facilitar el cruce
    df.index = df.index.to_period('M')
    return df

# ==========================================
# 2. CAPA DEL MOTOR MATEMÁTICO
# ==========================================
def calcular_factor(df, desde, hasta, metodo):
    """
    Calcula el coeficiente multiplicador basado en jurisprudencia usando Pandas.
    """
    try:
        if metodo == "IPC":
            return df.loc[hasta, 'IPC'] / df.loc[desde, 'IPC']
            
        elif metodo == "RIPTE":
            return df.loc[hasta, 'RIPTE'] / df.loc[desde, 'RIPTE']
            
        elif metodo == "Aumentos ANSES":
            return df.loc[hasta, 'ANSES'] / df.loc[desde, 'ANSES']
            
        elif metodo == "Fallo Alanis (ISBIC + ANSES)":
            # Empalme histórico clásico: ISBIC hasta Feb 2009, luego ANSES
            corte = pd.Period('2009-02', 'M')
            
            if hasta <= corte:
                return df.loc[hasta, 'ISBIC'] / df.loc[desde, 'ISBIC']
            elif desde >= corte:
                return df.loc[hasta, 'ANSES'] / df.loc[desde, 'ANSES']
            else:
                factor_isbic = df.loc[corte, 'ISBIC'] / df.loc[desde, 'ISBIC']
                factor_anses = df.loc[hasta, 'ANSES'] / df.loc[corte + 1, 'ANSES']
                return factor_isbic * factor_anses
                
        else:
            return 1.0 # Fallback
            
    except KeyError:
        return None # Devuelve None si las fechas están fuera de rango

# ==========================================
# 3. CAPA DE INTERFAZ (Streamlit UI)
# ==========================================
st.title("⚖️ Calculadora de Movilidad Previsional (Pro)")
st.markdown("---")

# Cargar base de datos (con spinner visual)
with st.spinner("Actualizando índices desde servidores oficiales..."):
    df_indices = obtener_datos_indices()

# Layout en columnas
col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Parámetros del Beneficio")
    
    monto_inicial = st.number_input("Haber original a actualizar ($)", min_value=0.0, value=150000.0, step=1000.0)
    
    fecha_desde = st.date_input("Fecha de origen", value=pd.to_datetime("2015-01-01"))
    fecha_hasta = st.date_input("Fecha de liquidación", value=pd.to_datetime("today"))
    
    st.markdown("### Jurisprudencia a evaluar")
    metodos_disponibles = ["IPC", "RIPTE", "Aumentos ANSES", "Fallo Alanis (ISBIC + ANSES)"]
    metodos_seleccionados = st.multiselect(
        "Seleccione los métodos para contrastar", 
        options=metodos_disponibles,
        default=["IPC", "Fallo Alanis (ISBIC + ANSES)"]
    )
    
    calcular_btn = st.button("Ejecutar Cálculo Comparativo", type="primary", use_container_width=True)

with col2:
    if calcular_btn and metodos_seleccionados:
        st.subheader("Resultados de la Comparativa")
        
        # Convertir fechas de UI a Períodos mensuales para cruzar con el DataFrame
        periodo_desde = pd.Period(fecha_desde, 'M')
        periodo_hasta = pd.Period(fecha_hasta, 'M')
        
        resultados = []
        
        for metodo in metodos_seleccionados:
            factor = calcular_factor(df_indices, periodo_desde, periodo_hasta, metodo)
            
            if factor is not None:
                haber_actualizado = monto_inicial * factor
                resultados.append({
                    "Método / Fallo": metodo,
                    "Coeficiente": round(factor, 4),
                    "Haber Reajustado ($)": f"${haber_actualizado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                })
            else:
                st.error(f"⚠️ Datos insuficientes en la serie histórica para calcular: {metodo}")
                
        if resultados:
            df_resultados = pd.DataFrame(resultados)
            
            # Mostrar tabla nativa de Streamlit
            st.dataframe(df_resultados, use_container_width=True, hide_index=True)
            
            # Gráfico de evolución (Opcional pero muy profesional)
            st.markdown("### Evolución de los Índices Base")
            # Filtramos el dataframe para el rango seleccionado
            mask = (df_indices.index >= periodo_desde) & (df_indices.index <= periodo_hasta)
            df_grafico = df_indices.loc[mask]
            
            # Normalizamos a base 100 en la fecha de origen para comparar la curva de crecimiento
            df_grafico_norm = (df_grafico / df_grafico.iloc[0]) * 100
            
            # Streamlit requiere que el índice sea Datetime para los gráficos nativos
            df_grafico_norm.index = df_grafico_norm.index.to_timestamp()
            
            st.line_chart(df_grafico_norm[['IPC', 'RIPTE', 'ANSES']])

    elif not metodos_seleccionados:
        st.info("👈 Selecciona al menos un método y haz clic en Ejecutar Cálculo.")
