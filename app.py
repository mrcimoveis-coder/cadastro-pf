import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import io
import re
import urllib.request
import streamlit as st

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# -----------------------------------------------------------------------------
# VALIDAÇÕES E FORMATAÇÕES
# -----------------------------------------------------------------------------
def validar_cpf(cpf_raw: str) -> bool:
    cpf = re.sub(r'\D', '', str(cpf_raw))
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False
    for i in range(9, 11):
        val = sum(int(cpf[num]) * ((i + 1) - num) for num in range(0, i))
        digit = ((val * 10) % 11) % 10
        if str(digit) != cpf[i]:
            return False
    return True

def validar_cnpj(cnpj_raw: str) -> bool:
    cnpj = re.sub(r'\D', '', str(cnpj_raw))
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    pesos_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos_2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    soma_1 = sum(int(cnpj[i]) * pesos_1[i] for i in range(12))
    resto_1 = soma_1 % 11
    digito_1 = 0 if resto_1 < 2 else 11 - resto_1
    if int(cnpj[12]) != digito_1:
        return False
    soma_2 = sum(int(cnpj[i]) * pesos_2[i] for i in range(13))
    resto_2 = soma_2 % 11
    digito_2 = 0 if resto_2 < 2 else 11 - resto_2
    return int(cnpj[13]) == digito_2

def formatar_cpf(val: str) -> str:
    d = re.sub(r'\D', '', str(val))
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}" if len(d) == 11 else val

def formatar_cnpj(val: str) -> str:
    d = re.sub(r'\D', '', str(val))
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}" if len(d) == 14 else val

def formatar_telefone(val: str) -> str:
    d = re.sub(r'\D', '', str(val))
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    elif len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return val

def formatar_data(val: str) -> str:
    d = re.sub(r'\D', '', str(val))
    return f"{d[:2]}/{d[2:4]}/{d[4:]}" if len(d) == 8 else val

def formatar_moeda(val: str) -> str:
    if not val:
        return ""
    clean = str(val).upper().replace("R$", "").strip()
    clean_digits = re.sub(r'[^\d,.]', '', clean)
    if ',' in clean_digits:
        clean_digits = clean_digits.replace('.', '').replace(',', '.')
    else:
        if clean_digits.count('.') > 1:
            clean_digits = clean_digits.replace('.', '')
        elif clean_digits.count('.') == 1 and len(clean_digits.split('.')[1]) != 2:
            clean_digits = clean_digits.replace('.', '')
    try:
        num = float(clean_digits)
        return f"R$ {num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except ValueError:
        return val

