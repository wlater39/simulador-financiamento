import pdfplumber
import json
import re
from datetime import datetime
from typing import Dict, List, Any

def formatar_valor(valor_str: str) -> float:
    """Converte string de valor para float, tratando formato brasileiro de números."""
    try:
        if not valor_str or valor_str.strip() == '':
            return 0.0
            
        # Remove espaços e caracteres não numéricos (exceto ponto e vírgula)
        valor_str = re.sub(r'[^\d.,]', '', valor_str.strip())
        
        if not valor_str:
            return 0.0
            
        # Remove pontos de milhar e substitui vírgula por ponto
        valor_str = valor_str.replace('.', '').replace(',', '.')
        
        return float(valor_str)
        
    except Exception as e:
        print(f"Erro ao converter valor '{valor_str}': {str(e)}")
        return 0.0

def extrair_metadados(texto: str) -> Dict[str, Any]:
    """Extrai os metadados do contrato do texto do PDF."""
    metadados = {}
    
    # Padrões para extração
    padroes = {
        'cliente': r'Cliente:\s*(.*?)(?=\n)',
        'cpf': r'CPF:\s*(\d{3}\.\d{3}\.\d{3}-\d{2})',
        'agencia': r'Agência:\s*(\d+)',
        'conta': r'Conta:\s*(\d+-\d+)',
        'valor_operacao': r'Valor da Operação:\s*R\$\s*([\d.,]+)',
        'taxa_juros_mensal': r'Taxa de Juros Mensal:\s*([\d.,]+)',
        'sistema_amortizacao': r'Sistema de Amortização:\s*(.*?)(?=\n)',
        'data_vencimento_final': r'Data de Vencimento Final:\s*(\d{2}/\d{2}/\d{4})'
    }
    
    for campo, padrao in padroes.items():
        match = re.search(padrao, texto)
        if match:
            valor = match.group(1)
            if campo in ['valor_operacao', 'taxa_juros_mensal']:
                valor = formatar_valor(valor)
            metadados[campo] = valor
    
    return metadados

def limpar_valor(valor_str: str) -> str:
    """Remove caracteres indesejados e formata o valor para conversão."""
    # Remove caracteres não numéricos, exceto ponto e vírgula
    valor_str = re.sub(r'[^\d.,]', '', valor_str)
    return valor_str

def extrair_parcelas(texto: str) -> List[Dict[str, Any]]:
    """Extrai as informações das parcelas do texto do PDF."""
    parcelas = []
    
    # Processar linha por linha
    for linha in texto.split('\n'):
        try:
            # Processar apenas linhas que começam com número seguido de data
            if re.match(r'^\s*\d+\s+\d{2}/\d{2}/\d{4}', linha):
                # Dividir por espaços simples
                partes = linha.strip().split()
                
                print(f"\nProcessando linha: {linha}")
                print(f"Partes encontradas: {partes}")
                
                if len(partes) >= 17:  # Ajustado para o número correto de campos
                    parcela = {
                        'tipo': 'parcela',
                        'numero': int(partes[0]),
                        'vencimento': partes[1],
                        'amortizacao': formatar_valor(partes[2]),
                        'juros': formatar_valor(partes[3]),
                        'indice_correcao_parcela': formatar_valor(partes[4]),
                        'seguro_mip': formatar_valor(partes[5]),
                        'seguro_dfi': formatar_valor(partes[6]),
                        'seguro_res': formatar_valor(partes[7]),
                        'tca': formatar_valor(partes[8]),
                        'indice_correcao_saldo': formatar_valor(partes[9]),
                        'multa': formatar_valor(partes[10]),
                        'mora': formatar_valor(partes[11]),
                        'ajuste_financeiro': formatar_valor(partes[12]),
                        'fgts_mensal': formatar_valor(partes[13]),
                        'parcelado_acordado': formatar_valor(partes[14]),
                        'situacao_parcela': partes[15],  # Situação da Parcela
                        'valor_parcela': formatar_valor(partes[16]),
                        'saldo_devedor': formatar_valor(partes[17])
                    }
                    
                    print(f"Parcela processada: {parcela}")
                    parcelas.append(parcela)
                else:
                    print(f"Linha ignorada (campos insuficientes): {linha}")
                    print(f"Número de campos encontrados: {len(partes)}")
                    print(f"Campos: {partes}")
                    
        except Exception as e:
            print(f"Erro ao processar linha: {linha}")
            print(f"Erro detalhado: {str(e)}")
            continue
    
    return parcelas

