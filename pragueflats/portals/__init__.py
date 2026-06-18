"""Portal adapters. Each exposes fetch() -> Iterable[RawListing] and fails in isolation
so one broken source never sinks the whole run."""
