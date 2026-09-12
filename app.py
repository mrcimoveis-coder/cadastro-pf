import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import io
import re
import urllib.request
import streamlit as st

# ReportLab para geração do PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# -----------------------------------------------------------------------------
# FUNÇÕES AUXILIARES DE VALIDAÇÃO E FORMATAÇÃO
# -----------------------------------------------------------------------------
def validar_cpf(cpf_raw: str) -> bool:
    cpf = re.sub(r'\D', '', cpf_raw)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in range(9, 11):
        val = sum(int(cpf[num]) * ((i + 1) - num) for num in range(0, i))
        digit = ((val * 10) % 11) % 10
        if str(digit) != cpf[i]:
            return False
    return True

def formatar_moeda(valor_raw: str) -> str:
    numeros = re.sub(r'[^\d,]', '', valor_raw.replace('.', ''))
    if not numeros:
        return "R$ 0,00"
    return f"R$ {numeros}"

# -----------------------------------------------------------------------------
# GERADOR DE PDF DA FICHA CADASTRAL
# -----------------------------------------------------------------------------
def gerar_pdf_ficha(dados: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    
    style_title = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=13, textColor=colors.HexColor("#C4001A"), spaceAfter=8)
    style_section = ParagraphStyle('Section', parent=styles['Heading2'], fontSize=11, textColor=colors.HexColor("#2B2B2B"), spaceBefore=10, spaceAfter=5)
    style_body = ParagraphStyle('Body', parent=styles['Normal'], fontSize=9, leading=12, textColor=colors.HexColor("#333333"))
    style_bold = ParagraphStyle('Bold', parent=style_body, fontName='Helvetica-Bold')

    elements = []

    # Inserção do Logotipo da MRC Imóveis no PDF
    try:
        logo_url = "https://raw.githubusercontent.com/mrcimoveis-coder/intranet/main/logo.jpeg"
        logo_data = urllib.request.urlopen(logo_url).read()
        logo_io = io.BytesIO(logo_data)
        img = Image(logo_io, width=140, height=48)
        img.hAlign = 'LEFT'
        elements.append(img)
        elements.append(Spacer(1, 8))
    except Exception:
        pass

    # Cabeçalho do Documento
    elements.append(Paragraph("<b>FICHA CADASTRAL DE LOCAÇÃO — PESSOA FÍSICA</b>", style_title))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#C4001A"), spaceAfter=12))

    def montar_tabela(dados_sec):
        data_table = []
        for k, v in dados_sec.items():
            p_key = Paragraph(f"<b>{k}:</b>", style_bold)
            p_val = Paragraph(str(v) if v else "-", style_body)
            data_table.append([p_key, p_val])
        t = Table(data_table, colWidths=[160, 360])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('PADDING', (0,0), (-1,-1), 4),
        ]))
        return t

    # 1. Dados Básicos
    elements.append(Paragraph("1. Identificação e Imóvel Pretendido", style_section))
    elements.append(montar_tabela({
        "Tipo de Cadastro": dados["tipo_cadastro"],
        "Nome Completo": dados["nome_completo"],
        "CPF": dados["cpf"],
        "RG": f"{dados['rg']} (Órgão: {dados['rg_orgao']})",
        "Data de Nascimento": dados["dt_nascimento"],
        "Estado Civil": dados["estado_civil"],
        "E-mail": dados["email_contato"],
        "Telefones": f"{dados['celular']} / {dados['tel_residencial']}",
        "Imóvel Pretendido": dados["endereco_imovel"],
        "Valor do Aluguel": dados["valor_aluguel"],
        "Garantia": f"{dados['garantia']} ({dados['detalhe_garantia']})",
        "Endereço Atual": f"{dados['endereco_atual']} (Moradia: {dados['tipo_residencia_atual']})"
    }))
    elements.append(Spacer(1, 8))

    # 2. Cônjuge (se houver)
    if dados.get("conj_nome"):
        elements.append(Paragraph("2. Dados do Cônjuge / Companheiro(a)", style_section))
        elements.append(montar_tabela({
            "Nome do Cônjuge": dados["conj_nome"],
            "CPF do Cônjuge": dados["conj_cpf"],
            "RG do Cônjuge": f"{dados['conj_rg']} (Órgão: {dados['conj_rg_orgao']})",
            "Profissão": dados["conj_profissao"],
            "Empresa": dados["conj_empresa"],
            "Cargo": dados["conj_cargo"],
            "Renda Bruta": dados["conj_renda"]
        }))
        elements.append(Spacer(1, 8))

    # 3. Profissional e Renda
    elements.append(Paragraph("3. Dados Profissionais e Renda", style_section))
    elements.append(montar_tabela({
        "Condição de Trabalho": dados["condicao_trabalho"],
        "Profissão": dados["profissao"],
        "Empresa / Órgão": dados["empresa"],
        "Cargo": dados["cargo"],
        "Renda Bruta Mensal": dados["renda_bruta"],
        "Outras Rendas": dados["outras_rendas"]
    }))
    elements.append(Spacer(1, 8))

    # 4. Referências e Observações
    elements.append(Paragraph("4. Referências e Observações", style_section))
    elements.append(montar_tabela({
        "Referências Pessoais": dados["ref_pessoais"],
        "Referências Bancárias": dados["ref_bancarias"],
        "Referências Comerciais": dados["ref_comerciais"],
        "Observações": dados["observacoes"]
    }))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# -----------------------------------------------------------------------------
