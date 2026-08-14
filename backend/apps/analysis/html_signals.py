"""Extração dos sinais de uma página, com o `html.parser` da stdlib.

Os sinais que o ERD pede são presença de tag e de atributo: existe `<form>`? existe link para
o WhatsApp? existe `meta[name=viewport]`? Para isso o parser da stdlib basta — e ele é
tolerante a HTML quebrado, que é o normal em site de pequeno negócio. `BeautifulSoup` seria
mais confortável, não mais correto, e custaria uma dependência.

Nada aqui julga. "Não tem agendamento" é observação; se isso vale uma venda é a Etapa 10.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

# Domínios de link que caracterizam contato por WhatsApp.
PADRAO_WHATSAPP = re.compile(r"(wa\.me|api\.whatsapp\.com|web\.whatsapp\.com|whatsapp://)", re.I)

# Plataformas de agendamento comuns no Brasil, mais os termos que sinalizam a intenção.
PADRAO_AGENDAMENTO = re.compile(
    r"(calendly|agendor|simplybook|doctoralia|boaconsulta|zenklub|acuity|booking|"
    r"agendar|agendamento|marcar[\s-]?(consulta|hor[áa]rio))",
    re.I,
)

# Sinais de e-commerce. `add-to-cart` cobre WooCommerce e boa parte dos temas prontos.
PADRAO_CARRINHO = re.compile(
    r"(add[\s_-]?to[\s_-]?cart|adicionar ao carrinho|/carrinho|/cart|shopify|woocommerce|"
    r"vtex|nuvemshop|loja[\s-]?integrada)",
    re.I,
)

# Campos que caracterizam um formulário de contato, e não uma caixa de busca ou login.
CAMPOS_DE_CONTATO = ("email", "e-mail", "mensagem", "message", "telefone", "phone", "assunto")


@dataclass
class Signals:
    title: str = ""
    meta_description: str = ""
    has_viewport: bool = False
    has_contact_form: bool = False
    has_whatsapp: bool = False
    has_booking: bool = False
    has_cart: bool = False
    form_count: int = 0
    extras: dict = field(default_factory=dict)


class _Coletor(HTMLParser):
    """Percorre a página uma vez, juntando o que interessa."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sinais = Signals()
        self._dentro_do_title = False
        self._campos_do_form: list[str] = []
        self._dentro_de_form = False

    def handle_starttag(self, tag, attrs):
        atributos = {chave.lower(): (valor or "") for chave, valor in attrs}

        if tag == "title":
            self._dentro_do_title = True

        elif tag == "meta":
            nome = atributos.get("name", "").lower()
            if nome == "viewport":
                self.sinais.has_viewport = True
            elif nome == "description" and not self.sinais.meta_description:
                self.sinais.meta_description = atributos.get("content", "").strip()[:500]

        elif tag == "form":
            self._dentro_de_form = True
            self._campos_do_form = []
            self.sinais.form_count += 1

        elif tag in ("input", "textarea", "select") and self._dentro_de_form:
            # Nome, id, placeholder e type juntos: temas prontos usam qualquer um deles.
            self._campos_do_form.append(
                " ".join(
                    atributos.get(k, "")
                    for k in ("name", "id", "placeholder", "type", "aria-label")
                ).lower()
            )
            if tag == "textarea":
                # Área de texto livre é o sinal mais forte de formulário de contato: busca e
                # login não têm.
                self._campos_do_form.append("mensagem")

        elif tag == "a":
            href = atributos.get("href", "")
            if PADRAO_WHATSAPP.search(href):
                self.sinais.has_whatsapp = True
            if PADRAO_AGENDAMENTO.search(href):
                self.sinais.has_booking = True
            if PADRAO_CARRINHO.search(href):
                self.sinais.has_cart = True

    def handle_endtag(self, tag):
        if tag == "title":
            self._dentro_do_title = False
        elif tag == "form":
            texto = " ".join(self._campos_do_form)
            if any(campo in texto for campo in CAMPOS_DE_CONTATO):
                self.sinais.has_contact_form = True
            self._dentro_de_form = False

    def handle_data(self, data):
        if self._dentro_do_title and not self.sinais.title:
            self.sinais.title = data.strip()[:300]


def extract(html: str) -> Signals:
    """Lê a página e devolve os sinais.

    HTML malformado não pode derrubar uma varredura: o `HTMLParser` é tolerante, mas se algo
    escapar, o que se perde é um sinal — não o scan inteiro nem a fila.
    """
    coletor = _Coletor()
    try:
        coletor.feed(html)
        coletor.close()
    except Exception:  # noqa: BLE001 - ver acima; o motivo fica registrado no sinal
        coletor.sinais.extras["parse_incompleto"] = True

    sinais = coletor.sinais

    # Alguns sinais aparecem no texto da página e não em `href`: botão de agendamento em
    # `<button>`, WhatsApp escrito por extenso, carrinho pintado por JavaScript.
    if not sinais.has_booking:
        sinais.has_booking = bool(PADRAO_AGENDAMENTO.search(html))
    if not sinais.has_whatsapp:
        sinais.has_whatsapp = bool(PADRAO_WHATSAPP.search(html))
    if not sinais.has_cart:
        sinais.has_cart = bool(PADRAO_CARRINHO.search(html))

    return sinais