# -----------------------------------------------------------------------------
# GERADOR DE PDF
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

    try:
        logo_url = "https://raw.githubusercontent.com/mrcimoveis-coder/intranet/main/logo.jpeg"
        logo_data = urllib.request.urlopen(logo_url).read()
        elements.append(Image(io.BytesIO(logo_data), width=140, height=48, hAlign='LEFT'))
        elements.append(Spacer(1, 8))
    except Exception:
        pass

    elements.append(Paragraph(f"<b>FICHA CADASTRAL — {dados['tipo_cadastro'].upper()}</b>", style_title))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#C4001A"), spaceAfter=12))

    def montar_tabela(dados_sec):
        data_table = []
        for k, v in dados_sec.items():
            if v:
                data_table.append([Paragraph(f"<b>{k}:</b>", style_bold), Paragraph(str(v), style_body)])
        if not data_table:
            return Spacer(1, 1)
        t = Table(data_table, colWidths=[160, 360])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F8FAFC")),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E8F0")),
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('PADDING', (0,0), (-1,-1), 4),
        ]))
        return t

    # 1. Identificação
    sec1 = {
        "Tipo de Cadastro": dados["tipo_cadastro"],
        "Nome / Razão Social": dados["nome_completo"],
        "CPF / CNPJ": dados["cpf_cnpj"],
        "RG (Sócio Rep.)": f"{dados['rg']} (Órgão: {dados['rg_orgao']})" if dados.get('rg') else "",
        "Data Nasc. / Fundação": dados["dt_nascimento"],
        "Estado Civil (Sócio Rep.)": dados.get("estado_civil"),
        "E-mail": dados["email_contato"],
        "Telefone Celular / Comercial": dados["celular"],
        "Imóvel Pretendido": dados["endereco_imovel"],
        "Valor do Aluguel": dados["valor_aluguel"],
    }
    
    if dados["tipo_cadastro"] == "Locatário (Inquilino)":
        sec1["Garantia Oferecida"] = f"{dados['garantia']} ({dados['detalhe_garantia']})" if dados.get('detalhe_garantia') else dados.get('garantia')
        sec1["Motivo Mudança"] = dados.get("motivo_mudanca_novo")
    elif dados["tipo_cadastro"] == "Fiador (Pessoa Física)":
        sec1["Imóvel Próprio no DF"] = dados.get("imovel_fiador_status")
    else:
        sec1["Imóvel da Empresa em Garantia (DF)"] = dados.get("imovel_fiador_status")
        sec1["Sócio Administrador Responsável"] = dados.get("socio_resp_nome")

    elements.append(Paragraph("1. Identificação e Imóvel Pretendido", style_section))
    elements.append(montar_tabela(sec1))
    elements.append(Spacer(1, 8))

    # 2. Endereço
    sec2 = {
        "Endereço Residencial / Sede": dados["endereco_atual"],
        "Moradia / Sede Atual": dados["tipo_residencia_atual"]
    }
    elements.append(Paragraph("2. Informações de Endereço Atual", style_section))
    elements.append(montar_tabela(sec2))
    elements.append(Spacer(1, 8))

    # 3. Profissional / Renda
    sec3 = {
        "Condição de Trabalho / Atividade": dados["condicao_trabalho"],
        "Profissão / Cargo": dados["profissao"],
        "Empresa / Órgão": dados["empresa"],
        "Renda Bruta / Faturamento Mensal": dados["renda_bruta"],
    }
    elements.append(Paragraph("3. Dados Profissionais / Renda", style_section))
    elements.append(montar_tabela(sec3))
    elements.append(Spacer(1, 8))

    # 4. Cônjuge (se houver)
    if dados.get("conj_nome"):
        sec4 = {
            "Nome do Cônjuge": dados["conj_nome"],
            "CPF do Cônjuge": dados["conj_cpf"],
            "Renda Cônjuge": dados.get("conj_renda")
        }
        elements.append(Paragraph("4. Dados do Cônjuge", style_section))
        elements.append(montar_tabela(sec4))
        elements.append(Spacer(1, 8))

    # 5. Referências e Observações
    sec5 = {
        "Referencias Pessoais / Comerciais": dados["ref_pessoais"],
        "Observações": dados["observacoes"]
    }
    elements.append(Paragraph("5. Referências e Observações", style_section))
    elements.append(montar_tabela(sec5))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# -----------------------------------------------------------------------------
# INTERFACE STREAMLIT
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Ficha Cadastral | MRC Imóveis", page_icon="📝", layout="centered")

try:
    st.image("https://raw.githubusercontent.com/mrcimoveis-coder/intranet/main/logo.jpeg", width=260)
except Exception:
    pass

st.title("📝 Ficha Cadastral")
st.write("Preencha os dados e anexe a documentação necessária para análise da locação.")

st.subheader("1. Identificação e Imóvel Pretendido")
tipo_cadastro = st.radio("Você é: *", ["Locatário (Inquilino)", "Fiador (Pessoa Física)", "Fiador (Pessoa Jurídica)"], horizontal=True)

email_contato = st.text_input("Seu E-mail principal *", placeholder="exemplo@email.com")
endereco_imovel = st.text_input("Endereço do imóvel a ser alugado *")
valor_aluguel_raw = st.text_input("Valor do Aluguel Mensal (opcional)", placeholder="Ex: 3000")

