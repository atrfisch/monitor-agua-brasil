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
            menor_distancia =
