# Sprint 6 — Agrégats quotidiens de mobilité

## Objectif

Créer une couche analytique quotidienne permettant de conserver les tendances
de disponibilité Vélib sur le long terme, d’accélérer les futurs tableaux de
bord Superset et de préparer une future politique de rétention.

Ce sprint ne supprime aucune donnée et n’active aucune rétention automatique.

## Modèle créé

Le modèle dbt suivant a été ajouté :

```text
schema_analytics.agg_velib_station_daily
```

Il est matérialisé sous forme de table incrémentale.

## Grain

Une ligne représente :

```text
une station Vélib et une journée d’observation
```

La clé déterministe `daily_station_id` est construite à partir de :

```text
station_id + observation_date
```

Cette clé possède un index unique PostgreSQL.

## Source

Le modèle quotidien utilise la table de faits historisée :

```text
schema_analytics.fct_velib_status
```

Il ne lit pas directement la table RAW.

Cette séparation garantit que les indicateurs quotidiens reposent sur les
données nettoyées et testées par dbt.

## Indicateurs calculés

Pour chaque station et chaque journée, le modèle calcule :

- le nombre d’observations ;
- le nombre moyen de vélos disponibles ;
- le nombre minimum de vélos disponibles ;
- le nombre maximum de vélos disponibles ;
- le nombre moyen de bornes disponibles ;
- le taux moyen d’occupation ;
- le nombre d’observations avec une station vide ;
- le nombre d’observations sans borne disponible ;
- le nombre d’observations avec une station hors service ;
- le nombre d’anomalies où les vélos dépassent la capacité déclarée ;
- la première observation métier de la journée ;
- la dernière observation métier de la journée ;
- le dernier chargement technique inclus.

## Stratégie incrémentale

Le modèle utilise la configuration suivante :

```text
materialized = incremental
unique_key = daily_station_id
incremental_strategy = delete+insert
```

Lorsqu’une nouvelle observation arrive, le modèle identifie les couples
`station_id` et `observation_date` concernés.

Il recharge ensuite toutes les observations disponibles pour ces couples avant
de recalculer leurs agrégats.

Cette stratégie évite de remplacer un agrégat quotidien complet par un calcul
portant uniquement sur les nouvelles observations.

Une relance sans nouvelle donnée ne crée aucune ligne supplémentaire.

## Index PostgreSQL

Les index suivants sont gérés directement par dbt :

```text
UNIQUE (daily_station_id)
(station_id, observation_date)
(observation_date)
```

L’index unique garantit le grain du modèle.

L’index composite accélère l’historique quotidien d’une station.

L’index sur la date accélère les comparaisons temporelles entre stations et les
filtres des futurs tableaux de bord.

## Validation du grain

Résultat observé après la première construction :

```text
daily_station_rows = 1720
unique_station_days = 1720
aggregated_observations = 3528
first_date = 2021-02-21
latest_date = 2026-07-17
```

Le nombre de lignes est identique au nombre de couples station/journée
distincts.

Les 3 528 observations présentes au moment de la première construction ont été
représentées exactement une fois dans les agrégats quotidiens.

## Volumétrie

Mesure locale après création du modèle :

| Élément | Valeur |
|---|---:|
| Lignes estimées | 1 720 |
| Taille de la table | 296 kB |
| Taille des index | 224 kB |
| Taille totale | 560 kB |

La réduction actuelle reste limitée, car l’historique local contient encore
peu d’observations par station et par journée.

Avec une ingestion horaire complète, une station peut produire environ
24 observations détaillées par jour, contre une seule ligne dans le modèle
quotidien.

La réduction du nombre de lignes pourra donc approcher un facteur 24 pour les
journées complètes.

## Tests

### Tests génériques

Les colonnes principales sont contrôlées avec les tests dbt suivants :

- `unique` ;
- `not_null` ;
- `relationships`.

La relation entre `agg_velib_station_daily.station_id` et
`dim_stations.station_id` est vérifiée automatiquement.

### Cohérence des métriques

