# Sprint 12 — Dashboard Superset du trafic routier parisien

## Objectif

Construire un dashboard Superset consacré à l’état actuel et à l’évolution récente du trafic routier parisien.

Le dashboard doit permettre de consulter :

- le nombre d’arcs routiers suivis ;
- le débit moyen de véhicules ;
- le taux d’occupation moyen ;
- le nombre d’arcs congestionnés ;
- la répartition des arcs par état du trafic ;
- la localisation et l’état des arcs routiers ;
- l’évolution quotidienne du débit routier.

## Branche

```text
feat/superset-road-traffic-dashboard
```

## Données disponibles

Le contrôle initial de la table de faits a donné :

```text
fact_rows=8937
arcs=2979
first_observation=2026-07-17 20:00:00+00
latest_observation=2026-07-17 22:00:00+00
flow_measurements=4792
occupancy_measurements=4927
```

Répartition historique des observations :

```text
Fluide=4507
Inconnu=4010
Pré-saturé=292
Saturé=92
Bloqué=36
```

## Modèle de statut courant

Le modèle dbt suivant a été ajouté :

```text
schema_analytics.fct_road_traffic_current_status
```

Le modèle est matérialisé sous forme de vue.

Une ligne représente le dernier état connu d’un arc routier.

### Grain

```text
arc_id
```

### Source

Le modèle utilise directement :

```text
schema_analytics.stg_road_traffic
```

Cette source permet de conserver un état courant complet même lorsque les anciennes observations détaillées sont supprimées par la politique de rétention.

### Sélection de l’état courant

Les observations sont classées par arc selon :

1. `observed_at` décroissant ;
2. `loaded_at` décroissant.

Seule la première observation de chaque arc est conservée.

### Colonnes principales

Le modèle expose notamment :

- `observation_id` ;
- `arc_id` ;
- `arc_label` ;
- `observed_at` ;
- `vehicle_flow` ;
- `occupancy_rate` ;
- `traffic_status` ;
- `arc_status` ;
- les nœuds amont et aval ;
- `longitude` ;
- `latitude` ;
- `geo_shape` ;
- les indicateurs de disponibilité des mesures ;
- `loaded_at` ;
- `source_run_id` ;
- `data_age_minutes` ;
- `is_fresh`.

Une observation est considérée comme fraîche lorsque son chargement date de moins de deux heures.

## Résultat du modèle courant

Le contrôle fonctionnel a donné :

```text
current_rows=2979
unique_arcs=2979
arcs_with_flow=1579
average_vehicle_flow=650.93
arcs_with_occupancy=1624
average_occupancy_rate=6.91
congested_arcs=46
fresh_arcs=0
```

Répartition du dernier état connu :

```text
Fluide=1474
Inconnu=1355
Pré-saturé=104
Saturé=33
Bloqué=13
```

Le grain est conforme : une ligne est présente pour chacun des 2 979 arcs distincts.

## Coordonnées absentes

Trente-et-un arcs ne possèdent pas de longitude ou de latitude dans les données sources.

Ces valeurs nulles sont acceptées et documentées.

La carte Superset utilise l’option :

```text
Ignore null locations
```

Les arcs concernés restent disponibles pour les KPI et les analyses, mais ne sont pas affichés sur la carte.

## Contrôle de cohérence

Le test singulier suivant a été ajouté :

```text
dbt_mobility/tests/assert_current_road_traffic_matches_staging.sql
```

Il vérifie que le nombre de lignes de la vue courante correspond au nombre d’arcs distincts présents dans le staging.

Les tests du modèle courant ont donné :

```text
PASS=18
WARN=0
ERROR=0
SKIP=0
TOTAL=18
```

## Gestion de la fraîcheur de la source

Une nouvelle exécution du DAG routier a interrogé l’API avec succès.

Résultat :

```text
records_received=8937
records_inserted=0
records_updated=0
records_unchanged=8937
```

L’API ne fournissait aucune observation plus récente que :

```text
2026-07-17 22:00:00+00
```

La fraîcheur dbt signalait donc correctement une source périmée.

## Correction du DAG routier

Le contrôle `dbt source freshness` était exécuté à la fin de la tâche principale du DAG.

Une API techniquement disponible mais sans nouvelle observation provoquait ainsi l’échec complet du DAG après une ingestion, une transformation et des tests réussis.

Le contrôle bloquant a été retiré de la tâche principale.

Le DAG continue d’exécuter :

- les transformations dbt du trafic routier ;
- les tests de modèles ;
- les tests des sources ;
- les tests du monitoring.

