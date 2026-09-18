import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import io
import re
import unicodedata
import urllib.request
import streamlit as st
import streamlit.components.v1 as components
from PIL import Image as PILImage, ImageChops

# ReportLab para geração do PDF
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

LOGO_URL = "https://raw.githubusercontent.com/mrcimoveis-coder/portal-intranet/main/logo.jpeg"

@st.cache_data(ttl=3600)
def obter_logo_bytes():
    """Baixa e recorta as margens brancas da identidade visual atual da MRC."""
    logo_data = urllib.request.urlopen(LOGO_URL, timeout=10).read()
    with PILImage.open(io.BytesIO(logo_data)).convert("RGB") as imagem:
        fundo = PILImage.new("RGB", imagem.size, "white")
        diferenca = ImageChops.difference(imagem, fundo).convert("L")
        limite = diferenca.point(lambda pixel: 255 if pixel > 12 else 0)
        caixa = limite.getbbox()
        if caixa:
            imagem = imagem.crop(caixa)
        saida = io.BytesIO()
        imagem.save(saida, format="PNG", optimize=True)
        return saida.getvalue()

# -----------------------------------------------------------------------------
# FUNÇÕES AUXILIARES DE VALIDAÇÃO E FORMATAÇÃO
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

def formatar_cpf(val: str) -> str:
    d = re.sub(r'\D', '', str(val))
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return val

def formatar_telefone(val: str) -> str:
    d = re.sub(r'\D', '', str(val))
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    elif len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return val

def formatar_data(val: str) -> str:
    d = re.sub(r'\D', '', str(val))
    if len(d) == 8:
        return f"{d[:2]}/{d[2:4]}/{d[4:]}"
    return val

def formatar_moeda(val: str) -> str:
    if not val:
        return ""
    clean = str(val).upper().replace("R$", "").strip()
    if not clean:
        return ""
    clean_digits = re.sub(r'[^\d,.]', '', clean)
    if ',' in clean_digits:
        clean_digits = clean_digits.replace('.', '').replace(',', '.')
    else:
        if clean_digits.count('.') > 1:
            clean_digits = clean_digits.replace('.', '')
        elif clean_digits.count('.') == 1:
            parts = clean_digits.split('.')
            if len(parts[1]) != 2:
                clean_digits = clean_digits.replace('.', '')
    try:
        num = float(clean_digits)
        formatted = f"{num:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {formatted}"
    except ValueError:
        return val

def sanitizar_nome_arquivo(nome):
    """Higieniza nomes de arquivos para impedir rejeição do Gmail (evita 'noname')"""
    n = unicodedata.normalize('NFKD', str(nome)).encode('ASCII', 'ignore').decode('utf-8')
    n = re.sub(r'[^a-zA-Z0-9.]', '_', n)
    n = re.sub(r'\.+', '.', n)
    return re.sub(r'_+', '_', n).strip('_')

