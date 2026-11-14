"""Controller-owned construction capacity and pre-dispatch reservation."""
from .billing import reserve_cost

# A transport/resource bound, not a model context-window or prompt-injection defense.
# Shared by native and Docker coding so ordinary multi-file history has room to grow.
MAX_REQUEST_BYTES=2*1024*1024
MAX_OUTPUT_TOKENS=6000
LONG_CONTEXT_INPUT_TOKENS=272000


def cost_estimate(cfg,input_tokens,output_tokens):
    """Compatibility entry for reservation only; settlement uses billing.settlement."""
    return reserve_cost(cfg,input_tokens,output_tokens)
