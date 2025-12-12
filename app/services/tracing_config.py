"""Tracing configuration for Neon Trader observability.

Sets up OpenTelemetry tracing for the multi-agent orchestration system.
Enables visualization of agent research, council deliberation, and trade execution.
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Configuration from environment or defaults
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "http://localhost:4317")
OTLP_ENABLED = os.getenv("OTLP_ENABLED", "true").lower() == "true"
ENABLE_SENSITIVE_DATA = os.getenv("ENABLE_SENSITIVE_DATA", "true").lower() == "true"


def setup_tracing(endpoint: Optional[str] = None, enable_sensitive: bool = True) -> bool:
    """Initialize OpenTelemetry tracing for the application.

    Args:
        endpoint: OTLP gRPC endpoint (default: OTLP_ENDPOINT env var or localhost:4317)
        enable_sensitive: Enable capturing prompts and completions in traces

    Returns:
        True if tracing was initialized, False otherwise
    """
    if not OTLP_ENABLED:
        logger.info("Tracing disabled via OTLP_ENABLED=false")
        return False

    endpoint = endpoint or OTLP_ENDPOINT

    try:
        # Try agent_framework OpenTelemetry setup first
        try:
            from agent_framework.observability import setup_observability
            setup_observability(
                otlp_endpoint=endpoint,
                enable_sensitive_data=enable_sensitive
            )
            logger.info(f"✓ OpenTelemetry tracing initialized via agent_framework (endpoint={endpoint})")
            return True
        except ImportError:
            pass

        # Fallback: manual OpenTelemetry setup
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry import trace

        otlp_exporter = OTLPSpanExporter(endpoint=endpoint)
        trace_provider = TracerProvider()
        trace_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
        trace.set_tracer_provider(trace_provider)

        logger.info(f"✓ OpenTelemetry tracing initialized (endpoint={endpoint})")
        return True

    except ImportError as e:
        logger.warning(f"OpenTelemetry not available: {e}. Tracing will be disabled.")
        return False
    except Exception as e:
        logger.error(f"Failed to initialize tracing: {e}")
        return False


def get_tracer(name: str):
    """Get a tracer instance for a module.

    Args:
        name: Module or component name for the tracer

    Returns:
        A tracer instance
    """
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except Exception:
        # Return a no-op tracer if OpenTelemetry is not available
        class NoOpTracer:
            def start_as_current_span(self, name):
                return _NoOpSpan()

        class _NoOpSpan:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def set_attribute(self, key, value):
                pass
            def add_event(self, name, attributes=None):
                pass

        return NoOpTracer()


__all__ = ["setup_tracing", "get_tracer", "OTLP_ENDPOINT", "OTLP_ENABLED"]