motivo_mudanca_novo, garantia, detalhe_garantia, imovel_fiador_status, socio_resp_nome = "", "", "", "", ""

if tipo_cadastro == "Locatário (Inquilino)":
    motivo_mudanca_novo = st.text_input("Motivo da sua mudança para o novo imóvel *")
    st.subheader("2. Garantia da Locação")
    garantia = st.selectbox("Garantia oferecida *", ["2 Fiadores do DF com renda e imóvel", "Caução / Título de Capitalização", "Seguro Fiança", "Fiança Bancária", "CredPago", "Outra"])
    detalhe_garantia = st.text_input("Detalhamento da garantia (caso necessário)")
elif tipo_cadastro == "Fiador (Pessoa Física)":
    st.subheader("2. Imóvel Próprio do Fiador (PF)")
    imovel_fiador_status = st.selectbox("Situação do imóvel próprio no DF oferecido em garantia *", ["Própria Quitada", "Própria Financiada", "Consórcio"])
else:
    st.subheader("2. Imóvel Próprio da Empresa Fiadora (PJ)")
    socio_resp_nome = st.text_input("Nome Completo do Sócio-Administrador que assina pela Empresa *")
    imovel_fiador_status = st.selectbox("Situação do imóvel próprio da empresa no DF *", ["Própria Quitada", "Própria Financiada", "Consórcio"])

st.subheader("3. Dados Principais")
col1, col2 = st.columns(2)
with col1:
    label_nome = "Razão Social da Empresa *" if tipo_cadastro == "Fiador (Pessoa Jurídica)" else "Nome Completo *"
    nome_completo = st.text_input(label_nome)
    
    label_doc = "CNPJ da Empresa *" if tipo_cadastro == "Fiador (Pessoa Jurídica)" else "CPF *"
    cpf_cnpj_raw = st.text_input(label_doc, placeholder="00.000.000/0001-00" if tipo_cadastro == "Fiador (Pessoa Jurídica)" else "000.000.000-00")
    
    rg = st.text_input("RG / Inscrição Estadual *" if tipo_cadastro == "Fiador (Pessoa Jurídica)" else "Número do RG *")
    rg_orgao = st.text_input("Órgão Emissor / UF *" if tipo_cadastro != "Fiador (Pessoa Jurídica)" else "UF Inscrição *")
    dt_nasc_raw = st.text_input("Data de Fundação *" if tipo_cadastro == "Fiador (Pessoa Jurídica)" else "Data de Nascimento *", placeholder="DD/MM/AAAA")
with col2:
    celular_raw = st.text_input("Telefone Comercial *" if tipo_cadastro == "Fiador (Pessoa Jurídica)" else "Telefone Celular *", placeholder="(61) 90000-0000")
    tel_res_raw = st.text_input("Telefone Secundário", placeholder="(61) 3000-0000")
    estado_civil = st.selectbox("Estado Civil *" if tipo_cadastro != "Fiador (Pessoa Jurídica)" else "Regime da Empresa *", ["Solteiro(a)", "Casado(a)", "União Estável", "Divorciado(a)", "Viúvo(a)"] if tipo_cadastro != "Fiador (Pessoa Jurídica)" else ["LTDA", "S/A", "EIRELI", "SLU"])
    tipo_residencia_atual = st.selectbox("Sede Atual *" if tipo_cadastro == "Fiador (Pessoa Jurídica)" else "Moradia Atual *", ["Própria Quitada", "Própria Financiada", "Alugada"])

endereco_atual = st.text_input("Endereço Completo da Sede (com CEP) *" if tipo_cadastro == "Fiador (Pessoa Jurídica)" else "Endereço Residencial Atual Completo (com CEP) *")

