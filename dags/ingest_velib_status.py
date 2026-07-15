from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
from datetime import datetime, timedelta
import requests

default_args = {
    'owner': 'Amadou',
    'depends_on_past': False,
    'start_date': datetime(2026, 7, 1),
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

def extract_and_load_velib():
    # URL de l'API Open Data Paris avec limite à 100 stations
    api_url = "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/velib-disponibilite-en-temps-reel/records?limit=100"
    response = requests.get(api_url)
    if response.status_code != 200:
        raise Exception(f"Erreur lors de l'appel API: {response.status_code}")
    
    data = response.json()
    records = data.get('results', [])
    
    pg_hook = PostgresHook(postgres_conn_id='postgres_dest_conn')
    conn = pg_hook.get_conn()
    cursor = conn.cursor()
    
    # 1. Création de la table RAW avec l'intégralité des 16 champs de l'API
    cursor.execute("""
        CREATE SCHEMA IF NOT EXISTS schema_raw;
        CREATE TABLE IF NOT EXISTS schema_raw.stg_raw_stations (
            stationcode VARCHAR(50),
            name VARCHAR(255),
            is_installed VARCHAR(10),
            capacity INT,
            num_docks_available INT,
            num_bikes_available INT,
            mechanical INT,
            ebike INT,
            is_renting VARCHAR(10),
            is_returning VARCHAR(10),
            last_reported TIMESTAMP,
            lon DOUBLE PRECISION,
            lat DOUBLE PRECISION,
            nom_arrondissement_communes VARCHAR(255),
            code_insee_commune VARCHAR(50),
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    
    # 2. Insertion de toutes les clés de l'API
    for record in records:
        # Extraction de la latitude et longitude du dictionnaire coordonnees_geo
        coords = record.get('coordonnees_geo', {})
        lon = coords.get('lon') if coords else None
        lat = coords.get('lat') if coords else None

        cursor.execute("""
            INSERT INTO schema_raw.stg_raw_stations 
            (
                stationcode, name, is_installed, capacity, num_docks_available, 
                num_bikes_available, mechanical, ebike, is_renting, is_returning, 
                last_reported, lon, lat, nom_arrondissement_communes, code_insee_commune
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
        """, (
            record.get('stationcode'),
            record.get('name'),
            record.get('is_installed'),
            record.get('capacity'),
            record.get('numdocksavailable'),
            record.get('numbikesavailable'),
            record.get('mechanical'),
            record.get('ebike'),
            record.get('is_renting'),
            record.get('is_returning'),
            record.get('duedate'), # duedate contient le timestamp de mise à jour dans l'API
            lon,
            lat,
            record.get('nom_arrondissement_communes'),
            record.get('code_insee_commune')
        ))
        
    conn.commit()
    cursor.close()
    conn.close()
    print(f"🎉 Ingestion réussie : {len(records)} stations insérées avec tous leurs attributs.")

with DAG(
    'ingest_and_transform_velib',
    default_args=default_args,
    description='Pipeline unifié : Ingestion API & Transformation dbt',
    schedule_interval='@hourly',
    catchup=False
) as dag:

    ingest_task = PythonOperator(
        task_id='extract_and_load_velib_task',
        python_callable=extract_and_load_velib
    )

    dbt_run_task = BashOperator(
        task_id='dbt_run_task',
        bash_command='''
        python -m pip install dbt-postgres==1.9.1
        cd /opt/airflow/dbt_mobility
        dbt run --profiles-dir .
        dbt test --profiles-dir .
        '''
    )

    ingest_task >> dbt_run_task