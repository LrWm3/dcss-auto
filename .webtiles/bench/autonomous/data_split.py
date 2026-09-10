"""Reserved seed namespaces for fresh, permanently quarantined evaluation."""

CONFIRMATION_PREFIX = 0xD
AUDIT_PREFIX = 0xE


def held_out_seed(seed):
    return seed is not None and int(seed) >> 60 in (CONFIRMATION_PREFIX, AUDIT_PREFIX)


def assert_training_seed(seed):
    if held_out_seed(seed):
        raise ValueError("confirmation/audit seed is prohibited in training or counterfactuals")
