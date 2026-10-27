class Stop(RuntimeError):
    def __init__(self, message, outcome='identity_or_lease_failure'):
        self.outcome = outcome
        super().__init__(message)
