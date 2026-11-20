import os

os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
os.environ["LITELLM_MODE"] = "DEV"
os.environ["LITELLM_TELEMETRY"] = "False"
os.environ["ANONYMOUS_TELEMETRY"] = "False"
