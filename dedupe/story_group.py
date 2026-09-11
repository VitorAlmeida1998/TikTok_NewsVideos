"""Agrupamento de notícias que contam a MESMA história.

Cinco feeds cobrem os mesmos fatos: "Forza Horizon 6 atrasou no PS5"
(eurogamer) e "Forza Horizon 6 NÃO atrasou, diz estúdio" (eurogamer, horas
depois) viraram dois vídeos contraditórios no mesmo perfil. Aqui as notícias
recebem um `story_group` (o id do item mais antigo do grupo) por similaridade
de título dentro de uma janela de horas, e o pipeline só gera roteiro/vídeo
para o primeiro item de cada grupo.

Comparação por conjunto de tokens (Jaccard) em vez de embeddings: os títulos
dos feeds repetem o nome do jogo e os termos-chave, é barato e offline.
"""
from __future__ import annotations

import re

SIMILARITY_THRESHOLD = 0.45
GROUP_WINDOW_HOURS = 36

# Palavras que não ajudam a distinguir uma história de outra.
STOPWORDS = {
    "a", "the", "of", "in", "on", "for", "to", "and", "is", "are", "was",
    "were", "be", "been", "at", "by", "with", "from", "as", "it", "its", "this",
    "that", "has", "have", "had", "will", "would", "can", "could", "new", "news",
    "after", "before", "into", "out", "up", "down", "over", "about", "more", "most",
    "you", "your", "we", "our", "they", "their", "he", "she", "his", "her", "but",
    "not", "no", "yes", "all", "some", "one", "two", "now", "just", "still", "says",
    "say", "said", "de", "da", "do", "um", "uma",
}


def title_tokens(title: str) -> set[str]:
    """Tokens significativos do título (minúsculo, sem stopwords nem
    pontuação). Números e siglas curtas (GTA, PS5, 6) são mantidos: costumam
    ser exatamente o que identifica a história."""
    words = re.findall(r"[a-z0-9]+", title.lower())
    return {w for w in words if w not in STOPWORDS and (len(w) > 2 or w.isdigit())}


def similarity(title_a: str, title_b: str) -> float:
    """Jaccard entre os tokens significativos dos dois títulos (0.0 a 1.0)."""
    a, b = title_tokens(title_a), title_tokens(title_b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_story_group(
    title: str,
    candidates: list[tuple[int, str, int | None]],
    threshold: float = SIMILARITY_THRESHOLD,
) -> int | None:
    """Devolve o `story_group` do candidato mais parecido acima do limiar, ou
    None se a história for nova.

    `candidates`: (id, title, story_group) de itens já avaliados dentro da
    janela de tempo, do mais recente para o mais antigo.
    """
    best_group = None
    best_score = threshold
    for candidate_id, candidate_title, candidate_group in candidates:
        score = similarity(title, candidate_title)
        if score >= best_score:
            best_score = score
            best_group = candidate_group if candidate_group is not None else candidate_id
    return best_group
