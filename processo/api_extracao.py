import pdfplumber
import re
import pandas as pd
import csv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from io import BytesIO, StringIO

app = FastAPI(title="API Extrator de Débitos")

# Configuração de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ExtratorProcessos:
    def __init__(self):
        # --- REGEX PATTERNS ---
        # Atualizado para aceitar ponto OU vírgula como separador decimal (ex: 32.77 ou 32,77)
        self.re_money_flexible = re.compile(r'(?:R\$\s*)?[\d.]*\d+[.,]\d{2}\b', re.IGNORECASE)
        
        # Datas e Competências
        self.re_date = re.compile(r'\b\d{2}/\d{2}/\d{4}\b')
        self.re_year = re.compile(r'\b(19|20)\d{2}(?:/\d{1,2})?\b')

    def processar_pdf(self, file_bytes):
        todos_dados = []
        try:
            with pdfplumber.open(BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    text = page.extract_text(x_tolerance=2, y_tolerance=2)
                    if not text: continue
                        
                    lines = text.split('\n')
                    for line in lines:
                        # Tenta processar
                        dados = self._processar_linha(line)
                        if dados:
                            todos_dados.append(dados)
            return todos_dados
        except Exception as e:
            print(f"Erro Interno: {e}")
            return []

    def _processar_linha(self, line):
        line = line.strip()
        if not line: return None

        # ESTRATÉGIA 1: Tentar ler como CSV Estruturado
        # O modelo espera aspas e vírgulas delimitando os campos
        if '"' in line and ',' in line:
            try:
                reader = csv.reader(StringIO(line))
                row = next(reader)
                
                # A nova estrutura tem 23 colunas. 
                # Aceitamos se tiver pelo menos 20 para ser tolerante com alguma coluna vazia no final
                if len(row) >= 18: 
                    return self._mapear_colunas_csv(row)
            except Exception:
                pass 

        # ESTRATÉGIA 2: Fallback Regex (se não conseguir parsear como CSV)
        return self._processar_linha_regex(line)

    def _mapear_colunas_csv(self, row):
        """
        Mapeia as colunas baseadas na ordem estrita fornecida:
        0: #(IDENTIFICADOR)
        1: NATUREZA
        2: ORIGEM
        3: I.C REDUZIDO
        4: I.C
        5: COMP.(ANOS)
        6: VENC.
        7: PRINCIPAL REF.
        8: PRINCIPAL
        9: DESC/ABATI.
        10: PRINCIPAL(PAGO)
        11: PRINCIPAL(SALDO)
        12: MULTA
        13: JUROS
        14: CORREÇÃO
        15: HONORÁRIOS
        16: DILIGÊNCIAS
        17: SALDO(ATUALIZADO) -> vTotal
        18: SIT. LANC.
        19: SIT. DIVIDA
        20: N° PROCESSO FÓRUM
        21: N° PROCESSO DA
        22: CDA
        """
        try:
            # Helper para limpar valores monetários
            def clean_money(val):
                if not val: return '0,00'
                val = str(val).strip()
                # Se for formato americano 32.77, vira 32,77. 
                if '.' in val and ',' not in val: 
                    return val.replace('.', ',')
                return val

            # Helper para pegar índice seguro
            def get_col(idx):
                if idx < len(row):
                    return row[idx].strip()
                return ""

            return {
                'id': get_col(0),           # #(IDENTIFICADOR)
                'nat': get_col(1),          # NATUREZA
                'orig': get_col(2),         # ORIGEM
                'icRed': get_col(3),        # I.C REDUZIDO
                'ic': get_col(4),           # I.C
                'comp': get_col(5),         # COMP.(ANOS)
                'venc': get_col(6),         # VENC.
                'vPrincRef': clean_money(get_col(7)),   # PRINCIPAL REF.
                'vPrinc': clean_money(get_col(8)),      # PRINCIPAL
                'vDesc': clean_money(get_col(9)),       # DESC/ABATI.
                'vPago': clean_money(get_col(10)),      # PRINCIPAL(PAGO)
                'vSaldoP': clean_money(get_col(11)),    # PRINCIPAL(SALDO)
                'vMulta': clean_money(get_col(12)),     # MULTA
                'vJuros': clean_money(get_col(13)),     # JUROS
                'vCorr': clean_money(get_col(14)),      # CORREÇÃO
                'vHon': clean_money(get_col(15)),       # HONORÁRIOS
                'vDilig': clean_money(get_col(16)),     # DILIGÊNCIAS
                'vTotal': clean_money(get_col(17)),     # SALDO(ATUALIZADO)
                'sitLanc': get_col(18),     # SIT. LANC.
                'sitDiv': get_col(19),      # SIT. DIVIDA
                'procF': get_col(20),       # N° PROCESSO FÓRUM
                'procD': get_col(21),       # N° PROCESSO DA
                'cda': get_col(22)          # CDA
            }
        except Exception as e:
            print(f"Erro parse CSV: {e}")
            return None

    def _processar_linha_regex(self, line):
        """Fallback para linhas que não seguem o padrão CSV exato"""
        line_clean = line.replace('"', ' ').replace("'", " ")

        valores = [v.replace('R$', '').strip() for v in self.re_money_flexible.findall(line_clean)]
        if not valores: return None

        # Padroniza valores
        valores = [v.replace('.', ',') if '.' in v and ',' not in v else v for v in valores]

        # Extração básica de datas
        comp_match = self.re_year.search(line_clean)
        venc_match = self.re_date.search(line_clean)
        
        comp = comp_match.group(0) if comp_match else ""
        venc = venc_match.group(0) if venc_match else ""

        # Preenche zeros se faltar (assume 11 valores monetários padrão)
        vals = valores + ['0,00'] * (11 - len(valores))

        # Tenta pegar ID se for o primeiro token
        tokens = line_clean.split()
        id_val = tokens[0] if tokens and tokens[0].isdigit() else 'REGEX'

        return {
            'id': id_val,
            'nat': 'VERIF',
            'orig': line_clean[:20] + '...',
            'icRed': '',
            'ic': '',
            'comp': comp,
            'venc': venc,
            'vPrincRef': vals[0] if len(vals) > 0 else '0,00',
            'vPrinc': vals[1] if len(vals) > 1 else '0,00',
            'vDesc': vals[2] if len(vals) > 2 else '0,00',
            'vPago': vals[3] if len(vals) > 3 else '0,00',
            'vSaldoP': vals[4] if len(vals) > 4 else '0,00',
            'vMulta': vals[5] if len(vals) > 5 else '0,00',
            'vJuros': vals[6] if len(vals) > 6 else '0,00',
            'vCorr': vals[7] if len(vals) > 7 else '0,00',
            'vHon': vals[8] if len(vals) > 8 else '0,00',
            'vDilig': vals[9] if len(vals) > 9 else '0,00',
            'vTotal': vals[-1] if vals else '0,00',
            'sitLanc': 'VERIF',
            'sitDiv': 'VERIF',
            'procF': '',
            'procD': '',
            'cda': ''
        }

extrator = ExtratorProcessos()

@app.get("/")
def read_root():
    return {"status": "online", "message": "API de Extração Kyro rodando"}

@app.post("/extract")
async def extract_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Arquivo deve ser PDF")
    
    content = await file.read()
    dados = extrator.processar_pdf(content)
    
    return {
        "filename": file.filename,
        "data": dados,
        "count": len(dados)
    }