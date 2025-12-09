import streamlit as st
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pandas as pd
import plotly.express as px
from geopy.geocoders import Nominatim
from geopy.distance import geodesic

# Configuração da Página
st.set_page_config(page_title="Qual é meu Reservatório?", page_icon="🚰", layout="wide")

# --- 1. DADOS DOS RESERVATÓRIOS (Base Ampliada) ---
RESERVATORIOS = [
    {"nome": "Cantareira (SP)", "id": "12456", "lat": -23.15, "lon": -46.38, "estado": "SP"},
    {"nome": "Billings (SP)", "id": "12450", "lat": -23.78, "lon": -46.63, "estado": "SP"},
    {"nome": "Guarapiranga (SP)", "id": "12448", "lat": -23.68, "lon": -46.73, "estado": "SP"},
    {"nome": "Furnas (MG)", "id": "12423", "lat": -20.67, "lon": -46.30, "estado": "MG"},
    {"nome": "Sobradinho (BA/PE)", "id": "12415", "lat": -9.43, "lon": -40.83, "estado": "BA"},
    {"nome": "Tucuruí (PA)", "id": "12406", "lat": -3.83, "lon": -49.64, "estado": "PA"},
    {"nome": "Itaipu (PR)", "id": "12389", "lat": -25.41, "lon": -54.59, "estado": "PR"},
    {"nome": "Descoberto (DF)", "id": "12458", "lat": -15.80, "lon": -48.17, "estado": "DF"},
    {"nome": "Santa Maria (DF)", "id": "12457", "lat": -15.65, "lon": -48.01, "estado": "DF"},
    {"nome": "Três Marias (MG)", "id": "12411", "lat": -18.21, "lon": -45.26, "estado": "MG"},
    {"nome": "Serra da Mesa (GO)", "id": "12409", "lat": -13.83, "lon": -48.33, "estado": "GO"},
    {"nome": "Xingó (SE/AL)", "id": "12417", "lat": -9.63, "lon": -37.79, "estado": "SE"},
    {"nome": "Castanhão (CE)", "id": "12368", "lat": -5.50, "lon": -38.47, "estado": "CE"},
    {"nome": "Itaparica (PE/BA)", "id": "12416", "lat": -9.13, "lon": -38.30, "estado": "PE"},
]

# --- 2. MAPEAMENTO MANUAL (Cidades -> Reservatório Principal) ---
MAPEAMENTO_CIDADES = {
    "sao paulo": "Cantareira (SP)",
    "brasília": "Descoberto (DF)",
    "brasilia": "Descoberto (DF)",
    "recife": "Itaparica (PE/BA)",
    "fortaleza": "Castanhão (CE)",
    "belo horizonte": "Furnas (MG)",
    "curitiba": "Itaipu (PR)", # Simplificação
}

# --- FUNÇÕES DE BACKEND (CORRIGIDAS) ---

@st.cache_data(ttl=3600)
def pegar_nivel_ana(codigo_ana):
    """Consulta a API da ANA de forma robusta (olhando 45 dias para trás)"""
    hoje = datetime.now()
    inicio = hoje - timedelta(days=45) # CORREÇÃO: Busca mais longa
    
    url = f"http://sarws.ana.gov.br/SarService.asmx/DadosHistoricos?boletim=sin&reservatorio={codigo_ana}&dataInicial={inicio.strftime('%d/%m/%Y')}&dataFinal={hoje.strftime('%d/%m/%Y')}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, timeout=10, headers=headers) # CORREÇÃO: Headers adicionados
        root = ET.fromstring(response.content)
        registros = root.findall("./Reservatorio")
        
        # CORREÇÃO: Loop reverso para achar o último dado NÃO VAZIO
        if registros:
            for registro in reversed(registros):
                try:
                    texto_volume = registro.find("VolumePercentual").text
                    if texto_volume:
                        return float(texto_volume.replace(",", "."))
                except:
                    continue
    except Exception as e:
        return None
    return None

def encontrar_reservatorio_proximo(lat_cidade, lon_cidade):
    """Calcula a distância geodésica e retorna o reservatório mais perto"""
    menor_distancia = float('inf')
    reservatorio_perto = None
    
    for res in RESERVATORIOS:
        coords_res = (res['lat'], res['lon'])
        coords_cidade = (lat_cidade, lon_cidade)
        dist = geodesic(coords_cidade, coords_res).km
        
        if dist < menor_distancia:
            menor_distancia = dist
            reservatorio_perto = res
            
    return reservatorio_perto, menor_distancia

def buscar_cidade(nome_cidade):
    geolocator = Nominatim(user_agent="app_caixa_dagua_brasil_v2")
    try:
        location = geolocator.geocode(f"{nome_cidade}, Brazil")
        if location:
            return location.latitude, location.longitude, location.address
    except:
        return None, None, None
    return None, None, None

@st.cache_data(ttl=3600)
def carregar_dados_mapa():
    """Carrega dados para o mapa geral"""
    hoje = datetime.now()
    inicio = hoje - timedelta(days=30)
    data_final = hoje.strftime("%d/%m/%Y")
    data_inicial = inicio.strftime("%d/%m/%Y")
    
    dados_processados = []
    headers = {"User-Agent": "Mozilla/5.0"} # Header simples

    for res in RESERVATORIOS:
        url = f"http://sarws.ana.gov.br/SarService.asmx/DadosHistoricos?boletim=sin&reservatorio={res['id']}&dataInicial={data_inicial}&dataFinal={data_final}"
        try:
            response = requests.get(url, timeout=5, headers=headers)
            root = ET.fromstring(response.content)
            registros = root.findall("./Reservatorio")
            
            # Pega o último válido
            if registros:
                for registro in reversed(registros):
                    try:
                        vol_texto = registro.find("VolumePercentual").text
                        if vol_texto:
                            vol = float(vol_texto.replace(",", "."))
                            
                            risco = "Normal"
                            if vol < 40: risco = "Atenção"
                            if vol < 20: risco = "Crítico"
                            
                            dados_processados.append({
                                "Nome": res['nome'],
                                "Estado": res['estado'],
                                "Volume (%)": vol,
                                "Latitude": res['lat'],
                                "Longitude": res['lon'],
                                "Situação": risco
                            })
                            break # Achou o último válido, para o loop deste reservatório
                    except:
                        continue
        except:
            pass
            
    return pd.DataFrame(dados_processados)