Le test suivant a été ajouté :

```text
assert_daily_metrics_are_consistent
```

Il vérifie notamment que :

- le nombre d’observations est strictement positif ;
- la moyenne de vélos reste comprise entre le minimum et le maximum ;
- les compteurs d’événements restent compris entre zéro et le nombre total
  d’observations ;
- la première observation ne se situe pas après la dernière.

### Correspondance avec la table de faits

Le test suivant a été ajouté :

```text
assert_daily_aggregate_matches_fact
```

Il compare, pour chaque station et chaque journée, le nombre d’observations de
la table de faits avec le nombre enregistré dans le modèle quotidien.

Toute observation manquante, dupliquée ou attribuée à une mauvaise journée
fait échouer ce test.

## Résultat des tests

Validation ciblée du modèle quotidien :

```text
PASS = 20
WARN = 0
ERROR = 0
SKIP = 0
```

Validation complète du projet dbt :

```text
PASS = 56
WARN = 1
ERROR = 0
SKIP = 0
TOTAL = 57
```

L’avertissement correspond au contrôle connu des observations pour lesquelles
le nombre de vélos disponibles dépasse temporairement la capacité déclarée par
l’API.

## Validation Airflow de bout en bout

Un test complet du DAG Airflow a été exécuté après la création du modèle.

Résultat de l’ingestion :

```text
pages_fetched = 16
reported_total = 1516
records_received = 1516
records_inserted = 1503
duplicates_ignored = 13
```

Résultat de la transformation :

```text
Modèles dbt : 5 réussis
Tests dbt : 56 réussis, 1 avertissement, 0 erreur
État final du DAG : success
```

Après cette nouvelle ingestion :

```text
fact_rows = 5031
aggregated_observations = 5031
daily_station_rows = 1720
latest_aggregate_load = 2026-07-18 00:44:06.267046
```

L’égalité entre `fact_rows` et `aggregated_observations` confirme que le
traitement incrémental a intégré les nouvelles observations sans perte ni
double comptage.

## Données historiques atypiques

La plage temporelle contient quelques observations anciennes et isolées.

Ces dates proviennent des horodatages métier transmis par l’API. Elles sont
conservées sans correction artificielle afin de préserver la traçabilité de la
source.

Les contrôles de qualité permettent de les identifier sans altérer les données
brutes.

## Utilisation future dans Superset

Le modèle quotidien pourra alimenter des visualisations telles que :

- disponibilité moyenne par station et par jour ;
- stations régulièrement vides ;
- stations régulièrement saturées ;
- évolution quotidienne du taux d’occupation ;
- fréquence des interruptions de service ;
- fréquence des anomalies de capacité ;
- comparaison entre communes et périodes.

Les attributs descriptifs et géographiques restent disponibles dans
`dim_stations`.

## Rétention

Aucune ligne RAW ou analytique n’est supprimée pendant ce sprint.

Le modèle quotidien constitue un prérequis à une future politique de
rétention, mais celle-ci ne sera activée qu’après :

1. la mise en place des sauvegardes PostgreSQL ;
2. la validation d’une procédure de restauration ;
3. la protection des reconstructions dbt complètes ;
4. la validation explicite de la durée de conservation ;
5. la vérification des tableaux de bord utilisant l’historique détaillé.

## Fichiers concernés

Fichiers créés :

- `dbt_mobility/models/marts/agg_velib_station_daily.sql` ;
- `dbt_mobility/tests/assert_daily_metrics_are_consistent.sql` ;
- `dbt_mobility/tests/assert_daily_aggregate_matches_fact.sql` ;
- `docs/sprints/sprint-06.md`.

Fichier modifié :

- `dbt_mobility/models/marts/schema.yml`.

## Suite

Les prochaines étapes prévues sont :

- préparer les sauvegardes PostgreSQL ;
- documenter la restauration ;
- surveiller la croissance réelle des tables ;
- définir la rétention définitive ;
- construire les tableaux de bord Superset en fin de projet.