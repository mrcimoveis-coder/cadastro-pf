import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import streamlit as st

# Configuração da Página
st.set_page_config(page_title="Ficha Cadastral PF | MRC Imóveis", page_icon="📝", layout="centered")

# Exibição Destacada da Logo da MRC Imóveis
try:
    st.image("https://raw.githubusercontent.com/mrcimoveis-coder/intranet/main/logo.jpeg", width=260)
except Exception:
    pass

st.title("📝 Ficha Cadastral - Pessoa Física")
st.write("Preencha os dados abaixo e anexe a documentação necessária para análise da locação.")

with st.form("form_cadastro_pf", clear_on_submit=False):
    st.subheader("1. Identificação e Imóvel Pretendido")
    tipo_cadastro = st.radio("Você é:", ["Locatário (Inquilino)", "Fiador"], horizontal=True)
    email_contato = st.text_input("Seu E-mail principal *", placeholder="exemplo@email.com")
    endereco_imovel = st.text_input("Endereço do imóvel a ser alugado *")
    valor_aluguel = st.text_input("Valor do Aluguel (opcional)")

    st.subheader("2. Garantia da Locação")
    garantia = st.selectbox(
        "Garantia oferecida *",
        [
            "2 Fiadores do DF com renda e imóvel",
            "Caução / Título de Capitalização",
            "Seguro Fiança",
            "Fiança Bancária / Associação",
            "CredPago",
            "Outra"
        ]
    )
    detalhe_garantia = st.text_input("Detalhamento da garantia (caso necessário)")

    st.subheader("3. Dados Pessoais")
    col1, col2 = st.columns(2)
    with col1:
        nome_completo = st.text_input("Nome Completo *")
        cpf = st.text_input("CPF *")
        rg = st.text_input("RG *")
        dt_nascimento = st.text_input("Data de Nascimento *", placeholder="DD/MM/AAAA")
    with col2:
        celular = st.text_input("Telefone Celular *")
        tel_residencial = st.text_input("Telefone Residencial")
        estado_civil = st.selectbox("Estado Civil *", ["Solteiro(a)", "Casado(a)", "Divorciado(a)", "União Estável", "Viúvo(a)"])
        tipo_residencia_atual = st.selectbox("Moradia Atual *", ["Própria Quitada", "Própria Financiada", "Alugada"])

    endereco_atual = st.text_input("Endereço Residencial Atual Completo (com CEP) *")

    # Dados do Cônjuge (caso aplicável)
    if estado_civil in ["Casado(a)", "União Estável"]:
        st.markdown("---")
        st.subheader("3.1. Dados do Cônjuge / Companheiro(a)")
        conj_nome = st.text_input("Nome Completo do Cônjuge")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            conj_cpf = st.text_input("CPF do Cônjuge")
            conj_rg = st.text_input("RG do Cônjuge")
        with col_c2:
            conj_celular = st.text_input("Celular do Cônjuge")
            conj_profissao = st.text_input("Profissão do Cônjuge")
        conj_renda = st.text_input("Renda Bruta Mensal do Cônjuge (R$)")

    st.subheader("4. Dados Profissionais e Renda")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        condicao_trabalho = st.selectbox("Condição de Trabalho *", ["Empregado", "Servidor Público", "Autônomo", "Empresário", "Aposentado/Pensionista"])
        profissao = st.text_input("Profissão *")
        empresa = st.text_input("Empresa / Órgão em que Trabalha *")
    with col_p2:
        cargo = st.text_input("Cargo *")
        renda_bruta = st.text_input("Renda Bruta Mensal (R$) *")
        outras_rendas = st.text_input("Outras Rendas / Origem")

    st.subheader("5. Referências")
    ref_pessoais = st.text_area("Referências Pessoais (Nome e Telefone de 2 pessoas) *")
    ref_bancarias = st.text_input("Referências Bancárias (Banco, Agência, Conta)")
    ref_comerciais = st.text_input("Referências Comerciais")

    st.subheader("6. Envio de Documentos (Anexos)")
    st.info("Formatos aceitos: PDF, JPG, PNG. Você pode selecionar múltiplos arquivos em cada campo.")
    
    doc_id = st.file_uploader("1. Documento de Identificação (RG/CPF ou CNH) *", accept_multiple_files=True)
    doc_estado_civil = st.file_uploader("2. Comprovante de Estado Civil (Certidões)", accept_multiple_files=True)
    doc_residencia = st.file_uploader("3. Comprovante de Residência Atual (últimos 3 meses) *", accept_multiple_files=True)
    doc_renda = st.file_uploader("4. Comprovantes de Renda (3 últimos contracheques / extratos) *", accept_multiple_files=True)
    doc_ir = st.file_uploader("5. Declaração de Imposto de Renda com Recibo *", accept_multiple_files=True)

    observacoes = st.text_area("Observações Adicionais")

    aceito = st.checkbox("Declaro que as informações prestadas são verdadeiras e autorizo a análise cadastral pela MRC Imóveis. *")

    btn_enviar = st.form_submit_button("🚀 Enviar Cadastro e Documentos", type="primary")