def ativar_sincronizacao_autopreenchimento():
    """Faz o Streamlit reconhecer valores escolhidos no preenchimento automático."""
    components.html(
        """
        <script>
        (() => {
          const host = window.parent;
          const doc = host.document;
          if (host.__mrcAutofillSyncInstalled) return;
          host.__mrcAutofillSyncInstalled = true;

          const style = doc.createElement("style");
          style.textContent = `
            @keyframes mrcAutofillStarted { from {} to {} }
            input:-webkit-autofill { animation-name: mrcAutofillStarted; animation-duration: 0.01s; }
          `;
          doc.head.appendChild(style);

          const campos = () => doc.querySelectorAll(
            'input:not([type="file"]):not([type="checkbox"]):not([type="radio"]):not([type="button"]):not([type="submit"]), textarea'
          );

          const registrar = (input) => {
            if (input && 'value' in input) input.dataset.mrcUltimoValor = input.value;
          };

          const sincronizar = (input) => {
            if (!input || !('value' in input)) return;
            const valor = input.value;
            const anterior = input.dataset.mrcUltimoValor;
            if (valor === anterior) return;
            const tracker = input._valueTracker;
            if (tracker) tracker.setValue(anterior ?? "");
            input.dispatchEvent(new InputEvent("input", {
              bubbles: true,
              composed: true,
              inputType: "insertReplacementText",
              data: valor,
            }));
            input.dispatchEvent(new Event("change", { bubbles: true, composed: true }));
            registrar(input);
          };

          doc.addEventListener("animationstart", (event) => {
            if (event.animationName === "mrcAutofillStarted") {
              host.setTimeout(() => sincronizar(event.target), 50);
            }
          }, true);

          doc.addEventListener("input", (event) => registrar(event.target), true);
          doc.addEventListener("change", (event) => registrar(event.target), true);
          doc.addEventListener("focusin", (event) => registrar(event.target), true);
          doc.addEventListener("focusout", (event) => sincronizar(event.target), true);
          doc.addEventListener("click", () => host.setTimeout(() => campos().forEach(sincronizar), 0), true);

          host.setInterval(() => {
            campos().forEach(sincronizar);
          }, 250);
        })();
        </script>
        """,
        height=0,
        width=0,
    )

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

    try:
        logo_data = obter_logo_bytes()
        logo_io = io.BytesIO(logo_data)
        img = Image(logo_io, width=140, height=48)
        img.hAlign = 'LEFT'
        elements.append(img)
        elements.append(Spacer(1, 8))
    except Exception:
        pass

    elements.append(Paragraph("<b>FICHA CADASTRAL DE LOCAÇÃO — PESSOA FÍSICA</b>", style_title))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#C4001A"), spaceAfter=12))

    def montar_tabela(dados_sec):
        data_table = []
        for k, v in dados_sec.items():
            if v:
                p_key = Paragraph(f"<b>{k}:</b>", style_bold)
                p_val = Paragraph(str(v), style_body)
                data_table.append([p_key, p_val])
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
        "Nome Completo": dados["nome_completo"],
        "CPF": dados["cpf"],
        "RG": f"{dados['rg']} (Órgão: {dados['rg_orgao']})",
        "Data de Nascimento": dados["dt_nascimento"],
        "Estado Civil": dados["estado_civil"],
        "E-mail": dados["email_contato"],
        "Telefone Celular": dados["celular"],
        "Telefone Residencial": dados["tel_residencial"],
        "Imóvel Pretendido": dados["endereco_imovel"],
        "Valor do Aluguel": dados["valor_aluguel"],
    }
    
    if dados["tipo_cadastro"] == "Locatário (Inquilino)":
        sec1["Garantia Oferecida"] = f"{dados['garantia']} ({dados['detalhe_garantia']})" if dados.get('detalhe_garantia') else dados.get('garantia')
        sec1["Motivo Mudança (Novo Imóvel)"] = dados.get("motivo_mudanca_novo")
    else:
        if dados["tipo_cadastro"] == "Fiador (de Empresa / PJ)":
            sec1["Empresa Afiançada"] = dados.get("empresa_afiancada")
        sec1["Imóvel Próprio do Fiador"] = dados.get("imovel_fiador_status")

    elements.append(Paragraph("1. Identificação e Imóvel Pretendido", style_section))
    elements.append(montar_tabela(sec1))
    elements.append(Spacer(1, 8))

    # 2. Residência Atual
    sec2 = {
        "Endereço Residencial Atual": dados["endereco_atual"],
        "Moradia Atual": dados["tipo_residencia_atual"]
    }
    if dados["tipo_residencia_atual"] == "Alugada":
        sec2.update({
            "Valor do Aluguel Atual": dados.get("aluguel_atual_valor"),
            "Imobiliária / Locador": dados.get("aluguel_atual_locador"),
            "Telefone Imobiliária / Locador": dados.get("aluguel_atual_fone"),
            "Tempo de Residência": dados.get("aluguel_atual_tempo"),
            "Motivo da Saída Atual": dados.get("aluguel_atual_motivo")
        })
    elements.append(Paragraph("2. Informações de Residência Atual", style_section))
    elements.append(montar_tabela(sec2))
    elements.append(Spacer(1, 8))

    # 3. Profissional e Renda (Principal)
    sec3 = {
        "Condição de Trabalho": dados["condicao_trabalho"],
        "Profissão": dados["profissao"],
        "Empresa / Órgão": dados["empresa"],
        "Cargo": dados["cargo"],
        "Data de Admissão": dados["dt_admissao"],
        "Endereço Empresa/Trabalho": dados["end_empresa"],
        "Telefone Comercial": dados["tel_comercial"],
        "Renda Bruta Mensal": dados["renda_bruta"],
        "Outras Rendas": dados["outras_rendas"]
    }
    elements.append(Paragraph("3. Dados Profissionais e Renda (Principal)", style_section))
    elements.append(montar_tabela(sec3))
    elements.append(Spacer(1, 8))

    # 4. Cônjuge (se houver)
    if dados.get("conj_nome"):
        sec4 = {
            "Nome do Cônjuge": dados["conj_nome"],
            "CPF do Cônjuge": dados["conj_cpf"],
            "RG do Cônjuge": f"{dados['conj_rg']} (Órgão: {dados['conj_rg_orgao']})",
            "Data de Nascimento": dados.get("conj_dt_nasc"),
            "Celular": dados.get("conj_celular"),
            "E-mail": dados.get("conj_email"),
            "Condição de Trabalho": dados.get("conj_condicao"),
            "Profissão": dados.get("conj_profissao"),
            "Empresa / Órgão": dados.get("conj_empresa"),
            "Cargo": dados.get("conj_cargo"),
            "Data de Admissão": dados.get("conj_dt_admissao"),
            "Endereço da Empresa": dados.get("conj_end_empresa"),
            "Telefone Comercial": dados.get("conj_tel_comercial"),
            "Renda Bruta Mensal": dados.get("conj_renda"),
            "Outras Rendas": dados.get("conj_outras_rendas")
        }
        elements.append(Paragraph("4. Dados Completos do Cônjuge / Companheiro(a)", style_section))
        elements.append(montar_tabela(sec4))
        elements.append(Spacer(1, 8))

    # 5. Moradores Adicionais
    if dados.get("outros_moradores_flag"):
        sec5 = {
            "Morarão Outras Pessoas?": dados["outros_moradores_flag"],
            "Relação de Moradores": dados.get("outros_moradores_lista")
        }
        elements.append(Paragraph("5. Utilização do Imóvel / Outros Moradores", style_section))
        elements.append(montar_tabela(sec5))
        elements.append(Spacer(1, 8))

    # 6. Referências e Observações
    sec6 = {
        "Referências Pessoais": dados["ref_pessoais"],
        "Referências Bancárias": dados["ref_bancarias"],
        "Referências Comerciais": dados["ref_comerciais"],
        "Observações": dados["observacoes"]
    }
    elements.append(Paragraph("6. Referências e Observações", style_section))
    elements.append(montar_tabela(sec6))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()


