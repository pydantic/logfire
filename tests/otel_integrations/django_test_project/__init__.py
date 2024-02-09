import sys
from pathlib import Path

from opentelemetry.instrumentation.django import DjangoInstrumentor

sys.path.append(str(Path(__file__).parent))


DjangoInstrumentor().instrument()
