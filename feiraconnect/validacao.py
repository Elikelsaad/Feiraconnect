"""
Validações dos cadastros: CPF, CNPJ, CEP, celular, data de nascimento, login e senha.
Cada função devolve o valor limpo (ou levanta ErroValidacao com a mensagem para o usuário).
"""
import re
from datetime import date, datetime

LOGIN_MIN, LOGIN_MAX = 3, 10      # "login com no máximo dez dígitos"
SENHA_MIN, SENHA_MAX = 6, 10      # senha também limitada a 10 caracteres
IDADE_MINIMA = 18


class ErroValidacao(ValueError):
    pass


def so_digitos(texto):
    return re.sub(r"\D", "", texto or "")


def cpf_valido(cpf):
    c = so_digitos(cpf)
    if len(c) != 11 or c == c[0] * 11:
        return False
    for tam in (9, 10):
        soma = sum(int(c[i]) * (tam + 1 - i) for i in range(tam))
        dig = (soma * 10 % 11) % 10
        if dig != int(c[tam]):
            return False
    return True


def cnpj_valido(cnpj):
    c = so_digitos(cnpj)
    if len(c) != 14 or c == c[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, pos in ((pesos1, 12), (pesos2, 13)):
        soma = sum(int(c[i]) * pesos[i] for i in range(len(pesos)))
        resto = soma % 11
        dig = 0 if resto < 2 else 11 - resto
        if dig != int(c[pos]):
            return False
    return True


def validar_documento(valor, aceita_cnpj=False):
    """Retorna (tipo, digitos)."""
    d = so_digitos(valor)
    if len(d) == 11 and cpf_valido(d):
        return "CPF", d
    if aceita_cnpj and len(d) == 14 and cnpj_valido(d):
        return "CNPJ", d
    raise ErroValidacao("CPF ou CNPJ inválido." if aceita_cnpj else "CPF inválido.")


def formatar_documento(tipo, d):
    if tipo == "CPF" and len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if tipo == "CNPJ" and len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return d


def mascarar_documento(tipo, d):
    """Exibição protegida (LGPD): ***.456.789-**"""
    if tipo == "CPF" and len(d) == 11:
        return f"***.{d[3:6]}.{d[6:9]}-**"
    if tipo == "CNPJ" and len(d) == 14:
        return f"{d[:2]}.***.***/{d[8:12]}-**"
    return "***"


def validar_cep(cep):
    d = so_digitos(cep)
    if len(d) != 8:
        raise ErroValidacao("CEP deve ter 8 números.")
    return f"{d[:5]}-{d[5:]}"


def validar_celular(cel):
    d = so_digitos(cel)
    if d.startswith("55") and len(d) in (12, 13):
        d = d[2:]
    if len(d) != 11 or d[2] != "9":
        raise ErroValidacao("Celular inválido. Use DDD + número com 9 dígitos, ex.: (92) 99123-4567.")
    return f"({d[:2]}) {d[2:7]}-{d[7:]}"


def validar_nascimento(valor, idade_minima=IDADE_MINIMA):
    try:
        nasc = datetime.strptime(valor.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
        try:
            nasc = datetime.strptime(valor.strip(), "%d/%m/%Y").date()
        except (ValueError, AttributeError):
            raise ErroValidacao("Data de nascimento inválida.")
    hoje = date.today()
    idade = hoje.year - nasc.year - ((hoje.month, hoje.day) < (nasc.month, nasc.day))
    if idade < idade_minima:
        raise ErroValidacao(f"É preciso ter pelo menos {idade_minima} anos para se cadastrar.")
    if idade > 120:
        raise ErroValidacao("Data de nascimento inválida.")
    return nasc.isoformat()


def validar_login(login):
    login = (login or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9._]{%d,%d}" % (LOGIN_MIN, LOGIN_MAX), login):
        raise ErroValidacao(f"O login deve ter de {LOGIN_MIN} a {LOGIN_MAX} caracteres "
                            "(letras sem acento, números, ponto ou sublinhado).")
    return login


def validar_senha(senha, confirmacao=None):
    senha = senha or ""
    if not SENHA_MIN <= len(senha) <= SENHA_MAX:
        raise ErroValidacao(f"A senha deve ter de {SENHA_MIN} a {SENHA_MAX} caracteres.")
    if not (re.search(r"[A-Za-z]", senha) and re.search(r"\d", senha)):
        raise ErroValidacao("A senha precisa ter letras e números.")
    if confirmacao is not None and senha != confirmacao:
        raise ErroValidacao("A confirmação da senha não confere.")
    return senha


def validar_nome(nome):
    nome = re.sub(r"\s+", " ", (nome or "").strip())
    if len(nome) < 5 or " " not in nome:
        raise ErroValidacao("Informe o nome completo (nome e sobrenome).")
    return nome[:120]


def obrigatorio(valor, campo, maximo=200):
    v = (valor or "").strip()
    if not v:
        raise ErroValidacao(f"Preencha o campo {campo}.")
    return v[:maximo]
