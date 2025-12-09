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
# Adicionei coordenadas reais para permitir o cálculo de distância
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
# Útil para capitais onde a proximidade geográfica simples pode enganar
MAPEAMENTO_CIDADES = {
    "sao paulo": "Cantareira (SP)",
    "brasília": "Descoberto (DF)",
    "brasilia": "Descoberto (DF)",
    "recife": "Itaparica (PE/BA)", # Simplificação para exemplo
    "fortaleza": "Castanhão (CE)",
    "belo horizonte": "Furnas (MG)", # Simplificação
}

# --- FUNÇÕES DE BACKEND ---

# --- SUBSTIRUA A FUNÇÃO pegar_nivel_ana POR ESTA ---

@st.cache_data(ttl=3600)
def pegar_nivel_ana(codigo_ana):
    """Consulta a API da ANA para um reservatório específico"""
    hoje = datetime.now()
    
    # CORREÇÃO 1: Aumentamos a busca para 45 dias atrás
    # Motivo: Muitos reservatórios ficam semanas sem atualizar no sistema oficial
    inicio = hoje - timedelta(days=45)
    
    url = f"http://sarws.ana.gov.br/SarService.asmx/DadosHistoricos?boletim=sin&reservatorio={codigo_ana}&dataInicial={inicio.strftime('%d/%m/%Y')}&dataFinal={hoje.strftime('%d/%m/%Y')}"
    
    try:
        # CORREÇÃO 2: Fingimos ser um navegador para evitar bloqueios
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, timeout=10, headers=headers)
        
        # Parse do XML
        root = ET.fromstring(response.content)
        registros = root.findall("./Reservatorio")
        
        # CORREÇÃO 3: Busca reversa inteligente
        # Em vez de pegar só o último, varremos do mais recente para o mais antigo
        # até achar um que tenha o campo "VolumePercentual" preenchido.
        if registros:
            for registro in reversed(registros):
                try:
                    texto_volume = registro.find("VolumePercentual").text
                    if texto_volume: # Se não for vazio
                        return float(texto_volume.replace(",", "."))
                except:
                    continue # Tenta o dia anterior
                    
    except Exception as e:
        print(f"Erro de conexão ou parse: {e}")
        return None
        
    return None

# --- INTERFACE VISUAL ---

st.title("🚰 De onde vem sua água?")
st.markdown("Descubra a situação do reservatório que (provavelmente) abastece sua região.")

# Entrada do usuário
col1, col2 = st.columns([3, 1])
with col1:
    cidade_input = st.text_input("Digite o nome da sua cidade:", placeholder="Ex: Campinas, Sobradinho, Curitiba...")
with col2:
    st.write("") 
    st.write("")
    buscar_btn = st.button("🔍 Buscar", type="primary")

if buscar_btn and cidade_input:
    with st.spinner(f"Localizando {cidade_input} no mapa..."):
        
        # 1. Tenta achar Lat/Lon da cidade
        lat, lon, endereco_completo = buscar_cidade(cidade_input)
        
        if lat:
            st.success(f"📍 Localizado: **{endereco_completo}**")
            
            # 2. Lógica de decisão: Manual ou Proximidade?
            res_selecionado = None
            metodo = ""
            
            cidade_lower = cidade_input.lower()
            
            # Verifica se está no nosso dicionário manual
            if cidade_lower in MAPEAMENTO_CIDADES:
                nome_res_manual = MAPEAMENTO_CIDADES[cidade_lower]
                # Busca o objeto completo na lista
                res_selecionado = next((r for r in RESERVATORIOS if r["nome"] == nome_res_manual), None)
                metodo = "Mapeamento Direto"
                distancia = 0 # Irrelevante neste caso
            
            # Se não, vai pela distância
            if not res_selecionado:
                res_selecionado, distancia = encontrar_reservatorio_proximo(lat, lon)
                metodo = "Geolocalização (Mais Próximo)"

            # 3. Exibe os resultados
            if res_selecionado:
                nivel = pegar_nivel_ana(res_selecionado['id'])
                
                st.markdown("---")
                
                # Layout de colunas para o resultado
                col_res, col_graf = st.columns(2)
                
                with col_res:
                    st.subheader("Reservatório de Referência")
                    st.info(f"🌊 **{res_selecionado['nome']}**")
                    if metodo == "Geolocalização (Mais Próximo)":
                        st.caption(f"Este é o reservatório monitorado mais próximo da sua cidade (aprox. {distancia:.0f}km).")
                    
                    if nivel is not None:
                        # Define cor e texto do status
                        cor_status = "green" if nivel > 60 else "orange" if nivel > 30 else "red"
                        texto_status = "Normal" if nivel > 60 else "Atenção" if nivel > 30 else "Crítico"
                        
                        st.metric(label="Nível Atual", value=f"{nivel:.2f}%")
                        st.markdown(f"Status: **:{cor_status}[{texto_status}]**")
                    else:
                        st.warning("Dados temporariamente indisponíveis na ANA para este reservatório.")

                with col_graf:
                    # Mapa mostrando a cidade e o reservatório
                    if nivel is not None:
                        dados_mapa = pd.DataFrame([
                            {"lat": lat, "lon": lon, "nome": "Sua Cidade", "tipo": "Cidade", "tamanho": 5},
                            {"lat": res_selecionado['lat'], "lon": res_selecionado['lon'], "nome": res_selecionado['nome'], "tipo": "Reservatório", "tamanho": 15}
                        ])
                        
                        fig = px.scatter_mapbox(
                            dados_mapa, lat="lat", lon="lon", hover_name="nome", color="tipo",
                            size="tamanho", zoom=5, mapbox_style="open-street-map",
                            color_discrete_map={"Cidade": "blue", "Reservatório": "red"}
                        )
                        fig.update_layout(margin={"r":0,"t":0,"l":0,"b":0}, height=250)
                        st.plotly_chart(fig, use_container_width=True)

            else:
                st.error("Não encontramos reservatórios monitorados próximos o suficiente.")
        else:
            st.error("Cidade não encontrada. Tente digitar 'Cidade, Estado' (ex: Valinhos, SP).")

st.markdown("---")
with st.expander("ℹ️ Como funciona essa busca?"):
    st.write("""
    1. O sistema localiza as coordenadas da sua cidade.
    2. Calculamos a distância entre sua cidade e os principais reservatórios do Sistema Interligado Nacional (SIN) monitorados pela ANA.
    3. Mostramos o reservatório mais próximo como referência de disponibilidade hídrica regional.
    *Nota: Algumas cidades pequenas usam poços artesianos ou rios locais não listados aqui.*
    """)
