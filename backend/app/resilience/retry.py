from tenacity import retry, stop_after_attempt, wait_exponential_jitter


def external_call_retry():
    """Shared tenacity retry policy for the innermost fetch call of each
    external-dependency tool: 3 attempts, exponential backoff with jitter.
    Deliberately scoped to the fetch function only, *inside* the circuit
    breaker -- repeated transient failures still count toward tripping it.
    """
    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=4),
        reraise=True,
    )
