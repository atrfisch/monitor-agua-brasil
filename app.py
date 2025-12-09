import streamlit as st
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

# Configuração da Página
st.set_page_config(page_title="Monitor de Reservatórios Brasil", page_icon="💧", layout="wide")

# --- 1. LISTA MANUAL (Estratégicos para o Mapa Rápido) ---
RESERVATORIOS_ESTRATEGICOS = [
    # Sudeste
    {"nome": "Sistema Cantareira (SP)", "id": "12456", "lat": -23.15, "lon": -46.38, "estado": "SP"},
    {"nome": "Furnas (MG)", "id": "12423", "lat": -20.67, "lon": -46.30, "estado": "MG"},
    {"nome": "Três Marias (MG)", "id": "12411", "lat": -18.21, "lon": -45.26, "estado": "MG"},
    # Nordeste
    {"nome": "Sobradinho (BA)", "id": "12415", "lat": -9.43, "lon": -40.83, "estado": "BA"},
    {"nome": "Castanhão (CE)", "id": "12368", "lat": -5.50, "lon": -38.47, "estado": "CE"},
    {"nome": "Boqueirão (PB)", "id": "12306", "lat": -7.49, "lon": -36.13, "estado": "PB"},
    {"nome": "Armando Ribeiro (RN)", "id": "12347", "lat": -5.67, "lon": -36.88, "estado": "RN"},
    # Norte
    {"nome": "Tucuruí (PA)", "id": "12406", "lat": -3.83, "lon": -49.64, "estado": "PA"},
    # Sul
    {"nome": "Itaipu (PR)", "id": "12389", "lat": -25.41, "lon": -54.59, "estado": "PR"},
    # Centro-Oeste
    {"nome": "Descoberto (DF)", "id": "12458", "lat": -15.80, "lon": -48.17, "estado": "DF"},
]

# --- 2. FUNÇÕES DE BACKEND ---

@st.cache_data(ttl=86400) # Cache de 24h pois a lista de reservatórios muda pouco
def carregar_catalogo_completo():
    """Baixa a lista de TODOS os reservatórios cadastrados na ANA"""
    url = "http://sarws.ana.gov.br/SarService.asmx/ObterReservatorios"
    try:
        response = requests.get(url, timeout=15)
        root = ET.fromstring(response.content)
        lista = []
        for res in root.findall("./Reservatorio"):
            nome = res.find("NomeReservatorio").text
            codigo = res.find("Codigo").text
            municipio = res.find("Municipio").text
            estado = res.find("Estado").text
            
            # Cria um rótulo bonito para busca
            label = f"{nome} - {municipio}/{estado}"
            lista.append({"label": label, "id": codigo, "nome": nome, "uf": estado})
            
        return pd.DataFrame(lista).sort_values("label")
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def pegar_nivel_ana(codigo_ana):
    """Busca Profunda (365 dias) para um ID específico"""
    hoje = datetime.now()
    inicio = hoje - timedelta(days=365)
    
    url = f"http://sarws.ana.gov.br/SarService.asmx/DadosHistoricos?boletim=sin&reservatorio={codigo_ana}&dataInicial={inicio.strftime('%d/%m/%Y')}&dataFinal={hoje.strftime('%d/%m/%Y')}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        response = requests.get(url, timeout=10, headers=headers)
        root = ET.fromstring(response.content)
        registros = root.findall("./Reservatorio")
        
        if registros:
            for registro in reversed(registros):
                try:
                    texto_volume = registro.find("VolumePercentual").text
                    data_medicao = registro.find("DataInformacao").text
                    if texto_volume and data_medicao:
                        return {"volume": float(texto_volume.replace(",", ".")), "data": data_medicao}
                except:
                    continue
    except:
        return None
    return None

def buscar_cidade(nome_cidade):
    geolocator = Nominatim(user_agent="app_monitor_brasil_v5")
    try:
        location = geolocator.geocode(f"{nome_cidade}, Brazil")
        if location:
            return location.latitude, location.longitude, location.address
    except:
        return None, None, None
    return None, None, None

def encontrar_proximo_estrategico(lat_cidade, lon_cidade):
    menor_distancia = float('inf')
    reservatorio_perto = None
    for res in RESERVATORIOS_ESTRATEGICOS:
        dist = geodesic((lat_cidade, lon_cidade), (res['lat'], res['lon'])).km
        if dist < menor_distancia:
            menor_distancia = dist
            reservatorio_perto = res
    return reservatorio_perto, menor_distancia

