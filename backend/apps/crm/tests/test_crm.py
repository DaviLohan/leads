"""CRM: funil, histórico, supressão e a fronteira do tenant.

Duas propriedades que este arquivo existe para segurar:

- **o histórico não se reescreve** — é o único registro de que a abordagem aconteceu, e a
  prova diante da LGPD;
- **o opt-out tem efeito imediato**, inclusive sobre o trabalho já em andamento.
"""

import pytest
from django.utils import timezone

from apps.companies.models import Company, CompanyContact, CompanyWebsite
from apps.core.models import AppendOnlyError, AuditLog
from apps.crm import services
from apps.crm.management.commands.seed_pipeline import criar_funil_padrao
from apps.crm.models import Interaction, Lead, Pipeline, SuppressionEntry

pytestmark = pytest.mark.django_db


@pytest.fixture
def funil(org):
    return criar_funil_padrao(org)


@pytest.fixture
def empresa(db):
    return Company.objects.create(name="Clínica São José")


@pytest.fixture
def lead(org, funil, empresa, user):
    return services.create_lead(organization=org, company=empresa, owner=user)


class TestFunil:
    def test_criado_sob_demanda(self, org, empresa):
        """A primeira pessoa que prospecta não pode esbarrar em "configure um funil antes"."""
        assert not Pipeline.objects.filter(organization=org).exists()

        lead = services.create_lead(organization=org, company=empresa)

        assert lead.stage.code == "novo"
        assert Pipeline.objects.get(organization=org).is_default

    def test_seed_e_idempotente(self, org):
        criar_funil_padrao(org)
        criar_funil_padrao(org)

        assert Pipeline.objects.filter(organization=org).count() == 1
        assert Pipeline.objects.get(organization=org).stages.count() == 8

    def test_um_funil_padrao_por_organizacao(self, org, funil):
        from django.db.utils import IntegrityError

        with pytest.raises(IntegrityError):
            Pipeline.objects.create(organization=org, name="Outro", is_default=True)


class TestLead:
    def test_nasce_no_primeiro_estagio_com_historico(self, lead):
        assert lead.stage.code == "novo"
        assert lead.interactions.get().kind == Interaction.Kind.STATUS_CHANGE

    def test_guarda_o_score_da_entrada(self, org, funil, empresa):
        """O score da empresa muda quando o site muda; a prioridade de entrada não."""
        from apps.analysis.models import Score

        Score.objects.create(company=empresa, value=75, version="x")

        lead = services.create_lead(organization=org, company=empresa)
        assert lead.score_snapshot == 75

        empresa.score.value = 10
        empresa.score.save()
        lead.refresh_from_db()
        assert lead.score_snapshot == 75

    def test_a_mesma_empresa_nao_vira_dois_leads(self, org, funil, empresa):
        """Dois vendedores da mesma casa ligando para o mesmo cliente é o pior resultado."""
        primeiro = services.create_lead(organization=org, company=empresa)
        segundo = services.create_lead(organization=org, company=empresa)

        assert primeiro.pk == segundo.pk
        assert Lead.objects.count() == 1

    def test_duas_organizacoes_prospectam_a_mesma_empresa(self, org, make_org, empresa):
        """`Company` é global; `Lead` é do tenant. É a fronteira do ADR-0007 na prática."""
        outra = make_org("Concorrente")

        services.create_lead(organization=org, company=empresa)
        services.create_lead(organization=outra, company=empresa)

        assert Lead.objects.count() == 2
        assert Lead.objects.filter(organization=org).count() == 1


