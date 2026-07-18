# Sprint 9 — Ingestion du trafic routier parisien

## Objectif

Enrichir la plateforme avec les données horaires de circulation du
réseau routier parisien, sans charger l’historique complet de plus de
28 millions d’enregistrements.

Le pipeline doit fournir :

- une extraction incrémentale ;
- une pagination complète ;
- une ingestion idempotente ;
- une historisation détaillée ;
- des modèles dbt incrémentaux ;
- des agrégats journaliers ;
- des tests de qualité ;
- des métriques d’observabilité ;
- une politique de rétention ;
- une sauvegarde restaurable.

## Source de données

Jeu de données Paris Open Data :

```text
comptages-routiers-permanents
```

L’API utilisée est l’API Explore v2.1 de Paris Open Data.

Les principales colonnes collectées sont :

- `iu_ac` : identifiant métier de l’axe ;
- `libelle` : libellé de l’axe ;
- `t_1h` : horodatage métier de la mesure ;
- `q` : débit de véhicules ;
- `k` : taux d’occupation ;
- `etat_trafic` : état du trafic ;
- `etat_barre` : état opérationnel de l’axe ;
- les nœuds amont et aval ;
- les coordonnées géographiques ;
- la géométrie de l’axe.

Les mesures de débit et d’occupation peuvent être absentes dans la
source. Les valeurs nulles sont donc conservées et documentées plutôt
que remplacées artificiellement.

## Architecture du pipeline

```text
Paris Open Data
        │
        ▼
Airflow — fenêtre incrémentale
        │
        ▼
Découpage en fenêtres de deux heures
        │
        ▼
Pagination complète et déduplication
        │
        ▼
PostgreSQL RAW
schema_raw.road_traffic_observations
        │
        ▼
dbt staging
stg_road_traffic
        │
        ├──► dim_road_arcs
        │
        ├──► fct_road_traffic
        │
        └──► agg_road_traffic_daily
                    │
                    ▼
               Superset
```

## Stratégie d’extraction

### Fenêtre initiale

Lors du premier lancement, le DAG récupère les six dernières heures
disponibles.

### Watermark

Les exécutions suivantes utilisent :

```sql
max(observed_at)
```

comme watermark.

Une période de recouvrement de deux heures est appliquée afin de
récupérer les éventuelles corrections ou données arrivées tardivement.

### Découpage de l’API

Une fenêtre globale peut contenir plus de 10 000 résultats, ce qui
dépasse la limite de pagination de l’API.

La période est donc découpée en sous-fenêtres de deux heures.

Chaque sous-fenêtre est paginée avec :

```text
limit=100
order_by=t_1h asc, iu_ac asc
```

Les observations présentes sur les limites de plusieurs fenêtres sont
dédoublonnées avec la clé métier :

```text
arc_id + observed_at
```

### Robustesse HTTP

Le client API utilise :

- un timeout ;
- des retries ;
- un backoff ;
- la gestion des statuts HTTP temporaires ;
- la validation de la structure JSON ;
- le contrôle des volumes annoncés ;
- la déduplication entre pages et fenêtres.

## DAG Airflow

Le DAG créé est :

```text
ingest_paris_road_traffic
```

Planification :

```text
35 * * * *
```

Il s’exécute chaque heure à la minute 35 afin de ne pas entrer en
concurrence directe avec le DAG Vélib.

Ordre des tâches :

```text
initialize_traffic_raw_schema
        │
        ▼
initialize_traffic_monitoring_schema
        │
        ▼
extract_and_load_road_traffic
        │
        ▼
transform_and_test_road_traffic
```

La dernière tâche exécute :

- les modèles dbt du trafic ;
- les tests associés ;
- les tests des sources ;
- le contrôle de fraîcheur de la source routière.

## Stockage RAW

Table :

```text
schema_raw.road_traffic_observations
```

Grain :

```text
une ligne par axe routier et par horodatage métier
```

Clé d’unicité :

```text
arc_id + observed_at
```

Le chargement utilise un upsert PostgreSQL en lot.

Chaque observation est classée comme :

- insérée ;
- mise à jour ;
- inchangée.

Une relance sur les mêmes données ne crée aucun doublon.

## Modèles dbt

### `stg_road_traffic`

Vue de normalisation des données RAW.

Elle fournit notamment :

- une clé déterministe `observation_id` ;
- des types SQL cohérents ;
- les indicateurs de présence des mesures ;
- les horodatages métier et technique ;
- l’identifiant du run source.

### `dim_road_arcs`

Dimension courante des axes routiers.

Grain :

```text
une ligne par arc_id
```

Elle conserve la description la plus récente de chaque axe :

- libellé ;
- nœuds amont et aval ;
- coordonnées ;
- première et dernière observation ;
- première et dernière ingestion.

### `fct_road_traffic`

Table de faits détaillée et incrémentale.

Grain :

```text
une ligne par arc_id et observed_at
```

Clé unique :

```text
observation_id
```

La table possède des index sur :

- `observation_id` ;
- `arc_id, observed_at` ;
- `observed_at`.

### `agg_road_traffic_daily`

Agrégat incrémental destiné aux analyses historiques et à Superset.

Grain :

```text
une ligne par axe et par jour
```

Métriques calculées :

- nombre total d’observations ;
- nombre de mesures de débit ;
- nombre de mesures d’occupation ;
- débit moyen et maximal ;
- occupation moyenne et maximale ;
- observations fluides ;
- observations pré-saturées ;
- observations saturées ;
- observations bloquées ;
- observations inconnues ;
- états ouvert, barré et invalide ;
- première et dernière observation ;
- dernier chargement technique.

Lors d’une exécution incrémentale, seuls les couples `axe + jour`
affectés par de nouvelles données sont recalculés.

