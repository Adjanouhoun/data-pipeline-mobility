# Sprint 1 — Ingestion Vélib complète et idempotente

## Objectif

Remplacer l’ingestion limitée à 100 stations par une ingestion complète,
robuste et historisée de toutes les stations Vélib exposées par l’API
Paris Open Data.

## Fonctionnement

Le pipeline appelle l’API avec les paramètres suivants :

- `limit=100` ;
- pagination avec `offset` ;
- tri stable avec `order_by=stationcode` ;
- timeout HTTP de 30 secondes ;
- trois retries avec backoff ;
- retry sur les statuts 429, 500, 502, 503 et 504.

Le tri par `stationcode` est indispensable. Sans ordre explicite, un test
réel a récupéré seulement 1 421 observations uniques sur les 1 516
annoncées par l’API.

## Validation des réponses

Chaque réponse doit contenir :

- un `total_count` entier positif ou nul ;
- une liste `results` ;
- un `stationcode` pour chaque station ;
- un horodatage métier `duedate`.

Une page vide avant d’atteindre `total_count` provoque l’échec du run afin
d’éviter une ingestion partielle silencieuse.

## Idempotence

La clé métier d’une observation est :

```text
(stationcode, last_reported)
```

Un index unique PostgreSQL protège cette clé.

Les insertions utilisent :

```sql
ON CONFLICT (stationcode, last_reported) DO NOTHING
```

Une observation déjà présente est ignorée. Une nouvelle observation de la
même station avec un autre horodatage est conservée dans l’historique.

## Chargement PostgreSQL

Les enregistrements sont insérés en lot avec `execute_values`, dans une
transaction unique.

En cas d’erreur :

- la transaction est annulée ;
- aucune ingestion partielle n’est conservée ;
- l’erreur est journalisée dans Airflow.

## Résultats des tests locaux

Test réel de pagination :

```text
pages=16 total=1516 uniques=1516
```

Première ingestion complète :

```text
received=1516 inserted=1516 duplicates_ignored=0
```

Relance immédiate :

```text
received=1516 inserted=61 duplicates_ignored=1455
```

Les 61 insertions correspondent à des stations dont l’horodatage métier
avait changé entre les deux appels.

Contrôle PostgreSQL après ingestion :

```text
total_rows=2027
unique_observations=2027
```

## Tests automatisés

Les tests unitaires couvrent :

- la pagination sur plusieurs pages ;
- le tri stable par `stationcode` ;
- la déduplication par clé métier ;
- les pages vides prématurées ;
- les réponses invalides ;
- les identifiants de station manquants ;
- les horodatages manquants ;
- la limite maximale de taille de page.

Commande :

```bash
python -m unittest discover -s tests/unit -p "test_*.py" -v
```

Résultat :

```text
Ran 7 tests
OK
```

## Limites connues à la fin du sprint

- dbt est encore installé pendant chaque exécution du DAG ;
- les migrations SQL sont encore exécutées par la tâche d’ingestion ;
- la clé Fernet Airflow n’est pas encore configurée ;
- les champs temporels PostgreSQL conservent leur type existant pour
  préserver les vues dbt ;
- la migration vers `TIMESTAMPTZ` sera traitée séparément.