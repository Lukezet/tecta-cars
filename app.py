from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import uvicorn

from detecta_images.api import create_app


app = create_app()


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
