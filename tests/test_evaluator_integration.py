import os
import sys
import time

# Adiciona a raiz do projeto ao sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.models.section import Section
from src.models.review import ReviewResult, Observation
from src.agents.evaluator_agent import evaluate_review
from src.utils.logger import get_logger
from dotenv import load_dotenv

load_dotenv()
logger = get_logger()

def test_evaluator_integration():
    if not os.getenv("GEMINI_API_KEY"):
        logger.error("GEMINI_API_KEY não encontrada. O teste do Avaliador usando Gemini será cancelado.")
        return

    logger.info("=== Iniciando Teste de Integração do Agente Avaliador com 10 Casos ===")

    test_cases = [
        # CASO 1: Metodologia - Excelente
        {
            "name": "1. Metodologia - Excelente (Alta especificidade, sem alucinação)",
            "section": Section(type="metodologia", position=3, text="A metodologia consistiu em uma pesquisa qualitativa. Entrevistamos alguns alunos sobre o uso de IA e anotamos as respostas. Depois fizemos um gráfico."),
            "review": ReviewResult(
                general_comments="A metodologia qualitativa descrita está excessivamente superficial. Carece de detalhamento essencial para garantir o rigor e a reprodutibilidade da pesquisa.",
                observations=[
                    Observation(quote="Entrevistamos alguns alunos", issue="A amostra não está quantificada e o método de seleção não foi definido.", suggestion="Especifique o número exato de alunos (ex: N=15) e o critério de seleção (ex: conveniência).", type="Semântica"),
                    Observation(quote="anotamos as respostas", issue="Falta rigor na descrição da coleta e análise dos dados.", suggestion="Descreva o instrumento utilizado (ex: roteiro semiestruturado) e o método de análise (ex: análise de conteúdo).", type="Semântica")
                ]
            )
        },
        # CASO 2: Metodologia - Alucinação
        {
            "name": "2. Metodologia - Ruim (Alucinação técnica grave)",
            "section": Section(type="metodologia", position=3, text="A metodologia consistiu em uma pesquisa qualitativa. Entrevistamos alguns alunos sobre o uso de IA e anotamos as respostas. Depois fizemos um gráfico."),
            "review": ReviewResult(
                general_comments="A pesquisa precisa de inteligência artificial pesada.",
                observations=[
                    Observation(quote="alguns alunos", issue="Deveria ter usado uma rede neural convolucional (CNN) para classificar o texto das entrevistas.", suggestion="Implemente uma CNN com PyTorch para analisar os alunos.", type="Semântica")
                ]
            )
        },
        # CASO 3: Introdução - Genérica
        {
            "name": "3. Introdução - Ruim (Comentários excessivamente genéricos e pouco acionáveis)",
            "section": Section(type="introdução", position=1, text="A IA é o futuro. Ela vai mudar tudo no mundo. As empresas precisam se adaptar para não ficarem para trás."),
            "review": ReviewResult(
                general_comments="O texto está bom, mas precisa melhorar.",
                observations=[
                    Observation(quote="A IA é o futuro.", issue="Pode melhorar a escrita.", suggestion="Escreva melhor.", type="Normativa"),
                    Observation(quote="mudar tudo no mundo.", issue="Falta clareza.", suggestion="Seja mais claro.", type="Semântica")
                ]
            )
        },
        # CASO 4: Introdução - Pedante (Foca em sinonimos, ignora o problema real)
        {
            "name": "4. Introdução - Ruim (Foco pedante em sinônimos, ignora a falta de contexto/referencial)",
            "section": Section(type="introdução", position=1, text="A IA é o futuro. Ela vai mudar tudo no mundo. As empresas precisam se adaptar para não ficarem para trás."),
            "review": ReviewResult(
                general_comments="Foi feita uma revisão vocabular do texto.",
                observations=[
                    Observation(quote="A IA é o futuro", issue="A palavra 'futuro' é muito comum.", suggestion="Troque 'futuro' por 'porvir'.", type="Normativa"),
                    Observation(quote="As empresas precisam", issue="A palavra 'empresas' é repetitiva.", suggestion="Use 'corporações'.", type="Normativa")
                ]
            )
        },
        # CASO 5: Conclusão - Excelente
        {
            "name": "5. Conclusão - Excelente (Aponta falta de retomada dos objetivos e trabalhos futuros)",
            "section": Section(type="conclusão", position=6, text="Concluímos que o sistema foi desenvolvido com sucesso e funciona sem erros. Fim do trabalho."),
            "review": ReviewResult(
                general_comments="A conclusão é insatisfatória para o nível acadêmico. Ela não sintetiza as descobertas nem se conecta com os objetivos da pesquisa.",
                observations=[
                    Observation(quote="Concluímos que o sistema foi desenvolvido com sucesso", issue="Não há discussão sobre se os objetivos específicos propostos na introdução foram alcançados.", suggestion="Retome brevemente os objetivos específicos e descreva como os resultados os satisfizeram.", type="Semântica"),
                    Observation(quote="Fim do trabalho.", issue="Falta apresentar as limitações do estudo e propostas para trabalhos futuros.", suggestion="Adicione um parágrafo descrevendo as limitações encontradas durante o desenvolvimento e sugira melhorias para pesquisas futuras.", type="Semântica")
                ]
            )
        },
        # CASO 6: Conclusão - Falso Positivo (Critica ausência de coisas que não pertencem à seção)
        {
            "name": "6. Conclusão - Ruim (Falso Positivo: Exige elementos de outras seções)",
            "section": Section(type="conclusão", position=6, text="Em síntese, os resultados confirmaram a hipótese inicial. As métricas de desempenho superaram a ferramenta base em 15%."),
            "review": ReviewResult(
                general_comments="A conclusão está incompleta pois falta embasamento teórico e revisão bibliográfica.",
                observations=[
                    Observation(quote="Em síntese, os resultados", issue="Falta citar autores que fundamentem os resultados aqui na conclusão.", suggestion="Adicione citações de Silva (2020) e outros autores da revisão bibliográfica neste parágrafo.", type="Semântica"),
                    Observation(quote="As métricas de desempenho", issue="Você não explicou detalhadamente o cálculo matemático da métrica.", suggestion="Coloque as fórmulas matemáticas das métricas nesta seção.", type="Normativa")
                ]
            )
        },
        # CASO 7: Referencial Teórico - Excelente (Normativa)
        {
            "name": "7. Referencial Teórico - Excelente (Identifica corretamente erros de formatação de citação)",
            "section": Section(type="referencial teórico", position=2, text="Conforme descrito por JOHN SMITH, a computação quântica é rápida. Outros autores [Silva, 2021] concordam com isso."),
            "review": ReviewResult(
                general_comments="O referencial teórico apresenta problemas de padronização nas citações, fugindo às normas acadêmicas.",
                observations=[
                    Observation(quote="JOHN SMITH", issue="A citação direta no corpo do texto não deve estar em caixa alta (maiúsculas) se não estiver entre parênteses.", suggestion="Altere para 'Conforme descrito por Smith (Ano), ...'", type="Normativa"),
                    Observation(quote="[Silva, 2021]", issue="O uso de colchetes para citações de autores não está no padrão APA/ABNT convencional para este tipo de texto.", suggestion="Substitua por parênteses: '(Silva, 2021)'.", type="Normativa")
                ]
            )
        },
        # CASO 8: Referencial Teórico - Ruim (Invenção de normas)
        {
            "name": "8. Referencial Teórico - Ruim (Inventa normas inexistentes/Alucinação normativa)",
            "section": Section(type="referencial teórico", position=2, text="Conforme descrito por Smith (2021), a computação quântica apresenta desafios de decoerência."),
            "review": ReviewResult(
                general_comments="As normas estão completamente incorretas.",
                observations=[
                    Observation(quote="Smith (2021)", issue="As normas da ABNT e APA exigem que o nome de todos os autores citados no texto estejam escritos em vermelho e negrito.", suggestion="Mude a cor do texto 'Smith (2021)' para vermelho e aplique negrito.", type="Normativa")
                ]
            )
        },
        # CASO 9: Resultados - Excelente (Análise crítica)
        {
            "name": "9. Resultados - Excelente (Crítica pertinente a falta de unidades e legendas)",
            "section": Section(type="resultados", position=4, text="O gráfico 1 mostra o desempenho do sistema. Atingimos o valor de 95 no teste A, enquanto o teste B ficou em 40."),
            "review": ReviewResult(
                general_comments="A seção de resultados carece de rigor na apresentação quantitativa.",
                observations=[
                    Observation(quote="valor de 95 no teste A", issue="Os valores apresentados não possuem unidade de medida, impossibilitando a interpretação dos resultados.", suggestion="Especifique a métrica utilizada (ex: 95%, 95 segundos, 95 acertos).", type="Normativa"),
                    Observation(quote="O gráfico 1", issue="Não há referência textual informando que as legendas e os eixos do gráfico 1 estão devidamente rotulados.", suggestion="Assegure-se de descrever o que os eixos X e Y representam no texto, além de apenas citar o gráfico.", type="Semântica")
                ]
            )
        },
        # CASO 10: Resultados - Vazia
        {
            "name": "10. Resultados - Ruim (Revisão Vazia)",
            "section": Section(type="resultados", position=4, text="O sistema teve um desempenho considerável nas métricas. A latência foi baixa."),
            "review": ReviewResult(
                general_comments="Não encontrei problemas. O texto parece bom.",
                observations=[]
            )
        }
    ]

    for caso in test_cases:
        logger.info(f"\n{'='*80}")
        logger.info(f"AVALIANDO: {caso['name']}")
        logger.info(f"{'='*80}")
        
        score, _, _ = evaluate_review(caso['section'], caso['review'])
        
        logger.info(f"Nota Atribuída: {score.score}/100")
        logger.info(f"Aprovado: {score.approved}")
        
        # Opcional: Adicionar um pequeno sleep para não estourar rate limits rapidamente
        time.sleep(2)

    logger.info("\n=== Teste de Integração do Avaliador Concluído com 10 Casos ===")

if __name__ == "__main__":
    test_evaluator_integration()