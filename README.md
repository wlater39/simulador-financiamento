# Simulador de Financiamento Imobiliário

Simulador de financiamento imobiliário que permite visualizar diferentes cenários de amortização, incluindo redução de prazo e redução de valor das parcelas.

## Funcionalidades

- Visualização do cronograma de pagamentos
- Simulação de amortizações
- Comparação entre cenários com e sem antecipação
- Gráficos de evolução do saldo devedor
- Cálculos detalhados de juros e amortizações

## Requisitos

- Python 3.8 ou superior
- Dependências listadas em `requirements.txt`

## Instalação

1. Clone o repositório:
```bash
git clone [URL_DO_SEU_REPOSITORIO]
```

2. Instale as dependências:
```bash
pip install -r requirements.txt
```

3. Execute a aplicação:
```bash
streamlit run financiamento_simulador.py
```

## Estrutura do Projeto

- `financiamento_simulador.py`: Aplicação principal
- `requirements.txt`: Dependências do projeto
- `financiamento.json`: Dados do financiamento (se necessário)

## Deploy

A aplicação pode ser facilmente deployada no Streamlit Cloud:

1. Crie uma conta no [Streamlit Cloud](https://streamlit.io/cloud)
2. Conecte com seu repositório GitHub
3. Selecione o arquivo principal (`financiamento_simulador.py`)
4. Clique em "Deploy" 