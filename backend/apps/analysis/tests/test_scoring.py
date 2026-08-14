"""O motor de pontuação e seu breakdown.

Duas propriedades que o ADR-0008 exige e que o teste tem de segurar:

- o breakdown **soma** o valor exibido (a menos do corte, e o corte é visível);
- ajustar peso é `UPDATE`, não deploy.
"""

import pytest

from apps.analysis.models import Score, ScoreRule, WebsiteScan
from apps.analysis.rules import CompanyContext
from apps.analysis.scoring import MAXIMO, compute, ruleset_version, score_company
from apps.companies.models import Company, CompanyContact, CompanyWebsite

pytestmark = pytest.mark.django_db


def _regra(code, points, **extra):
    return ScoreRule.objects.create(
        code=code,
        name=code,
        points=points,
        reason_template=extra.pop("reason_template", f"motivo de {code}"),
        **extra,
    )


def _ctx(**campos) -> CompanyContext:
    padrao = {"company_id": 1, "name": "X", "website_status": "NOT_FOUND", "has_website": False}
    return CompanyContext(**{**padrao, **campos})


class TestAritmetica:
    def test_soma_as_regras_que_acionaram(self, db):
        regras = [_regra("sem_site", 35), _regra("poucos_contatos", -20)]

        resultado = compute(_ctx(), regras)

        assert resultado.bruto == 15
        assert resultado.value == 15
        assert {c for c, _, _ in resultado.parcelas} == {"sem_site", "poucos_contatos"}

    def test_regra_que_nao_acionou_nao_entra_no_breakdown(self, db):
        regras = [_regra("sem_site", 35), _regra("site_sem_https", 15)]

        resultado = compute(_ctx(), regras)

        assert [c for c, _, _ in resultado.parcelas] == ["sem_site"]

    def test_o_breakdown_soma_o_valor(self, db):
        """Relatório que não fecha é o pior tipo de relatório."""
        regras = [_regra("sem_site", 30), _regra("poucos_contatos", -10)]

        resultado = compute(_ctx(), regras)

        assert sum(p for _, p, _ in resultado.parcelas) == resultado.value

    def test_corte_e_no_fim_e_sobre_a_soma(self, db):
        """Cortar parcela a parcela esconderia que o conjunto passou do teto."""
        regras = [_regra("sem_site", 80), _regra("poucos_contatos", 80)]

        resultado = compute(_ctx(), regras)

        assert resultado.bruto == 160
        assert resultado.value == MAXIMO

    def test_nao_fica_negativo(self, db):
        resultado = compute(
            _ctx(website_status="FOUND", has_website=True), [_regra("poucos_contatos", -50)]
        )

        assert resultado.bruto == -50
        assert resultado.value == 0

    def test_sem_regras_cadastradas_da_zero_e_nao_erro(self, db):
        """ADR-0008, seção operacional."""
        assert compute(_ctx(), []).value == 0


class TestPesoNoBanco:
    def test_mudar_o_peso_muda_o_score_sem_deploy(self, db):
        """É o ponto do ADR-0008 inteiro."""
        regra = _regra("sem_site", 10)
        assert compute(_ctx(), [regra]).value == 10

        regra.points = 40
        regra.save()
        assert compute(_ctx(), [ScoreRule.objects.get(pk=regra.pk)]).value == 40

    def test_desativar_regra_a_tira_da_conta(self, db):
        _regra("sem_site", 35)
        _regra("poucos_contatos", 10, is_active=False)

        empresa = Company.objects.create(
            name="Sem nada", website_status=Company.WebsiteStatus.NOT_FOUND
        )
        score = score_company(empresa)

        assert score.value == 35
        assert set(score.components.values_list("rule_code", flat=True)) == {"sem_site"}

    def test_parametro_vem_do_banco(self, db):
        regra = _regra("poucos_contatos", 10, params={"minimo": 3})
        ctx = _ctx(phone_count=2)

        assert compute(ctx, [regra]).value == 10  # 2 < 3, aciona

        regra.params = {"minimo": 1}
        assert compute(ctx, [regra]).value == 0  # 2 >= 1, não aciona

    def test_regra_desconhecida_nao_derruba_o_calculo(self, db):
        """Um UPDATE errado no banco não pode zerar o radar (ADR-0008, regra 1)."""
        regras = [_regra("sem_site", 35), _regra("regra-que-nao-existe", 50)]

        assert compute(_ctx(), regras).value == 35