class TestMovimentacao:
    def test_gera_registro_no_historico(self, lead, funil, user):
        """Sem isso o funil vira um campo que muda sozinho."""
        qualificado = funil.stages.get(code="qualificado")

        services.move_lead(lead=lead, stage=qualificado, actor=user)

        registro = lead.interactions.filter(kind=Interaction.Kind.STATUS_CHANGE).first()
        assert "Qualificado" in registro.description
        assert lead.stage == qualificado

    def test_grava_auditoria(self, lead, funil, user):
        services.move_lead(lead=lead, stage=funil.stages.get(code="ganho"), actor=user)

        registro = AuditLog.objects.filter(
            object_type="crm.Lead", action=AuditLog.Action.UPDATE
        ).first()
        assert registro.changes["para"] == "ganho"

    def test_mover_para_o_mesmo_estagio_nao_gera_ruido(self, lead):
        antes = lead.interactions.count()
        services.move_lead(lead=lead, stage=lead.stage)
        assert lead.interactions.count() == antes

    def test_recusa_estagio_de_outra_organizacao(self, lead, make_org):
        """Mover para o funil alheio vazaria o lead para fora do tenant."""
        alheio = criar_funil_padrao(make_org("Concorrente"))

        with pytest.raises(services.CrmError, match="outra organização"):
            services.move_lead(lead=lead, stage=alheio.stages.first())


class TestHistoricoAppendOnly:
    def test_nao_pode_ser_alterado(self, lead, user):
        interacao = services.log_interaction(
            lead=lead, kind=Interaction.Kind.CALL, author=user, description="Liguei"
        )

        interacao.description = "Não liguei"
        with pytest.raises(AppendOnlyError):
            interacao.save()

    def test_nao_pode_ser_apagado(self, lead, user):
        interacao = services.log_interaction(lead=lead, kind=Interaction.Kind.CALL, author=user)

        with pytest.raises(AppendOnlyError):
            interacao.delete()

    def test_nem_em_massa(self, lead, user):
        services.log_interaction(lead=lead, kind=Interaction.Kind.CALL, author=user)

        with pytest.raises(AppendOnlyError):
            Interaction.objects.all().delete()


class TestUltimoContato:
    def test_contato_de_verdade_atualiza(self, lead, user):
        services.log_interaction(lead=lead, kind=Interaction.Kind.CALL, author=user)

        lead.refresh_from_db()
        assert lead.last_contacted_at is not None

    @pytest.mark.parametrize("kind", [Interaction.Kind.NOTE, Interaction.Kind.STATUS_CHANGE])
    def test_anotacao_e_mudanca_de_estagio_nao_contam_como_contato(self, lead, user, kind):
        """Contá-los faria o time achar que falou com o cliente quando só mexeu no sistema."""
        services.log_interaction(lead=lead, kind=kind, author=user)

        lead.refresh_from_db()
        assert lead.last_contacted_at is None

    def test_proxima_acao_sobe_para_o_lead(self, lead, user):
        quando = timezone.now() + timezone.timedelta(days=3)
        services.log_interaction(
            lead=lead, kind=Interaction.Kind.CALL, author=user, next_action_at=quando
        )

        lead.refresh_from_db()
        assert lead.next_action_at == quando


