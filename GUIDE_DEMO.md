# Guide de démonstration — Kompilo MVP

Un parcours **pas-à-pas** pour montrer Kompilo de bout en bout : une tâche réelle →
intention comprise → stratégie → prompt compilé → exécution → résultat → diagnostic.
Chaque étape indique **ce que tu dois voir**. Durée : ~8 minutes.

> Rappel d'honnêteté (voir [`LIMITES_CONNUES.md`](LIMITES_CONNUES.md)) : sans clé LLM,
> l'exécution tourne via un **STUB hors-ligne** clairement signalé (`provider_is_real:false`).
> Tout le reste du parcours (compréhension, stratégie, compilation, diagnostic, coût réel,
> cache, versioning, vérification) est **réel**.

---

## 0. Préparer la démo (une fois)

```bash
# 1) Démarrer la stack (API + worker + Postgres + Redis + frontend)
cp .env.example .env
python3 -c "import secrets; print('JWT_SECRET='+secrets.token_urlsafe(48))"   # colle la valeur dans .env
docker compose up --build

# 2) Dans un second terminal : créer le compte + quelques prompts de démo
cd backend && python scripts/seed_demo.py
```

Le seed affiche les identifiants à utiliser (par défaut) :

| Champ        | Valeur            |
|--------------|-------------------|
| org (slug)   | `demo`            |
| email        | `owner@demo.io`   |
| mot de passe | `demo-pass-1234`  |

Ouvre **http://localhost:5173**.

---

## Scénario A — Compiler une intention (grand public, sans compte)

C'est le cœur de Kompilo : transformer une phrase en instruction exécutable.

1. Onglet **« Compiler »**. Dans **« Que veux-tu accomplir ? »**, saisis une tâche réelle :

   > `Rédige un email de relance poli pour une facture de 1 200 € impayée depuis 30 jours`

2. Laisse le mode sur **Pro**, clique **Compiler**.

**Ce que tu dois voir, dans l'ordre :**

- **INTENTION COMPRISE** — l'objectif reformulé + le `domaine` détecté (ex. `writing`).
  → *Kompilo a compris la demande avant d'agir.*
- **INSTRUCTION COMPILÉE** — le prompt prêt à l'emploi, avec 3 onglets
  **Compact / Pro / Expert** et un bouton **Copier**. Les sections (Role, Mission,
  Output format…) sont **sélectionnées dynamiquement** : pas de section décorative vide.
- **DIAGNOSTIC** — **8 axes** (Clarté, Complétude, Spécificité, Robustesse,
  Exécutabilité, Qualité du contexte, Définition de la sortie, Gestion des ambiguïtés).
  Chaque axe est **faible / moyen / élevé** ; un axe faible affiche **Pourquoi** + une
  **Action** corrective. → *Il n'y a jamais de note unique : les forces et faiblesses
  sont nommées.*
- Déplie **« Détails »** → le **plan d'exécution** (stratégie `single/chain/rag`, modèle
  routé + fallbacks), les **coûts ESTIMÉS** (heuristique), les sections et les métadonnées.

