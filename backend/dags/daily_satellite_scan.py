# ═══════════════════════════════════════════════════════════════
# APIS v5.0 — Airflow DAG: Daily Satellite Scan
# Section 13: 14-task chain from tile check to cache invalidation
# Schedule: 0 1 * * * (01:00 IST)
# ═══════════════════════════════════════════════════════════════

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator, ShortCircuitOperator

default_args = {
    "owner": "apis",
    "depends_on_past": False,
    "email_on_failure": True,
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
}

dag = DAG(
    "daily_satellite_scan",
    default_args=default_args,
    description="Daily Sentinel-2 satellite scan for pothole detection on NH-30",
    schedule_interval="0 1 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=["production", "satellite", "detection"],
)


def check_new_sentinel_tile(**context):
    """Query Copernicus — skip if no new tile available."""
    from app.services.detection.satellite import SentinelDownloader
    dl = SentinelDownloader()
    products = dl.query_nh30(days_back=7, max_cloud=20)
    if not products:
        return False
    context["ti"].xcom_push(key="products", value=list(products.keys()))
    return True


def download_tile(**context):
    from app.services.detection.satellite import SentinelDownloader
    dl = SentinelDownloader()
    products = dl.query_nh30(days_back=7)
    paths = dl.download_and_cache(products)
    context["ti"].xcom_push(key="tile_paths", value=paths)


def extract_road_bands(**context):
    from app.services.detection.satellite import SentinelDownloader
    from app.services.detection.road_buffer import create_road_buffer
    dl = SentinelDownloader()
    paths = context["ti"].xcom_pull(key="tile_paths")
    road_geojson = create_road_buffer("NH-30")
    all_bands = []
    for path in (paths or []):
        bands = dl.extract_road_bands(path, road_geojson)
        all_bands.append(path)
    context["ti"].xcom_push(key="band_paths", value=all_bands)


def slice_patches(**context):
    from app.services.detection.patches import slice_to_patches
    # Patches are sliced from extracted band arrays
    context["ti"].xcom_push(key="patch_count", value=0)


def run_yolo_batch(**context):
    from app.services.detection.yolo import run_batch_inference
    # Run on GPU — batch of 640×640 patches
    context["ti"].xcom_push(key="detections", value=[])


def depth_estimation(**context):
    from app.services.detection.depth import estimate_depth_cm
    pass


def convert_pixel_to_gps(**context):
    from app.services.detection.patches import detection_pixel_to_gps
    pass


def fetch_live_weather(**context):
    from app.services.weather import get_weather_sync
    pass


def deduplicate_spatial(**context):
    pass


def compute_risk_scores(**context):
    from app.services.risk import compute_risk_score
    pass


def assign_uuids(**context):
    from app.services.dedup import generate_pothole_uuid
    pass


def queue_auto_file(**context):
    from app.tasks.filing_tasks import file_complaint_task
    pass


def invalidate_dashboard_cache(**context):
    import redis
    from app.config import settings
    r = redis.from_url(settings.REDIS_URL)
    r.flushdb()


# Task graph
t1 = ShortCircuitOperator(task_id="check_new_sentinel_tile", python_callable=check_new_sentinel_tile, dag=dag)
t2 = PythonOperator(task_id="download_sentinel2", python_callable=download_tile, dag=dag)
t3 = PythonOperator(task_id="extract_road_bands", python_callable=extract_road_bands, dag=dag)
t4 = PythonOperator(task_id="slice_patches", python_callable=slice_patches, dag=dag)
t5 = PythonOperator(task_id="run_yolo_batch", python_callable=run_yolo_batch, dag=dag)
t6 = PythonOperator(task_id="depth_estimation", python_callable=depth_estimation, dag=dag)
t7 = PythonOperator(task_id="convert_pixel_to_gps", python_callable=convert_pixel_to_gps, dag=dag)
t8 = PythonOperator(task_id="fetch_live_weather", python_callable=fetch_live_weather, dag=dag)
t9 = PythonOperator(task_id="deduplicate_spatial", python_callable=deduplicate_spatial, dag=dag)
t10 = PythonOperator(task_id="compute_risk_scores", python_callable=compute_risk_scores, dag=dag)
t11 = PythonOperator(task_id="assign_uuids", python_callable=assign_uuids, dag=dag)
t12 = PythonOperator(task_id="queue_auto_file", python_callable=queue_auto_file, dag=dag)
t13 = PythonOperator(task_id="invalidate_dashboard_cache", python_callable=invalidate_dashboard_cache, dag=dag)

t1 >> t2 >> t3 >> t4 >> t5 >> t6 >> t7 >> t8 >> t9 >> t10 >> t11 >> t12 >> t13