conj_nome, conj_cpf_raw, conj_renda_raw = "", "", ""
if estado_civil in ["Casado(a)", "União Estável"] and tipo_cadastro != "Fiador (Pessoa Jurídica)":
    st.markdown("---")
    st.subheader("3.1. Dados do Cônjuge")
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        conj_nome = st.text_input("Nome Completo do Cônjuge *")
        conj_cpf_raw = st.text_input("CPF do Cônjuge *", placeholder="000.000.000-00")
    with col_c2:
        conj_renda_raw = st.text_input("Renda Bruta Mensal Cônjuge *", placeholder="Ex: 5000")

st.markdown("---")
st.subheader("4. Dados Profissionais e Renda / Faturamento")
col_p1, col_p2 = st.columns(2)
with col_p1:
    condicao_trabalho = st.selectbox("Ramo de Atividade *" if tipo_cadastro == "Fiador (Pessoa Jurídica)" else "Condição de Trabalho *", ["Serviços", "Comércio", "Indústria"] if tipo_cadastro == "Fiador (Pessoa Jurídica)" else ["Empregado", "Servidor Público", "Autônomo", "Empresário", "Aposentado/Pensionista"])
    profissao = st.text_input("Objeto Social *" if tipo_cadastro == "Fiador (Pessoa Jurídica)" else "Profissão *")
    empresa = st.text_input("Razão Social *" if tipo_cadastro == "Fiador (Pessoa Jurídica)" else "Empresa / Órgão em que Trabalha *")
with col_p2:
    renda_bruta_raw = st.text_input("Faturamento Médio Mensal (R$) *" if tipo_cadastro == "Fiador (Pessoa Jurídica)" else "Renda Bruta Mensal (R$) *", placeholder="Ex: 10000")

st.markdown("---")
st.subheader("5. Referências e Anexos")
ref_pessoais = st.text_area("Referências Comerciais / Pessoais (Nome e Telefone de 02 contatos) *")

doc_id = st.file_uploader("1. Documento de Identificação (RG/CPF ou Contrato Social) *", accept_multiple_files=True)
doc_residencia = st.file_uploader("2. Comprovante de Endereço / Sede *", accept_multiple_files=True)
doc_renda = st.file_uploader("3. Comprovantes de Renda / Balanço Patrimonial *", accept_multiple_files=True)

observacoes = st.text_area("Observações Adicionais")
aceito = st.checkbox("Declaro que as informações prestadas são verdadeiras e autorizo a análise cadastral pela MRC Imóveis. *")

btn_enviar = st.button("🚀 Enviar Ficha Cadastral", type="primary", use_container_width=True)

