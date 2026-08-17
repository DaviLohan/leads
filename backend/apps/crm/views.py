"""API do CRM.

Tudo aqui é do tenant (ADR-0007) e passa por `TenantViewSet`, o ponto único onde o
isolamento é imposto. Lead de outra organização responde **404**, não 403.
"""

from __future__ import annotations

from datetime import timedelta

from django.db import models
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import MinRole
from apps.companies.export import linhas_csv
from apps.companies.models import Company, CompanyContact
from apps.companies.queries import company_table_queryset, contato_principal, do_endereco
from apps.companies.serializers import CompanyTableSerializer
from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.viewsets import TenantViewSet
from apps.crm import services
from apps.crm.models import (
    CompanyList,
    CompanyListItem,
    Lead,
    Note,
    Pipeline,
    PipelineStage,
    SuppressionEntry,
)
from apps.crm.serializers import (
    CompanyListSerializer,
    InteractionSerializer,
    LeadSerializer,
    NoteSerializer,
    PipelineSerializer,
    SuppressionEntrySerializer,
)

#: Teto de um lote. Existe para que "selecionar tudo" numa base de milhões não vire uma
#: requisição que o servidor tenta atender por dez minutos.
LOTE_MAXIMO = 200


class PipelineViewSet(TenantViewSet):
    serializer_class = PipelineSerializer
    permission_classes = [MinRole.at_least(Role.MANAGER)]

    def get_permissions(self):
        """Ler o funil é SALES; mexer nele é MANAGER.

        Estava tudo em MANAGER, e isso quebrava a tela de Leads inteira para vendedor: a
        régua de estágios é a primeira coisa que a tela carrega, e sem ela a página não
        abre. Desenhar o funil continua sendo decisão de quem gere o time.
        """
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [MinRole.at_least(Role.SALES)()]
        return super().get_permissions()

    def get_queryset(self):
        return (
            Pipeline.objects.prefetch_related(
                models.Prefetch(
                    "stages",
                    # `lead_count` por anotação: sem isso, a tela do funil faria uma consulta
                    # por coluna só para mostrar o número em cima de cada uma.
                    queryset=PipelineStage.objects.annotate(
                        lead_count=models.Count("leads")
                    ).order_by("position"),
                )
            )
            .for_organization(self.get_organization())
            .order_by("name")
        )