# -----------------------------------------------------------------------------
# INTERFACE STREAMLIT
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Ficha Cadastral PF | MRC Imóveis", page_icon="📝", layout="centered")
ativar_sincronizacao_autopreenchimento()

# ESTADO DE ENVIO COM SUCESSO (TELA DE AGRADECIMENTO)
if "enviado_sucesso" not in st.session_state:
    st.session_state.enviado_sucesso = False

if st.session_state.enviado_sucesso:
    st.balloons()
    try:
        st.image(obter_logo_bytes(), width=260)
    except Exception:
        pass
    
    st.success("✅ **Ficha Cadastral e Documentos Enviados com Sucesso!**")
    st.markdown("""
    ### Obrigado por enviar seus dados para a **MRC Imóveis**! 🎉
    
    Sua ficha cadastral e documentação foram encaminhadas com sucesso para o nosso setor de análise de locação.
    
    **O que acontece agora?**
    * Nossa equipe iniciará a análise das informações prestadas.
    * Entraremos em contato em breve através do e-mail ou telefone informado na ficha.
    
    ---
    📬 **Contatos Úteis:**
    * **E-mail:** aluguel@mrcimoveis.com.br / comercial@mrcimoveis.com.br
    """)
    st.markdown("---")
    if st.button("🔄 Preencher outro cadastro"):
        st.session_state.enviado_sucesso = False
        st.rerun()
    st.stop()

