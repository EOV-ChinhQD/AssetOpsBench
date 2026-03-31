import os
import sys
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from io import StringIO
import contextlib
from typing import Dict, Any

def execute_python_code(code: str, data_context: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Executes Python code in a restricted environment.
    Provides access to pandas, matplotlib, and data_context.
    """
    # 1. Setup local environment
    loc = {
        "pd": pd,
        "plt": plt,
        "np": np,
        "data": data_context or {}
    }
    
    # 2. Redirect stdout
    stdout = StringIO()
    
    # 3. Create plots directory if it doesn't exist
    plots_dir = os.path.join(os.getcwd(), "plots")
    os.makedirs(plots_dir, exist_ok=True)
    
    try:
        with contextlib.redirect_stdout(stdout):
            # Execute the code
            exec(code, {}, loc)
            
            # Check if a plot was created (look for any active figures)
            if plt.get_fignums():
                plot_filename = f"dynamic_plot_{os.getpid()}.png"
                plot_path = os.path.join(plots_dir, plot_filename)
                plt.savefig(plot_path)
                plt.close()
                
                # --- [NEW] MinIO Upload logic ---
                minio_endpoint = os.getenv("MINIO_ENDPOINT")
                if minio_endpoint:
                    try:
                        from minio import Minio
                        client = Minio(
                            minio_endpoint,
                            access_key=os.getenv("MINIO_ACCESS_KEY"),
                            secret_key=os.getenv("MINIO_SECRET_KEY"),
                            secure=os.getenv("MINIO_USE_SSL", "false").lower() == "true"
                        )
                        bucket = os.getenv("MINIO_BUCKET", "hanoi-water-images")
                        # Ensure bucket exists
                        if not client.bucket_exists(bucket):
                            client.make_bucket(bucket)
                        
                        # Upload
                        client.fput_object(bucket, plot_filename, plot_path)
                        public_url = f"{os.getenv('IMAGE_STORAGE_BASE_URL')}/{plot_filename}"
                        url_msg = f"Biểu đồ đã được lưu tại: {public_url}"
                    except Exception as upload_err:
                        url_msg = f"Lỗi upload MinIO: {upload_err}. (Local: file://{plot_path})"
                else:
                    url_msg = f"Biểu đồ đã được lưu tại: file://{plot_path}"
                
                output_msg = f"Output: {stdout.getvalue()}\n{url_msg}"
            else:
                output_msg = f"Output: {stdout.getvalue()}"
                
        return {"status": "success", "result": output_msg}
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    test_code = """
import pandas as pd
df = pd.DataFrame({'month': ['Jan', 'Feb', 'Mar'], 'value': [10, 20, 15]})
print(df)
df.plot(x='month', y='value', kind='bar')
"""
    print(execute_python_code(test_code))
