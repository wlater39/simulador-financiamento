import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import json
import plotly.express as px
import plotly.graph_objects as go
from decimal import Decimal, ROUND_HALF_UP

# Configuração da página
st.set_page_config(
    page_title="Simulador de Financiamento",
    layout="wide",
    initial_sidebar_state="collapsed"
)

def formatar_valor_contabil(valor):
    """Formata valor para o padrão contábil brasileiro (R$ 0.000,00) sem depender do locale"""
    try:
        # Arredondar para 2 casas decimais
        valor_decimal = Decimal(str(valor)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        # Converter para string e separar parte inteira e decimal
        valor_str = f"{valor_decimal:,.2f}"
        parte_inteira, parte_decimal = valor_str.split('.')
        # Substituir separadores para formato brasileiro
        parte_inteira = parte_inteira.replace(',', '.')
        # Montar string final
        return f"R$ {parte_inteira},{parte_decimal}"
    except:
        return "R$ 0,00"

def formatar_numero(valor, casas_decimais=2):
    """Formata número com quantidade específica de casas decimais sem depender do locale"""
    try:
        valor_decimal = Decimal(str(valor)).quantize(Decimal(f'0.{"0" * casas_decimais}'), rounding=ROUND_HALF_UP)
        valor_str = f"{valor_decimal:,.{casas_decimais}f}"
        if casas_decimais > 0:
            parte_inteira, parte_decimal = valor_str.split('.')
            parte_inteira = parte_inteira.replace(',', '.')
            return f"{parte_inteira},{parte_decimal}"
        else:
            return valor_str.replace(',', '.')
    except:
        return "0,00" if casas_decimais > 0 else "0"

def formatar_percentual(valor, casas_decimais=2):
    """Formata valor percentual sem depender do locale"""
    try:
        valor_percentual = valor * 100
        return f"{formatar_numero(valor_percentual, casas_decimais)}%"
    except:
        return "0,00%"

def carregar_dados_json(caminho_json="financiamento.json"):
    """Carrega os dados do arquivo JSON gerado pelo pdf_to_json_converter.py"""
    try:
        with open(caminho_json, 'r', encoding='utf-8') as f:
            dados = json.load(f)
        return dados
    except Exception as e:
        st.error(f"Erro ao carregar arquivo JSON: {str(e)}")
        return None

def criar_tabela_consolidada(dados_json):
    """Cria uma tabela consolidada com parcelas e operações de amortização"""
    try:
        # Criar DataFrame para parcelas
        parcelas = []
        for evento in dados_json["eventos"]:
            if evento["tipo"] == "parcela":
                parcela = {
                    "numero": evento["numero"],
                    "vencimento": evento["vencimento"],
                    "amortizacao": evento["amortizacao"],
                    "juros": evento["juros"],
                    "seguro_mip": evento.get("seguro_mip", 0),
                    "seguro_df": evento.get("seguro_df", 0),
                    "taxa_adm": evento.get("taxa_adm", 0),
                    "valor_parcela": evento["valor_parcela"],
                    "saldo_devedor": evento["saldo_devedor"],
                    "situacao_parcela": evento["situacao_parcela"],
                    "tipo": "parcela",
                    "data": datetime.strptime(evento["vencimento"], "%d/%m/%Y")
                }
                parcelas.append(parcela)
            elif evento["tipo"] == "operacao" and "amortizacao" in evento.get("descricao", "").lower():
                operacao = {
                    "numero": None,
                    "vencimento": evento["data"],
                    "amortizacao": evento.get("valor", 0),
                    "juros": evento.get("juros_pro_rata", 0),
                    "seguro_mip": None,
                    "seguro_df": None,
                    "taxa_adm": None,
                    "valor_parcela": evento.get("valor", 0),
                    "saldo_devedor": None,
                    "situacao_parcela": "Amortizado",
                    "tipo": "amortizacao",
                    "data": datetime.strptime(evento["data"], "%d/%m/%Y")
                }
                parcelas.append(operacao)
        
        # Criar DataFrame
        df = pd.DataFrame(parcelas)
        
        # Ordenar por data
        df = df.sort_values("data")
        
        # Calcular saldo devedor para operações de amortização
        saldo_atual = None
        for idx, row in df.iterrows():
            if row["tipo"] == "parcela":
                saldo_atual = row["saldo_devedor"]
            elif row["tipo"] == "amortizacao" and saldo_atual is not None:
                df.at[idx, "saldo_devedor"] = saldo_atual - row["amortizacao"]
                saldo_atual = df.at[idx, "saldo_devedor"]
        
        # Calcular valores acumulados
        df["valor_total_pago"] = df["valor_parcela"].cumsum()
        df["valor_total_amortizado"] = df["amortizacao"].cumsum()
        df["valor_total_juros"] = df["juros"].cumsum()
        
        return df
    except Exception as e:
        st.error(f"Erro ao criar tabela consolidada: {str(e)}")
        return None

def calcular_nova_tabela(df, parcela_alvo, valor_amortizacao, tipo_reducao='prazo'):
    """Calcula nova tabela após amortização com opção de tipo de redução"""
    try:
        # Inicializar lista de logs
        logs = []
        
        df_novo = df.copy()
        
        # Encontrar a parcela alvo pelo número (não pelo índice)
        idx = df_novo[df_novo['numero'] == parcela_alvo].index[0]
        parcela_atual = df_novo.loc[idx]
        
        logs.append({
            'titulo': "Estado da Parcela Alvo",
            'dados': {
                "Número da Parcela": parcela_atual['numero'],
                "Saldo Devedor": f"R$ {parcela_atual['saldo_devedor']:,.2f}",
                "Valor da Parcela": f"R$ {parcela_atual['valor_parcela']:,.2f}",
                "Juros": f"R$ {parcela_atual['juros']:,.2f}",
                "Amortização": f"R$ {parcela_atual['amortizacao']:,.2f}"
            }
        })
            
        # Validar valor da amortização
        saldo_atual = parcela_atual["saldo_devedor"]
        if valor_amortizacao > saldo_atual:
            st.error("Valor da amortização maior que o saldo devedor!")
            return df
            
        # Taxa de juros anual do contrato
        taxa_juros_anual = 0.10490  # 10.49%
        taxa_juros_mensal = (1 + taxa_juros_anual) ** (1/12) - 1
        
        logs.append({
            'titulo': "Parâmetros do Cálculo",
            'dados': {
                "Taxa de Juros Anual": f"{taxa_juros_anual:.4%}",
                "Taxa de Juros Mensal": f"{taxa_juros_mensal:.4%}",
                "Valor da Amortização": f"R$ {valor_amortizacao:,.2f}",
                "Tipo de Redução": tipo_reducao
            }
        })
        
        # Criar linha de amortização extra
        nova_linha = pd.Series({
            'numero': None,
            'vencimento': parcela_atual['vencimento'],
            'amortizacao': valor_amortizacao,
            'juros': 0,  # Juros pro-rata seriam calculados se necessário
            'seguro_mip': 0,
            'seguro_df': 0,
            'taxa_adm': 0,
            'valor_parcela': valor_amortizacao,
            'saldo_devedor': saldo_atual - valor_amortizacao,
            'situacao_parcela': 'Amortizado',
            'tipo': 'amortizacao',
            'data': pd.to_datetime(parcela_atual['vencimento'], format='%d/%m/%Y')
        })
        
        # Inserir linha de amortização após a parcela atual
        df_novo = pd.concat([
            df_novo.iloc[:idx+1],
            pd.DataFrame([nova_linha]),
            df_novo.iloc[idx+1:]
        ]).reset_index(drop=True)
        
        # Atualizar saldo devedor após amortização
        novo_saldo = nova_linha['saldo_devedor']
        
        if tipo_reducao == 'prazo':
            # Dados iniciais
            valor_parcela_atual = parcela_atual['valor_parcela']
            parcelas_restantes = len(df_novo[df_novo['tipo'] == 'parcela']) - (idx + 1)
            
            # Calcular novo prazo (n')
            # n' = SD' / (P - (SD' * i))
            novo_prazo = int(novo_saldo / (valor_parcela_atual - (novo_saldo * taxa_juros_mensal)))
            
            # Calcular nova amortização mensal (A')
            # A' = SD' / n'
            nova_amortizacao_mensal = novo_saldo / novo_prazo
            
            logs.append({
                'titulo': "Cálculo de Redução de Prazo",
                'dados': {
                    "Saldo Após Amortização": f"R$ {novo_saldo:,.2f}",
                    "Valor da Parcela Atual": f"R$ {valor_parcela_atual:,.2f}",
                    "Parcelas Restantes Original": parcelas_restantes,
                    "Novo Prazo": novo_prazo,
                    "Nova Amortização Mensal": f"R$ {nova_amortizacao_mensal:,.2f}"
                }
            })
            
            # Ajustar o dataframe para o novo prazo
            if novo_prazo < parcelas_restantes:
                df_novo = df_novo.iloc[:idx + 2 + novo_prazo].copy()
        
        # Recalcular parcelas futuras
        for i in range(idx + 2, len(df_novo)):
            if df_novo.loc[i, 'tipo'] == 'parcela':
                saldo_anterior = df_novo.iloc[i-1]['saldo_devedor']
                
                # 1. Calcular nova amortização mensal
                amortizacao = nova_amortizacao_mensal
                
                # 2. Calcular juros sobre novo saldo
                juros = saldo_anterior * taxa_juros_mensal
                
                # 3. Calcular valor da parcela (deve ser praticamente igual à anterior)
                valor_parcela = amortizacao + juros
                
                # 4. Atualizar saldo
                novo_saldo = saldo_anterior - amortizacao
                
                df_novo.loc[i, 'juros'] = juros
                df_novo.loc[i, 'amortizacao'] = amortizacao
                df_novo.loc[i, 'valor_parcela'] = valor_parcela
                df_novo.loc[i, 'saldo_devedor'] = novo_saldo
                
                logs.append({
                    'titulo': f"Recálculo Parcela {i}",
                    'dados': {
                        "Saldo Anterior": f"R$ {saldo_anterior:,.2f}",
                        "Amortização": f"R$ {amortizacao:,.2f}",
                        "Juros": f"R$ {juros:,.2f}",
                        "Valor da Parcela": f"R$ {valor_parcela:,.2f}",
                        "Novo Saldo": f"R$ {novo_saldo:,.2f}"
                    }
                })
        
        # Recalcular valores acumulados
        df_novo['valor_total_pago'] = df_novo['valor_parcela'].cumsum()
        df_novo['valor_total_amortizado'] = df_novo['amortizacao'].cumsum()
        df_novo['valor_total_juros'] = df_novo['juros'].cumsum()
        
        logs.append({
            'titulo': "Resumo da Simulação",
            'dados': {
                "Parcelas Originais": len(df),
                "Parcelas após Simulação": len(df_novo),
                "Diferença": len(df) - len(df_novo),
                "Total Pago Original": f"R$ {df['valor_parcela'].sum():,.2f}",
                "Total Pago Simulado": f"R$ {df_novo['valor_parcela'].sum():,.2f}",
                "Diferença Total": f"R$ {df_novo['valor_parcela'].sum() - df['valor_parcela'].sum():,.2f}"
            }
        })
        
        # Salvar logs na session_state
        st.session_state.debug_logs = logs
        
        return df_novo
    except Exception as e:
        st.error(f"Erro ao calcular nova tabela: {str(e)}")
        return df

def calcular_impacto(df_original, df_simulado):
    # Diferença de juros
    juros_original = df_original["juros"].sum()
    juros_simulado = df_simulado["juros"].sum()
    diferenca_juros = juros_original - juros_simulado
    
    # Diferença de prazo
    prazo_original = len(df_original)
    prazo_simulado = len(df_simulado)
    diferenca_prazo = prazo_original - prazo_simulado
    
    # Economia total
    economia_total = df_original["valor_total_pago"].iloc[-1] - df_simulado["valor_total_pago"].iloc[-1]
    
    return {
        'diferenca_juros': diferenca_juros,
        'diferenca_prazo': diferenca_prazo,
        'economia_total': economia_total
    }

# Inicialização dos dados
dados_json = carregar_dados_json()
if dados_json is None:
    st.error("Não foi possível carregar os dados. Verifique o arquivo 'financiamento.json' e tente novamente.")
    st.stop()

df_original = criar_tabela_consolidada(dados_json)
if df_original is None:
    st.error("Erro ao criar tabela consolidada.")
    st.stop()

# Inicializar estados
if 'df_simulado' not in st.session_state:
    st.session_state.df_simulado = df_original.copy()

if 'amortizacoes' not in st.session_state:
    st.session_state.amortizacoes = pd.DataFrame({
        'data': [],
        'parcela': [],
        'valor': [],
        'tipo': [],
        'saldo_anterior': [],
        'saldo_atual': []
    })

# Interface principal
st.title("Simulador de Financiamento Imobiliário")

# Criar abas
tab1, tab2, tab3, tab4 = st.tabs(["Visão Geral", "Cronograma", "Simulador", "Debug"])

with tab1:
    # Visão Geral
    st.subheader("Situação do contrato")
    
    # Encontrar última operação realizada (parcela paga ou amortização)
    df_pagos = df_original[df_original['situacao_parcela'].isin(['Paga', 'Amortizado'])]
    ultima_operacao = df_pagos.iloc[-1] if len(df_pagos) > 0 else None
    
    # Criar dois containers lado a lado com bordas
    col1, col2 = st.columns(2)
    
    # Dados do Contrato
    with col1:
        # Valores originais do contrato (fixos)
        valor_financiado = 815000.00
        prazo_original = 420
        
        # Valores atuais do contrato (do JSON)
        valor_total_pagar = df_original['valor_total_pago'].iloc[-1]
        
        # Cálculo correto do prazo restante
        total_parcelas = len(df_original[df_original['tipo'] == 'parcela'])
        parcelas_pagas = len(df_original[df_original['situacao_parcela'] == 'Paga'])
        prazo_restante = total_parcelas - parcelas_pagas
        
        st.markdown(f"""
            <div style='border: 1px solid #e0e0e0; border-radius: 5px; padding: 1rem;'>
                <h4 style='font-size: 1.1rem; margin-bottom: 1rem;'>Dados do Contrato</h4>
                <div style='margin-bottom: 0.5rem;'>
                    <span style='color: #666; font-size: 0.9rem;'>Valor Financiado</span><br>
                    <span style='font-size: 1.2rem;'>{formatar_valor_contabil(valor_financiado)}</span>
                </div>
                <div style='margin-bottom: 0.5rem;'>
                    <span style='color: #666; font-size: 0.9rem;'>Prazo Original</span><br>
                    <span style='font-size: 1.2rem;'>{formatar_numero(prazo_original, 0)} meses</span>
                </div>
                <div style='margin-bottom: 0.5rem;'>
                    <span style='color: #666; font-size: 0.9rem;'>Valor Total a Pagar</span><br>
                    <span style='font-size: 1.2rem;'>{formatar_valor_contabil(valor_total_pagar)}</span>
                </div>
                <div>
                    <span style='color: #666; font-size: 0.9rem;'>Prazo Restante</span><br>
                    <span style='font-size: 1.2rem;'>{formatar_numero(prazo_restante, 0)} meses</span>
                </div>
            </div>
        """, unsafe_allow_html=True)
    
    # Valores pagos até o momento
    with col2:
        if ultima_operacao is not None:
            # Calcular valor total amortizado (soma das operações de amortização)
            amortizacoes_extras = sum(
                evento.get('valor', 0)
                for evento in dados_json['eventos']
                if evento['tipo'] == 'operacao' and 'Amortizacaoreducaodeprazorecursoproprio' in evento.get('descricao', '')
            )
            
            # Valor total de juros original e cálculo de economia
            juros_total_original = 1432084.96
            juros_atuais = df_original['juros'].sum()  # Total de juros (pagos + a pagar)
            juros_economizados = juros_total_original - juros_atuais
            
            st.markdown(f"""
                <div style='border: 1px solid #e0e0e0; border-radius: 5px; padding: 1rem;'>
                    <h4 style='font-size: 1.1rem; margin-bottom: 1rem;'>Valores pagos até o momento</h4>
                    <div style='margin-bottom: 0.5rem;'>
                        <span style='color: #666; font-size: 0.9rem;'>Valor Total Pago</span><br>
                        <span style='font-size: 1.2rem;'>{formatar_valor_contabil(ultima_operacao['valor_total_pago'])}</span>
                    </div>
                    <div style='margin-bottom: 0.5rem;'>
                        <span style='color: #666; font-size: 0.9rem;'>Principal Pago</span><br>
                        <span style='font-size: 1.2rem;'>{formatar_valor_contabil(ultima_operacao['valor_total_amortizado'])}</span>
                    </div>
                    <div style='margin-bottom: 0.5rem;'>
                        <span style='color: #666; font-size: 0.9rem;'>Juros Pagos</span><br>
                        <span style='font-size: 1.2rem;'>{formatar_valor_contabil(ultima_operacao['valor_total_juros'])}</span>
                    </div>
                    <div style='margin-bottom: 0.5rem;'>
                        <span style='color: #666; font-size: 0.9rem;'>Valor Amortizado</span><br>
                        <span style='font-size: 1.2rem;'>{formatar_valor_contabil(amortizacoes_extras)}</span>
                    </div>
                    <div style='margin-bottom: 0.5rem;'>
                        <span style='color: #666; font-size: 0.9rem;'>Juros Economizados</span><br>
                        <span style='font-size: 1.2rem;'>{formatar_valor_contabil(juros_economizados)}</span>
                    </div>
                    <div>
                        <span style='color: #666; font-size: 0.9rem;'>Saldo Devedor Atual</span><br>
                        <span style='font-size: 1.2rem;'>{formatar_valor_contabil(ultima_operacao['saldo_devedor'])}</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.info("Nenhuma parcela paga até o momento.")
    
    # Adicionar espaço antes do gráfico
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Gráfico de composição dos pagamentos
    if ultima_operacao is not None:
        # Calcular valores
        principal_pago = ultima_operacao['valor_total_amortizado']
        juros_pagos = ultima_operacao['valor_total_juros']
        valor_restante = df_original['valor_total_pago'].iloc[-1] - (principal_pago + juros_pagos)
        
        # Criar título personalizado
        st.markdown("### Proporção de Pagamento")
        
        # Criar o gráfico com plotly
        fig = go.Figure()
        
        # Adicionar as barras em sequência
        fig.add_trace(go.Bar(
            name='Principal Pago',
            x=[principal_pago],
            y=[''],
            orientation='h',
            marker=dict(color='#2ecc71'),
            text=formatar_valor_contabil(principal_pago),
            textposition='auto',
            hovertemplate=f'Principal Pago: {formatar_valor_contabil(principal_pago)}<extra></extra>'
        ))
        
        fig.add_trace(go.Bar(
            name='Juros Pagos',
            x=[juros_pagos],
            y=[''],
            orientation='h',
            marker=dict(color='#e74c3c'),
            text=formatar_valor_contabil(juros_pagos),
            textposition='auto',
            hovertemplate=f'Juros Pagos: {formatar_valor_contabil(juros_pagos)}<extra></extra>'
        ))
        
        fig.add_trace(go.Bar(
            name='Saldo Devedor',
            x=[valor_restante],
            y=[''],
            orientation='h',
            marker=dict(color='#ecf0f1'),
            text=formatar_valor_contabil(valor_restante),
            textposition='auto',
            hovertemplate=f'Saldo Devedor: {formatar_valor_contabil(valor_restante)}<extra></extra>'
        ))
        
        # Atualizar o layout
        fig.update_layout(
            barmode='stack',
            height=100,
            showlegend=True,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            ),
            margin=dict(l=0, r=0, t=30, b=0),
            plot_bgcolor='white',
            paper_bgcolor='white',
            xaxis=dict(
                showgrid=False,
                zeroline=False,
                showline=False,
                showticklabels=False
            ),
            yaxis=dict(
                showgrid=False,
                zeroline=False,
                showline=False,
                showticklabels=False
            )
        )
        
        # Mostrar o gráfico
        st.plotly_chart(fig, use_container_width=True)
        
        # Adicionar legenda com os valores em texto
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"**Principal Pago**<br>{formatar_valor_contabil(principal_pago)}", unsafe_allow_html=True)
        with col2:
            st.markdown(f"**Juros Pagos**<br>{formatar_valor_contabil(juros_pagos)}", unsafe_allow_html=True)
        with col3:
            st.markdown(f"**Saldo Devedor**<br>{formatar_valor_contabil(valor_restante)}", unsafe_allow_html=True)
    else:
        st.info("Nenhuma parcela paga até o momento.")

with tab2:
    # Cronograma
    st.subheader("Cronograma de Pagamentos")
    
    # Formatar valores monetários
    df_display = df_original.copy()
    colunas_monetarias = ['valor_parcela', 'amortizacao', 'juros', 'saldo_devedor', 'seguro_mip', 'seguro_df', 'taxa_adm']
    for col in colunas_monetarias:
        df_display[col] = df_display[col].apply(lambda x: formatar_valor_contabil(x) if pd.notnull(x) else "-")
    
    # Mostrar DataFrame com todas as colunas
    st.dataframe(
        df_display,
        use_container_width=True
    )

with tab3:
    # Simulador
    st.markdown("### Simulador de Amortizações", help="Simule diferentes cenários de amortização")
    
    # Controles em um expander para economizar espaço
    with st.expander("Controles da Simulação", expanded=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            parcela_alvo = st.number_input(
                "Número da Parcela",
                min_value=1,
                max_value=len(df_original[df_original["tipo"] == "parcela"]),
                value=1
            )
        
        with col2:
            saldo_atual = float(df_original[df_original["tipo"] == "parcela"].loc[parcela_alvo-1, "saldo_devedor"])
            valor_amortizacao = st.number_input(
                "Valor da Amortização (R$)",
                min_value=0.0,
                max_value=saldo_atual,
                value=0.0,
                format="%.2f"
            )
        
        with col3:
            tipo_reducao = st.radio(
                "Tipo de Redução",
                ["Redução de Prazo", "Redução de Valor"],
                index=0
            )
        
        col_btn1, col_btn2 = st.columns([1, 4])
        with col_btn1:
            if st.button("Aplicar Amortização"):
                # Salvar amortização na lista de amortizações
                nova_amortizacao = {
                    'data': datetime.now().strftime("%d/%m/%Y"),
                    'parcela': parcela_alvo,
                    'valor': valor_amortizacao,
                    'tipo': tipo_reducao
                }
                
                if 'amortizacoes_simuladas' not in st.session_state:
                    st.session_state.amortizacoes_simuladas = []
                
                st.session_state.amortizacoes_simuladas.append(nova_amortizacao)
                
                st.session_state.df_simulado = calcular_nova_tabela(
                    df_original if 'df_simulado' not in st.session_state else st.session_state.df_simulado,
                    parcela_alvo,
                    valor_amortizacao,
                    'prazo' if tipo_reducao == "Redução de Prazo" else 'valor'
                )
                st.success("Amortização aplicada com sucesso!")
        
        with col_btn2:
            if st.button("Resetar Simulação"):
                st.session_state.df_simulado = df_original.copy()
                st.session_state.amortizacoes_simuladas = []
                st.rerun()
    
    # Tabela de amortizações simuladas
    st.markdown("#### Amortizações Aplicadas na Simulação")
    
    if 'amortizacoes_simuladas' in st.session_state and len(st.session_state.amortizacoes_simuladas) > 0:
        df_amortizacoes = pd.DataFrame(st.session_state.amortizacoes_simuladas)
        st.dataframe(df_amortizacoes, use_container_width=True)
    else:
        st.info("Nenhuma amortização simulada ainda.")

    # Comparação dos cenários
    st.markdown("#### Comparação dos Cenários")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Sem antecipação de pagamento**")
        
        # Calcular valores originais
        valor_financiado = 815000.00
        total_parcelas = df_original['valor_parcela'].sum()
        total_amortizacoes_extras = df_original[
            (df_original['tipo'] == 'amortizacao') & 
            (df_original['situacao_parcela'] == 'Amortizado')
        ]['valor_parcela'].sum()
        total_a_pagar = total_parcelas + total_amortizacoes_extras
        
        metricas_original = {
            "Valor financiado": formatar_valor_contabil(valor_financiado),
            "Valor total a ser pago": formatar_valor_contabil(total_a_pagar),
            "Total amortizado (extra)": formatar_valor_contabil(total_amortizacoes_extras),
            "Total de juros": formatar_valor_contabil(df_original['juros'].sum()),
            "Quantidade de parcelas": formatar_numero(len(df_original[df_original['tipo'] == 'parcela']), 0),
            "Data da última parcela": df_original[df_original['tipo'] == 'parcela']['vencimento'].iloc[-1]
        }
        
        for k, v in metricas_original.items():
            st.metric(k, v, label_visibility="visible")

    with col2:
        st.markdown("**Com antecipação de pagamento**")
        df_simulado = st.session_state.get('df_simulado', df_original.copy())
        
        # Calcular valores simulados
        total_parcelas_simulado = df_simulado['valor_parcela'].sum()
        total_amortizacoes_simuladas = sum(amort['valor'] for amort in st.session_state.get('amortizacoes_simuladas', []))
        total_amortizacoes_extras_simulado = total_amortizacoes_extras + total_amortizacoes_simuladas
        total_a_pagar_simulado = total_parcelas_simulado + total_amortizacoes_extras_simulado
        
        metricas_simulado = {
            "Valor financiado": formatar_valor_contabil(valor_financiado),
            "Valor total a ser pago": formatar_valor_contabil(total_a_pagar_simulado),
            "Total amortizado (extra)": formatar_valor_contabil(total_amortizacoes_extras_simulado),
            "Total de juros": formatar_valor_contabil(df_simulado['juros'].sum()),
            "Quantidade de parcelas": formatar_numero(len(df_simulado[df_simulado['tipo'] == 'parcela']), 0),
            "Data da última parcela": df_simulado[df_simulado['tipo'] == 'parcela']['vencimento'].iloc[-1]
        }
        
        for k, v in metricas_simulado.items():
            # Calcular a diferença para mostrar o delta
            if k.startswith("Valor financiado"):
                st.metric(k, v, label_visibility="visible")
            elif k.startswith("R$"):
                valor_original = float(metricas_original[k].replace("R$ ", "").replace(",", ""))
                valor_simulado = float(v.replace("R$ ", "").replace(",", ""))
                delta = ((valor_simulado - valor_original) / valor_original) * 100 if valor_original != 0 else 0
                st.metric(k, v, f"{delta:.1f}%", label_visibility="visible")
            elif k == "Quantidade de parcelas":
                delta = int(v) - int(metricas_original[k])
                st.metric(k, v, f"{delta} parcelas", label_visibility="visible")
            else:
                st.metric(k, v, label_visibility="visible")
    
    # Gráfico de evolução do saldo devedor
    st.markdown("#### Evolução do Saldo Devedor")
    
    # Filtrar apenas valores positivos do saldo devedor
    df_plot_original = df_original[df_original['saldo_devedor'] > 0]
    df_plot_simulado = df_simulado[df_simulado['saldo_devedor'] > 0]
    
    fig = go.Figure()
    
    # Adicionar linha do cenário original
    fig.add_trace(go.Scatter(
        x=df_plot_original['data'],
        y=df_plot_original['saldo_devedor'],
        name='Sem Antecipação',
        line=dict(color='#3498db')
    ))
    
    # Adicionar linha do cenário simulado
    fig.add_trace(go.Scatter(
        x=df_plot_simulado['data'],
        y=df_plot_simulado['saldo_devedor'],
        name='Com Antecipação',
        line=dict(color='#2ecc71')
    ))
    
    fig.update_layout(
        xaxis_title='Data',
        yaxis_title='Saldo Devedor (R$)',
        height=400,
        yaxis=dict(
            rangemode='nonnegative'  # Força o eixo Y a começar do zero
        ),
        margin=dict(t=0, b=0)  # Remove margens superior e inferior
    )
    
    st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.markdown("### Debug da Simulação")
    
    # Seção de Logs
    with st.expander("Logs de Cálculo", expanded=True):
        if 'debug_logs' in st.session_state:
            for log in st.session_state.debug_logs:
                st.markdown(f"#### {log['titulo']}")
                st.write(log['dados'])
    
    # Tabelas Comparativas
    st.markdown("### Cronogramas Detalhados")
    
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### Cronograma Original")
        # Formatar valores monetários
        df_display = df_original.copy()
        colunas_monetarias = ['valor_parcela', 'amortizacao', 'juros', 'saldo_devedor']
        for col in colunas_monetarias:
            df_display[col] = df_display[col].apply(lambda x: f"R$ {x:,.2f}" if pd.notnull(x) else "-")
        
        st.dataframe(
            df_display,
            use_container_width=True
        )

    with col2:
        st.markdown("#### Cronograma Simulado")
        if 'df_simulado' in st.session_state:
            # Formatar valores monetários
            df_display = st.session_state.df_simulado.copy()
            for col in colunas_monetarias:
                df_display[col] = df_display[col].apply(lambda x: f"R$ {x:,.2f}" if pd.notnull(x) else "-")
            
            st.dataframe(
                df_display,
                use_container_width=True
            )
        else:
            st.info("Nenhuma simulação realizada ainda.")
    
    # Análise de Diferenças
    if 'df_simulado' in st.session_state:
        st.markdown("### Análise de Diferenças")
        
        # Diferenças nos totais
        st.markdown("#### Totais")
        df_diff = pd.DataFrame({
            'Métrica': ['Valor Total', 'Total Amortização', 'Total Juros', 'Número de Parcelas'],
            'Original': [
                df_original['valor_parcela'].sum(),
                df_original['amortizacao'].sum(),
                df_original['juros'].sum(),
                len(df_original[df_original['tipo'] == 'parcela'])
            ],
            'Simulado': [
                st.session_state.df_simulado['valor_parcela'].sum(),
                st.session_state.df_simulado['amortizacao'].sum(),
                st.session_state.df_simulado['juros'].sum(),
                len(st.session_state.df_simulado[st.session_state.df_simulado['tipo'] == 'parcela'])
            ]
        })
        
        df_diff['Diferença'] = df_diff['Simulado'] - df_diff['Original']
        df_diff['Diferença %'] = (df_diff['Diferença'] / df_diff['Original'] * 100)
        
        # Formatar valores monetários
        for idx, row in df_diff.iterrows():
            if row['Métrica'] != 'Número de Parcelas':
                df_diff.at[idx, 'Original'] = formatar_valor_contabil(row['Original'])
                df_diff.at[idx, 'Simulado'] = formatar_valor_contabil(row['Simulado'])
                df_diff.at[idx, 'Diferença'] = formatar_valor_contabil(row['Diferença'])
                df_diff.at[idx, 'Diferença %'] = formatar_percentual(row['Diferença %'] / 100)
            else:
                df_diff.at[idx, 'Original'] = formatar_numero(row['Original'], 0)
                df_diff.at[idx, 'Simulado'] = formatar_numero(row['Simulado'], 0)
                df_diff.at[idx, 'Diferença'] = formatar_numero(row['Diferença'], 0)
                df_diff.at[idx, 'Diferença %'] = formatar_percentual(row['Diferença %'] / 100)
        
        st.dataframe(df_diff, use_container_width=True)
        
        # Gráfico de evolução das parcelas
        st.markdown("#### Evolução do Valor das Parcelas")
        
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=df_original['numero'],
            y=df_original['valor_parcela'],
            name='Original',
            line=dict(color='#3498db')
        ))
        
        fig.add_trace(go.Scatter(
            x=st.session_state.df_simulado['numero'],
            y=st.session_state.df_simulado['valor_parcela'],
            name='Simulado',
            line=dict(color='#2ecc71')
        ))
        
        fig.update_layout(
            xaxis_title='Número da Parcela',
            yaxis_title='Valor da Parcela (R$)',
            height=400
        )
        
        st.plotly_chart(fig, use_container_width=True) 