@st.cache_data(ttl=3600)
def carregar_dados_mapa_estrategico():
    hoje = datetime.now()
    inicio = hoje - timedelta(days=60)
    url_base = "http://sarws.ana.gov.br/SarService.asmx/DadosHistoricos"
    
    dados = []
    headers = {"User-Agent": "Mozilla/5.0"}
    
    # Barra de loading silenciosa
    for res in RESERVATORIOS_ESTRATEGICOS:
        try:
            full_url = f"{url_base}?boletim=sin&reservatorio={res['id']}&dataInicial={inicio.strftime('%d/%m/%Y')}&dataFinal={hoje.strftime('%d/%m/%Y')}"
            response = requests.get(full_url, timeout=4, headers=headers)
            root = ET.fromstring(response.content)
            registros = root.findall("./Reservatorio")
            if registros:
                for reg in reversed(registros):
                    vol = reg.find("VolumePercentual").text
                    if vol:
                        v = float(vol.replace(",", "."))
                        status = "Crítico" if v < 20 else "Atenção" if v < 40 else "Normal"
                        dados.append({
                            "Nome": res['nome'], "Latitude": res['lat'], "Longitude": res['lon'], 
                            "Volume (%)": v, "Situação": status, "Estado": res['estado']
                        })
                        break
        except:
            pass
    return pd.DataFrame(dados)

# --- INTERFACE ---

st.title("💧 Monitor de Reservatórios Brasil")
st.markdown("Monitoramento via API oficial da Agência Nacional de Águas (ANA).")

# Menu de Navegação
tab1, tab2, tab3 = st.tabs(["🔍 Por Cidade (Smart)", "📋 Lista Completa", "🗺️ Mapa Estratégico"])

# --- ABA 1: Busca Inteligente por Cidade ---
with tab1:
    col1, col2 = st.columns([3, 1])
    cidade = col1.text_input("Sua cidade:", placeholder="Ex: Campinas, Sobral...")
    btn_cidade = col2.button("Localizar", type="primary")
    
    if btn_cidade and cidade:
        with st.spinner("Geolocalizando..."):
            lat, lon, address = buscar_cidade(cidade)
            if lat:
                st.success(f"📍 {address}")
                res, dist = encontrar_proximo_estrategico(lat, lon)
                
                st.markdown(f"**Referência Regional:** O grande reservatório estratégico mais próximo é **{res['nome']}** ({dist:.0f}km).")
                
                dados = pegar_nivel_ana(res['id'])
                if dados:
                    st.metric("Volume Atual", f"{dados['volume']:.1f}%")
                    st.caption(f"Data: {dados['data']}")
                    st.progress(min(dados['volume']/100, 1.0))
                else:
                    st.warning("Sem dados recentes.")
            else:
                st.error("Cidade não encontrada.")

# --- ABA 2: Lista Completa (O QUE VOCÊ PEDIU) ---
with tab2:
    st.markdown("### Banco de Dados Completo da ANA")
    st.markdown("Pesquise manualmente qualquer reservatório cadastrado no sistema federal.")
    
    with st.spinner("Baixando catálogo da ANA (pode levar alguns segundos na primeira vez)..."):
        df_catalogo = carregar_catalogo_completo()
    
    if not df_catalogo.empty:
        # Selectbox com Search
        opcao = st.selectbox(
            "Selecione o Reservatório:", 
            df_catalogo["label"].unique(),
            index=None,
            placeholder="Digite o nome (ex: Billings, Coremas, Pedra do Cavalo...)"
        )
        
        if opcao:
            # Pega o ID baseado na escolha
            item = df_catalogo[df_catalogo["label"] == opcao].iloc[0]
            st.divider()
            st.subheader(f"📊 {item['nome']} ({item['uf']})")
            
            with st.spinner(f"Consultando nível de {item['nome']}..."):
                dados_reais = pegar_nivel_ana(item['id'])
                
            if dados_reais:
                col_a, col_b = st.columns(2)
                col_a.metric("Volume Útil", f"{dados_reais['volume']:.2f}%")
                col_a.caption(f"Última medição: {dados_reais['data']}")
                
                # Visualização da caixa
                nivel = dados_reais['volume']
                cor = "#e74c3c" if nivel < 20 else "#f1c40f" if nivel < 40 else "#3498db"
                col_b.markdown(f"""
                <div style="width:100%; background-color:#ddd; border-radius:10px; height:30px;">
                    <div style="width:{min(nivel, 100)}%; background-color:{cor}; height:30px; border-radius:10px; text-align:right; padding-right:10px; color:white; font-weight:bold; line-height:30px;">
                        {nivel:.1f}%
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                if nivel < 15:
                    st.error("🚨 Nível Crítico!")
            else:
                st.warning("⚠️ Este reservatório consta no cadastro, mas a ANA não retornou dados de telemetria no último ano.")
    else:
        st.error("Erro ao baixar catálogo da ANA.")

# --- ABA 3: Mapa Visual ---
with tab3:
    st.caption("Exibindo principais reservatórios estratégicos para performance.")
    df_mapa = carregar_dados_mapa_estrategico()
    if not df_mapa.empty:
        fig = px.scatter_mapbox(
            df_mapa, lat="Latitude", lon="Longitude", color="Situação", size="Volume (%)",
            color_discrete_map={"Normal": "blue", "Atenção": "orange", "Crítico": "red"},
            zoom=3, mapbox_style="open-street-map", hover_name="Nome", height=500
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Carregando mapa...")