class TestSupressao:
    def test_bloqueia_a_criacao_de_lead(self, org, funil, empresa, user):
        CompanyContact.objects.create(
            company=empresa,
            kind=CompanyContact.Kind.PHONE,
            value_raw="x",
            value_normalized="+554333241000",
        )
        services.suppress(
            organization=org,
            identifier_kind=SuppressionEntry.Kind.PHONE,
            identifier_value="+554333241000",
            reason="Pediu para não ser contatado",
            actor=user,
        )

        with pytest.raises(services.SuppressedError, match="supressão"):
            services.create_lead(organization=org, company=empresa)

    def test_por_identificador_e_nao_por_empresa(self, org, funil, empresa, make_org):
        """A mesma pessoa reaparece com outro `company_id` na próxima busca (§3.4)."""
        services.suppress(
            organization=org,
            identifier_kind=SuppressionEntry.Kind.PHONE,
            identifier_value="+554333241000",
        )

        # Empresa nova, id novo, mesmo telefone: tem de continuar bloqueada.
        outra_empresa = Company.objects.create(name="Mesma pessoa, outro registro")
        CompanyContact.objects.create(
            company=outra_empresa,
            kind=CompanyContact.Kind.PHONE,
            value_raw="x",
            value_normalized="+554333241000",
        )

        with pytest.raises(services.SuppressedError):
            services.create_lead(organization=org, company=outra_empresa)

    def test_por_dominio(self, org, funil, empresa):
        CompanyWebsite.objects.create(company=empresa, url="https://x.com.br", domain="x.com.br")
        services.suppress(
            organization=org,
            identifier_kind=SuppressionEntry.Kind.DOMAIN,
            identifier_value="x.com.br",
        )

        with pytest.raises(services.SuppressedError):
            services.create_lead(organization=org, company=empresa)

    def test_encerra_os_leads_ja_abertos(self, org, funil, empresa, user):
        """Registrar sem encerrar deixaria o lead na fila de alguém, que ligaria amanhã."""
        lead = services.create_lead(organization=org, company=empresa, owner=user)
        CompanyContact.objects.create(
            company=empresa,
            kind=CompanyContact.Kind.PHONE,
            value_raw="x",
            value_normalized="+554333241000",
        )

        _, encerrados = services.suppress(
            organization=org,
            identifier_kind=SuppressionEntry.Kind.PHONE,
            identifier_value="+554333241000",
            actor=user,
        )

        lead.refresh_from_db()
        assert encerrados == 1
        assert lead.stage.code == "nao-contatar"
        assert lead.stage.is_terminal

    def test_bloqueia_contato_em_lead_ja_existente(self, org, funil, empresa, user):
        """A supressão pode entrar depois do lead — e é aí que ela precisa valer."""
        lead = services.create_lead(organization=org, company=empresa, owner=user)
        CompanyContact.objects.create(
            company=empresa,
            kind=CompanyContact.Kind.EMAIL,
            value_raw="a@b.com",
            value_normalized="a@b.com",
        )
        services.suppress(
            organization=org,
            identifier_kind=SuppressionEntry.Kind.EMAIL,
            identifier_value="a@b.com",
        )

        with pytest.raises(services.SuppressedError):
            services.log_interaction(lead=lead, kind=Interaction.Kind.CALL, author=user)

    def test_anotacao_interna_continua_permitida(self, org, funil, empresa, user):
        """Suprimir proíbe contatar, não proíbe registrar o que já se sabe."""
        lead = services.create_lead(organization=org, company=empresa, owner=user)
        CompanyContact.objects.create(
            company=empresa,
            kind=CompanyContact.Kind.EMAIL,
            value_raw="a@b.com",
            value_normalized="a@b.com",
        )
        services.suppress(
            organization=org,
            identifier_kind=SuppressionEntry.Kind.EMAIL,
            identifier_value="a@b.com",
        )

        interacao = services.log_interaction(
            lead=lead, kind=Interaction.Kind.NOTE, author=user, description="Pediu opt-out"
        )
        assert interacao.pk

    def test_e_por_organizacao_e_nao_global(self, org, make_org, funil, empresa):
        """`Company` é global; a supressão é de quem pediu. Ver crm/suppression.py."""
        outra = make_org("Concorrente")
        criar_funil_padrao(outra)
        CompanyContact.objects.create(
            company=empresa,
            kind=CompanyContact.Kind.PHONE,
            value_raw="x",
            value_normalized="+554333241000",
        )
        services.suppress(
            organization=org,
            identifier_kind=SuppressionEntry.Kind.PHONE,
            identifier_value="+554333241000",
        )

        with pytest.raises(services.SuppressedError):
            services.create_lead(organization=org, company=empresa)

        # A outra organização nunca pediu nada e continua podendo prospectar.
        assert services.create_lead(organization=outra, company=empresa).pk

    def test_a_empresa_continua_no_banco(self, org, funil, empresa):
        """Suprimir é proibir contato, não apagar dado público global (ADR-0007)."""
        services.suppress(
            organization=org,
            identifier_kind=SuppressionEntry.Kind.COMPANY,
            identifier_value=str(empresa.pk),
        )

        assert Company.objects.filter(pk=empresa.pk).exists()

    def test_grava_auditoria(self, org, funil, empresa, user):
        services.suppress(
            organization=org,
            identifier_kind=SuppressionEntry.Kind.PHONE,
            identifier_value="+554333241000",
            reason="opt-out",
            actor=user,
        )

        registro = AuditLog.objects.get(object_type="crm.SuppressionEntry")
        assert registro.changes["kind"] == "PHONE"
        assert registro.actor == user