Le contrôle de fraîcheur reste disponible séparément pour le diagnostic et l’observabilité.

Après correction, le test complet du DAG a terminé avec :

```text
state=success
```

## Dataset Superset courant

Le dataset suivant a été créé :

```text
schema_analytics.fct_road_traffic_current_status
```

Il alimente :

- les quatre KPI ;
- le diagramme de répartition ;
- la carte routière.

## Dataset Superset historique

Le dataset suivant est utilisé pour l’évolution quotidienne :

```text
schema_analytics.agg_road_traffic_daily
```

Son grain est :

```text
arc_id + observation_date
```

## Dashboard Superset

Le dashboard publié porte le nom :

```text
Trafic routier parisien
```

## Visualisations

### Arcs routiers observés

Type :

```text
Big Number
```

Mesure :

```text
COUNT_DISTINCT(arc_id)
```

Résultat observé :

```text
2979
```

### Débit moyen de véhicules

Type :

```text
Big Number
```

Mesure :

```text
AVG(vehicle_flow)
```

Les valeurs nulles sont ignorées par la moyenne.

Résultat observé :

```text
650.93 véhicules par heure et par arc
```

### Taux d’occupation moyen

Type :

```text
Big Number
```

Mesure :

```text
AVG(occupancy_rate)
```

Résultat observé :

```text
6.91 %
```

### Arcs congestionnés

Type :

```text
Big Number
```

Mesure :

```text
COUNT_DISTINCT(arc_id)
```

Filtre :

```text
traffic_status IN ('Saturé', 'Bloqué')
```

Résultat observé :

```text
46
```

### Répartition des arcs par état du trafic

Type :

```text
Pie Chart
```

Dimension :

```text
traffic_status
```

Mesure :

```text
COUNT_DISTINCT(arc_id)
```

Le graphique est affiché sous forme de donut avec la catégorie et le pourcentage.

### Carte de l’état du trafic routier

Type :

```text
deck.gl Scatterplot
```

Coordonnées :

```text
longitude
latitude
```

La couleur des points dépend de :

```text
traffic_status
```

Les colonnes transmises à l’infobulle sont :

```text
arc_label
traffic_status
arc_status
vehicle_flow
occupancy_rate
```

L’infobulle affiche :

- le libellé de l’arc ;
- l’état du trafic ;
- l’état opérationnel de l’arc ;
- le débit horaire ;
- le taux d’occupation.

### Évolution quotidienne du débit routier

Type :

```text
Line Chart
```

Axe temporel :

```text
observation_date
```

Grain temporel :

```text
Day
```

Fenêtre temporelle :

```text
Last month
```

La moyenne quotidienne est pondérée par le nombre de mesures disponibles :

```sql
SUM(
    average_vehicle_flow
    * vehicle_flow_observation_count
)
/
NULLIF(
    SUM(vehicle_flow_observation_count),
    0
)
```

Libellé :

```text
Débit moyen quotidien
```

Résultat disponible pour le 17 juillet 2026 :

```text
635.59 véhicules par heure
```

Un seul point est actuellement affiché car l’agrégat exploitable ne couvre qu’une journée. Le graphique s’enrichira automatiquement avec les prochaines ingestions.

## Organisation du dashboard

La première ligne contient les quatre KPI avec une largeur identique.

La deuxième ligne contient :

- la répartition des arcs par état, sur un tiers de la largeur ;
- la carte routière, sur deux tiers de la largeur.

La troisième ligne contient le graphique d’évolution quotidienne.

## Export versionné

L’export Superset est stocké dans :

```text
superset/exports/road_traffic
```

Il contient :

- 7 graphiques ;
- 1 dashboard ;
- 2 datasets ;
- la définition de la connexion PostgreSQL ;
- les métadonnées d’export.

## Protection des secrets

L’URI PostgreSQL exportée contient un mot de passe masqué :

```text
postgresql+psycopg2://data_engineer:XXXXXXXXXX@postgres_destination:5432/mobility_warehouse
```

Aucun secret réel, mot de passe, jeton ou clé d’API n’est présent dans l’export versionné.

## Résultat

Le dashboard permet désormais de consulter le dernier état connu du trafic routier parisien, les niveaux de congestion, les mesures de débit et d’occupation, la répartition géographique des arcs et l’évolution quotidienne du trafic.

## Suite

Le Sprint 13 sera consacré à la finalisation locale du projet :

- documentation générale ;
- mise à jour du README ;
- validation complète des pipelines ;
- audit de sécurité ;
- nettoyage des fichiers ;
- préparation du déploiement.