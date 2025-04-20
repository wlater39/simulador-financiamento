import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import json
import plotly.express as px
import plotly.graph_objects as go

# Configuração da página
st.set_page_config(
    page_title="Simulador de Financiamento",
    layout="wide",
    initial_sidebar_state="collapsed"
)

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
    st.subheader("Situação Atual do Contrato")
    
    # Encontrar última operação realizada (parcela paga ou amortização)
    df_pagos = df_original[df_original['situacao_parcela'].isin(['Paga', 'Amortizado'])]
    ultima_operacao = df_pagos.iloc[-1] if len(df_pagos) > 0 else None
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Visão do Contrato")
        
        # Métricas do contrato
        col_met1, col_met2 = st.columns(2)
        with col_met1:
            st.metric(
                "Valor Financiado",
                f"R$ {df_original['saldo_devedor'].iloc[0]:,.2f}"
            )
            st.metric(
                "Prazo Original",
                f"{len(df_original)} meses"
            )
        
        with col_met2:
            st.metric(
                "Valor Total a Pagar",
                f"R$ {df_original['valor_total_pago'].iloc[-1]:,.2f}"
            )
            st.metric(
                "Prazo Restante",
                f"{len(df_original) - len(df_original[df_original['situacao_parcela'].isin(['Paga', 'Amortizado'])])} meses"
            )
    
    with col2:
        st.subheader("Valores Pagos até o Momento")
        
        if ultima_operacao is not None:
            col_met3, col_met4 = st.columns(2)
            with col_met3:
                st.metric(
                    "Valor Total Pago",
                    f"R$ {ultima_operacao['valor_total_pago']:,.2f}"
                )
                st.metric(
                    "Principal Pago",
                    f"R$ {ultima_operacao['valor_total_amortizado']:,.2f}"
                )
            
            with col_met4:
                st.metric(
                    "Juros Pagos",
                    f"R$ {ultima_operacao['valor_total_juros']:,.2f}"
                )
                st.metric(
                    "Saldo Devedor Atual",
                    f"R$ {ultima_operacao['saldo_devedor']:,.2f}"
                )
            
            # Gráfico de composição dos pagamentos
            fig = go.Figure()
            fig.add_trace(go.Bar(
                name='Principal',
                y=['Total'],
                x=[ultima_operacao['valor_total_amortizado']],
                orientation='h',
                marker_color='#2ecc71'
            ))
            fig.add_trace(go.Bar(
                name='Juros',
                y=['Total'],
                x=[ultima_operacao['valor_total_juros']],
                orientation='h',
                marker_color='#e74c3c'
            ))
            
            fig.update_layout(
                barmode='stack',
                height=200,
                showlegend=True,
                margin=dict(l=0, r=0, t=0, b=0),
                title='Composição dos Pagamentos Realizados'
            )
            
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Nenhuma parcela paga até o momento.")

with tab2:
    # Cronograma
    st.subheader("Cronograma de Pagamentos")
    
    # Estilizar DataFrame
    def color_status(val):
        if val == 'Paga':
            return 'background-color: #2ecc71'
        elif val == 'Amortizado':
            return 'background-color: #3498db'
        return ''
    
    # Definir ordem das colunas
    colunas = [
        "numero", "vencimento", "amortizacao", "juros", 
        "seguro_mip", "seguro_df", "taxa_adm", 
        "valor_parcela", "saldo_devedor", "situacao_parcela"
    ]
    
    # Mostrar DataFrame com todas as colunas
    st.dataframe(
        df_original[colunas].style.applymap(color_status, subset=['situacao_parcela']),
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
            "Valor financiado": f"R$ {valor_financiado:,.2f}",
            "Valor total a ser pago": f"R$ {total_a_pagar:,.2f}",
            "Total amortizado (extra)": f"R$ {total_amortizacoes_extras:,.2f}",
            "Total de juros": f"R$ {df_original['juros'].sum():,.2f}",
            "Quantidade de parcelas": len(df_original[df_original['tipo'] == 'parcela']),
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
            "Valor financiado": f"R$ {valor_financiado:,.2f}",
            "Valor total a ser pago": f"R$ {total_a_pagar_simulado:,.2f}",
            "Total amortizado (extra)": f"R$ {total_amortizacoes_extras_simulado:,.2f}",
            "Total de juros": f"R$ {df_simulado['juros'].sum():,.2f}",
            "Quantidade de parcelas": len(df_simulado[df_simulado['tipo'] == 'parcela']),
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
        df_diff['Diferença %'] = (df_diff['Diferença'] / df_diff['Original'] * 100).round(2)
        
        # Formatar valores monetários
        for col in ['Original', 'Simulado', 'Diferença']:
            df_diff[col] = df_diff.apply(
                lambda x: f"R$ {x[col]:,.2f}" if x['Métrica'] != 'Número de Parcelas' else f"{x[col]:.0f}",
                axis=1
            )
        df_diff['Diferença %'] = df_diff['Diferença %'].apply(lambda x: f"{x:.2f}%")
        
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