# Processamento e disparo do e-mail
if btn_enviar:
    if not aceito:
        st.error("⚠️ Você precisa marcar o campo de declaração para enviar o cadastro.")
    elif not nome_completo or not cpf or not email_contato or not celular:
        st.error("⚠️ Por favor, preencha todos os campos obrigatórios marcados com *.")
    else:
        with st.spinner("Enviando seu cadastro e anexando documentos... Aguarde..."):
            try:
                smtp_server = st.secrets["smtp"]["server"]
                smtp_port = st.secrets["smtp"]["port"]
                sender_email = st.secrets["smtp"]["email"]
                sender_password = st.secrets["smtp"]["password"]
                receiver_email = "aluguel@mrcimoveis.com.br"  # Destino fixo MRC

                msg = MIMEMultipart()
                msg['From'] = sender_email
                msg['To'] = receiver_email
                msg['Subject'] = f"NOVO CADASTRO PF [{tipo_cadastro}] - {nome_completo}"

                corpo = f"""
                ====================================================
                FICHA CADASTRAL DE PESSOA FÍSICA - MRC IMÓVEIS
                ====================================================
                TIPO: {tipo_cadastro}
                NOME: {nome_completo}
                CPF: {cpf} | RG: {rg}
                NASCIMENTO: {dt_nascimento} | ESTADO CIVIL: {estado_civil}
                E-MAIL: {email_contato}
                TELEFONES: {celular} / {tel_residencial}

                --- IMÓVEL PRETENDIDO ---
                ENDEREÇO: {endereco_imovel}
                VALOR ALUGUEL: {valor_aluguel}
                GARANTIA: {garantia} ({detalhe_garantia})

                --- ENDEREÇO ATUAL ---
                {endereco_atual} (Moradia: {tipo_residencia_atual})

                --- DADOS PROFISSIONAIS E RENDA ---
                CONDIÇÃO: {condicao_trabalho}
                PROFISSÃO: {profissao} | CARGO: {cargo}
                EMPRESA: {empresa}
                RENDA BRUTA: {renda_bruta}
                OUTRAS RENDAS: {outras_rendas}

                --- REFERÊNCIAS ---
                PESSOAIS: {ref_pessoais}
                BANCÁRIAS: {ref_bancarias}
                COMERCIAIS: {ref_comerciais}

                --- OBSERVAÇÕES ---
                {observacoes}
                """
                msg.attach(MIMEText(corpo, 'plain'))

                def anexar_arquivos(lista_uploads, categoria):
                    if lista_uploads:
                        for upload in lista_uploads:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(upload.read())
                            encoders.encode_base64(part)
                            part.add_header('Content-Disposition', f'attachment; filename="{categoria}_{upload.name}"')
                            msg.attach(part)

                anexar_arquivos(doc_id, "ID")
                anexar_arquivos(doc_estado_civil, "ESTADO_CIVIL")
                anexar_arquivos(doc_residencia, "RESIDENCIA")
                anexar_arquivos(doc_renda, "RENDA")
                anexar_arquivos(doc_ir, "IMPOSTO_RENDA")

                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, receiver_email, msg.as_string())
                server.quit()

                st.success("✅ Ficha cadastral e documentos enviados com sucesso para a MRC Imóveis!")
                st.balloons()
            except Exception as e:
                st.error(f"❌ Erro ao enviar o cadastro: {e}. Verifique as configurações de SMTP nos Secrets do Streamlit.")
