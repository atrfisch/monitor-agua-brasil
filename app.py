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

# --- 1. DADOS DOS RESERVATÓRIOS (BASE EXPANDIDA: NE + CANTAREIRA) ---
RESERVATORIOS = [
    # --- SUDESTE (Foco SP/MG) ---
    {"nome": "Sistema Cantareira (SP)", "id": "12456", "lat": -23.15, "lon": -46.38, "estado": "SP"},
    {"nome": "Sistema Alto Tietê (SP)", "id": "12454", "lat": -23.51, "lon": -46.25, "estado": "SP"},
    {"nome": "Billings (SP)", "id": "12450", "lat": -23.78, "lon": -46.63, "estado": "SP"},
    {"nome": "Guarapiranga (SP)", "id": "12448", "lat": -23.68, "lon": -46.73, "estado": "SP"},
    {"nome": "Furnas (MG)", "id": "12423", "lat": -20.67, "lon": -46.30, "estado": "MG"},
    {"nome": "Três Marias (MG)", "id": "12411", "lat": -18.21, "lon": -45.26, "estado": "MG"},
    
    # --- CENTRO-OESTE ---
    {"nome": "Descoberto (DF)", "id": "12458", "lat": -15.80, "lon": -48.17, "estado": "DF"},
    {"nome": "Santa Maria (DF)", "id": "12457", "lat": -15.65, "lon": -48.01, "estado": "DF"},
    {"nome": "Serra da Mesa (GO)", "id": "12409", "lat": -13.83, "lon": -48.33, "estado": "GO"},

    # --- SUL ---
    {"nome": "Itaipu (PR)", "id": "12389", "lat": -25.41, "lon": -54.59, "estado": "PR"},
    {"nome": "Passo Real (RS)", "id": "12328", "lat": -29.03, "lon": -53.20, "estado": "RS"},

    # --- NORDESTE E SEMIÁRIDO (CRÍTICOS) ---
    {"nome": "Sobradinho (BA/PE)", "id": "12415", "lat": -9.43, "lon": -40.83, "estado": "BA"},
    {"nome": "Itaparica (Luiz Gonzaga) (PE)", "id": "12416", "lat": -9.13, "lon": -38.30, "estado": "PE"},
    {"nome": "Castanhão (CE)", "id": "12368", "lat": -5.50, "lon": -38.47, "estado": "CE"},
    {"nome": "Orós (CE)", "id": "12374", "lat": -6.24, "lon": -38.91, "estado": "CE"},
    {"nome": "Banabuiú (CE)", "id": "12356", "lat": -5.31, "lon": -38.92, "estado": "CE"},
    {"nome": "Armando Ribeiro Gonçalves (RN)", "id": "12347", "lat": -5.67, "lon": -36.88, "estado": "RN"},
    {"nome": "Epitácio Pessoa (Boqueirão) (PB)", "id": "12306", "lat": -7.49, "lon": -36.13, "estado": "PB"},
    {"nome": "Xingó (SE/AL)", "id": "12417", "lat": -9.63, "lon": -37.79, "estado": "SE"},
    
    # --- NORTE ---
    {"nome": "Tucuruí (PA)", "id": "12406", "lat": -3.83, "lon": -49.64, "estado": "PA"},
    {"nome": "Belo Monte (PA)", "id": "12516", "lat": -3.11, "lon": -51.78, "estado": "PA"},
]

# --- 2. MAPEAMENTO MANUAL (Adicionado capitais e cidades chave do NE) ---
MAPEAMENTO_CIDADES = {
    # Sudeste
    "sao paulo": "Sistema Cantareira (SP)",
    "rio de janeiro": "Furnas (MG)", # Paraíba do Sul depende da regulação de montante
    "belo horizonte": "Três Marias (MG)", # Ref regional
    
    # Centro-Oeste
    "brasília": "Descoberto (DF)",
    "brasilia": "Descoberto (DF)",
    
    # Nordeste
    "recife": "Itaparica (Luiz Gonzaga) (PE)", 
    "fortaleza": "Castanhão (CE)",
    "natal": "Armando Ribeiro Gonçalves (RN)",
    "joao pessoa": "Epitácio Pessoa (Boqueirão) (PB)", # Abastecimento misto, mas Boqueirão é o termômetro do estado
    "campina grande": "Epitácio Pessoa (Boqueirão) (PB)",
    "juazeiro do norte": "Orós (CE)",
    "mossoro": "Armando Ribeiro Gonçalves (RN)",
    "sobral": "Araras (CE)", # Araras ID 12351 (adicionando lógica de fallback se não estiver na lista princ)
    
    # Sul
    "curitiba": "Itaipu (PR)",
    "porto alegre": "Passo Real (RS)",
}