def extrair_operacoes(texto: str) -> List[Dict[str, Any]]:
    """Extrai as informações das operações especiais do texto do PDF."""
    operacoes = []
    
    # Padrão para identificar operações especiais
    padrao_operacao = r'Operação:\s*(.*?)(?=\n)'
    
    # Encontra todas as ocorrências de "Operação:"
    matches = re.finditer(padrao_operacao, texto)
    
    for match in matches:
        linha_operacao = match.group(1).strip()
        
        # Tenta extrair a data da operação
        data_match = re.search(r'(\d{2}/\d{2}/\d{4})', linha_operacao)
        data = data_match.group(1) if data_match else None
        
        # Extrai a descrição da operação
        descricao = linha_operacao.split('Data:')[0].strip()
        
        # Inicializa os campos específicos da operação de amortização
        juros_pro_rata = None
        atualizacao_monetaria = None
        valor_operacao = None
        
        # Se for uma operação de amortização, extrai os campos específicos
        if "Amortizacaoreducaodeprazorecursoproprio" in descricao:
            # Extrai Juros Pró-rata
            juros_match = re.search(r'JurosPró-rata:([\d.,]+)', linha_operacao)
            if juros_match:
                juros_pro_rata = formatar_valor(juros_match.group(1))
            
            # Extrai Atualização monetária
            atualizacao_match = re.search(r'Atualizaçãomonetária:([\d.,]+)', linha_operacao)
            if atualizacao_match:
                atualizacao_monetaria = formatar_valor(atualizacao_match.group(1))
            
            # Extrai Valor da Operação
            valor_match = re.search(r'ValordaOperação:([\d.,]+)', linha_operacao)
            if valor_match:
                valor_operacao = formatar_valor(valor_match.group(1))
        
        operacao = {
            'tipo': 'operacao',
            'descricao': descricao,
            'data': data,
            'valor': valor_operacao,
            'juros_pro_rata': juros_pro_rata,
            'atualizacao_monetaria': atualizacao_monetaria
        }
        
        # Remove valores None do dicionário
        operacao = {k: v for k, v in operacao.items() if v is not None}
        
        operacoes.append(operacao)
    
    return operacoes

def converter_pdf_para_json(caminho_pdf: str, caminho_json: str) -> None:
    """Converte o PDF para JSON e salva o resultado."""
    data = {"metadados": {}, "eventos": []}
    
    with pdfplumber.open(caminho_pdf) as pdf:
        texto_completo = ""
        for page in pdf.pages:
            texto_completo += page.extract_text() + "\n"
    
    # Extrair metadados
    data["metadados"] = extrair_metadados(texto_completo)
    
    # Extrair parcelas e operações
    parcelas = extrair_parcelas(texto_completo)
    operacoes = extrair_operacoes(texto_completo)
    
    # Combinar e ordenar eventos
    data["eventos"] = sorted(
        parcelas + operacoes,
        key=lambda x: datetime.strptime(x['vencimento'] if x['tipo'] == 'parcela' else x['data'], '%d/%m/%Y')
    )
    
    # Salvar como JSON
    with open(caminho_json, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    # Exemplo de uso
    caminho_pdf = "shareFile-5.pdf"
    caminho_json = "financiamento.json"  # Agora salva no mesmo diretório
    converter_pdf_para_json(caminho_pdf, caminho_json) 