class LeadViewSet(TenantViewSet):
    serializer_class = LeadSerializer
    permission_classes = [MinRole.at_least(Role.SALES)]
    filterset_fields = ["stage", "owner", "stage__is_terminal"]

    def get_queryset(self):
        return (
            Lead.objects.select_related("company", "company__score", "stage", "owner")
            # Telefone e cidade na própria linha do lead: a fila de trabalho de quem vende é
            # uma lista de ligações, e mandar abrir a empresa para ver o número transformava
            # cada ligação em três cliques. As subconsultas são as mesmas da tela Empresas.
            .annotate(
                phone=contato_principal(CompanyContact.Kind.PHONE, ref="company_id"),
                whatsapp=contato_principal(CompanyContact.Kind.WHATSAPP, ref="company_id"),
                city_name=do_endereco("city__name", ref="company_id"),
                uf=do_endereco("city__state__uf", ref="company_id"),
            )
            .prefetch_related("company__opportunities__type")
            .for_organization(self.get_organization())
            # Maior score primeiro: é a ordem de trabalho de quem prospecta.
            .order_by("-score_snapshot", "-created_at")
        )

    def create(self, request, *args, **kwargs):
        """Cria o lead pelo serviço, e não pelo serializer.

        É o serviço que verifica supressão, escolhe o estágio inicial e abre o histórico.
        Deixar o serializer gravar direto puliria as três coisas.
        """
        empresa = Company.objects.filter(pk=request.data.get("company")).first()
        if empresa is None:
            raise ValidationError({"company": ["Empresa não encontrada."]})

        try:
            lead = services.create_lead(
                organization=self.get_organization(),
                company=empresa,
                owner=request.user,
                request=request,
            )
        except services.SuppressedError as exc:
            # 403 e não 400: não é payload inválido, é uma proibição.
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        serializer = self.get_serializer(lead)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """O painel: como está a prospecção desta organização.

        Um endpoint com agregações, e não seis chamadas da tela — cada uma delas voltaria uma
        listagem inteira para contar linhas no navegador.

        Só números que existem de fato. "Respostas" e "taxa de resposta" ficariam bonitos
        aqui e seriam invenção: nada no modelo registra resposta do cliente hoje.
        """
        organizacao = self.get_organization()
        leads = Lead.objects.for_organization(organizacao)
        agora = timezone.now()
        inicio_do_dia = agora.replace(hour=0, minute=0, second=0, microsecond=0)

        por_estagio = (
            PipelineStage.objects.filter(pipeline__organization=organizacao)
            .annotate(
                lead_count=models.Count("leads", filter=models.Q(leads__organization=organizacao))
            )
            .order_by("position")
            .values("code", "name", "position", "is_terminal", "is_won", "lead_count")
        )

        ganhos = leads.filter(stage__is_won=True).count()
        encerrados = leads.filter(stage__is_terminal=True).count()

        melhores = company_table_queryset(organizacao).filter(lead_id__isnull=True)[:5]

        return Response(
            {
                "por_estagio": list(por_estagio),
                "total": leads.count(),
                "novos_hoje": leads.filter(created_at__gte=inicio_do_dia).count(),
                "novos_semana": leads.filter(created_at__gte=agora - timedelta(days=7)).count(),
                "contatados_hoje": leads.filter(last_contacted_at__gte=inicio_do_dia).count(),
                # Fila esquecida: já está no funil, ninguém falou com ele, e não está
                # encerrado. É o número que mais dói olhar, e por isso aparece.
                "sem_contato": leads.filter(
                    last_contacted_at__isnull=True, stage__is_terminal=False
                ).count(),
                "ganhos": ganhos,
                # Conversão sobre o que **já foi decidido**, não sobre o funil inteiro: dividir
                # por leads em aberto faz a taxa cair só porque o time prospectou mais.
                "conversao": round(ganhos / encerrados, 3) if encerrados else None,
                "melhores_oportunidades": CompanyTableSerializer(melhores, many=True).data,
            }
        )

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        """Manda um lote de empresas para o funil.

        Resultado parcial é resultado legítimo, não erro: empresa suprimida não vira lead, e
        quem já estava no funil não entra de novo — os três números voltam separados para a
        tela poder dizer "18 adicionadas, 1 já estava, 1 recusada por opt-out".
        """
        ids = request.data.get("company_ids") or []
        if not isinstance(ids, list) or not ids:
            raise ValidationError({"company_ids": ["Informe ao menos uma empresa."]})
        if len(ids) > LOTE_MAXIMO:
            raise ValidationError({"company_ids": [f"No máximo {LOTE_MAXIMO} empresas por vez."]})

        organizacao = self.get_organization()
        empresas = list(Company.objects.filter(pk__in=ids))
        ja_existiam = set(
            Lead.objects.filter(organization=organizacao, company__in=empresas).values_list(
                "company_id", flat=True
            )
        )

        criados, suprimidos = 0, []
        for empresa in empresas:
            if empresa.pk in ja_existiam:
                continue
            try:
                services.create_lead(
                    organization=organizacao,
                    company=empresa,
                    owner=request.user,
                    request=request,
                )
            except services.SuppressedError:
                # Nunca em silêncio: quem selecionou precisa saber quem ficou de fora e por quê.
                suprimidos.append({"id": str(empresa.pk), "name": empresa.name})
            else:
                criados += 1

        return Response(
            {"criados": criados, "ja_existiam": len(ja_existiam), "suprimidos": suprimidos},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def move(self, request, pk=None):
        lead = self.get_object()
        estagio = PipelineStage.objects.filter(
            pk=request.data.get("stage"), pipeline__organization=self.get_organization()
        ).first()
        if estagio is None:
            raise ValidationError({"stage": ["Estágio não encontrado neste funil."]})

        services.move_lead(
            lead=lead,
            stage=estagio,
            actor=request.user,
            note=request.data.get("note", ""),
            request=request,
        )
        return Response(self.get_serializer(lead).data)

    @action(detail=True, methods=["get", "post"])
    def interactions(self, request, pk=None):
        lead = self.get_object()

        if request.method == "GET":
            pagina = self.paginate_queryset(lead.interactions.select_related("author"))
            return self.get_paginated_response(InteractionSerializer(pagina, many=True).data)

        entrada = InteractionSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            interacao = services.log_interaction(
                lead=lead, author=request.user, **entrada.validated_data
            )
        except services.SuppressedError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)

        return Response(InteractionSerializer(interacao).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get", "post"])
    def notes(self, request, pk=None):
        lead = self.get_object()

        if request.method == "GET":
            pagina = self.paginate_queryset(lead.notes.select_related("author"))
            return self.get_paginated_response(NoteSerializer(pagina, many=True).data)

        entrada = NoteSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        nota = Note.objects.create(lead=lead, author=request.user, **entrada.validated_data)
        return Response(NoteSerializer(nota).data, status=status.HTTP_201_CREATED)


class CompanyListViewSet(TenantViewSet):
    """Listas de trabalho — o lote antes da decisão.

    Guardar 20 empresas numa lista não é prospectar: não gera lead, não gera interação e não
    conta como contato. É por isso que lista e funil são coisas separadas.
    """

    serializer_class = CompanyListSerializer
    permission_classes = [MinRole.at_least(Role.SALES)]

    def get_queryset(self):
        return (
            CompanyList.objects.annotate(company_count=models.Count("items"))
            .for_organization(self.get_organization())
            .order_by("name")
        )

    def perform_create(self, serializer):
        serializer.save(organization=self.get_organization(), created_by=self.request.user)

    @action(detail=True, methods=["post", "delete"])
    def items(self, request, pk=None):
        """Adiciona ou remove um lote de empresas.

        A idempotência é da constraint `uniq_empresa_por_lista` + `get_or_create`: salvar o
        mesmo lote duas vezes não duplica nem quebra.
        """
        lista = self.get_object()
        ids = request.data.get("company_ids") or []
        if not isinstance(ids, list) or not ids:
            raise ValidationError({"company_ids": ["Informe ao menos uma empresa."]})
        if len(ids) > LOTE_MAXIMO:
            raise ValidationError({"company_ids": [f"No máximo {LOTE_MAXIMO} empresas por vez."]})

        if request.method == "DELETE":
            removidos, _ = lista.items.filter(company_id__in=ids).delete()
            return Response({"removidos": removidos})

        empresas = Company.objects.filter(pk__in=ids)
        adicionados = 0
        for empresa in empresas:
            _, criado = CompanyListItem.objects.get_or_create(
                company_list=lista, company=empresa, defaults={"added_by": request.user}
            )
            adicionados += int(criado)

        return Response(
            # `ja_estavam` explícito: "20 selecionadas, 3 adicionadas" é informação, não erro.
            {"adicionados": adicionados, "ja_estavam": len(empresas) - adicionados},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        """A lista em CSV. Mesmo gerador da tela Empresas — um formato só."""
        lista = self.get_object()
        queryset = company_table_queryset(self.get_organization()).filter(
            list_items__company_list=lista
        )

        record_audit(
            action=AuditLog.Action.EXPORT,
            object_type="crm.CompanyList",
            object_id=lista.pk,
            actor=request.user,
            organization=self.get_organization(),
            request=request,
            changes={"lista": lista.name},
        )

        resposta = StreamingHttpResponse(
            linhas_csv(queryset, CompanyTableSerializer), content_type="text/csv; charset=utf-8"
        )
        resposta["Content-Disposition"] = f'attachment; filename="{slugify(lista.name)}.csv"'
        return resposta

    @action(detail=True, methods=["get"])
    def companies(self, request, pk=None):
        """As empresas da lista, com as mesmas colunas da tela Empresas.

        Reusa `companies.queries`: a otimização da tabela é escrita uma vez só, senão esta
        tela teria o N+1 que a outra não tem.
        """
        lista = self.get_object()
        queryset = company_table_queryset(self.get_organization()).filter(
            list_items__company_list=lista
        )
        pagina = self.paginate_queryset(queryset)
        return self.get_paginated_response(CompanyTableSerializer(pagina, many=True).data)


class SuppressionEntryViewSet(TenantViewSet):
    """Lista de quem não pode ser contatado (LGPD).

    Criar exige ADMIN: é decisão de conformidade, não de rotina comercial. E não tem
    `destroy` — remover alguém de uma lista de opt-out é o tipo de operação que precisa de
    decisão explícita e rastro, não de um botão de lixeira.
    """

    serializer_class = SuppressionEntrySerializer
    permission_classes = [MinRole.at_least(Role.ADMIN)]
    filterset_fields = ["identifier_kind"]
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return SuppressionEntry.objects.for_organization(self.get_organization()).order_by(
            "-created_at"
        )

    def create(self, request, *args, **kwargs):
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)

        registro, encerrados = services.suppress(
            organization=self.get_organization(),
            actor=request.user,
            **entrada.validated_data,
        )
        return Response(
            {**self.get_serializer(registro).data, "leads_encerrados": encerrados},
            status=status.HTTP_201_CREATED,
        )