if btn_enviar:
    cpf_cnpj = formatar_cnpj(cpf_cnpj_raw) if tipo_cadastro == "Fiador (Pessoa Jurídica)" else formatar_cpf(cpf_cnpj_raw)
    celular = formatar_telefone(celular_raw)
    dt_nascimento = formatar_data(dt_nasc_raw)
    valor_aluguel = formatar_moeda(valor_aluguel_raw)
    renda_bruta = formatar_moeda(renda_bruta_raw)

    erros = []
    if not aceito:
        erros.append("Marque a caixa de declaração autorizando a análise.")
    if not nome_completo or not cpf_cnpj_raw or not email_contato or not celular_raw or not endereco_imovel or not endereco_atual:
        erros.append("Preencha todos os campos obrigatórios (*).")

    if tipo_cadastro == "Fiador (Pessoa Jurídica)":
        if not validar_cnpj(cpf_cnpj_raw):
            erros.append("CNPJ inválido.")
    else:
        if not validar_cpf(cpf_cnpj_raw):
            erros.append("CPF inválido.")

    if erros:
        for err in erros:
            st.error(f"⚠️ {err}")
    else:
        with st.spinner("Enviando cadastro..."):
            try:
                dados_form = {
                    "tipo_cadastro": tipo_cadastro, "nome_completo": nome_completo, "cpf_cnpj": cpf_cnpj,
                    "rg": rg, "rg_orgao": rg_orgao, "dt_nascimento": dt_nascimento, "estado_civil": estado_civil,
                    "email_contato": email_contato, "celular": celular, "endereco_imovel": endereco_imovel,
                    "valor_aluguel": valor_aluguel, "garantia": garantia, "detalhe_garantia": detalhe_garantia,
                    "motivo_mudanca_novo": motivo_mudanca_novo, "imovel_fiador_status": imovel_fiador_status,
                    "socio_resp_nome": socio_resp_nome, "endereco_atual": endereco_atual,
                    "tipo_residencia_atual": tipo_residencia_atual, "conj_nome": conj_nome, "conj_cpf": formatar_cpf(conj_cpf_raw),
                    "conj_renda": formatar_moeda(conj_renda_raw), "condicao_trabalho": condicao_trabalho,
                    "profissao": profissao, "empresa": empresa, "renda_bruta": renda_bruta,
                    "ref_pessoais": ref_pessoais, "observacoes": observacoes
                }

                pdf_bytes = gerar_pdf_ficha(dados_form)

                smtp_server = st.secrets["smtp"]["server"]
                smtp_port = st.secrets["smtp"]["port"]
                sender_email = st.secrets["smtp"]["email"]
                sender_password = st.secrets["smtp"]["password"]
                receiver_email = "aluguel@mrcimoveis.com.br"

                msg = MIMEMultipart()
                msg['From'] = sender_email
                msg['To'] = receiver_email
                msg['Subject'] = f"NOVO CADASTRO [{tipo_cadastro}] - {nome_completo}"

                html_body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; color: #333333; background-color: #F4F6F8; padding: 20px;">
                    <div style="max-width: 650px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; border-top: 5px solid #C4001A; padding: 25px;">
                        <h2 style="color: #C4001A; margin-top: 0;">Novo Cadastro Recebido — MRC Imóveis</h2>
                        <p><strong>Tipo:</strong> {tipo_cadastro}</p>
                        <p><strong>Nome/Empresa:</strong> {nome_completo} ({cpf_cnpj})</p>
                        <p><strong>E-mail:</strong> {email_contato} | <strong>Telefone:</strong> {celular}</p>
                        <p><strong>Imóvel Pretendido:</strong> {endereco_imovel}</p>
                        <hr style="border: 0; border-top: 1px solid #E2E8F0; margin: 20px 0;">
                        <p style="color: #6C757D; font-size: 0.9em;">📌 <strong>A Ficha Cadastral completa está anexada em PDF.</strong></p>
                    </div>
                </body>
                </html>
                """
                msg.attach(MIMEText(html_body, 'html'))

                part_pdf = MIMEBase('application', 'pdf')
                part_pdf.set_payload(pdf_bytes)
                encoders.encode_base64(part_pdf)
                part_pdf.add_header('Content-Disposition', f'attachment; filename="Ficha_Cadastral_{nome_completo.replace(" ", "_")}.pdf"')
                msg.attach(part_pdf)

                def anexar_uploads(lista_uploads, categoria):
                    if lista_uploads:
                        for upload in lista_uploads:
                            part = MIMEBase('application', 'octet-stream')
                            part.set_payload(upload.read())
                            encoders.encode_base64(part)
                            part.add_header('Content-Disposition', f'attachment; filename="{categoria}_{upload.name}"')
                            msg.attach(part)

                anexar_uploads(doc_id, "IDENTIFICACAO")
                anexar_uploads(doc_residencia, "ENDERECO")
                anexar_uploads(doc_renda, "COMPROVANTE_RENDA")

                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, receiver_email, msg.as_string())
                server.quit()

                st.success("✅ Ficha cadastral e documentos enviados com sucesso para a MRC Imóveis!")
                st.balloons()
            except Exception as e:
                st.error(f"❌ Erro ao processar o envio: {e}")
