import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import base64

# =========================
# CONEXÃO E FUNÇÕES BASE
# =========================
def connect_google_sheets():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = st.secrets["gcp_service_account"]
        spreadsheet_name = st.secrets["spreadsheet_name"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        return client.open(spreadsheet_name)
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        st.stop()

sheet = connect_google_sheets()
ws_vendas = sheet.worksheet("vendas")
ws_usuarios = sheet.worksheet("usuarios")
ws_produtos = sheet.worksheet("produtos")

def get_users_df():
    df = pd.DataFrame(ws_usuarios.get_all_records())
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df

def get_products_df():
    data = ws_produtos.get_all_records()
    if not data:
        return pd.DataFrame(columns=['produto', 'preco', 'custo', 'status'])
    df = pd.DataFrame(data)
    df.columns = [str(c).strip().lower() for c in df.columns]
    if 'status' in df.columns:
        return df[df['status'] != 'Oculto']
    return df

# =========================
# SISTEMA DE LOGIN
# =========================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None
    st.session_state.role = None

if not st.session_state.logged_in:
    st.title("🛍️ Vendas bb.arte")
    df_u = get_users_df()
    
    user_sel = st.selectbox("Usuário", df_u['nome'].tolist())
    pwd_input = st.text_input("Senha", type="password")
    if st.button("Entrar", use_container_width=True):
        user_info = df_u[df_u['nome'] == user_sel].iloc[0]
        if str(pwd_input) == str(user_info['senha']):
            st.session_state.logged_in = True
            st.session_state.user = user_sel
            st.session_state.role = user_info['role']
            st.rerun()
        else:
            st.error("Senha incorreta.")
    st.stop()

# =========================
# INTERFACE PRINCIPAL
# =========================
st.markdown(f"### 👤 {st.session_state.user}: **{st.session_state.role}**")

abas_disponiveis = ["Registrar Venda", "Histórico"]
if st.session_state.role == "ADM":
    abas_disponiveis.append("Gerenciar Produtos")

tabs = st.tabs(abas_disponiveis)

# --- ABA 1: REGISTRAR VENDA ---
with tabs[0]:
    st.subheader("🛒 Nova Venda")
    df_p = get_products_df()
    
    if df_p.empty:
        st.info("Nenhum produto disponível.")
    else:
        with st.form("form_venda", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                prod_nome = st.selectbox("Produto", df_p['produto'].tolist())
                # Busca segura de dados do produto
                item_data = df_p[df_p['produto'] == prod_nome].iloc[0]
                
                p_unit = float(item_data['preco']) if item_data['preco'] != "" else 0.0
                c_unit = float(item_data['custo']) if 'custo' in item_data and item_data['custo'] != "" else 0.0
                
                qtd = st.number_input("Quantidade", min_value=1, value=1)
                v_total = st.number_input("Valor Total (R$)", value=p_unit * qtd, step=0.01)
                
            with col2:
                data_v = st.date_input("Data", datetime.now())
                obs = st.text_input("Observação")
                
            if st.form_submit_button("Confirmar Registro", use_container_width=True):
                ws_vendas.append_row([
                    st.session_state.user, 
                    data_v.strftime("%Y-%m-%d"), 
                    v_total, 
                    prod_nome, 
                    f"{obs} (Qtd: {qtd})",
                    data_v.strftime("%m/%Y"),
                    qtd,
                    c_unit * qtd
                ])
                st.toast("Venda registrada!")
                st.rerun()

# --- ABA 2: HISTÓRICO ---
with tabs[1]:
    st.subheader("📊 Relatório de Vendas")
    v_data = ws_vendas.get_all_records()
    if v_data:
        v_df = pd.DataFrame(v_data)
        v_df.columns = [str(c).strip().lower() for c in v_df.columns]
        
        if st.session_state.role != "ADM":
            v_df = v_df[v_df['vendedor'] == st.session_state.user]
        
        if not v_df.empty:
            meses = sorted(v_df['mes_referencia'].unique(), reverse=True)
            mes_f = st.selectbox("Mês", meses)
            df_f = v_df[v_df['mes_referencia'] == mes_f].copy()
            
            st.dataframe(df_f, use_container_width=True)
            
            # Métricas
            t_venda = pd.to_numeric(df_f['valor']).sum()
            st.metric("Total Vendido", f"R$ {t_venda:,.2f}")
            
            if st.session_state.role == "ADM" and 'custo_total' in df_f.columns:
                t_custo = pd.to_numeric(df_f['custo_total']).sum()
                st.metric("Lucro Total", f"R$ {t_venda - t_custo:,.2f}")

# --- ABA 3: PRODUTOS (ADM) ---
if st.session_state.role == "ADM":
    with tabs[2]:
        col_a, col_b = st.columns(2)
        
        with col_a:
            with st.expander("➕ Novo Produto", expanded=True):
                with st.form("add_prod", clear_on_submit=True):
                    n = st.text_input("Nome")
                    p = st.number_input("Preço", min_value=0.0)
                    c = st.number_input("Custo", min_value=0.0)
                    if st.form_submit_button("Salvar"):
                        ws_produtos.append_row([n, p, c, "Ativo"])
                        st.rerun()

        with col_b:
            with st.expander("📝 Editar/Remover", expanded=True):
                all_p = pd.DataFrame(ws_produtos.get_all_records())
                if not all_p.empty:
                    all_p.columns = [str(c).strip().lower() for c in all_p.columns]
                    sel = st.selectbox("Produto", all_p['produto'].tolist())
                    item = all_p[all_p['produto'] == sel].iloc[0]
                    idx = all_p[all_p['produto'] == sel].index[0] + 2
                    
                    with st.form("edit_prod"):
                        e_n = st.text_input("Nome", value=item['produto'])
                        e_p = st.number_input("Preço", value=float(item['preco']))
                        e_c = st.number_input("Custo", value=float(item['custo']))
                        
                        c1, c2 = st.columns(2)
                        if c1.form_submit_button("💾 Salvar"):
                            ws_produtos.update_cell(idx, 1, e_n)
                            ws_produtos.update_cell(idx, 2, e_p)
                            ws_produtos.update_cell(idx, 3, e_c)
                            st.rerun()
                        if c2.form_submit_button("🗑️ Apagar"):
                            ws_produtos.delete_rows(idx)
                            st.rerun()

if st.sidebar.button("Sair"):
    st.session_state.logged_in = False
    st.rerun()