# --- INTERFACE VISUAL ---

st.title("🚰 De onde vem sua água?")
st.markdown("Descubra a situação do reservatório que (provavelmente) abastece sua região.")

# Abas para separar a busca do mapa geral
tab1, tab2 = st.tabs(["🔍 Buscar Minha Cidade", "🗺️ Mapa do Brasil"])

with tab1:
    # Entrada do usuário
    col1, col2 = st.columns([3, 1])
    with col1:
        cidade_input = st.text_input("Digite o nome da sua cidade:", placeholder="Ex: Campinas, Sobradinho, Curitiba...")
    with col2:
        st.write("") 
        st.write("")
        buscar_btn = st.button("Buscar", type="primary")

    if buscar_btn and cidade_input:
        with st.spinner(f"Localizando {cidade_input} e consultando satélites..."):
            
            # 1. Tenta achar Lat/Lon da cidade
            lat, lon, endereco_completo = buscar_cidade(cidade_input)
            
            if lat:
                st.success(f"📍 Localizado: **{endereco_completo}**")
                
                # 2. Lógica de decisão
                res_selecionado = None
                metodo = ""
                
                cidade_lower = cidade_input.lower()
                
                if cidade_lower in MAPEAMENTO_CIDADES:
                    nome_res_manual = MAPEAMENTO_CIDADES[cidade_lower]
                    res_selecionado = next((r for r in RESERVATORIOS if r["nome"] == nome_res_manual), None)
                    metodo = "Mapeamento Direto"
                    distancia = 0
                
                if not res_selecionado:
                    res_selecionado, distancia = encontrar_reservatorio_proximo(lat, lon)
                    metodo = "Geolocalização"

                # 3. Exibe os resultados
                if res_selecionado:
                    nivel = pegar_nivel_ana(res_selecionado['id'])
                    
                    st.markdown("---")
                    col_res, col_graf = st.columns(2)
                    
                    with col_res:
                        st.subheader("Reservatório de Referência")
                        st.info(f"🌊 **{res_selecionado['nome']}**")
                        
                        if metodo == "Geolocalização":
                            st.caption(f"Reservatório monitorado mais próximo (aprox. {distancia:.0f}km).")
                        
                        if nivel is not None:
                            cor_status = "green" if nivel > 60 else "orange" if nivel > 30 else "red"
                            texto_status = "Confortável" if nivel > 60 else "Alerta" if nivel > 30 else "Crítico"
                            
                            st.metric(label="Nível Atual", value=f"{nivel:.1f}%")
                            st.markdown(f"Status: **:{cor_status}[{texto_status}]**")
                            
                            # Barra de progresso visual
                            st.progress(min(nivel/100, 1.0))
                        else:
                            st.warning("⚠️ Dados indisponíveis na ANA hoje. O reservatório pode estar sem medição recente.")

                    with col_graf:
                        if nivel is not None:
                            dados_mapa = pd.DataFrame([
                                {"lat": lat, "lon": lon, "nome": "Você", "tipo": "Cidade", "tamanho": 5},
                                {"lat": res_selecionado['lat'], "lon": res_selecionado['lon'], "nome": res_selecionado['nome'], "tipo": "Reservatório", "tamanho": 15}
                            ])
                            
                            fig = px.scatter_mapbox(
                                dados_mapa, lat="lat", lon="lon", hover_name="nome", color="tipo",
                                size="tamanho", zoom=5, mapbox_style="open-street-map",
                                color_discrete_map={"Cidade": "blue", "Reservatório": "red"}
                            )
                            fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=300)
                            st.plotly_chart(fig, use_container_width=True)

                else:
                    st.error("Erro interno ao buscar reservatório.")
            else:
                st.error("Cidade não encontrada. Tente digitar 'Cidade, Estado'.")

with tab2:
    st.subheader("Visão Geral dos Principais Reservatórios")
    df_mapa = carregar_dados_mapa()
    
    if not df_mapa.empty:
        color_map = {"Normal": "blue", "Atenção": "orange", "Crítico": "red"}
        fig_geral = px.scatter_mapbox(
            df_mapa, lat="Latitude", lon="Longitude", color="Situação",
            size="Volume (%)", size_max=25, hover_name="Nome",
            hover_data={"Volume (%)": True, "Estado": True, "Latitude": False, "Longitude": False},
            color_discrete_map=color_map, zoom=3, center={"lat": -15.7, "lon": -47.8},
            mapbox_style="open-street-map", height=600
        )
        st.plotly_chart(fig_geral, use_container_width=True)
    else:
        st.warning("Carregando dados do mapa... Se demorar, a API da ANA pode estar instável.")

st.markdown("---")
with st.expander("ℹ️ Sobre os dados"):
    st.write("""
    **Fonte:** Agência Nacional de Águas (ANA) - API do Sistema SAR.
    **Nota:** Este app busca o reservatório do Sistema Interligado Nacional (SIN) mais próximo da sua localização. 
    Pequenas cidades podem ser abastecidas por rios locais ou poços não listados aqui, mas o dado serve como indicador regional de seca.
    """)
