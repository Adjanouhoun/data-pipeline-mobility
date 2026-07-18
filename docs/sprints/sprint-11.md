# Sprint 11 — Dashboard Superset de disponibilité Vélib

## Objectif

Construire un dashboard Superset consacré à la disponibilité actuelle des stations Vélib et à son évolution récente.

Le dashboard doit permettre de consulter rapidement :

- le nombre de stations observées ;
- le nombre de vélos disponibles ;
- le nombre de bornes disponibles ;
- le nombre de stations vides ;
- la répartition des stations par statut ;
- la position et l’état de chaque station ;
- l’évolution quotidienne du nombre moyen de vélos disponibles.

## Branche

```text
feat/superset-velib-dashboard
```

## Modèle de statut courant

Le modèle dbt suivant a été ajouté :

```text
schema_analytics.fct_velib_current_status
```

Le modèle est matérialisé sous forme de vue.

Une ligne représente le dernier état connu d’une station Vélib.

### Grain

```text
station_id
```

### Source

Le modèle utilise directement :

```text
schema_analytics.stg_velib_stations
```

Cette source est utilisée afin que le statut courant reste disponible même lorsque les anciennes observations détaillées sont supprimées de la table de faits par la politique de rétention.

### Sélection de l’état courant

Les observations sont classées par station selon :

1. `status_updated_at` décroissant ;
2. `loaded_at` décroissant.

Seule l’observation classée en première position est conservée.

### Colonnes calculées

Le modèle calcule notamment :

- `observation_id` ;
- `occupancy_rate_percent` ;
- `station_status` ;
- `data_age_minutes` ;
- `is_fresh`.

### Statuts analytiques

Les valeurs possibles de `station_status` sont :

- `Normal` ;
- `Presque pleine` ;
- `Presque vide` ;
- `Vide` ;
- `Hors service` ;
- `Non installée`.

Une station est considérée comme fraîche lorsque son dernier chargement date de moins de deux heures.

## Contrôle de cohérence

Le test singulier suivant a été ajouté :

```text
dbt_mobility/tests/assert_current_velib_status_matches_staging.sql
```

Il vérifie que le nombre de stations présentes dans la vue courante correspond au nombre de stations distinctes disponibles dans le staging.

Résultat :

```text
PASS=20
WARN=0
ERROR=0
SKIP=0
TOTAL=20
```

## Résultat fonctionnel du modèle

Le contrôle effectué après reconstruction du modèle a donné :

```text
stations=1516
bikes_available=18516
mechanical_bikes=11218
electric_bikes=7298
docks_available=29085
empty_stations=29
out_of_service_stations=17
```

Le nombre de stations courantes correspond aux 1 516 identifiants de station distincts présents dans le staging.

## Correction du DAG Vélib

La tâche dbt du DAG Vélib exécutait auparavant la fraîcheur de toutes les sources du projet.

Une source de trafic routier périmée pouvait donc provoquer l’échec du DAG Vélib alors que l’ingestion Vélib elle-même avait réussi.

Les sélections dbt du DAG ont été limitées aux ressources nécessaires au pipeline Vélib :

```text
stg_velib_stations+
fct_ingestion_runs
fct_pipeline_runs
source:raw_data
source:monitoring_data.ingestion_runs
```

Le DAG Vélib ne dépend ainsi plus de la fraîcheur du pipeline de trafic routier.

Le test complet du DAG a terminé avec le statut :

```text
state=success
```

## Dataset Superset courant

Le dataset Superset suivant a été créé :

```text
schema_analytics.fct_velib_current_status
```

Il alimente les KPI, le diagramme de statut et la carte.

## Dataset Superset historique

Le dataset suivant est utilisé pour l’évolution quotidienne :

```text
schema_analytics.agg_velib_station_daily
```

Il contient une ligne par station et par date d’observation.

Le graphique historique utilise une fenêtre glissante d’un mois afin d’intégrer automatiquement les nouvelles observations.

## Dashboard Superset

Le dashboard publié porte le nom :

```text
Disponibilité Vélib
```

## Visualisations

### Stations Vélib observées

Type :

```text
Big Number
```

Mesure :

```text
COUNT_DISTINCT(station_id)
```

### Vélos disponibles

Type :

```text
Big Number
```

Mesure :

```text
SUM(bikes_available)
```

### Bornes disponibles maintenant

Type :

```text
Big Number
```

Mesure :

```text
SUM(docks_available)
```

### Stations vides

Type :

```text
Big Number
```

Filtre :

```text
station_status = 'Vide'
```

### Répartition des stations par statut

Type :

```text
Pie Chart
```

Dimension :

```text
station_status
```

Mesure :

```text
COUNT_DISTINCT(station_id)
```

### Carte de disponibilité des stations Vélib

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
station_status
```

L’infobulle affiche :

- le nom de la station ;
- la catégorie analytique ;
- le nombre de vélos disponibles ;
- le nombre de bornes disponibles.

Les colonnes utilisées dans `Extra Data for JS` sont :

```text
station_name
station_status
bikes_available
docks_available
```

### Évolution quotidienne des vélos disponibles

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

Mesure :

```text
AVG(average_bikes_available)
```

Fenêtre temporelle :

```text
Last month
```

## Configuration JavaScript de Superset

Les contrôles JavaScript ont été activés avec le feature flag :

```python
FEATURE_FLAGS = {
    "ENABLE_JAVASCRIPT_CONTROLS": True,
}
```

La politique CSP de Superset a été ajustée pour autoriser l’exécution du générateur d’infobulle :

```python
from superset.config import TALISMAN_CONFIG

TALISMAN_CONFIG[
    "content_security_policy"
][
    "script-src"
].append("'unsafe-eval'")
```

Cette autorisation est nécessaire au fonctionnement des contrôles JavaScript de la carte.

Elle réduit cependant la protection CSP. Les droits permettant de modifier les graphiques et leur JavaScript devront être réservés aux administrateurs de confiance lors du déploiement.

## Export versionné

L’export Superset est stocké dans :

```text
superset/exports/velib_availability
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

Aucun mot de passe réel, secret, jeton ou clé d’API n’est présent dans l’export versionné.

## Résultat

Le dashboard permet désormais de suivre la disponibilité actuelle des stations Vélib, leur répartition géographique, leur état opérationnel et l’évolution récente du nombre moyen de vélos disponibles.

## Suite

Le prochain sprint pourra construire le dashboard Superset consacré au trafic routier parisien, en réutilisant :

- `fct_road_traffic` ;
- `dim_road_arcs` ;
- `agg_road_traffic_daily` ;
- `fct_traffic_ingestion_runs`.