# --- FUNÇÕES DE BACKEND (Busca Profunda 365 dias) ---

@st.cache_data(ttl=3600)
def pegar_nivel_ana(codigo_ana):
    hoje = datetime.now()
    # Busca 1 ano para trás (essencial para o Semiárido onde a medição pode falhar)
    inicio = hoje - timedelta(days=365)
    
    url = f"http://sarws.ana.gov.br/SarService.asmx/DadosHistoricos?boletim=sin&reservatorio={codigo_ana}&dataInicial={inicio.strftime('%d/%m/%Y')}&dataFinal={hoje.strftime('%d/%m/%Y')}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        response = requests.get(url, timeout=15, headers=headers)
        root = ET.fromstring(response.content)
        registros = root.findall("./Reservatorio")
        
        if registros:
            for registro in reversed(registros):
                try:
                    texto_volume = registro.find("VolumePercentual").text
                    data_medicao = registro.find("DataInformacao").text
                    
                    if texto_volume and data_medicao:
                        return {
                            "volume": float(texto_volume.replace(",", ".")),
                            "data": data_medicao
                        }
                except:
                    continue
    except Exception as e:
        return None
    return None

def encontrar_reservatorio_proximo(lat_cidade, lon_cidade):
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
    geolocator = Nominatim(user_agent="app_monitor_aguas_br_v4")
    try:
        location = geolocator.geocode(f"{nome_cidade}, Brazil")
        if location:
            return location.latitude, location.longitude, location.address
    except:
        return None, None, None
    return None, None, None

@st.cache_data(ttl=3600)
def carregar_dados_mapa():
    hoje = datetime.now()
    inicio = hoje - timedelta(days=90) # 90 dias para o mapa
    data_final = hoje.strftime("%d/%m/%Y")
    data_inicial = inicio.strftime("%d/%m/%Y")
    
    dados_processados = []
    headers = {"User-Agent": "Mozilla/5.0"}

    # Barra de progresso para carregamento inicial
    progresso = st.progress(0)
    total = len(RESERVATORIOS)

    for i, res in enumerate(RESERVATORIOS):
        url = f"http://sarws.ana.gov.br/SarService.asmx/DadosHistoricos?boletim=sin&reservatorio={res['id']}&dataInicial={data_inicial}&dataFinal={data_final}"
        try:
            response = requests.get(url, timeout=5, headers=headers)
            root = ET.fromstring(response.content)
            registros = root.findall("./Reservatorio")
            
            if registros:
                for registro in reversed(registros):
                    try:
                        vol_texto = registro.find("VolumePercentual").text
                        data_texto = registro.find("DataInformacao").text
                        if vol_texto:
                            vol = float(vol_texto.replace(",", "."))
                            
                            risco = "Normal"
                            if vol < 40: risco = "Atenção"
                            if vol < 20: risco = "Crítico"
                            
                            dados_processados.append({
                                "Nome": res['nome'],
                                "Estado": res['estado'],
                                "Volume (%)": vol,
                                "Data": data_texto,
                                "Latitude": res['lat'],
                                "Longitude": res['lon'],
                                "Situação": risco
                            })
                            break
                    except:
                        continue
        except:
            pass
        progresso.progress((i + 1) / total)
        
    progresso.empty()
    return pd.DataFrame(dados_processados)

# --- INTERFACE VISUAL ---

st.title("💧 Monitor de Reservatórios Brasil")
st.markdown("Acompanhe o nível dos principais reservatórios, com foco no **Sistema Cantareira** e no **Semiárido Nordestino**.")

tab1, tab2 = st.tabs(["🔍 Buscar por Cidade", "🗺️ Mapa Nacional"])

