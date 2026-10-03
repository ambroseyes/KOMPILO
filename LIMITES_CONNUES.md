# Limites connues — Kompilo MVP

Honnêteté totale : ce document liste **tout ce qui est encore STUB / PLACEHOLDER /
partiel** dans le MVP, et ce qui est prévu pour la **V1.5**. Rien de simulé n'est présenté
comme réel dans le produit — chaque STUB ci-dessous est signalé dans le code et, quand il
affecte une sortie, dans la réponse de l'API (ex. `provider_is_real:false`, un `note`, un
statut `skipped`).

## Ce qui est RÉEL (pour éviter toute ambiguïté)

- **Compréhension** (CATR) via l'Intent Engine : heuristiques déterministes, + un LLM léger
  **uniquement** si la confiance est basse et qu'une clé est configurée.
- **Stratégie** : ambiguïté (ASK/PROCEED), complexité (règles), stratégie (single/chain/rag),
  routage par le registre de capacités.
- **Compilation** : Prompt Compiler (IR + 3 rendus) + Kompilo Core (`/v1/compile`).
- **Diagnostic explicable** à 8 axes (sans note unique).
- **Exécution** réelle via la Gateway : cache sémantique Redis, retries/fallback, **coût
  réel** (tokens × prix du registre), idempotence, journalisation par étape.
- **Vérification** de format (JSON + sous-ensemble de JSON-Schema).
- **Bibliothèque & versioning** : CRUD tenant-isolé (RLS), tags, pagination, sauvegarde de
  compilation, historique, diff neutre.
- **Infra** : multi-tenant PostgreSQL RLS, migrations Alembic, worker ARQ, auth JWT + RBAC.

## STUB / PLACEHOLDER (ne PAS présenter comme réel)

| Zone | État actuel | Impact |
|------|-------------|--------|
| **Exécution sans clé LLM** | `EchoProvider` hors-ligne déterministe | La sortie n'est pas d'un vrai modèle. Signalé `provider_is_real:false` + `note`. Mets `OPENAI_API_KEY` pour un vrai modèle (OpenAI/Ollama/LM Studio). |
| **Récupération / RAG** | Étape `retrieve` = STUB (`[retrieval STUB — no corpus configured]`) | Le routeur peut choisir la stratégie `rag`, mais aucune source n'est réellement récupérée. pgvector est en base, non câblé. |
| **Évaluer / Améliorer** | `EvaluateStage` / `ImproveStage` = `skipped` (score `null`, suggestions `[]`) | **Aucune mesure de qualité** : c'est pourquoi le diff de versions reste neutre (« aucun verdict sans mesure »). Pas de boucle d'amélioration. |
| **Pipeline générique `stages.py`** | `understand` + `strategize` RÉELS ; `compile/route/execute/verify/evaluate/improve` STUB | Ce chemin (worker ARQ générique) reste partiel. Les fonctions réelles vivent dans les endpoints dédiés `/v1/compile`, `/v1/execute`, `/v1/executions/{id}/stream`. |
| **Streaming SSE** | Le texte **final** est redécoupé en morceaux de 48 caractères, puis diffusé | Progressif à l'affichage, mais ce n'est **pas** un vrai streaming de tokens du provider. |
| **Complexité « apprise »** | `method="rules-v1"` ; backend PyTorch = STUB futur | L'évaluation de complexité est à base de règles, pas d'un modèle entraîné. |
| **Coûts à la compilation** | Estimation heuristique (≈ 4 caractères/token) | Marqués `estimated:true`. Le coût **réel** n'apparaît qu'à l'exécution. |
| **Registre de modèles** | 3 modèles, prix/capacités maintenus à la main (`last_verified`) | À re-vérifier régulièrement ; une capacité absente = « non supportée » (fail-closed). |
| **Vérifieur** | Sous-ensemble de JSON-Schema : `required` + `type` (récursif) | Pas d'`enum`, `pattern`, bornes min/max, `format`, etc. |
| **Auth** | Signup/login/refresh + RBAC (owner/admin/member) | Pas de vérification d'email, pas de reset de mot de passe, pas de rate-limiting sur le login. Le fallback `X-Tenant-ID` existe **hors production uniquement**. |
| **Frontend** | Jeton en mémoire (aucun stockage navigateur) ; login seulement (pas de signup UI) | Un rafraîchissement déconnecte. Pagination simple (précédent/suivant). |
| **Observabilité** | Logs structurés uniquement | Pas de tracing/métriques exportés (OpenTelemetry, etc.). |
| **Outils / function-calling** | Catégorie d'erreur `TOOL` prévue, mais aucun outil réel branché | L'exécution n'appelle pas encore d'outils externes. |

## Feuille de route V1.5 — 3 améliorations prioritaires (par impact)

### 1. Boucle **Évaluer → Améliorer** (harnais d'éval + scoring) — *impact : le plus fort*
C'est la promesse centrale du produit encore absente. Un harnais d'évaluation
(jeux de cas + critères mesurables : conformité au format, couverture des contraintes,
jugements LLM reproductibles) permettrait enfin de **mesurer** une version, donc de
transformer le diff neutre en **comparaison étayée**, de détecter les régressions, et
d'alimenter une amélioration automatique du prompt. Débloque : A/B de versions, « quelle
version est meilleure **et pourquoi, chiffres à l'appui** », suggestions d'amélioration.
*Pré-requis déjà en place : versioning, diagnostic, exécution réelle, coût réel.*

### 2. **RAG réel** (corpus + embeddings via pgvector) — *impact : fort*
Le routeur choisit déjà la stratégie `rag`, pgvector est déjà installé, mais l'étape
`retrieve` est un STUB. Câbler l'ingestion d'un corpus, l'indexation vectorielle et une
vraie récupération rendrait les tâches « ancrées sur une source » réellement fonctionnelles
(et ferait passer l'axe de diagnostic « Qualité du contexte » du signalement à l'action).

### 3. **Exécution de production** : vrai streaming de tokens + garde-fous — *impact : moyen-fort*
Diffuser les **vrais tokens** du provider (au lieu de redécouper le texte final), et durcir
l'exécution pour la production : backoff conscient du `rate-limit`, **budgets/quotas de coût
par tenant**, délais d'expiration explicites, et métriques exportées. Rend l'exécution
crédible en charge réelle et maîtrise les coûts.

---

*Ce document doit rester à jour : toute nouvelle fonctionnalité réelle qui remplace un STUB
ci-dessus doit être retirée de la table correspondante.*