# FORMULÁRIO PADRÃO
try:
    st.image(obter_logo_bytes(), width=260)
except Exception:
    pass

st.title("📝 Ficha Cadastral - Pessoa Física")
st.write("Preencha os dados abaixo e anexe a documentação necessária para análise da locação.")

# 1. Identificação
st.subheader("1. Identificação e Imóvel Pretendido")
tipo_cadastro = st.radio(
    "Você é: *", 
    ["Locatário (Inquilino)", "Fiador (de Inquilino PF)", "Fiador (de Empresa / PJ)"], 
    horizontal=True
)
email_contato = st.text_input("Seu E-mail principal *", placeholder="exemplo@email.com")
endereco_imovel = st.text_input("Endereço do imóvel a ser alugado *")
valor_aluguel_raw = st.text_input("Valor do Aluguel Mensal (opcional)", placeholder="Ex: 3000 ou R$ 3.000,00")

motivo_mudanca_novo = ""
garantia = ""
detalhe_garantia = ""
imovel_fiador_status = ""
empresa_afiancada = ""

# LÓGICA CONDICIONAL DA SEÇÃO 2
if tipo_cadastro == "Locatário (Inquilino)":
    motivo_mudanca_novo = st.text_input("Motivo da sua mudança para o novo imóvel *")

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

else:
    st.subheader("2. Informações sobre Imóvel Próprio do Fiador")
    
    if tipo_cadastro == "Fiador (de Empresa / PJ)":
        empresa_afiancada = st.text_input("Razão Social ou CNPJ da empresa que você está afiançando *")
        
    imovel_fiador_status = st.selectbox(
        "Como Fiador, qual a situação do seu imóvel próprio no DF? *",
        [
            "Própria Quitada",
            "Própria Financiada",
            "Consórcio",
            "Não possui imóvel próprio no DF"
        ]
    )

# 3. Dados Pessoais
st.subheader("3. Dados Pessoais")
col1, col2 = st.columns(2)
with col1:
    nome_completo = st.text_input("Nome Completo *")
    cpf_raw = st.text_input("CPF *", placeholder="000.000.000-00")
    rg = st.text_input("Número do RG *")
    rg_orgao = st.text_input("Órgão Emissor / UF *", placeholder="Ex: SSP/DF")
    dt_nasc_raw = st.text_input("Data de Nascimento *", placeholder="DD/MM/AAAA")
with col2:
    celular_raw = st.text_input("Telefone Celular *", placeholder="(61) 90000-0000")
    tel_res_raw = st.text_input("Telefone Residencial", placeholder="(61) 3000-0000")
    estado_civil = st.selectbox("Estado Civil *", ["Solteiro(a)", "Casado(a)", "União Estável", "Divorciado(a)", "Viúvo(a)"])
    tipo_residencia_atual = st.selectbox("Moradia Atual *", ["Própria Quitada", "Própria Financiada", "Alugada"])

# Se Moradia Atual for Alugada
aluguel_atual_valor_raw, aluguel_atual_locador, aluguel_atual_fone_raw, aluguel_atual_tempo, aluguel_atual_motivo = "", "", "", "", ""
if tipo_residencia_atual == "Alugada":
    st.info("ℹ️ Preencha os detalhes do aluguel atual:")
    col_a1, col_a2 = st.columns(2)
    with col_a1:
        aluguel_atual_valor_raw = st.text_input("Valor do aluguel pago atualmente *", placeholder="Ex: 2500")
        aluguel_atual_locador = st.text_input("Nome da Imobiliária ou Proprietário *")
        aluguel_atual_fone_raw = st.text_input("Telefone da Imobiliária ou Locador *")
    with col_a2:
        aluguel_atual_tempo = st.text_input("Tempo de residência no imóvel atual *", placeholder="Ex: 2 anos")
        aluguel_atual_motivo = st.text_input("Motivo da mudança do imóvel atual *")

endereco_atual = st.text_input("Endereço Residencial Atual Completo (com CEP) *")

