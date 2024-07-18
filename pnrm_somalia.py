# -*- coding: utf-8 -*-
"""pnrm-somalia.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/15bUxEEugjn1FIEHyVNVm8UK24wgyiWJn
"""

import requests
from datetime import datetime
import geopandas as gpd

api_url = "https://prmn-somalia.unhcr.org/api/displacement-data/All/All/All/All/All/All/d/{start_date}/{final_date}"
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_5) AppleWebKit/537.36 (KHTML, like Gecko)',
    'referer': 'https://prmn-somalia.unhcr.org'
}

r = requests.get(api_url.format(start_date='2016-01-01', final_date=datetime.now().strftime('%Y-%m-%d')), headers=headers)
# r = requests.get("https://prmn-somalia.unhcr.org/api/displacement-data/All/All/All/All/All/All/d/2001-01-01/2015-12-31", headers=headers)

if r.status_code != 201:
    r.raise_for_status()

data = r.json()
gdf = gpd.GeoDataFrame.from_features(data['geojson']).set_crs(epsg=4326).rename(
    columns={
        'geometry':'geom',
        'AllPeople': 'total_displaced',
        'Category': 'hazard',
        'CurentRegion':'region_of_origin',
        'CurrentDistrict': 'district_of_origin',
        'CurrentSettlement': 'place_of_settlement',
        'Date': 'displacement_date',
        'key':'comment'}
).set_geometry('geom')
gdf.head()

# from sqlalchemy import create_engine
# from sqlalchemy.engine import URL
# from mukau.settings import Settings

# def get_external_db_engine(port: int, host: str | None = '197.254.13.230'):
#     settings = Settings()

#     db_str = URL.create(
#         drivername=settings.driver_name,
#         host=host,
#         port=port,
#         password=settings.db_password,
#         username=settings.db_user,
#         database=settings.db_name,
#     )
#     return create_engine(db_str, echo=False)


# conn2 = get_external_db_engine(port=6752)
# conn4 = get_external_db_engine(port=6754)
# conn2

# gdf.head()

from mukau.settings import create_sa_engine

conn = create_sa_engine()

admin = gpd.read_postgis(
    con=conn,
    sql="SELECT gid_0, gid_1, gid_2, geom FROM thematic.gadm4_admin_level2_boundaries WHERE gid_0 = 'SOM'"
)

join = gpd.sjoin(
    admin,
    gdf,
    predicate='contains'
).drop(columns=['index_right','geom'])
join.head()

cleaned = join.groupby(
    [col for col in join.columns.tolist() if col != 'total_displaced']
).agg({'total_displaced':'sum'}).rename(
    columns={'total_displaced':'displaced'}
).reset_index().query('displaced > 0').rename(
    columns={'displaced':'total_displaced'}
)
cleaned.head()

index_cols = ['gid_2', 'hazard', 'total_displaced', 'displacement_date', 'district_of_origin', 'place_of_settlement']
dups = cleaned[cleaned.duplicated(subset=index_cols, keep=False)]
dups.head()

import math
from datetime import datetime
from pangres import upsert
from tqdm import tqdm
from sqlalchemy import Engine

def insert_upsert(
        conn: Engine,
        df: gpd.GeoDataFrame,
        table_name: str,
        schema: str,
        index_cols: list[str],
        if_row_exists: str | None = "update",
        chunksize: int | None = 20000,
    ):
        print(f"Executing insert/update into {schema}.{table_name}")
        df = df.assign(updated_when=datetime.now()).set_index(index_cols)
        iterator = upsert(
            con=conn,
            df=df,
            table_name=table_name,
            schema=schema,
            if_row_exists=if_row_exists,
            chunksize=chunksize,
            yield_chunks=True,
        )
        iterations = math.ceil(len(df) / chunksize)
        for _ in tqdm(
            iterator,
            desc=f"Upsert into {schema}.{table_name}",
            total=iterations,
            unit="chunk",
        ):
            pass

insert_upsert(df=cleaned, conn=conn, table_name='prmn_somalia_unhcr_org', schema='displacement', index_cols=index_cols, chunksize=10000)