class TestVersao:
    def test_mesmo_conjunto_gera_a_mesma_versao(self, db):
        regras = [_regra("sem_site", 35), _regra("site_lento", 10)]
        assert ruleset_version(regras) == ruleset_version(list(reversed(regras)))

    def test_mudar_peso_muda_a_versao(self, db):
        """Sem isso, comparar scores de semanas diferentes é comparar coisas distintas."""
        regra = _regra("sem_site", 35)
        antes = ruleset_version([regra])

        regra.points = 40
        assert ruleset_version([regra]) != antes

    def test_mudar_parametro_muda_a_versao(self, db):
        regra = _regra("site_lento", 10, params={"threshold_ms": 3000})
        antes = ruleset_version([regra])

        regra.params = {"threshold_ms": 1000}
        assert ruleset_version([regra]) != antes


class TestPersistencia:
    def test_grava_score_e_breakdown(self, db):
        _regra("sem_site", 35, reason_template="Nenhum site identificado.")
        empresa = Company.objects.create(
            name="Sem site", website_status=Company.WebsiteStatus.NOT_FOUND
        )

        score = score_company(empresa)

        assert score.value == 35
        assert score.version
        parcela = score.components.get()
        assert (parcela.rule_code, parcela.points) == ("sem_site", 35)
        assert parcela.reason == "Nenhum site identificado."

    def test_recalcular_substitui_em_vez_de_empilhar(self, db):
        """Parcela velha de regra desativada mentiria sobre de onde veio o número."""
        regra = _regra("sem_site", 35)
        empresa = Company.objects.create(
            name="Sem site", website_status=Company.WebsiteStatus.NOT_FOUND
        )
        score_company(empresa)

        regra.is_active = False
        regra.save()
        score = score_company(empresa)

        assert Score.objects.count() == 1
        assert score.components.count() == 0
        assert score.value == 0

    def test_uma_pontuacao_por_empresa(self, db):
        _regra("sem_site", 35)
        empresa = Company.objects.create(
            name="Sem site", website_status=Company.WebsiteStatus.NOT_FOUND
        )

        score_company(empresa)
        score_company(empresa)

        assert Score.objects.filter(company=empresa).count() == 1

    def test_banco_recusa_valor_fora_da_faixa(self, db):
        """0 a 100 no banco, e não só no motor: cálculo com bug não grava 340."""
        from django.db.utils import IntegrityError

        empresa = Company.objects.create(name="X")
        with pytest.raises(IntegrityError):
            Score.objects.create(company=empresa, value=340, version="x")


class TestEmpresaNuncaAnalisada:
    def test_nao_pontua_por_ausencia_que_ninguem_verificou(self, db):
        """A mesma regra do Opportunity Engine: "não sei" não vira "não tem"."""
        from django.core.management import call_command

        call_command("seed_score_rules", verbosity=0)
        empresa = Company.objects.create(name="Nunca analisada")
        assert empresa.website_status == Company.WebsiteStatus.NOT_CHECKED

        score = score_company(empresa)

        # Só a regra de contato aciona, e ela é negativa — nenhuma ausência de site ou de
        # sinal de página pode pontuar sem alguém ter olhado.
        assert set(score.components.values_list("rule_code", flat=True)) == {"poucos_contatos"}
        assert score.value == 0


def test_site_pobre_pontua_mais_que_site_bom(db):
    """Prova o motor inteiro com o seed real: o pior site é o melhor lead."""
    from django.core.management import call_command

    call_command("seed_score_rules", verbosity=0)

    def _com_scan(nome, **campos):
        empresa = Company.objects.create(name=nome, website_status=Company.WebsiteStatus.FOUND)
        site = CompanyWebsite.objects.create(
            company=empresa, url="https://x.com.br", domain=f"{nome}.com.br", is_primary=True
        )
        CompanyContact.objects.create(
            company=empresa,
            kind=CompanyContact.Kind.PHONE,
            value_raw="x",
            value_normalized=f"+55433324{len(nome):04d}",
        )
        padrao = {
            "status": WebsiteScan.Status.OK,
            "http_status": 200,
            "is_https": True,
            "has_viewport": True,
            "has_contact_form": True,
            "has_whatsapp": True,
            "has_booking": True,
            "response_time_ms": 300,
        }
        WebsiteScan.objects.create(company=empresa, website=site, **{**padrao, **campos})
        return empresa

    bom = _com_scan("bom")
    ruim = _com_scan(
        "ruim",
        is_https=False,
        has_viewport=False,
        has_contact_form=False,
        has_whatsapp=False,
        has_booking=False,
        response_time_ms=9000,
    )
    sem_site = Company.objects.create(
        name="sem site", website_status=Company.WebsiteStatus.NOT_FOUND
    )
    CompanyContact.objects.create(
        company=sem_site,
        kind=CompanyContact.Kind.PHONE,
        value_raw="x",
        value_normalized="+554333249999",
    )

    valores = {e.name: score_company(e).value for e in (bom, ruim, sem_site)}

    assert valores["bom"] == 0
    assert valores["ruim"] > 0
    assert valores["sem site"] > 0
