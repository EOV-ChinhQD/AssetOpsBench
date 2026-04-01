from src.hanoi_water_db import get_engine
from sqlalchemy import text

engine = get_engine()

def seed():
    with engine.connect() as conn:
        print("Creating schemas and ensuring correct YYYY-MM formats...")
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS app;"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS silver;"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS gold;"))
        
        # Drop and recreate to ensure VARCHAR(7) as requested
        conn.execute(text("DROP TABLE IF EXISTS silver.stg_water_demand CASCADE;"))
        conn.execute(text("DROP TABLE IF EXISTS gold.v_forecasts CASCADE;"))
        
        # 1. User Preferences
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS app.user_preferences (
                id SERIAL PRIMARY KEY,
                user_id VARCHAR(255),
                pref_key VARCHAR(255),
                pref_value TEXT,
                source VARCHAR(50),
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, pref_key)
            );
        """))
        
        # 2. Silver Data (Historical) - Forced to VARCHAR(7)
        conn.execute(text("""
            CREATE TABLE silver.stg_water_demand (
                id SERIAL PRIMARY KEY,
                madma VARCHAR(50),
                nam INT,
                thang INT,
                tongsl FLOAT,
                year_month VARCHAR(7)
            );
        """))
        
        # 3. Gold Data (Forecasts) - Forced to VARCHAR(7)
        conn.execute(text("""
            CREATE TABLE gold.v_forecasts (
                madma VARCHAR(50),
                year_month VARCHAR(7),
                predicted_demand FLOAT,
                source VARCHAR(50)
            );
        """))
        
        print("Inserting standardized test data (YYYY-MM)...")
        # 06-QM Historical
        conn.execute(text("""
            INSERT INTO silver.stg_water_demand (madma, nam, thang, tongsl, year_month)
            VALUES ('06-QM', 2024, 10, 8560, '2024-10');
        """))
        
        # 05-LB Historical
        conn.execute(text("""
            INSERT INTO silver.stg_water_demand (madma, nam, thang, tongsl, year_month)
            VALUES ('05-LB', 2024, 9, 95180, '2024-09');
        """))
        
        # 01-LB Forecast
        conn.execute(text("""
            INSERT INTO gold.v_forecasts (madma, year_month, predicted_demand, source)
            VALUES ('01-LB', '2026-04', 34653.0, 'Short-term');
        """))
        
        # Additional DMAs for text_to_sql testing
        conn.execute(text("""
            INSERT INTO silver.stg_water_demand (madma, nam, thang, tongsl, year_month)
            VALUES ('01-LT', 2024, 10, 1000, '2024-10'),
                   ('01-BM', 2024, 10, 2000, '2024-10');
        """))
        
        conn.commit()
        print("Seed 100% completed with YYYY-MM format!")

if __name__ == "__main__":
    seed()