**Points à souligner :** le cœur est **déterministe** (`metadata.deterministic: true`
sans clé), les capacités des modèles viennent d'un **registre** (jamais codées en dur),
et les coûts affichés ici sont des **estimations** (le coût réel vient de l'exécution).

---

## Scénario B — Quand la demande est trop vague (ASK)

1. Toujours dans **Compiler**, saisis une tâche volontairement floue : `truc`.
2. Clique **Compiler**.

**Ce que tu dois voir :** pas de prompt compilé, mais des **questions de clarification**
ciblées, et l'axe **Clarté** du diagnostic en **faible** avec sa raison + son action.
→ *Kompilo refuse d'inventer : il pose le minimum de questions critiques au lieu de
produire un prompt bancal.*

---

## Scénario C — Bibliothèque & versioning (avec le compte de démo)

1. Onglet **« Bibliothèque »** → connecte-toi avec les identifiants du seed
   (`demo` / `owner@demo.io` / `demo-pass-1234`).
2. **Ce que tu dois voir :** la liste des prompts de démo, filtrable par **recherche**,
   par **tags** (ex. `email`) et par **projet**, avec **pagination**.
3. Ouvre **« Email de bienvenue client »**.
   → Son détail affiche ses **tags** et ses **versions** (le seed en a créé au moins une).
4. Dans **« Sauvegarder une compilation »**, saisis une variante, par ex. :

   > `Rédige un email de bienvenue chaleureux et bref, avec un appel à l'action`

   Clique **Compiler & sauvegarder**. → Une **nouvelle version** apparaît (v+1). Kompilo
   a **compilé côté serveur** et enregistré le snapshot (catr / ir / renders / diagnostics).
5. Dans **« Comparer deux versions »**, choisis deux versions puis **Comparer**.

**Ce que tu dois voir :** un **diff neutre** — « v1 → v2 : N champ(s) CATR, M rendu(s),
K axe(s) de diagnostic modifié(s) », les champs CATR changés, et les rendus modifiés
(diff unifié dépliable). La mention **« Comparaison neutre… sans juger laquelle est
meilleure (aucun verdict sans mesure) »** est affichée.
→ *Kompilo ne prétend pas qu'une version est « meilleure » sans mesure : l'évaluation
viendra en V1.5.*

---

## Scénario D — Exécution réelle, coût réel, cache & streaming (avancé)

### Dans l'interface
De retour sur **Compiler**, compile une tâche claire, puis déplie
**« Exécution en direct (avancé) »**, colle un `access_token` (celui du seed, récupéré
via `POST /v1/auth/login`) et clique **Exécuter en streaming**.

**Ce que tu dois voir :** la sortie qui s'affiche **progressivement** (SSE), l'état
`flux : done`, le **coût réel** (minuscule mais réel), le marqueur **STUB offline** si
aucune clé n'est configurée, et la **vérification** (« conforme ✓ »).

### En terminal (variante curl) — montre le cache et le coût réel
```bash
TOKEN=$(curl -s -X POST http://localhost:8000/v1/auth/login -H 'Content-Type: application/json' \
     -d '{"org_slug":"demo","email":"owner@demo.io","password":"demo-pass-1234"}' \
     | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 1er appel : coût réel > 0, cached:false
curl -s -X POST http://localhost:8000/v1/execute -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"task":"Rédige un message de bienvenue chaleureux pour un nouveau client"}' \
     | python3 -m json.tool

# 2e appel identique : servi par le cache, cost_usd:0, cached:true
curl -s -X POST http://localhost:8000/v1/execute -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' \
     -d '{"task":"Rédige un message de bienvenue chaleureux pour un nouveau client"}' \
     | python3 -m json.tool
```
**Ce que tu dois voir :** le **2e appel est gratuit** (`cached:true`, `cost_usd:0`). Le
coût est **réel** (tokens × prix du registre), distinct de l'estimation de compilation.

### Vérification de format (Verifier)
```bash
curl -s -X POST http://localhost:8000/v1/execute -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' -d '{
       "task":"Rédige la fiche d un client fictif nommé Dupont, avec son nom et son âge, au format JSON",
       "output_format":"json",
       "output_schema":{"required":["name","age"],
                        "properties":{"name":{"type":"string"},"age":{"type":"integer"}}}
     }' | python3 -c "import sys,json;print(json.load(sys.stdin)['verification'])"
```
**Ce que tu dois voir :** un rapport `verification` précis. Avec le STUB hors-ligne, la
sortie JSON ne contient pas `name`/`age`, donc `valid:false` avec des `issues` pointant le
problème exact — `kind:"missing_field"`, `path:"name"` puis `path:"age"`. Avec un vrai
modèle qui renvoie ces champs, `valid:true`. Jamais un simple vrai/faux : on sait toujours
*ce qui* manque ou cloche.

---

## Fil narratif (résumé à dire)

1. *« Je donne une intention en langage naturel. »* → **Compiler**.
2. *« Kompilo la comprend (CATR), détecte les ambiguïtés, et me dit ce qui manque. »* →
   **Intention comprise** + **Diagnostic**.
3. *« Il choisit une stratégie et un modèle, puis compile une instruction propre. »* →
   **Détails** + **Instruction compilée**.
4. *« Je peux l'exécuter : coût réel, cache, vérification du format, en streaming. »* →
   **Exécution en direct** / curl.
5. *« Tout est versionné et comparable — sans jamais inventer un verdict de qualité. »* →
   **Bibliothèque** + **diff**.

Ce qui est encore simulé (et ce qui vient en V1.5) est listé, sans détour, dans
[`LIMITES_CONNUES.md`](LIMITES_CONNUES.md).