with tab1:
    col1, col2 = st.columns([3, 1])
    with col1:
        cidade_input = st.text_input("Digite o nome da sua cidade:", placeholder="Ex: Campina Grande, São Paulo, Sobral...")
    with col2:
        st.write("") 
        st.write("")
        buscar_btn = st.button("Buscar Nível", type="primary")

    if buscar_btn and cidade_input:
        with st.spinner(f"Analisando dados hídricos para {cidade_input}..."):
            
            lat, lon, endereco_completo = buscar_cidade(cidade_input)
            
            if lat:
                st.success(f"📍 Localizado: **{endereco_completo}**")
                
                res_selecionado = None
                metodo = ""
                
                cidade_lower = cidade_input.lower()
                
                # Tenta busca manual primeiro
                if cidade_lower in MAPEAMENTO_CIDADES:
                    nome_res_manual = MAPEAMENTO_CIDADES[cidade_lower]
                    res_selecionado = next((r for r in RESERVATORIOS if r["nome"] == nome_res_manual), None)
                    metodo = "Mapeamento Estratégico"
                    distancia = 0
                
                # Se não achar manual, vai por proximidade
                if not res_selecionado:
                    res_selecionado, distancia = encontrar_reservatorio_proximo(lat, lon)
                    metodo = "Geolocalização (Mais Próximo)"

                if res_selecionado:
                    dados = pegar_nivel_ana(res_selecionado['id'])
                    
                    st.markdown("---")
                    col_res, col_graf = st.columns(2)
                    
                    with col_res:
                        st.subheader("Reservatório de Referência")
                        st.info(f"🌊 **{res_selecionado['nome']}**")
                        
                        if metodo != "Mapeamento Estratégico":
                            st.caption(f"Reservatório monitorado mais próximo (aprox. {distancia:.0f}km).")
                        
                        if dados:
                            nivel = dados['volume']
                            data_medicao = dados['data']
                            
                            cor_status = "green" if nivel > 60 else "orange" if nivel > 30 else "red"
                            texto_status = "Confortável" if nivel > 60 else "Alerta" if nivel > 30 else "Crítico"
                            
                            # Destaque visual
                            st.metric(label="Volume Útil (%)", value=f"{nivel:.2f}%")
                            st.caption(f"📅 Data da medição: **{data_medicao}**")
                            
                            st.markdown(f"**Situação:** :{cor_status}[{texto_status}]")
                            st.progress(min(nivel/100, 1.0))
                            
                            if nivel < 20:
                                st.error("🚨 Atenção: Nível muito baixo! Economize água.")
                            
                        else:
                            st.error("❌ Dados indisponíveis temporariamente na ANA.")
                            st.caption("A estação de telemetria deste reservatório pode estar offline.")

                    with col_graf:
                        if dados:
                            dados_mapa = pd.DataFrame([
                                {"lat": lat, "lon": lon, "nome": "Sua Localização", "tipo": "Cidade", "tamanho": 6},
                                {"lat": res_selecionado['lat'], "lon": res_selecionado['lon'], "nome": res_selecionado['nome'], "tipo": "Reservatório", "tamanho": 18}
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
    st.subheader("Panorama Nacional de Risco Hídrico")
    df_mapa = carregar_dados_mapa()
    
    if not df_mapa.empty:
        # Métricas rápidas no topo do mapa
        col_m1, col_m2, col_m3 = st.columns(3)
        criticos = df_mapa[df_mapa["Volume (%)"] < 20].shape[0]
        col_m1.metric("Reservatórios Monitorados", len(df_mapa))
        col_m2.metric("Nível Crítico (<20%)", criticos, delta_color="inverse")
        col_m3.metric("Média Nacional", f"{df_mapa['Volume (%)'].mean():.1f}%")

        color_map = {"Normal": "blue", "Atenção": "#FFD700", "Crítico": "red"} # Amarelo ouro para atenção
        
        fig_geral = px.scatter_mapbox(
            df_mapa, lat="Latitude", lon="Longitude", color="Situação",
            size="Volume (%)", size_max=25, hover_name="Nome",
            hover_data={"Volume (%)": True, "Data": True, "Estado": True},
            color_discrete_map=color_map, zoom=3.5, center={"lat": -13.5, "lon": -43.0}, # Centro ajustado para pegar NE e SE
            mapbox_style="open-street-map", height=650
        )
        st.plotly_chart(fig_geral, use_container_width=True)
    else:
        st.warning("Carregando dados... Se demorar, recarregue a página.")

st.markdown("---")
with st.expander("ℹ️ Fontes e Notas Técnicas"):
    st.write("""
    * **Fonte de Dados:** Agência Nacional de Águas e Saneamento Básico (ANA) - API SAR-B.
    * **Metodologia:** O sistema busca o dado mais recente disponível nos últimos 365 dias. Reservatórios do semiárido podem ter atualizações menos frequentes que os do Sudeste.
    * **Cobertura:** Focamos nos reservatórios estratégicos do SIN (Sistema Interligado Nacional) e grandes açudes do Nordeste (Castanhão, Armando Ribeiro, Boqueirão, etc).
    """)