# 4. Profissional e Renda (Principal)
st.markdown("---")
st.subheader("4. Dados Profissionais e Renda (Locatário / Fiador)")
col_p1, col_p2 = st.columns(2)
with col_p1:
    condicao_trabalho = st.selectbox("Condição de Trabalho *", ["Empregado", "Servidor Público", "Autônomo", "Empresário", "Aposentado/Pensionista"])
    profissao = st.text_input("Profissão *")
    empresa = st.text_input("Empresa / Órgão em que Trabalha (ou última se Aposentado/Pensionista) *")
    cargo = st.text_input("Cargo *")
    dt_admissao_raw = st.text_input("Data de Admissão no Emprego Atual *", placeholder="DD/MM/AAAA")
with col_p2:
    end_empresa = st.text_input("Endereço da Empresa que Trabalha *")
    tel_comercial_raw = st.text_input("Telefone do Trabalho (Comercial) *")
    renda_bruta_raw = st.text_input("Renda Bruta Mensal (R$) *", placeholder="Ex: 4500")
    outras_rendas = st.text_input("Outras Rendas / Origem")

# 4.1. Dados Completos do Cônjuge / Companheiro(a)
conj_nome, conj_cpf_raw, conj_rg, conj_rg_orgao, conj_dt_nasc_raw, conj_celular_raw, conj_email = "", "", "", "", "", "", ""
conj_condicao, conj_profissao, conj_empresa, conj_cargo, conj_dt_admissao_raw, conj_end_empresa, conj_tel_comercial_raw, conj_renda_raw, conj_outras_rendas = "", "", "", "", "", "", "", "", ""

if estado_civil in ["Casado(a)", "União Estável"]:
    st.markdown("---")
    st.subheader("4.1. Dados do Cônjuge / Companheiro(a)")
    st.caption("Preencha as informações pessoais e profissionais do cônjuge.")
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        conj_nome = st.text_input("Nome Completo do Cônjuge *")
        conj_cpf_raw = st.text_input("CPF do Cônjuge *", placeholder="000.000.000-00")
        conj_rg = st.text_input("RG do Cônjuge *")
        conj_rg_orgao = st.text_input("Órgão Emissor / UF Cônjuge *", placeholder="Ex: SSP/DF")
    with col_c2:
        conj_dt_nasc_raw = st.text_input("Data de Nascimento do Cônjuge *", placeholder="DD/MM/AAAA")
        conj_celular_raw = st.text_input("Celular do Cônjuge *", placeholder="(61) 90000-0000")
        conj_email = st.text_input("E-mail do Cônjuge *", placeholder="conjuge@email.com")

    st.markdown("**Vida Profissional do Cônjuge**")
    col_cp1, col_cp2 = st.columns(2)
    with col_cp1:
        conj_condicao = st.selectbox("Condição de Trabalho Cônjuge *", ["Empregado", "Servidor Público", "Autônomo", "Empresário", "Aposentado/Pensionista"])
        conj_profissao = st.text_input("Profissão do Cônjuge *")
        conj_empresa = st.text_input("Empresa / Órgão do Cônjuge (ou última se Aposentado) *")
        conj_cargo = st.text_input("Cargo do Cônjuge *")
    with col_cp2:
        conj_dt_admissao_raw = st.text_input("Data de Admissão Cônjuge *", placeholder="DD/MM/AAAA")
        conj_end_empresa = st.text_input("Endereço do Trabalho Cônjuge *")
        conj_tel_comercial_raw = st.text_input("Telefone Comercial Cônjuge *")
        conj_renda_raw = st.text_input("Renda Bruta Mensal Cônjuge *", placeholder="Ex: 5000")
        conj_outras_rendas = st.text_input("Outras Rendas Cônjuge (Origem)")