# INTERFACE STREAMLIT
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Ficha Cadastral PF | MRC Imóveis", page_icon="📝", layout="centered")

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
    valor_aluguel = st.text_input("Valor do Aluguel (opcional)", placeholder="Ex: R$ 2.500,00")

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
        cpf = st.text_input("CPF *", placeholder="000.000.000-00")
        rg = st.text_input("Número do RG *")
        rg_orgao = st.text_input("Órgão Emissor / UF *", placeholder="Ex: SSP/DF")
        dt_nascimento = st.text_input("Data de Nascimento *", placeholder="DD/MM/AAAA")
    with col2:
        celular = st.text_input("Telefone Celular *", placeholder="(61) 90000-0000")
        tel_residencial = st.text_input("Telefone Residencial")
        estado_civil = st.selectbox("Estado Civil *", ["Solteiro(a)", "Casado(a)", "União Estável", "Divorciado(a)", "Viúvo(a)"])
        tipo_residencia_atual = st.selectbox("Moradia Atual *", ["Própria Quitada", "Própria Financiada", "Alugada"])

    endereco_atual = st.text_input("Endereço Residencial Atual Completo (com CEP) *")

    # FICHA COMPLETA DO CÔNJUGE (EXPANSÍVEL)
    conj_nome, conj_cpf, conj_rg, conj_rg_orgao, conj_profissao, conj_empresa, conj_cargo, conj_renda = "", "", "", "", "", "", "", ""
    if estado_civil in ["Casado(a)", "União Estável"]:
        st.markdown("---")
        st.subheader("3.1. Dados Completos do Cônjuge / Companheiro(a)")
        col_c1, col_c2 = st.columns(2)
        with col_c1:
            conj_nome = st.text_input("Nome Completo do Cônjuge *")
            conj_cpf = st.text_input("CPF do Cônjuge *", placeholder="000.000.000-00")
            conj_rg = st.text_input("RG do Cônjuge *")
            conj_rg_orgao = st.text_input("Órgão Emissor / UF Cônjuge *", placeholder="Ex: SSP/DF")
        with col_c2:
            conj_profissao = st.text_input("Profissão do Cônjuge *")
            conj_empresa = st.text_input("Empresa / Órgão do Cônjuge")
            conj_cargo = st.text_input("Cargo do Cônjuge")
            conj_renda = st.text_input("Renda Bruta Mensal do Cônjuge *", placeholder="Ex: R$ 5.000,00")

    st.subheader("4. Dados Profissionais e Renda")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        condicao_trabalho = st.selectbox("Condição de Trabalho *", ["Empregado", "Servidor Público", "Autônomo", "Empresário", "Aposentado/Pensionista"])
        profissao = st.text_input("Profissão *")
        empresa = st.text_input("Empresa / Órgão em que Trabalha *")
    with col_p2:
        cargo = st.text_input("Cargo *")
        renda_bruta = st.text_input("Renda Bruta Mensal (R$) *", placeholder="Ex: R$ 4.500,00")
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