## Observabilité

Table technique :

```text
schema_monitoring.traffic_ingestion_runs
```

Vue analytique :

```text
schema_analytics.fct_traffic_ingestion_runs
```

Les métriques enregistrées sont :

- identifiant du run Airflow ;
- fenêtre interrogée ;
- watermark précédent ;
- nombre de pages ;
- volume annoncé ;
- volume unique reçu ;
- lignes insérées ;
- lignes mises à jour ;
- lignes inchangées ;
- durée ;
- débit de traitement ;
- taux d’insertion ;
- taux de mise à jour ;
- taux de lignes inchangées ;
- statut ;
- message d’erreur éventuel.

## Résultats des exécutions

### Première exécution

```text
records_received=5958
records_inserted=5958
records_updated=0
records_unchanged=0
duration_seconds=7.855
```

### Deuxième exécution

```text
records_received=8937
records_inserted=2979
records_updated=0
records_unchanged=5958
duration_seconds=16.400
```

### Relance idempotente

```text
records_received=8937
records_inserted=0
records_updated=0
records_unchanged=8937
```

La relance complète ne crée donc aucun doublon.

## Volumes validés

```text
RAW trafic : 8937
Faits trafic : 8937
Axes distincts : 2979
Agrégats axe/jour : 2979
Observations agrégées : 8937
```

Période de l’échantillon initial :

```text
2026-07-17 20:00:00 UTC
à
2026-07-17 22:00:00 UTC
```

Disponibilité des mesures :

```text
Mesures de débit : 4792
Mesures d’occupation : 4927
```

## Répartition observée du trafic

```text
Fluide       : 4507
Inconnu      : 4010
Pré-saturé   : 292
Saturé       : 92
Bloqué       : 36
```

État opérationnel des axes :

```text
Ouvert       : 6195
Invalide     : 2523
Barré        : 219
```

## Qualité des données

Les contrôles couvrent :

- unicité des observations ;
- unicité des axes ;
- clés obligatoires ;
- relations faits/dimensions ;
- valeurs autorisées des statuts ;
- mesures non négatives ;
- occupation comprise entre 0 et 100 ;
- cohérence des indicateurs de présence ;
- cohérence interne des agrégats journaliers ;
- réconciliation entre faits et agrégats ;
- fraîcheur de la source ;
- cohérence des métriques d’ingestion.

Résultats :

```text
Tests Python : 36 réussis
Tests dbt trafic : aucune erreur
Fraîcheur trafic : réussie
Erreurs d’import Airflow : aucune
DAG complet : success
```

L’avertissement dbt restant concerne uniquement une anomalie métier
Vélib connue et ne concerne pas le trafic routier.

## Politique de rétention

Politique retenue :

```text
Vélib RAW              : 30 jours
Vélib faits détaillés  : 24 mois
Trafic RAW             : 7 jours
Trafic faits détaillés : 6 mois
Monitoring             : 12 mois
Agrégats journaliers   : conservation longue durée
```

Avant toute suppression, le script vérifie que chaque fait expiré
possède bien son agrégat journalier.

L’exécution réelle exige :

- une sauvegarde ;
- un checksum valide ;
- une restauration vérifiée ;
- un marqueur de vérification récent ;
- une confirmation explicite.

Le mode par défaut reste un dry-run.

Résultat du dry-run du Sprint 9 :

```text
Aucune ligne expirée
Protection agrégats Vélib : réussie
Protection agrégats trafic : réussie
Aucune suppression exécutée
```

## Sauvegarde et restauration

Une nouvelle sauvegarde a été créée :

```text
mobility_warehouse_20260718T025604Z.dump
```

La restauration a été testée dans une base temporaire.

Volumes restaurés pour le trafic :

```text
RAW : 8937
Faits : 8937
Axes : 2979
Agrégats : 2979
Monitoring : 3
```

Les contrôles d’unicité ont réussi et la base temporaire a été
supprimée automatiquement après validation.

Les archives et leurs checksums restent exclus de Git.

## Fichiers principaux

```text
dags/ingest_road_traffic.py
dags/lib/traffic_api.py
dags/lib/traffic_ingestion.py

sql/003_traffic_raw_schema.sql
sql/004_traffic_monitoring_schema.sql

dbt_mobility/models/staging/stg_road_traffic.sql
dbt_mobility/models/marts/dim_road_arcs.sql
dbt_mobility/models/marts/fct_road_traffic.sql
dbt_mobility/models/marts/agg_road_traffic_daily.sql
dbt_mobility/models/monitoring/fct_traffic_ingestion_runs.sql

dbt_mobility/tests/assert_road_traffic_measurements_are_valid.sql
dbt_mobility/tests/assert_road_traffic_daily_metrics_are_consistent.sql
dbt_mobility/tests/assert_road_traffic_daily_aggregate_matches_fact.sql

tests/unit/test_traffic_api.py
tests/unit/test_traffic_ingestion.py

scripts/apply_data_retention.sh
scripts/verify_warehouse_backup.sh
```

## Exploitation future dans Superset

Les futurs tableaux de bord pourront présenter :

- une carte des axes routiers ;
- le débit moyen par axe ;
- le taux d’occupation ;
- les axes saturés ou bloqués ;
- l’évolution quotidienne du trafic ;
- la disponibilité des mesures ;
- les performances d’ingestion ;
- le taux de succès des runs ;
- la fraîcheur de la dernière collecte ;
- la comparaison entre trafic routier et disponibilité Vélib.

## Conclusion

Le projet couvre désormais deux domaines de mobilité parisienne :

- la disponibilité Vélib ;
- le trafic routier permanent.

Les deux pipelines sont incrémentaux, historisés, testés, observables,
sauvegardés et adaptés à une infrastructure légère.