# 5. Outros Moradores (exclusivo para Locatário)
outros_moradores_flag, outros_moradores_lista = "", ""
if tipo_cadastro == "Locatário (Inquilino)":
    st.markdown("---")
    st.subheader("5. Sobre a Utilização do Imóvel")
    outros_moradores_flag = st.radio(
        "Além do locatário e eventual cônjuge ou companheiro(a), alguém mais utilizará o imóvel para moradia? *",
        ["NÃO", "SIM"],
        horizontal=True
    )
    if outros_moradores_flag == "SIM":
        outros_moradores_lista = st.text_area(
            "Quem mais irá residir no imóvel locado além do locatário e cônjuge ou companheiro(a)? *",
            placeholder="Informe Nome Completo e CPF de cada morador extra."
        )

# 6. Referências
st.markdown("---")
st.subheader("6. Referências")
ref_pessoais = st.text_area("Referências Pessoais (Nome completo e celular de 02 pessoas) *")
ref_bancarias = st.text_input("Referências Bancárias (Banco, Agência, Conta e Gerente)")
ref_comerciais = st.text_input("Referências Comerciais")

# 7. Documentos
st.markdown("---")
st.subheader("7. Envio de Documentos (Anexos)")

st.warning("⚠️ **Atenção para enviar vários arquivos:** Para colocar mais de um arquivo no mesmo campo (Ex: 3 contracheques), você deve **selecionar todos eles de uma só vez** na janela que abrir. Se você anexar um e depois clicar no botão para anexar o segundo, o primeiro será substituído.")

st.info("Formatos aceitos: PDF, JPG, PNG.")

doc_id = st.file_uploader("1. Documento de Identificação (RG/CPF ou CNH) *", accept_multiple_files=True)
doc_estado_civil = st.file_uploader("2. Comprovante de Estado Civil (Certidões)", accept_multiple_files=True)
doc_residencia = st.file_uploader("3. Comprovante de Residência Atual (últimos 3 meses) *", accept_multiple_files=True)
doc_renda = st.file_uploader("4. Comprovantes de Renda (3 últimos contracheques / extratos) *", accept_multiple_files=True)
doc_ir = st.file_uploader("5. Declaração de Imposto de Renda com Recibo *", accept_multiple_files=True)

observacoes = st.text_area("Observações Adicionais")
aceito = st.checkbox("Declaro que as informações prestadas são verdadeiras e autorizo a análise cadastral pela MRC Imóveis. *")

btn_enviar = st.button("🚀 Enviar Cadastro e Documentos", type="primary", use_container_width=True)