# -----------------------------------------------------------------------------
# PROCESSAMENTO DO ENVIO
# -----------------------------------------------------------------------------
if btn_enviar:
    # Validações dos campos
    if not aceito:
        st.error("⚠️ Você precisa marcar o campo de declaração para enviar o cadastro.")
    elif not nome_completo or not cpf or not email_contato or not celular or not rg or not rg_orgao:
        st.error("⚠️ Por favor, preencha todos os campos obrigatórios marcados com *.")
    elif not validar_cpf(cpf):
        st.error("❌ O CPF digitado é inválido. Por favor, verifique o número informado.")
    elif estado_civil in ["Casado(a)", "União Estável"] and (not conj_nome or not conj_cpf or not validar_cpf(conj_cpf)):
        st.error("❌ Verifique os dados e o CPF do cônjuge/companheiro(a).")
    else:
        with st.spinner("Gerando Ficha Cadastral em PDF e enviando e-mail... Aguarde..."):
            try:
                dados_form = {
                    "tipo_cadastro": tipo_cadastro, "nome_completo": nome_completo, "cpf": cpf,
                    "rg": rg, "rg_orgao": rg_orgao, "dt_nascimento": dt_nascimento,
                    "estado_civil": estado_civil, "email_contato": email_contato, "celular": celular,
                    "tel_residencial": tel_residencial, "endereco_imovel": endereco_imovel,
                    "valor_aluguel": formatar_moeda(valor_aluguel), "garantia": garantia,
                    "detalhe_garantia": detalhe_garantia, "endereco_atual": endereco_atual,
                    "tipo_residencia_atual": tipo_residencia_atual, "conj_nome": conj_nome,
                    "conj_cpf": conj_cpf, "conj_rg": conj_rg, "conj_rg_orgao": conj_rg_orgao,
                    "conj_profissao": conj_profissao, "conj_empresa": conj_empresa,
                    "conj_cargo": conj_cargo, "conj_renda": formatar_moeda(conj_renda) if conj_renda else "",
                    "condicao_trabalho": condicao_trabalho, "profissao": profissao, "empresa": empresa,
                    "cargo": cargo, "renda_bruta": formatar_moeda(renda_bruta),
                    "outras_rendas": outras_rendas, "ref_pessoais": ref_pessoais,
                    "ref_bancarias": ref_bancarias, "ref_comerciais": ref_comerciais,
                    "observacoes": observacoes
                }

                # Gerar PDF em memória
                pdf_bytes = gerar_pdf_ficha(dados_form)

                # Credenciais SMTP
                smtp_server = st.secrets["smtp"]["server"]
                smtp_port = st.secrets["smtp"]["port"]
                sender_email = st.secrets["smtp"]["email"]
                sender_password = st.secrets["smtp"]["password"]
                receiver_email = "aluguel@mrcimoveis.com.br"

                msg = MIMEMultipart()
                msg['From'] = sender_email
                msg['To'] = receiver_email
                msg['Subject'] = f"NOVO CADASTRO PF [{tipo_cadastro}] - {nome_completo}"

                # CORPO DO E-MAIL EM FORMATO HTML ELEGANTE
                html_body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; color: #333333; background-color: #F4F6F8; padding: 20px;">
                    <div style="max-width: 650px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; border-top: 5px solid #C4001A; padding: 25px; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
                        <h2 style="color: #C4001A; margin-top: 0;">Novo Cadastro Recebido — MRC Imóveis</h2>
                        <p><strong>Tipo:</strong> {tipo_cadastro}</p>
                        <p><strong>Cliente:</strong> {nome_completo} (CPF: {cpf})</p>
                        <p><strong>E-mail:</strong> {email_contato} | <strong>Telefone:</strong> {celular}</p>
                        <p><strong>Imóvel Pretendido:</strong> {endereco_imovel}</p>
                        <p><strong>Renda Bruta:</strong> {formatar_moeda(renda_bruta)}</p>
                        <hr style="border: 0; border-top: 1px solid #E2E8F0; margin: 20px 0;">
                        <p style="color: #6C757D; font-size: 0.9em;">📌 <strong>A Ficha Cadastral completa está anexada neste e-mail no formato PDF (Ficha_Cadastral.pdf), juntamente com todos os documentos enviados pelo cliente.</strong></p>
                    </div>
                </body>
                </html>
                """
                msg.attach(MIMEText(html_body, 'html'))

                # Anexar a Ficha Cadastral em PDF
                part_pdf = MIMEBase('application', 'pdf')
                part_pdf.set_payload(pdf_bytes)
                encoders.encode_base64(part_pdf)
                part_pdf.add_header('Content-Disposition', f'attachment; filename="Ficha_Cadastral_{nome_completo.replace(" ", "_")}.pdf"')
                msg.attach(part_pdf)

                # Anexar documentos enviados pelo cliente
                def anexar_uploads(lista_uploads, categoria):
                    if lista_uploads:
                        for upload in lista_uploads:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(upload.read())
                            encoders.encode_base64(part)
                            part.add_header('Content-Disposition', f'attachment; filename="{categoria}_{upload.name}"')
                            msg.attach(part)

                anexar_uploads(doc_id, "ID")
                anexar_uploads(doc_estado_civil, "ESTADO_CIVIL")
                anexar_uploads(doc_residencia, "RESIDENCIA")
                anexar_uploads(doc_renda, "RENDA")
                anexar_uploads(doc_ir, "IMPOSTO_RENDA")

                # Conexão SMTP
                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, receiver_email, msg.as_string())
                server.quit()

                st.success("✅ Ficha cadastral e documentos enviados com sucesso para a MRC Imóveis!")
                st.balloons()
            except Exception as e:
                st.error(f"❌ Erro ao processar o envio: {e}")
