"""O Opportunity Engine.

A propriedade que mais importa: **"não sei" nunca vira "não tem"**. Empresa nunca analisada
não pode gerar oportunidade — venderíamos site institucional para quem já tem site, e o
diagnóstico inteiro perde credibilidade na primeira ligação.
"""

import pytest

from apps.analysis.models import Opportunity, OpportunityType, WebsiteScan
from apps.analysis.opportunities import build_context, detect
from apps.analysis.rules import REGISTRO, CompanyContext, evaluate
from apps.companies.models import Category, Company, CompanyContact, CompanyWebsite

pytestmark = pytest.mark.django_db


@pytest.fixture
def tipo_sem_site(db):
    return OpportunityType.objects.create(
        code="site-institucional", name="Site institucional", rule_code="sem_site"
    )


@pytest.fixture
def tipo_agendamento(db):
    return OpportunityType.objects.create(
        code="agendamento-online",
        name="Agendamento online",
        rule_code="sem_agendamento",
        category_slugs=["dentistas"],
    )


def _empresa_com_scan(nome="Clínica X", **campos_do_scan):
    empresa = Company.objects.create(name=nome, website_status=Company.WebsiteStatus.FOUND)
    site = CompanyWebsite.objects.create(
        company=empresa, url="https://x.com.br", domain="x.com.br", is_primary=True
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
    WebsiteScan.objects.create(company=empresa, website=site, **{**padrao, **campos_do_scan})
    return empresa


class TestNaoSeiNaoEhNaoTem:
    """A regra que sustenta a credibilidade do produto inteiro."""

    def test_empresa_nunca_analisada_nao_gera_oportunidade(self, tipo_sem_site):
        empresa = Company.objects.create(name="Nunca analisada")
        assert empresa.website_status == Company.WebsiteStatus.NOT_CHECKED

        assert detect(empresa).opened == 0
        assert Opportunity.objects.count() == 0

    def test_sinais_de_scan_que_falhou_nao_viram_ausencia(self, db):
        """Um scan falho traz os booleanos em `False` pelo padrão do model.

        Lidos como observação, virariam "não tem HTTPS, não tem viewport, não tem
        agendamento" — três oportunidades inventadas a partir de um site que nem foi visto.
        """
        empresa = Company.objects.create(name="Fora do ar")
        site = CompanyWebsite.objects.create(
            company=empresa, url="https://x.com.br", domain="x.com.br"
        )
        WebsiteScan.objects.create(
            company=empresa, website=site, status=WebsiteScan.Status.UNREACHABLE
        )

        ctx = build_context(empresa)

        assert ctx.site_reachable is False
        assert ctx.is_https is None
        assert ctx.has_booking is None
        assert ctx.has_viewport is None

    def test_contexto_de_empresa_nunca_analisada_e_todo_desconhecido(self, db):
        ctx = build_context(Company.objects.create(name="Nova"))

        assert ctx.site_reachable is None
        assert ctx.scan_status is None
        assert ctx.is_https is None


class TestPredicados:
    def test_sem_site_exige_que_a_analise_tenha_acontecido(self, db):
        nao_checada = CompanyContext(
            company_id=1, name="X", website_status="NOT_CHECKED", has_website=False
        )
        checada = CompanyContext(
            company_id=1, name="X", website_status="NOT_FOUND", has_website=False
        )

        assert evaluate("sem_site", nao_checada) is False
        assert evaluate("sem_site", checada) is True

    def test_site_fora_do_ar(self, db):
        ctx = CompanyContext(
            company_id=1,
            name="X",
            website_status="FOUND",
            has_website=True,
            site_reachable=False,
        )
        assert evaluate("site_fora_do_ar", ctx) is True

    def test_sinais_desconhecidos_nao_disparam_regra(self, db):
        """`None` em toda parte: nenhuma regra de sinal pode dizer sim."""
        ctx = CompanyContext(company_id=1, name="X", website_status="FOUND", has_website=True)

        for codigo in ("site_sem_https", "site_nao_responsivo", "sem_agendamento", "site_lento"):
            assert evaluate(codigo, ctx) is False, codigo

    def test_limiar_vem_do_banco_e_nao_do_codigo(self, db):
        """É o ponto do ADR-0008: ajustar o que é "lento" é UPDATE, não deploy."""
        ctx = CompanyContext(
            company_id=1,
            name="X",
            website_status="FOUND",
            has_website=True,
            site_reachable=True,
            response_time_ms=2000,
        )

        assert evaluate("site_lento", ctx, {"threshold_ms": 3000}) is False
        assert evaluate("site_lento", ctx, {"threshold_ms": 1000}) is True

    def test_regra_desconhecida_nao_quebra_o_calculo(self, db):
        """ADR-0008, regra 1: um UPDATE errado no banco não derruba o motor."""
        ctx = CompanyContext(company_id=1, name="X", website_status="FOUND", has_website=True)
        assert evaluate("regra_que_nao_existe", ctx) is None

    def test_regra_com_defeito_e_isolada(self, db, monkeypatch):
        monkeypatch.setitem(
            REGISTRO, "quebrada", lambda ctx, p: (_ for _ in ()).throw(ValueError("boom"))
        )
        ctx = CompanyContext(company_id=1, name="X", website_status="FOUND", has_website=True)

        assert evaluate("quebrada", ctx) is None

    def test_nao_existe_eval_no_motor(self):
        """ADR-0008, regra 4: sem `eval`, sem `exec`, sem expressão vinda do banco. Nunca.

        Pela AST, e não por busca de texto: a docstring de `rules.py` menciona `eval()`
        justamente para explicar por que ele não existe ali, e um `in` acusaria o comentário.
        """
        import ast
        from pathlib import Path

        for arquivo in ("rules.py", "opportunities.py"):
            arvore = ast.parse(Path(f"apps/analysis/{arquivo}").read_text())
            chamadas = {
                no.func.id
                for no in ast.walk(arvore)
                if isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
            }
            assert not chamadas & {"eval", "exec", "compile"}, arquivo


class TestDetecao:
    def test_abre_oportunidade_com_evidencia(self, tipo_sem_site, db):
        empresa = Company.objects.create(
            name="Sem site", website_status=Company.WebsiteStatus.NOT_FOUND
        )

        assert detect(empresa).opened == 1

        oportunidade = Opportunity.objects.get()
        assert oportunidade.type == tipo_sem_site
        assert oportunidade.status == Opportunity.Status.OPEN
        # Sem evidência, "detectamos que não tem site" é afirmação sem lastro.
        assert oportunidade.evidence["rule"] == "sem_site"
        assert oportunidade.evidence["website_status"] == "NOT_FOUND"

    def test_reavaliar_nao_duplica(self, tipo_sem_site, db):
        empresa = Company.objects.create(
            name="Sem site", website_status=Company.WebsiteStatus.NOT_FOUND
        )
        detect(empresa)
        segundo = detect(empresa)

        assert segundo.opened == 0
        assert segundo.kept == 1
        assert Opportunity.objects.count() == 1

    def test_oportunidade_resolvida_nao_e_apagada(self, tipo_sem_site, db):
        """A empresa que finalmente fez o site sai do radar, mas o histórico fica."""
        empresa = Company.objects.create(
            name="Sem site", website_status=Company.WebsiteStatus.NOT_FOUND
        )
        detect(empresa)

        empresa.website_status = Company.WebsiteStatus.FOUND
        empresa.save()
        relatorio = detect(empresa)

        assert relatorio.resolved == 1
        oportunidade = Opportunity.objects.get()
        assert oportunidade.status == Opportunity.Status.RESOLVED
        assert oportunidade.resolved_at is not None

    def test_tipo_desativado_resolve_a_oportunidade_aberta(self, tipo_sem_site, db):
        """Deixá-la aberta manteria no radar algo que ninguém mais avalia."""
        empresa = Company.objects.create(
            name="Sem site", website_status=Company.WebsiteStatus.NOT_FOUND
        )
        detect(empresa)

        tipo_sem_site.is_active = False
        tipo_sem_site.save()
        detect(empresa)

        assert Opportunity.objects.get().status == Opportunity.Status.RESOLVED


class TestRecorteDeCategoria:
    def test_so_vale_para_as_categorias_listadas(self, tipo_agendamento, db):
        """ "Sem agendamento" é lacuna em clínica e é normal em oficina."""
        from apps.companies.models import CompanyCategory

        dentista = Category.objects.create(slug="dentistas", name="Dentistas")
        oficina = Category.objects.create(slug="oficinas", name="Oficinas")

        clinica = _empresa_com_scan("Clínica", has_booking=False)
        CompanyCategory.objects.create(company=clinica, category=dentista)

        mecanica = _empresa_com_scan("Mecânica", has_booking=False)
        CompanyCategory.objects.create(company=mecanica, category=oficina)

        assert detect(clinica).opened == 1
        assert detect(mecanica).opened == 0

    def test_tipo_sem_categoria_vale_para_todas(self, tipo_sem_site, db):
        assert tipo_sem_site.category_slugs == []
        empresa = Company.objects.create(
            name="Qualquer", website_status=Company.WebsiteStatus.NOT_FOUND
        )
        assert detect(empresa).opened == 1


class TestSeed:
    def test_seed_e_idempotente_e_so_usa_regras_existentes(self, db):
        from django.core.management import call_command

        call_command("seed_opportunity_types", verbosity=0)
        call_command("seed_opportunity_types", verbosity=0)

        tipos = OpportunityType.objects.all()
        assert tipos.count() == 9
        for tipo in tipos:
            assert tipo.rule_code in REGISTRO, f"{tipo.code} aponta para regra inexistente"

    def test_empresa_ruim_gera_varias_oportunidades(self, db):
        """Prova o motor inteiro: site pobre vira lista de coisas para vender."""
        from django.core.management import call_command

        call_command("seed_opportunity_types", verbosity=0)
        empresa = _empresa_com_scan(
            "Site pobre",
            is_https=False,
            has_viewport=False,
            has_contact_form=False,
            has_whatsapp=False,
            has_booking=False,
            has_cart=False,
            response_time_ms=8000,
        )
        CompanyContact.objects.create(
            company=empresa,
            kind=CompanyContact.Kind.PHONE,
            value_raw="x",
            value_normalized="+554333241000",
        )

        detect(empresa)

        codigos = set(
            Opportunity.objects.filter(company=empresa, status=Opportunity.Status.OPEN).values_list(
                "type__code", flat=True
            )
        )
        assert codigos >= {
            "migracao-https",
            "site-responsivo",
            "otimizacao-desempenho",
            "canal-de-contato",
        }
        # Tem site, então não pode aparecer "site institucional"; tem telefone, então não
        # pode aparecer "cadastro de contato".
        assert "site-institucional" not in codigos
        assert "contato-digital" not in codigos