# -----------------------------------------------------------------------------
# PROCESSAMENTO DO ENVIO
# -----------------------------------------------------------------------------
if btn_enviar:
    cpf = formatar_cpf(cpf_raw)
    celular = formatar_telefone(celular_raw)
    tel_residencial = formatar_telefone(tel_res_raw)
    dt_nascimento = formatar_data(dt_nasc_raw)
    valor_aluguel = formatar_moeda(valor_aluguel_raw)
    renda_bruta = formatar_moeda(renda_bruta_raw)
    dt_admissao = formatar_data(dt_admissao_raw)
    tel_comercial = formatar_telefone(tel_comercial_raw)

    aluguel_atual_valor = formatar_moeda(aluguel_atual_valor_raw)
    aluguel_atual_fone = formatar_telefone(aluguel_atual_fone_raw)

    conj_cpf = formatar_cpf(conj_cpf_raw)
    conj_celular = formatar_telefone(conj_celular_raw)
    conj_dt_nasc = formatar_data(conj_dt_nasc_raw)
    conj_dt_admissao = formatar_data(conj_dt_admissao_raw)
    conj_tel_comercial = formatar_telefone(conj_tel_comercial_raw)
    conj_renda = formatar_moeda(conj_renda_raw)

    erros = []
    if not aceito:
        erros.append("Você precisa marcar a caixa de declaração autorizando a análise.")
    if not nome_completo or not cpf_raw or not email_contato or not celular_raw or not rg or not rg_orgao or not endereco_imovel or not endereco_atual:
        erros.append("Preencha todos os campos obrigatórios (*) da seção de identificação e endereço.")
    if not validar_cpf(cpf_raw):
        erros.append("O CPF informado no cadastro principal é inválido.")
    
    if tipo_cadastro == "Locatário (Inquilino)":
        if not motivo_mudanca_novo:
            erros.append("Informe o motivo da mudança para o novo imóvel.")
        if not garantia:
            erros.append("Selecione a garantia oferecida para a locação.")
    else:
        if tipo_cadastro == "Fiador (de Empresa / PJ)" and not empresa_afiancada:
            erros.append("Informe a Razão Social ou CNPJ da empresa que você está afiançando.")
        if not imovel_fiador_status:
            erros.append("Informe a situação do seu imóvel próprio como Fiador.")

    if tipo_residencia_atual == "Alugada" and (not aluguel_atual_valor_raw or not aluguel_atual_locador or not aluguel_atual_fone_raw or not aluguel_atual_tempo or not aluguel_atual_motivo):
        erros.append("Preencha todas as informações sobre o aluguel pago atualmente.")

    if not profissao or not empresa or not cargo or not dt_admissao_raw or not end_empresa or not tel_comercial_raw or not renda_bruta_raw:
        erros.append("Preencha todas as informações profissionais e de renda.")

    if estado_civil in ["Casado(a)", "União Estável"]:
        if not conj_nome or not conj_cpf_raw or not conj_rg or not conj_rg_orgao or not conj_profissao or not conj_empresa or not conj_renda_raw:
            erros.append("Preencha as informações pessoais e profissionais obrigatórias do cônjuge.")
        elif not validar_cpf(conj_cpf_raw):
            erros.append("O CPF do cônjuge é inválido.")

    if tipo_cadastro == "Locatário (Inquilino)" and outros_moradores_flag == "SIM" and not outros_moradores_lista:
        erros.append("Informe a relação de outros moradores que residirão no imóvel.")

    if not ref_pessoais:
        erros.append("Informe ao menos 02 referências pessoais com nome e telefone.")

    if erros:
        for err in erros:
            st.error(f"⚠️ {err}")
    else:
        with st.spinner("Gerando Ficha Cadastral em PDF e enviando e-mail... Aguarde..."):
            try:
                dados_form = {
                    "tipo_cadastro": tipo_cadastro, "nome_completo": nome_completo, "cpf": cpf,
                    "rg": rg, "rg_orgao": rg_orgao, "dt_nascimento": dt_nascimento,
                    "estado_civil": estado_civil, "email_contato": email_contato, "celular": celular,
                    "tel_residencial": tel_residencial, "endereco_imovel": endereco_imovel,
                    "valor_aluguel": valor_aluguel, "garantia": garantia,
                    "detalhe_garantia": detalhe_garantia, "motivo_mudanca_novo": motivo_mudanca_novo,
                    "imovel_fiador_status": imovel_fiador_status, "empresa_afiancada": empresa_afiancada,
                    "endereco_atual": endereco_atual, "tipo_residencia_atual": tipo_residencia_atual,
                    "aluguel_atual_valor": aluguel_atual_valor, "aluguel_atual_locador": aluguel_atual_locador,
                    "aluguel_atual_fone": aluguel_atual_fone, "aluguel_atual_tempo": aluguel_atual_tempo,
                    "aluguel_atual_motivo": aluguel_atual_motivo,
                    "conj_nome": conj_nome, "conj_cpf": conj_cpf, "conj_rg": conj_rg, "conj_rg_orgao": conj_rg_orgao,
                    "conj_dt_nasc": conj_dt_nasc, "conj_celular": conj_celular, "conj_email": conj_email,
                    "conj_condicao": conj_condicao, "conj_profissao": conj_profissao, "conj_empresa": conj_empresa,
                    "conj_cargo": conj_cargo, "conj_dt_admissao": conj_dt_admissao, "conj_end_empresa": conj_end_empresa,
                    "conj_tel_comercial": conj_tel_comercial, "conj_renda": conj_renda, "conj_outras_rendas": conj_outras_rendas,
                    "condicao_trabalho": condicao_trabalho, "profissao": profissao, "empresa": empresa,
                    "cargo": cargo, "dt_admissao": dt_admissao, "end_empresa": end_empresa,
                    "tel_comercial": tel_comercial, "renda_bruta": renda_bruta, "outras_rendas": outras_rendas,
                    "outros_moradores_flag": outros_moradores_flag, "outros_moradores_lista": outros_moradores_lista,
                    "ref_pessoais": ref_pessoais, "ref_bancarias": ref_bancarias, "ref_comerciais": ref_comerciais,
                    "observacoes": observacoes
                }

                pdf_bytes = gerar_pdf_ficha(dados_form)

                smtp_server = st.secrets["smtp"]["server"]
                smtp_port = st.secrets["smtp"]["port"]
                sender_email = st.secrets["smtp"]["email"]
                sender_password = st.secrets["smtp"]["password"]
                receiver_emails = ["aluguel@mrcimoveis.com.br", "comercial@mrcimoveis.com.br"]

                msg = MIMEMultipart()
                msg['From'] = sender_email
                msg['To'] = ", ".join(receiver_emails)
                msg['Subject'] = f"NOVO CADASTRO PF [{tipo_cadastro}] - {nome_completo}"

                html_body = f"""
                <html>
                <body style="font-family: Arial, sans-serif; color: #333333; background-color: #F4F6F8; padding: 20px;">
                    <div style="max-width: 650px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; border-top: 5px solid #C4001A; padding: 25px; box-shadow: 0 4px 10px rgba(0,0,0,0.05);">
                        <h2 style="color: #C4001A; margin-top: 0;">Novo Cadastro Recebido — MRC Imóveis</h2>
                        <p><strong>Tipo:</strong> {tipo_cadastro}</p>
                        <p><strong>Cliente:</strong> {nome_completo} (CPF: {cpf})</p>
                        <p><strong>E-mail:</strong> {email_contato} | <strong>Telefone:</strong> {celular}</p>
                        <p><strong>Imóvel Pretendido:</strong> {endereco_imovel}</p>
                        <p><strong>Renda Bruta:</strong> {renda_bruta}</p>
                        <hr style="border: 0; border-top: 1px solid #E2E8F0; margin: 20px 0;">
                        <p style="color: #6C757D; font-size: 0.9em;">📌 <strong>A Ficha Cadastral completa e formatada está anexada em PDF (Ficha_Cadastral.pdf), juntamente com todos os documentos enviados pelo cliente.</strong></p>
                    </div>
                </body>
                </html>
                """
                msg.attach(MIMEText(html_body, 'html'))

                part_pdf = MIMEBase('application', 'pdf')
                part_pdf.set_payload(pdf_bytes)
                encoders.encode_base64(part_pdf)
                part_pdf.add_header('Content-Disposition', 'attachment', filename=f"Ficha_Cadastral_{nome_completo.replace(' ', '_')}.pdf")
                msg.attach(part_pdf)

                def anexar_uploads(lista_uploads, categoria):
                    if lista_uploads:
                        for upload in lista_uploads:
                            upload.seek(0)
                            file_bytes = upload.read()
                            if not file_bytes:
                                continue
                            
                            nome_seguro = sanitizar_nome_arquivo(upload.name)
                            nome_final = f"{categoria}_{nome_seguro}"
                            
                            part = MIMEBase('application', 'octet-stream', name=nome_final)
                            part.set_payload(file_bytes)
                            encoders.encode_base64(part)
                            part.add_header('Content-Disposition', 'attachment', filename=nome_final)
                            msg.attach(part)

                anexar_uploads(doc_id, "ID")
                anexar_uploads(doc_estado_civil, "ESTADO_CIVIL")
                anexar_uploads(doc_residencia, "RESIDENCIA")
                anexar_uploads(doc_renda, "RENDA")
                anexar_uploads(doc_ir, "IMPOSTO_RENDA")

                server = smtplib.SMTP(smtp_server, smtp_port)
                server.starttls()
                server.login(sender_email, sender_password)
                server.sendmail(sender_email, receiver_emails, msg.as_string())
                server.quit()

                # REDIRECIONA PARA A TELA DE AGRADECIMENTO
                st.session_state.enviado_sucesso = True
                st.rerun()

            except Exception as e:
                st.error(f"❌ Erro ao processar o envio: {e}")
